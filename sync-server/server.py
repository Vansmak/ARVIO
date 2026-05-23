"""
ARVIO Sync Server
─────────────────
Minimal self-hosted settings sync server for the ARVIO Android TV app.

Implements the three endpoints the ARVIO app expects:
  GET  /api/integration/arvio/status    ← app pings this to verify the server
  GET  /api/integration/arvio/settings  ← app pulls settings on new-device setup
  PUT  /api/integration/arvio/settings  ← app pushes settings on every change

Settings are stored as a single JSON file (DATA_FILE env var, default /data/arvio_settings.json).
No database, no accounts, no cloud.
"""

import json
import os
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)

DATA_FILE = os.environ.get("DATA_FILE", "/data/arvio_settings.json")
_lock = threading.Lock()


def _load():
    with _lock:
        if not os.path.exists(DATA_FILE):
            return None
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def _save(data):
    with _lock:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


@app.route("/api/integration/arvio/status")
def status():
    data = _load()
    profiles = len((data or {}).get("profiles") or []) if data else 0
    updated_at = (data or {}).get("updatedAt")
    last_sync = None
    if updated_at:
        try:
            last_sync = datetime.fromtimestamp(updated_at / 1000, tz=timezone.utc).isoformat()
        except Exception:
            pass
    return jsonify({
        "status": "ok",
        "service": "arvio-sync",
        "settings_present": data is not None,
        "profiles": profiles,
        "last_sync": last_sync,
    })


@app.route("/api/integration/arvio/settings", methods=["GET"])
def get_settings():
    data = _load()
    if data is None:
        return jsonify({"error": "No settings saved yet"}), 404
    return jsonify(data)


@app.route("/api/integration/arvio/settings", methods=["PUT"])
def put_settings():
    body = request.get_json(silent=True, force=True)
    if not body or not isinstance(body, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    _save(body)
    profiles = len(body.get("profiles") or [])
    return jsonify({"status": "saved", "profiles": profiles})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
