# Arvio — Claude Code Project Context

## What This Is

Arvio (package `com.arflix.tv`) is an Android TV media hub — a fork of Arflix. It streams IPTV, Jellyfin, Plex, and Emby sources using ExoPlayer. Built with Kotlin + Jetpack Compose (TV material3), Hilt DI, Coroutines/Flow.

Joe is the sole developer. He works from a couch using an Android TV remote.

## Build & Deploy

```bash
# Build and sideload to TV
./gradlew :app:installSideloadDebug

# ADB device
adb connect 192.168.254.91:5555
```

## What We've Added (beyond upstream fork)

### 1. Progress Webhook (`ProgressWebhookRepository.kt`)
POSTs JSON playback events (start/pause/stop/progress) to a configurable URL. Debounced by interval. Used to integrate with Episeerr.

- Keys: `WEBHOOK_ENABLED_KEY`, `WEBHOOK_URL_KEY`, `WEBHOOK_INTERVAL_KEY` in `ProgressWebhookRepository.kt`
- Called from `PlayerViewModel` at start/pause/stop/periodic save

### 2. Server Session Reporting (`ServerSessionRepository.kt`)
Reports playback progress to the home media server (Jellyfin/Emby ticks, Plex timeline). One session UUID per item load.

- Called from `PlayerViewModel` alongside webhook calls

### 3. Watchlist API Server (`server/WatchlistApiServer.kt`)
NanoHTTPD server serving `GET /watchlist` as JSON over LAN so Episeerr can poll it. Default port 7979.

- Toggle + port live in **"stremio"** section (Plugins & Extensions), after the addon list
- Keys: `WATCHLIST_API_ENABLED_KEY`, `WATCHLIST_API_PORT_KEY` in `ProgressWebhookRepository.kt`

### 4. Settings Layout (no separate "integrations" section)
Settings are split across two existing sections:

**"accounts" section (TV) / "USER INFO & ACCOUNT" (mobile)** — indices 5–6:
- Episeerr URL (index 5)
- Restore from Episeerr (index 6)

**"stremio" section (TV) / "Plugins & Extensions" (mobile)** — after addon list (indices `addons.size+1` through `addons.size+5`):
- Progress webhook toggle (addons.size + 1)
- Webhook URL (addons.size + 2)
- Webhook interval (addons.size + 3)
- Watchlist API toggle (addons.size + 4)
- Watchlist API port (addons.size + 5)

**Key pattern:** The D-pad Enter key handler in `SettingsScreen` uses a `when { contentFocusIndex in range -> ... }` block for stremio (because addon count is dynamic), and `when (contentFocusIndex)` for accounts. Both must be kept in sync with `sectionMaxIndex`.

### 5. Episeerr Settings Sync (`CloudSyncRepository.kt`)
Cloud sync was originally Supabase-backed. Now routes through Episeerr:
- `PUT {episeerr_url}/api/integration/arvio/settings` — saves full settings JSON blob
- `GET {episeerr_url}/api/integration/arvio/settings` — loads it back

Episeerr URL stored under `EPISEERR_URL_KEY` in `ProgressWebhookRepository.kt` (shared keys file).

### 6. TMDB/Trakt Direct API Calls (`network/ApiProxyInterceptor.kt`)
Was routing through Supabase Edge Functions (all 404ing). Fixed to call APIs directly:
- TMDB: passes through with existing `api_key` query param from `BuildConfig.TMDB_API_KEY`
- Trakt: adds `trakt-api-key` and `trakt-api-version` headers directly (required by all Trakt endpoints)

### 7. Larger IPTV Text
Channel list text sizes increased for better TV readability.

### 8. Watchlist Home Row
Watchlist items appear as a browsable row on the home screen.

### 9. `serverItemId` on `StreamSource`
`StreamSource` data class has `serverItemId: String? = null` — populated from the home server item ID in `HomeServerRepository.buildStreamSources()`. Used by `ServerSessionRepository` to report to Jellyfin/Plex.

### 10. Server "Continue on…" Home Rows (`HomeServerRepository.kt`, `HomeViewModel.kt`)
Each connected home server gets its own "Continue on {ServerName}" row on the home screen, populated from the server's native resume data (not Trakt/local history).

- **Data class:** `HomeServerResumeItem` in `HomeServerRepository.kt`
- **API:** `HomeServerRepository.fetchResumeItems()` — Jellyfin/Emby uses `GET /Users/{userId}/Items/Resume` + a batch series lookup for TV episodes; Plex uses `GET /hubs/home/onDeck` + per-series GUID lookups for TV episodes
- **HomeViewModel:** `launchServerResumeFetch()` / `publishServerResume()` — mirrors the CW fetch pattern; row inserted after "Continue Watching", before other rows; restarted on profile switch
- Items with no resolvable TMDB ID are silently skipped

## Key Files

| File | Purpose |
|------|---------|
| `data/repository/ProgressWebhookRepository.kt` | Webhook + shared DataStore keys (WEBHOOK_*, WATCHLIST_API_*, EPISEERR_URL_KEY) |
| `data/repository/ServerSessionRepository.kt` | Home server session progress reporting |
| `data/repository/CloudSyncRepository.kt` | Settings sync via Episeerr (replaced Supabase) |
| `network/ApiProxyInterceptor.kt` | TMDB/Trakt direct API (no more Supabase proxy) |
| `server/WatchlistApiServer.kt` | LAN watchlist HTTP server (NanoHTTPD) |
| `ui/screens/settings/SettingsScreen.kt` | Settings UI — Episeerr in "accounts", webhook/watchlist in "stremio" |
| `ui/screens/settings/SettingsViewModel.kt` | Settings state + save fns: `saveWebhookUrl`, `saveEpiseerrUrl`, etc. |
| `ui/screens/player/PlayerViewModel.kt` | Triggers webhook + session calls at playback events |
| `data/model/Models.kt` | `StreamSource.serverItemId` field |
| `data/repository/HomeServerRepository.kt` | Populates `serverItemId` in `buildStreamSources()` |

## Settings Navigation Pattern

Settings uses a zone/index system:
- `Zone.SIDEBAR` → `Zone.SECTION` → `Zone.CONTENT`
- `contentFocusIndex` (0-based) tracks which row is focused
- `sectionMaxIndex(section)` caps navigation (must equal max valid index)
- **Enter key**: `when (currentSection)` block dispatches actions by `contentFocusIndex`
- Rows use `Modifier.settingsFocusSlot(index)` for scroll-into-view
- Visual focus: `isFocused = focusedIndex == N` passed into each row composable

When adding new rows to a section:
1. Increment `sectionMaxIndex` for that section
2. Add the row to the composable with the next index
3. Add the index case to the Enter key handler `when (currentSection) { "section" -> when (contentFocusIndex) { N -> ... } }`

## Episeerr Integration

Episeerr is Joe's own Python/Flask media management app at `~/projects/episeerr_dev/`. The Arvio integration blueprint is at `episeerr_dev/integrations/arvio.py`, URL prefix `/api/integration/arvio`.

Routes:
- `POST /webhook` — playback events
- `GET /watchlist` — watchlist with Sonarr/Radarr status
- `GET /status` — connection/sync status
- `POST /sync` — trigger watchlist sync to Sonarr/Radarr
- `GET /settings` — load saved Arvio settings blob
- `PUT /settings` — save Arvio settings blob (full CloudSync JSON)

Settings stored at `data/arvio_settings.json` inside the Episeerr working directory.

## TV Guide Layout (LiveTvScreen.kt)

TV is always fullscreen — video fills the screen, no mini-player. The guide is an overlay:

- **Any key press** (up/down/OK) → guide slides up from bottom (covers 60% of screen height)
- **Guide closed** → `FullscreenHud` shows channel/program info, auto-hides
- **Guide open** → channel list + EPG timeline; video visible above the guide
- **D-pad left** from channel list → category panel slides in from left (`guideGroupsVisible`)
- **D-pad right** from categories → categories hide, focus returns to channel list
- **Select channel / Back** → guide closes, video fullscreen again

Touch devices still use the old mini-player + side-by-side EPG layout (`useTouchRail` or `else Row` path).

Key state: `isGuideOpen`, `guideGroupsVisible` in `LiveTvScreen`. Helpers: `openGuide()`, `closeGuide()`.

## TODO

- **User-configurable API keys in Settings** — Move TMDB API key and Trakt Client ID/Secret from `BuildConfig` (baked into APK, extractable via decompilation) to user-editable settings stored in DataStore. Add fields to the "accounts" section in SettingsScreen. Fall back to `BuildConfig` values if the user hasn't entered their own. This eliminates the key-in-APK exposure for public repo distributions.
