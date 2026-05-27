# ARVIO Plugins

Plugins extend ARVIO with integrations to third-party media management tools. They're added the same way as addon sources — paste the plugin's base URL into **Settings → Plugins & Extensions → Add Addon**. The app probes the URL and, if it recognises a supported plugin, registers it and shows its settings inline in the plugin card.

Plugin settings are also exposed on the web UI (arvio-server) so you can configure everything from a browser during initial setup.

---

## Episeerr

[Episeerr](https://github.com/Vansmak/episeerr) is a self-hosted media management app that bridges your ARVIO watchlist with Sonarr and Radarr, and receives playback webhooks to track what you've watched.

### What it does

- **Playback webhooks** — ARVIO POSTs start / pause / stop / progress events to Episeerr so it can track what you're watching and trigger Sonarr/Radarr actions.
- **Watchlist sync** — Episeerr polls ARVIO's LAN watchlist API and automatically requests new shows/movies in Sonarr/Radarr.
- **Settings backup** — Episeerr can store your ARVIO settings blob so you can restore a fresh device in one step (same as using arvio-server).

### Adding Episeerr

1. In ARVIO, go to **Settings → Plugins & Extensions**.
2. Select **Add Addon** and enter your Episeerr base URL, e.g. `http://192.168.1.x:5002`.
3. The app detects Episeerr, adds it as a plugin, and pre-fills the webhook URL to `{url}/api/integration/arvio/webhook`.

If you're using **arvio-server** for setup, you can do the same thing from the web UI — paste the Episeerr URL into the addon input on the Plugins tab. The server detects it, registers the plugin, and fills in the webhook URL automatically.

### Settings (in Plugins & Extensions)

After adding Episeerr these six settings appear — both in the TV app and in the plugin card on the web UI:

| Setting | Description |
|---------|-------------|
| **Progress Webhook** | Toggle whether ARVIO sends playback events |
| **Webhook URL** | URL that receives the events — auto-set to `{episeerr_url}/api/integration/arvio/webhook` |
| **Webhook Interval** | How often progress events fire during playback (10 / 15 / 30 / 60 / 120 s) |
| **Watchlist API** | Toggle the LAN JSON server that Episeerr polls |
| **Watchlist API Port** | Port for the watchlist server (default 7979) |
| **Watched Threshold** | Playback % at which the item is marked watched (50–99%, default 90) |

### Webhook payload

```json
{
  "event": "progress",
  "media_type": "tv",
  "tmdb_id": 12345,
  "title": "Show Name",
  "season": 1,
  "episode": 3,
  "position_seconds": 840,
  "duration_seconds": 2700,
  "progress_percent": 31
}
```

`event` values: `start`, `pause`, `stop`, `progress`

### Watchlist API

When enabled, `GET http://{tv-ip}:{port}/watchlist` returns a JSON array of your current watchlist items. Episeerr polls this on a schedule to sync new additions to Sonarr/Radarr.

---

## Adding your own plugin

The plugin detection model is intentionally simple. When a URL is submitted to the addon input:

1. The server probes `{url}/api/integration/arvio/status` and `{url}/api/integration/arvio/watchlist`.
2. Any non-500 response (even a 404) means the service is reachable and responds on the Arvio integration path.
3. The server registers it as a named plugin, stores its URL, and pre-fills any relevant settings.

A compatible integration needs at minimum one of those two endpoints to respond. Everything else (webhook handling, watchlist endpoint, etc.) is optional and per-plugin.

Future plugins will follow the same pattern and get their own section in this file.
