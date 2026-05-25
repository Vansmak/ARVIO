# ARVIO — User Guide

## Installation

**Sideload (APK)**
1. Enable "Install from unknown sources" in your device settings.
2. Copy the APK to a USB drive or transfer it over your network.
3. Open a file manager on your TV and tap the APK to install.
4. On Fire TV: use "Downloader" or "ES File Explorer" to install.

**In-app updates** (sideload build only): A banner appears on the home screen when a new version is available. Select it to download and install automatically.

---

## First-Time Setup

1. **Create a profile** — on the profiles screen, add a name and optionally a PIN.
2. **Restore from server** (if you have a sync server or Episeerr):
   - Go to Settings → User Info & Account → Connect to Server.
   - Enter your server URL and select **Restore**. All settings, playlists, and catalog connections are pulled down in one step.
3. **Add sources manually** if not restoring:
   - **IPTV**: Settings → Plugins & Extensions → add your M3U or Xtream URL.
   - **Home servers**: Settings → Sources → add Jellyfin, Emby, or Plex URL.
   - **Addons**: Settings → Plugins & Extensions → paste an addon manifest URL.

---

## Home Screen

| Remote key | Action |
|------------|--------|
| D-pad | Move between rows and cards |
| OK / Enter | Open item |
| Back | Go back / close panel |

Rows shown (depending on your setup):
- Continue Watching (Trakt-based)
- Continue on *Server* (Jellyfin / Emby / Plex resume items)
- Watchlist
- Recent
- Catalog rows (movies, shows, by genre)

**Profiles**: select your avatar/icon at the top-right of the home screen to switch profiles.

---

## Live TV

### Opening the guide

- Navigate to **TV** in the top bar and press OK.
- The app opens with the guide visible, focused on your **Favorites** category.
- The video starts playing when you rest on a channel for half a second.

### Guide navigation

| Remote key | Action |
|------------|--------|
| Up / Down | Move between channels (plays channel after ~0.5s) |
| OK / Enter | Play selected channel immediately |
| D-pad Left | Open the **category / group panel** |
| Back | **Exit live TV** (return to home) |
| Back (while watching, guide closed) | Re-open the guide |

### Category panel

- Press **D-pad Left** from the channel list to slide the categories panel in from the left.
- Favorites, All, Recent, and any groups from your playlist are listed.
- Highlight a category and press OK to filter the channel list.
- Press **D-pad Right** to close the panel and return to the channel list.

### Channel guide (EPG)

- Press **D-pad Right** from a channel row to enter the program timeline.
- Highlight a past program with catchup available and press OK to play it.
- Press **Back** or **D-pad Left** from the timeline to return to the channel list.

### Favorites

- **Long-press OK** on any channel row to toggle it as a favorite.
- Favorites are saved per-profile and sync to your server.

---

## Video Player

### TV remote controls

| Remote key | Action |
|------------|--------|
| OK / Enter | Play / Pause |
| Back | Return to guide (live TV) or previous screen |
| D-pad Left / Right | Seek backward / forward |
| D-pad Up | Next audio track |
| D-pad Down | Next subtitle track |

### Player options

While something is playing, press **Menu** (☰) or long-press OK to open the options panel. From here you can:
- Switch stream source or quality
- Choose audio / subtitle track
- Toggle subtitles on/off

---

## Settings

Access settings from the left sidebar on the home screen or TV screen.

### Key sections

**User Info & Account**
- Connect to your sync server or Episeerr instance.
- Restore or save your full settings blob.
- Trakt.tv login for watchlist and continue-watching sync.

**Plugins & Extensions**
- Add / remove M3U and Xtream IPTV playlists.
- Add / remove addon manifest URLs.
- Progress webhook — enable to POST playback events to a URL (e.g. Episeerr).
- Watchlist API — serves your watchlist as JSON on a LAN port (default 7979) so Episeerr can poll it.

**Sources**
- Add Jellyfin, Emby, or Plex server connections.
- Each connected server adds a "Continue on *Name*" row to your home screen.

**Player**
- Preferred audio language, subtitle language, decoder settings.

---

## Episeerr Integration

If you run [Episeerr](https://github.com/Vansmak/episeerr):

1. Settings → User Info & Account → **Episeerr URL** — enter your Episeerr base URL (e.g. `http://192.168.1.x:5000`).
2. Enable **Progress Webhook** in Plugins & Extensions and set the webhook URL to `{episeerr_url}/api/integration/arvio/webhook`.
3. Enable **Watchlist API** — Episeerr polls `http://{tv-ip}:7979/watchlist` to sync your watchlist to Sonarr/Radarr automatically.
4. Use **Restore from Episeerr** in User Info & Account to pull your saved settings to a new device.

---

## Troubleshooting

**Live TV shows "CHANNELS 0" on Favorites**
Your playlist hasn't finished loading yet, or you have no favorited channels. Long-press OK on any channel to add it to Favorites.

**Guide freezes or is slow to open**
This can happen on lower-powered devices (ONN, some Fire TV sticks). The EPG grid defers rendering by one frame to avoid blocking the UI — if it's still slow, consider reducing your playlist size or disabling EPG loading for large categories.

**Back button exits the app instead of going back a screen**
On Android TV, the system Back button behavior depends on which screen has focus. If you're on the home screen with no panel open, Back will exit the app. This is standard Android TV behavior.

**Can't connect to ADB for sideloading**
Enable ADB debugging in Developer Options on your TV. Some devices require you to confirm the connection on-screen the first time. On ONN TV: Settings → Device Preferences → About → Build (click 7 times) → Developer Options → USB Debugging / Network Debugging.
