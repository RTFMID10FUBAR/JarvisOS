# YouTube Music Remote

Play a song on **your computer** from **your phone**, using YouTube Music.

This is a JarvisOS module in the project's local-first spirit: it runs entirely
on your own machine and network, needs no account or API key, and fails loud
instead of swallowing errors.

## How it works

```
 Phone (web remote)  ──HTTP──▶  This computer (FastAPI server)
                                      │
                                      ├─ search  → YouTube Music (ytmusicapi)
                                      └─ play    → opens the track, playing,
                                                   in the computer's browser
```

1. You run the server on the computer you want the music to come out of.
2. The server hosts a small mobile web page.
3. Your phone (on the same Wi-Fi) opens that page, searches for a song, and taps it.
4. The server resolves the song on YouTube Music and opens it **playing** in the
   computer's default browser. Transport buttons (play/pause, next, previous)
   drive the browser's player via the OS media bus.

## Quick start

```bash
cd youtube_music_remote/backend
./start.sh
```

The script installs dependencies and prints two URLs, e.g.:

```
  On this computer : http://localhost:8800
  On your phone    : http://192.168.1.42:8800   (same Wi-Fi)
```

Open the **phone** URL on your phone, search a song, and tap it. It plays on the
computer.

> Prefer not to use the start script? `pip install -r requirements.txt` then
> `python3 main.py`. Set `PORT` to change the port (default `8800`).

## API

| Method | Path               | Purpose                                            |
|--------|--------------------|----------------------------------------------------|
| GET    | `/`                | The mobile web remote                              |
| GET    | `/api/health`      | Status, whether search is available, the LAN URL   |
| GET    | `/api/search?q=`   | Search YouTube Music songs                          |
| POST   | `/api/play`        | Play `{ "query" }` or `{ "videoId" }` on this PC    |
| POST   | `/api/control`     | `{ "action": "play_pause" \| "next" \| "previous" }`|
| GET    | `/api/now-playing` | The last track this remote started                 |

Example — play by name from anything that can POST JSON:

```bash
curl -X POST http://localhost:8800/api/play \
  -H 'Content-Type: application/json' \
  -d '{"query": "daft punk - around the world"}'
```

## Notes & limitations

- **Search** uses the public, unauthenticated `ytmusicapi`. If it isn't
  installed, the remote still works in a limited mode: tapping Play opens the
  YouTube Music **search page** on the computer so you can press play there.
- **Autoplay**: opening a YouTube Music watch URL normally starts playback
  immediately. Some browsers block autoplay until the site has been interacted
  with once — if a track opens paused the first time, press play on the computer
  once and it will autoplay thereafter.
- **Transport controls** (play/pause, next, previous) are best-effort:
  - **Linux**: requires [`playerctl`](https://github.com/altdesktop/playerctl)
    (`sudo apt install playerctl`) — it controls the browser via MPRIS.
  - **macOS / Windows**: not wired up yet; the API reports this clearly rather
    than failing silently. (Searching and starting songs work on every
    platform.)
- Keep this on a **trusted network**. The server binds to your LAN and has no
  authentication, matching a home-network use case.
