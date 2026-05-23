# ARVIO Sync Server

Minimal self-hosted settings sync server for the ARVIO Android TV app.

Three endpoints, one JSON file, no accounts.

## Quick start

```bash
git clone https://github.com/Vansmak/ARVIO
cd ARVIO/sync-server
docker compose up -d
```

The server listens on port **7000**. In the ARVIO app, tap **Connect to Server** on the profile screen and enter `http://<your-server-ip>:7000`.

## What it stores

A single file — `data/arvio_settings.json` — containing the full ARVIO settings blob: profiles, addons, home server connections, IPTV config, Trakt tokens, watchlist, and all preferences. No database required.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/integration/arvio/status` | Health check — app verifies server before saving URL |
| `GET` | `/api/integration/arvio/settings` | Pull settings (new-device restore) |
| `PUT` | `/api/integration/arvio/settings` | Push settings (called automatically on every change) |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7000` | HTTP port |
| `DATA_FILE` | `/data/arvio_settings.json` | Settings file path inside the container |

Change the host port in `docker-compose.yml` if 7000 conflicts with something else on your server.
