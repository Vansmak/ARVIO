"""
Arvio Sync Server — standalone Flask server for Arvio Android TV app.

Provides:
  - Sync API  (compatible with Episeerr's /api/integration/arvio/* routes)
  - Dashboard API  (same surface as WebAppServer on the TV device)
  - Web UI at /
  - SSE player-state endpoint (for dashboard live updates)

Data lives in /data/ (mount as a Docker volume).
TMDB key and other server config are stored in /data/server_config.json.
"""

import json
import os
import time
import queue
import threading
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context

# ── Paths ─────────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE     = DATA_DIR / "arvio_settings.json"
WATCHLIST_FILE    = DATA_DIR / "watchlist.json"
HISTORY_FILE      = DATA_DIR / "history.json"
SERVER_CONFIG_FILE = DATA_DIR / "server_config.json"

WEB_DIR = Path(__file__).parent / "web"

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=str(WEB_DIR))
app.config["JSON_SORT_KEYS"] = False

# ── SSE broadcast ──────────────────────────────────────────────────────────────

_sse_queues: list[queue.Queue] = []
_sse_lock = threading.Lock()

_player_state: dict = {
    "isPlaying": False,
    "isPaused": False,
    "title": "",
    "episodeTitle": "",
    "overview": "",
    "positionMs": 0,
    "durationMs": 0,
    "streamUrl": "",
    "isLive": False,
}


def _broadcast_player_state():
    payload = "data: " + json.dumps(_player_state) + "\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_queues.remove(q)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2))


def _load_server_config() -> dict:
    defaults = {
        "server_name": "Arvio Server",
        "port": int(os.environ.get("PORT", 7979)),
    }
    cfg = _load_json(SERVER_CONFIG_FILE, {})
    return {**defaults, **cfg}


# ── Settings blob helpers ─────────────────────────────────────────────────────
# All setup (home servers, IPTV, addons) is stored in the same blob that syncs
# to the TV app via GET /api/integration/arvio/settings.

SETUP_PROFILE_ID = "default"


def _get_blob() -> dict:
    blob = _load_json(SETTINGS_FILE, {})
    profiles = blob.get("profiles", [])
    if not any(p.get("id") == SETUP_PROFILE_ID for p in profiles):
        profiles.insert(0, {"id": SETUP_PROFILE_ID, "name": "Default",
                             "avatarColor": 4294901760, "avatarId": 1})
        blob["profiles"] = profiles
        blob.setdefault("activeProfileId", SETUP_PROFILE_ID)
    return blob


def _save_blob(blob: dict):
    _save_json(SETTINGS_FILE, blob)


def _get_connections(blob: dict) -> list:
    try:
        json_str = (blob.get("profileSettingsById", {})
                       .get(SETUP_PROFILE_ID, {})
                       .get("homeServerConnectionJson", ""))
        return json.loads(json_str).get("connections", []) if json_str else []
    except Exception:
        return []


def _set_connections(blob: dict, connections: list):
    blob.setdefault("profileSettingsById", {}).setdefault(SETUP_PROFILE_ID, {})
    blob["profileSettingsById"][SETUP_PROFILE_ID]["homeServerConnectionJson"] = \
        json.dumps({"connections": connections})


def _get_iptv(blob: dict) -> dict:
    return blob.get("iptvByProfile", {}).get(SETUP_PROFILE_ID,
                                             {"m3uUrl": "", "epgUrl": ""})


def _set_iptv(blob: dict, m3u_url: str, epg_url: str):
    blob.setdefault("iptvByProfile", {})[SETUP_PROFILE_ID] = {
        "m3uUrl": m3u_url, "epgUrl": epg_url}
    blob["iptvM3uUrl"] = m3u_url
    blob["iptvEpgUrl"] = epg_url


def _get_addons(blob: dict) -> list:
    return blob.get("addonsByProfile", {}).get(SETUP_PROFILE_ID, [])


def _set_addons(blob: dict, addons: list):
    blob.setdefault("addonsByProfile", {})[SETUP_PROFILE_ID] = addons


# ── Home server auth helpers ──────────────────────────────────────────────────

def _detect_server_kind(server_url: str) -> str:
    try:
        r = requests.get(server_url.rstrip("/") + "/System/Info/Public", timeout=6)
        if r.ok:
            name = r.json().get("ProductName", "")
            return "EMBY" if "emby" in name.lower() else "JELLYFIN"
    except Exception:
        pass
    return "UNKNOWN"


def _auth_jellyfin_emby(server_url: str, username: str, password: str) -> dict:
    url = server_url.rstrip("/") + "/Users/AuthenticateByName"
    headers = {
        "Content-Type": "application/json",
        "X-Emby-Authorization": (
            'MediaBrowser Client="Arvio", Device="ArvioServer", '
            'DeviceId="arvio-server-001", Version="1.0"'
        ),
    }
    r = requests.post(url, json={"Username": username, "Pw": password},
                      headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    try:
        info = requests.get(server_url.rstrip("/") + "/System/Info/Public", timeout=6).json()
        server_name = info.get("ServerName", "")
    except Exception:
        server_name = ""
    return {
        "accessToken": data["AccessToken"],
        "userId": data["User"]["Id"],
        "userName": data["User"].get("Name", username),
        "serverName": server_name,
        "serverId": data.get("ServerId", ""),
    }


def _test_plex(server_url: str, token: str) -> dict:
    r = requests.get(
        server_url.rstrip("/") + "/identity",
        headers={"X-Plex-Token": token, "Accept": "application/json"},
        timeout=6,
    )
    r.raise_for_status()
    data = r.json().get("MediaContainer", {})
    return {
        "serverName": data.get("friendlyName", "Plex"),
        "serverId": data.get("machineIdentifier", ""),
    }


def _tmdb_get(path: str, params: dict | None = None) -> dict | None:
    # TMDB key lives in the settings blob so it syncs to the app
    key = (_load_json(SETTINGS_FILE, {}).get("tmdb_api_key") or
           os.environ.get("TMDB_API_KEY", ""))
    if not key:
        return None
    base_params = {"api_key": key}
    if params:
        base_params.update(params)
    try:
        r = requests.get(f"https://api.themoviedb.org/3{path}", params=base_params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _cors(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.after_request
def after_request(response):
    return _cors(response)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>", methods=["GET"])
def serve_static(path):
    if path and (WEB_DIR / path).exists():
        return send_from_directory(str(WEB_DIR), path)
    return send_from_directory(str(WEB_DIR), "index.html")


# ── OPTIONS pre-flight ────────────────────────────────────────────────────────

@app.route("/api/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    return _cors(Response("", 204))


# ── Server config (TMDB key, name, etc.) ─────────────────────────────────────

@app.route("/api/server/config", methods=["GET"])
def get_server_config():
    return jsonify(_load_server_config())


@app.route("/api/server/config", methods=["POST"])
def save_server_config():
    cfg = _load_server_config()
    cfg.update(request.get_json(force=True) or {})
    _save_json(SERVER_CONFIG_FILE, cfg)
    return jsonify({"ok": True})


# ── Sync API (Episeerr-compatible) ────────────────────────────────────────────

@app.route("/api/integration/arvio/settings", methods=["GET"])
def sync_get_settings():
    return jsonify(_load_json(SETTINGS_FILE, {}))


@app.route("/api/integration/arvio/settings", methods=["PUT"])
def sync_put_settings():
    data = request.get_json(force=True) or {}
    _save_json(SETTINGS_FILE, data)
    return jsonify({"ok": True})


@app.route("/api/integration/arvio/settings/backup", methods=["GET"])
def sync_backup_settings():
    settings = _load_json(SETTINGS_FILE, {})
    resp = Response(
        json.dumps(settings, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=arvio_settings_backup.json"},
    )
    return resp


@app.route("/api/integration/arvio/settings/backup", methods=["POST"])
def sync_restore_settings():
    data = request.get_json(force=True) or {}
    _save_json(SETTINGS_FILE, data)
    return jsonify({"ok": True, "restored": True})


@app.route("/api/integration/arvio/webhook", methods=["POST"])
def sync_webhook():
    event = request.get_json(force=True) or {}
    history = _load_json(HISTORY_FILE, [])

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event.get("event", "unknown"),
        "title": event.get("title", ""),
        "episodeTitle": event.get("episodeTitle", ""),
        "mediaType": event.get("mediaType", ""),
        "tmdbId": event.get("tmdbId"),
        "positionMs": event.get("positionMs", 0),
        "durationMs": event.get("durationMs", 0),
        "streamUrl": event.get("streamUrl", ""),
    }
    history.insert(0, entry)
    history = history[:500]
    _save_json(HISTORY_FILE, history)

    # Update live player state
    global _player_state
    ev = event.get("event", "")
    if ev in ("start", "progress"):
        _player_state = {
            "isPlaying": True,
            "isPaused": False,
            "title": entry["title"],
            "episodeTitle": entry["episodeTitle"],
            "overview": event.get("overview", ""),
            "positionMs": entry["positionMs"],
            "durationMs": entry["durationMs"],
            "streamUrl": entry["streamUrl"],
            "isLive": event.get("isLive", False),
        }
    elif ev == "pause":
        _player_state["isPaused"] = True
        _player_state["isPlaying"] = False
    elif ev in ("stop", "finish"):
        _player_state = {**_player_state, "isPlaying": False, "isPaused": False}

    _broadcast_player_state()
    return jsonify({"ok": True})


@app.route("/api/integration/arvio/status", methods=["GET"])
def sync_status():
    cfg = _load_server_config()
    return jsonify({
        "server": cfg.get("server_name", "Arvio Server"),
        "version": "1.0.0",
        "watchlist_count": len(_load_json(WATCHLIST_FILE, [])),
        "history_count": len(_load_json(HISTORY_FILE, [])),
        "tmdb_configured": bool(_load_json(SETTINGS_FILE, {}).get("tmdb_api_key") or os.environ.get("TMDB_API_KEY")),
    })


# ── Setup: home servers ───────────────────────────────────────────────────────

@app.route("/api/setup/servers", methods=["GET"])
def setup_get_servers():
    blob = _get_blob()
    servers = _get_connections(blob)
    # Strip accessToken from responses for safety
    safe = [{k: v for k, v in s.items() if k not in ("accessToken", "accountToken")}
            for s in servers]
    return jsonify(safe)


@app.route("/api/setup/servers/connect", methods=["POST"])
def setup_connect_server():
    body = request.get_json(force=True) or {}
    kind = body.get("kind", "").upper()          # JELLYFIN, EMBY, PLEX
    server_url = body.get("url", "").rstrip("/")
    display_name = body.get("displayName", "")

    if not server_url:
        return jsonify({"error": "url required"}), 400

    try:
        if kind in ("JELLYFIN", "EMBY", ""):
            username = body.get("username", "")
            password = body.get("password", "")
            if not kind:
                kind = _detect_server_kind(server_url)
            if kind == "UNKNOWN":
                return jsonify({"error": "Could not detect server type. Specify kind."}), 400
            auth = _auth_jellyfin_emby(server_url, username, password)
            conn = {
                "enabled": True,
                "connectionId": f"{kind}:{server_url}:{auth['userId']}",
                "serverUrl": server_url,
                "displayName": display_name or auth["serverName"] or server_url,
                "serverName": auth["serverName"],
                "serverKind": kind,
                "serverId": auth["serverId"],
                "userId": auth["userId"],
                "userName": auth["userName"],
                "accessToken": auth["accessToken"],
                "accountToken": "",
                "collections": [],
                "lastConnectedAt": int(datetime.utcnow().timestamp() * 1000),
            }
        elif kind == "PLEX":
            token = body.get("token", "")
            if not token:
                return jsonify({"error": "token required for Plex"}), 400
            info = _test_plex(server_url, token)
            conn = {
                "enabled": True,
                "connectionId": f"PLEX:{server_url}",
                "serverUrl": server_url,
                "displayName": display_name or info["serverName"] or server_url,
                "serverName": info["serverName"],
                "serverKind": "PLEX",
                "serverId": info["serverId"],
                "userId": "",
                "userName": "",
                "accessToken": token,
                "accountToken": token,
                "collections": [],
                "lastConnectedAt": int(datetime.utcnow().timestamp() * 1000),
            }
        else:
            return jsonify({"error": f"Unknown kind: {kind}"}), 400

        blob = _get_blob()
        connections = _get_connections(blob)
        connections = [c for c in connections if c.get("connectionId") != conn["connectionId"]]
        connections.append(conn)
        _set_connections(blob, connections)
        _save_blob(blob)

        safe = {k: v for k, v in conn.items() if k not in ("accessToken", "accountToken")}
        return jsonify({"ok": True, "connection": safe})

    except requests.HTTPError as e:
        return jsonify({"error": f"Auth failed: {e.response.status_code}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/setup/servers/<connection_id>", methods=["DELETE"])
def setup_delete_server(connection_id):
    blob = _get_blob()
    connections = [c for c in _get_connections(blob)
                   if c.get("connectionId") != connection_id]
    _set_connections(blob, connections)
    _save_blob(blob)
    return jsonify({"ok": True})


# ── Setup: IPTV ───────────────────────────────────────────────────────────────

@app.route("/api/setup/iptv", methods=["GET"])
def setup_get_iptv():
    return jsonify(_get_iptv(_get_blob()))


@app.route("/api/setup/iptv", methods=["POST"])
def setup_save_iptv():
    body = request.get_json(force=True) or {}
    blob = _get_blob()
    _set_iptv(blob, body.get("m3uUrl", ""), body.get("epgUrl", ""))
    _save_blob(blob)
    return jsonify({"ok": True})


# ── Setup: addons ─────────────────────────────────────────────────────────────

@app.route("/api/setup/addons", methods=["GET"])
def setup_get_addons():
    return jsonify(_get_addons(_get_blob()))


@app.route("/api/setup/addons", methods=["POST"])
def setup_add_addon():
    body = request.get_json(force=True) or {}
    manifest_url = body.get("url", "").strip().rstrip("/")
    if not manifest_url:
        return jsonify({"error": "url required"}), 400

    base_url = manifest_url.rstrip("/")

    # If it looks like a plain URL (no manifest.json), probe for Episeerr
    if not base_url.endswith("manifest.json"):
        for probe in ["/api/integration/arvio/status", "/api/integration/arvio/watchlist"]:
            try:
                r = requests.get(base_url + probe, timeout=10)
                if r.status_code < 500:
                    addon = {
                        "id": "episeerr",
                        "name": "Episeerr",
                        "version": "1.0.0",
                        "description": "Sonarr/Radarr watchlist integration",
                        "isInstalled": True,
                        "isEnabled": True,
                        "type": "EPISEERR",
                        "runtimeKind": "STREMIO",
                        "installSource": "DIRECT_URL",
                        "url": base_url,
                    }
                    blob = _get_blob()
                    addons = _get_addons(blob)
                    addons = [a for a in addons if a.get("id") != "episeerr"]
                    addons.insert(0, addon)
                    _set_addons(blob, addons)
                    blob["episeerr_url"] = base_url
                    blob["webhook_url"] = base_url + "/api/integration/arvio/webhook"
                    blob["webhook_enabled"] = True
                    _save_blob(blob)
                    return jsonify({"ok": True, "addon": addon})
            except Exception:
                pass

    # Fetch the Stremio manifest
    manifest_fetch_url = base_url
    if not manifest_fetch_url.endswith("manifest.json"):
        manifest_fetch_url = manifest_fetch_url + "/manifest.json"
    try:
        r = requests.get(manifest_fetch_url, timeout=10)
        r.raise_for_status()
        manifest = r.json()
    except Exception as e:
        return jsonify({"error": f"Could not fetch manifest: {e}"}), 400

    addon = {
        "id": manifest.get("id", manifest_url),
        "name": manifest.get("name", "Unknown"),
        "version": manifest.get("version", "0.0.1"),
        "description": manifest.get("description", ""),
        "isInstalled": True,
        "isEnabled": True,
        "type": "COMMUNITY",
        "runtimeKind": "STREMIO",
        "installSource": "DIRECT_URL",
        "url": base_url,
        "logo": manifest.get("logo"),
        "transportUrl": base_url,
    }

    blob = _get_blob()
    addons = _get_addons(blob)
    addons = [a for a in addons if a.get("id") != addon["id"]]
    addons.append(addon)
    _set_addons(blob, addons)
    _save_blob(blob)
    return jsonify({"ok": True, "addon": addon})


@app.route("/api/setup/addons/<path:addon_id>", methods=["DELETE"])
def setup_delete_addon(addon_id):
    blob = _get_blob()
    addons = [a for a in _get_addons(blob) if a.get("id") != addon_id]
    _set_addons(blob, addons)
    _save_blob(blob)
    return jsonify({"ok": True})


# ── Setup: profile name ───────────────────────────────────────────────────────

@app.route("/api/setup/profile", methods=["GET"])
def setup_get_profile():
    blob = _get_blob()
    profiles = blob.get("profiles", [])
    profile = next((p for p in profiles if p.get("id") == SETUP_PROFILE_ID), {})
    return jsonify({"name": profile.get("name", "Default")})


@app.route("/api/setup/profile", methods=["POST"])
def setup_save_profile():
    body = request.get_json(force=True) or {}
    name = body.get("name", "").strip() or "Default"
    blob = _get_blob()
    profiles = blob.get("profiles", [])
    updated = False
    for p in profiles:
        if p.get("id") == SETUP_PROFILE_ID:
            p["name"] = name
            updated = True
    if not updated:
        profiles.insert(0, {"id": SETUP_PROFILE_ID, "name": name,
                             "avatarColor": 4294901760, "avatarId": 1})
        blob["profiles"] = profiles
    _save_blob(blob)
    return jsonify({"ok": True, "name": name})


# ── Setup: Episeerr integration ───────────────────────────────────────────────

@app.route("/api/setup/episeerr", methods=["GET"])
def setup_get_episeerr():
    addons = _get_addons(_get_blob())
    ep = next((a for a in addons if a.get("id") == "episeerr"), None)
    return jsonify({"url": ep.get("url", "") if ep else ""})


@app.route("/api/setup/episeerr", methods=["POST"])
def setup_save_episeerr():
    body = request.get_json(force=True) or {}
    url = body.get("url", "").strip().rstrip("/")
    if not url:
        return jsonify({"error": "url required"}), 400
    addon = {
        "id": "episeerr",
        "name": "Episeerr",
        "version": "1.0.0",
        "description": "Sonarr/Radarr watchlist integration",
        "isInstalled": True,
        "isEnabled": True,
        "type": "EPISEERR",
        "runtimeKind": "STREMIO",
        "installSource": "DIRECT_URL",
        "url": url,
    }
    blob = _get_blob()
    addons = _get_addons(blob)
    addons = [a for a in addons if a.get("id") != "episeerr"]
    addons.insert(0, addon)
    _set_addons(blob, addons)
    _save_blob(blob)
    return jsonify({"ok": True, "url": url})


@app.route("/api/setup/episeerr", methods=["DELETE"])
def setup_delete_episeerr():
    blob = _get_blob()
    addons = [a for a in _get_addons(blob) if a.get("id") != "episeerr"]
    _set_addons(blob, addons)
    _save_blob(blob)
    return jsonify({"ok": True})


# ── Dashboard: settings (Arvio app settings blob) ────────────────────────────

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(_load_json(SETTINGS_FILE, {}))


@app.route("/api/settings", methods=["POST"])
def post_settings():
    data = request.get_json(force=True) or {}
    existing = _load_json(SETTINGS_FILE, {})
    existing.update(data)
    _save_json(SETTINGS_FILE, existing)
    return jsonify({"ok": True})


# ── Dashboard: watchlist ──────────────────────────────────────────────────────

@app.route("/api/media/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify(_load_json(WATCHLIST_FILE, []))


@app.route("/api/media/watchlist", methods=["POST"])
def add_to_watchlist():
    item = request.get_json(force=True) or {}
    if not item.get("id"):
        return jsonify({"error": "missing id"}), 400
    watchlist = _load_json(WATCHLIST_FILE, [])
    exists = any(w["id"] == item["id"] and w.get("mediaType") == item.get("mediaType") for w in watchlist)
    if not exists:
        item["inWatchlist"] = True
        item["addedAt"] = datetime.utcnow().isoformat() + "Z"
        watchlist.insert(0, item)
        _save_json(WATCHLIST_FILE, watchlist)
    return jsonify({"ok": True})


@app.route("/api/media/watchlist/<media_type>/<int:item_id>", methods=["DELETE"])
def remove_from_watchlist(media_type, item_id):
    watchlist = _load_json(WATCHLIST_FILE, [])
    watchlist = [w for w in watchlist if not (str(w.get("id")) == str(item_id) and w.get("mediaType", "") == media_type)]
    _save_json(WATCHLIST_FILE, watchlist)
    return jsonify({"ok": True})


# ── Dashboard: history ────────────────────────────────────────────────────────

@app.route("/api/media/history", methods=["GET"])
def get_history():
    history = _load_json(HISTORY_FILE, [])
    limit = int(request.args.get("limit", 50))
    return jsonify(history[:limit])


@app.route("/api/media/history", methods=["DELETE"])
def clear_history():
    _save_json(HISTORY_FILE, [])
    return jsonify({"ok": True})


# ── Dashboard: TMDB search + trending ────────────────────────────────────────

def _map_tmdb_item(item: dict, media_type: str | None = None) -> dict:
    mt = media_type or item.get("media_type", "movie")
    return {
        "id": item["id"],
        "title": item.get("title") or item.get("name", ""),
        "overview": item.get("overview", ""),
        "image": "https://image.tmdb.org/t/p/w342" + item["poster_path"] if item.get("poster_path") else "",
        "backdropUrl": "https://image.tmdb.org/t/p/w780" + item["backdrop_path"] if item.get("backdrop_path") else "",
        "mediaType": "show" if mt == "tv" else "movie",
        "year": (item.get("release_date") or item.get("first_air_date") or "")[:4],
        "rating": item.get("vote_average", 0),
        "popularity": item.get("popularity", 0),
        "inWatchlist": False,
    }


def _mark_watchlist(items: list[dict]) -> list[dict]:
    watchlist = _load_json(WATCHLIST_FILE, [])
    wl_keys = {(str(w["id"]), w.get("mediaType", "movie")) for w in watchlist}
    for item in items:
        item["inWatchlist"] = (str(item["id"]), item.get("mediaType", "movie")) in wl_keys
    return items


@app.route("/api/media/search", methods=["GET"])
def search_media():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    data = _tmdb_get("/search/multi", {"query": q, "page": 1})
    if not data:
        return jsonify({"error": "TMDB API key not configured"}), 503
    items = [
        _map_tmdb_item(r)
        for r in data.get("results", [])
        if r.get("media_type") in ("movie", "tv") and r.get("poster_path")
    ]
    return jsonify(_mark_watchlist(items))


@app.route("/api/media/trending", methods=["GET"])
def get_trending():
    movies = _tmdb_get("/trending/movie/week") or {}
    shows = _tmdb_get("/trending/tv/week") or {}
    items = (
        [_map_tmdb_item(r, "movie") for r in movies.get("results", []) if r.get("poster_path")]
        + [_map_tmdb_item(r, "tv") for r in shows.get("results", []) if r.get("poster_path")]
    )
    items.sort(key=lambda x: x["popularity"], reverse=True)
    return jsonify(_mark_watchlist(items[:40]))


# ── Dashboard: player state + SSE ────────────────────────────────────────────

@app.route("/api/player/state", methods=["GET"])
def get_player_state():
    return jsonify(_player_state)


@app.route("/api/player/events", methods=["GET"])
def player_events():
    q: queue.Queue = queue.Queue(maxsize=10)
    with _sse_lock:
        _sse_queues.append(q)

    def generate():
        # Send current state immediately on connect
        yield "data: " + json.dumps(_player_state) + "\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Legacy watchlist compat (Episeerr polls this) ─────────────────────────────

@app.route("/watchlist", methods=["GET"])
def legacy_watchlist():
    return jsonify(_load_json(WATCHLIST_FILE, []))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7979))
    app.run(host="0.0.0.0", port=port, threaded=True)
