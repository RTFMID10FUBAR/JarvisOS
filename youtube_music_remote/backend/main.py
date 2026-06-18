"""
JarvisOS — YouTube Music Remote

A tiny, local-first remote that lets you play a song on *this computer* from your
phone using YouTube Music.

How it works:
  1. Run this server on the computer you want music to play on.
  2. On your phone (same Wi-Fi), open the URL printed on startup
     (e.g. http://192.168.1.42:8800).
  3. Search for a song and tap it. The server resolves it to a YouTube Music
     track and opens it *playing* in this computer's default browser.

Design notes (in the spirit of JarvisOS):
  * Local-first — nothing leaves your network except the YouTube Music request.
  * No accounts / API keys — search uses the public, unauthenticated
    ytmusicapi. If that library isn't installed, the server falls back to
    opening the YouTube Music search page so you can tap play manually.
  * Fail-loud — errors surface as HTTP errors and are visible in the UI.

Transport controls (play/pause, next, previous) are best-effort and use the
operating system's media bus:
  * Linux: `playerctl` (controls the browser via MPRIS) if installed.
  * Other platforms report "unsupported" rather than failing silently.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Optional dependency: ytmusicapi gives real search results without any login.
# The remote still works without it (falls back to the YTM search page), so we
# import lazily and keep going if it isn't available.
# ---------------------------------------------------------------------------
try:
    from ytmusicapi import YTMusic

    _ytmusic = YTMusic()  # unauthenticated — search works without credentials
    _YTM_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on the host environment
    _ytmusic = None
    _YTM_ERROR = f"{type(exc).__name__}: {exc}"


app = FastAPI(title="JarvisOS YouTube Music Remote", version="0.1.0")

# The remote is opened from a phone on the same LAN, so the browser origin is
# the phone's, not localhost. Allow any origin — the server is meant to live on
# a trusted home network, bound to the LAN only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

YTM_WATCH = "https://music.youtube.com/watch?v={vid}"
YTM_SEARCH = "https://music.youtube.com/search?q={q}"

# Best-effort record of what we last asked the computer to play. We can't read
# the browser's real playback state, so this reflects our last command.
NOW_PLAYING: dict = {
    "title": None,
    "artist": None,
    "videoId": None,
    "url": None,
    "startedAt": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def lan_ip() -> str:
    """Best-effort LAN IP so we can tell the user what URL to open on the phone."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def yt_search(query: str, limit: int = 12) -> list[dict]:
    """Search YouTube Music for songs. Returns [] if ytmusicapi is unavailable."""
    if _ytmusic is None:
        return []
    try:
        raw = _ytmusic.search(query, filter="songs", limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"YouTube Music search failed: {exc}")

    songs = []
    for item in raw:
        vid = item.get("videoId")
        if not vid:
            continue
        artists = ", ".join(
            a["name"] for a in item.get("artists", []) if a.get("name")
        )
        album = item.get("album")
        album_name = album.get("name") if isinstance(album, dict) else None
        thumbs = item.get("thumbnails") or []
        songs.append(
            {
                "videoId": vid,
                "title": item.get("title"),
                "artist": artists,
                "album": album_name,
                "duration": item.get("duration"),
                "thumbnail": thumbs[-1]["url"] if thumbs else None,
            }
        )
    return songs


def open_on_host(url: str) -> bool:
    """Open a URL in this computer's default browser."""
    try:
        return webbrowser.open(url, new=0, autoraise=True)
    except Exception as exc:
        raise HTTPException(500, f"Could not open browser on host: {exc}")


def media_control(action: str) -> tuple[bool, str]:
    """Send a transport command to the OS media bus. Returns (ok, backend)."""
    mapping = {
        "play_pause": "play-pause",
        "play": "play",
        "pause": "pause",
        "next": "next",
        "previous": "previous",
        "stop": "stop",
    }
    cmd = mapping.get(action)
    if cmd is None:
        raise HTTPException(400, f"Unknown action: {action!r}")

    if sys.platform.startswith("linux") and shutil.which("playerctl"):
        try:
            subprocess.run(
                ["playerctl", cmd],
                check=True,
                capture_output=True,
                timeout=5,
            )
            return True, "playerctl"
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode().strip() or "no active media player found"
            raise HTTPException(503, f"playerctl: {detail}")
        except subprocess.TimeoutExpired:
            raise HTTPException(503, "playerctl timed out")

    return False, "unsupported"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "jarvis-youtube-music-remote",
        "version": "0.1.0",
        "ytmusicapi": _ytmusic is not None,
        "ytmusicapi_error": _YTM_ERROR,
        "media_control": "playerctl"
        if (sys.platform.startswith("linux") and shutil.which("playerctl"))
        else "unsupported",
        "lan_url": f"http://{lan_ip()}:{os.getenv('PORT', '8800')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/search")
def search(q: str, limit: int = 12):
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "Query 'q' cannot be empty")
    return {"query": q, "results": yt_search(q, limit=limit)}


class PlayRequest(BaseModel):
    query: Optional[str] = None
    videoId: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None


@app.post("/api/play")
def play(body: PlayRequest):
    vid = (body.videoId or "").strip() or None
    title = body.title
    artist = body.artist

    # If we were given a free-text query, resolve it to the top song.
    if vid is None and body.query:
        hits = yt_search(body.query.strip(), limit=1)
        if hits:
            vid = hits[0]["videoId"]
            title = title or hits[0]["title"]
            artist = artist or hits[0]["artist"]

    if vid:
        url = YTM_WATCH.format(vid=vid)
        resolved = True
    elif body.query:
        # ytmusicapi unavailable — open the search page so the user can tap play
        # on the computer themselves.
        url = YTM_SEARCH.format(q=quote_plus(body.query.strip()))
        resolved = False
    else:
        raise HTTPException(400, "Provide a 'query' or a 'videoId'")

    opened = open_on_host(url)
    NOW_PLAYING.update(
        {
            "title": title,
            "artist": artist,
            "videoId": vid,
            "url": url,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {
        "opened": opened,
        "resolved": resolved,
        "url": url,
        "nowPlaying": NOW_PLAYING,
    }


class ControlRequest(BaseModel):
    action: str  # play_pause | play | pause | next | previous | stop


@app.post("/api/control")
def control(body: ControlRequest):
    ok, backend = media_control(body.action)
    if not ok:
        raise HTTPException(
            501,
            "Transport control isn't supported on this platform. On Linux, "
            "install 'playerctl' to control the browser's player.",
        )
    return {"ok": True, "action": body.action, "backend": backend}


@app.get("/api/now-playing")
def now_playing():
    return NOW_PLAYING


# ---------------------------------------------------------------------------
# Mobile web remote (single self-contained page, no build step)
# ---------------------------------------------------------------------------
REMOTE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="theme-color" content="#0b0f14" />
<title>JarvisOS · YT Music Remote</title>
<style>
  :root { --bg:#0b0f14; --panel:#121822; --panel2:#1a2330; --line:#243044;
          --text:#e8eef6; --muted:#8aa0b8; --accent:#ff2d55; --accent2:#2dd4bf; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); padding-bottom:120px; }
  header { padding:18px 16px 12px; position:sticky; top:0; background:linear-gradient(var(--bg),rgba(11,15,20,.85));
           backdrop-filter:blur(8px); z-index:5; }
  h1 { margin:0; font-size:17px; letter-spacing:.3px; }
  h1 small { color:var(--muted); font-weight:400; display:block; font-size:12px; margin-top:2px; }
  .dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; background:#555; vertical-align:middle; }
  .dot.on { background:var(--accent2); box-shadow:0 0 8px var(--accent2); }
  .search { display:flex; gap:8px; padding:0 16px 12px; }
  input { flex:1; background:var(--panel2); border:1px solid var(--line); color:var(--text);
          padding:13px 14px; border-radius:12px; font-size:16px; outline:none; }
  input:focus { border-color:var(--accent); }
  button { background:var(--panel2); border:1px solid var(--line); color:var(--text);
           border-radius:12px; padding:13px 16px; font-size:15px; cursor:pointer; }
  button.go { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
  button:active { transform:scale(.97); }
  .list { padding:0 12px; }
  .row { display:flex; align-items:center; gap:12px; padding:10px; border-radius:14px; cursor:pointer; }
  .row:active { background:var(--panel); }
  .art { width:52px; height:52px; border-radius:10px; object-fit:cover; background:var(--panel2); flex:none; }
  .meta { min-width:0; flex:1; }
  .meta .t { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .meta .s { color:var(--muted); font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .dur { color:var(--muted); font-size:12px; flex:none; }
  .hint { color:var(--muted); text-align:center; padding:40px 24px; font-size:14px; }
  .hint b { color:var(--text); }
  .player { position:fixed; left:0; right:0; bottom:0; background:var(--panel);
            border-top:1px solid var(--line); padding:12px 16px calc(12px + env(safe-area-inset-bottom)); z-index:6; }
  .np { display:flex; align-items:center; gap:12px; margin-bottom:10px; }
  .np .t { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .np .s { color:var(--muted); font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .transport { display:flex; gap:10px; }
  .transport button { flex:1; padding:14px 0; font-size:18px; }
  .transport .pp { background:var(--accent2); border-color:var(--accent2); color:#04201c; font-weight:700; }
  .toast { position:fixed; left:50%; bottom:160px; transform:translateX(-50%); background:#222d3d;
           border:1px solid var(--line); color:var(--text); padding:10px 16px; border-radius:999px;
           font-size:13px; opacity:0; transition:opacity .25s; pointer-events:none; z-index:9; }
  .toast.show { opacity:1; }
</style>
</head>
<body>
  <header>
    <h1><span id="dot" class="dot"></span>JarvisOS · YouTube Music Remote
      <small id="sub">Connecting…</small></h1>
  </header>

  <div class="search">
    <input id="q" type="search" placeholder="Search a song or artist…" autocomplete="off"
           enterkeyhint="search" />
    <button class="go" id="goBtn">Play</button>
  </div>

  <div class="list" id="list">
    <div class="hint">Type a song and hit <b>Play</b> to start it on the computer.</div>
  </div>

  <div class="player">
    <div class="np">
      <div style="flex:1; min-width:0;">
        <div class="t" id="npTitle">Nothing playing</div>
        <div class="s" id="npArtist">Pick a song above</div>
      </div>
    </div>
    <div class="transport">
      <button id="prev" title="Previous">⏮</button>
      <button class="pp" id="pp" title="Play / Pause">⏯</button>
      <button id="next" title="Next">⏭</button>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
let searchTimer = null;

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._x); t._x = setTimeout(() => t.classList.remove('show'), 1800);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let d = ''; try { d = (await r.json()).detail; } catch (e) {}
    throw new Error(d || ('HTTP ' + r.status));
  }
  return r.json();
}

async function health() {
  try {
    const h = await api('/api/health');
    $('dot').classList.add('on');
    $('sub').textContent = h.ytmusicapi
      ? 'Ready · search powered by YouTube Music'
      : 'Ready · limited mode (install ytmusicapi for search)';
  } catch (e) {
    $('sub').textContent = 'Offline — is the server running?';
  }
}

function row(song) {
  const el = document.createElement('div');
  el.className = 'row';
  const art = song.thumbnail
    ? `<img class="art" src="${song.thumbnail}" loading="lazy" />`
    : `<div class="art"></div>`;
  el.innerHTML = `${art}
    <div class="meta">
      <div class="t">${escapeHtml(song.title || 'Unknown')}</div>
      <div class="s">${escapeHtml(song.artist || '')}${song.album ? ' · ' + escapeHtml(song.album) : ''}</div>
    </div>
    <div class="dur">${song.duration || ''}</div>`;
  el.onclick = () => playSong(song);
  return el;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function doSearch() {
  const q = $('q').value.trim();
  if (!q) { return; }
  try {
    const data = await api('/api/search?limit=15&q=' + encodeURIComponent(q));
    const list = $('list');
    list.innerHTML = '';
    if (!data.results.length) {
      list.innerHTML = '<div class="hint">No songs found. Hit <b>Play</b> to open it on the computer anyway.</div>';
      return;
    }
    data.results.forEach(s => list.appendChild(row(s)));
  } catch (e) {
    toast('Search: ' + e.message);
  }
}

async function playSong(song) {
  try {
    const body = song.videoId
      ? { videoId: song.videoId, title: song.title, artist: song.artist }
      : { query: $('q').value.trim() };
    const res = await api('/api/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const np = res.nowPlaying;
    $('npTitle').textContent = np.title || 'Playing…';
    $('npArtist').textContent = np.artist || (res.resolved ? '' : 'Opened search on computer');
    toast(res.resolved ? '▶ Playing on computer' : 'Opened on computer — tap play there');
  } catch (e) {
    toast('Play: ' + e.message);
  }
}

async function control(action) {
  try {
    await api('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
  } catch (e) {
    toast(e.message);
  }
}

$('goBtn').onclick = () => {
  const q = $('q').value.trim();
  if (q) { playSong({ query: q }); }
};
$('q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
$('q').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 350);
});
$('prev').onclick = () => control('previous');
$('next').onclick = () => control('next');
$('pp').onclick = () => control('play_pause');

health();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def remote_page():
    return HTMLResponse(REMOTE_HTML)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8800"))
    ip = lan_ip()
    print("\n  JarvisOS · YouTube Music Remote")
    print("  --------------------------------")
    print(f"  On this computer : http://localhost:{port}")
    print(f"  On your phone    : http://{ip}:{port}   (same Wi-Fi)")
    if _ytmusic is None:
        print("\n  [!] ytmusicapi not installed — running in limited mode.")
        print("      Install it for in-app search:  pip install ytmusicapi")
    print()
    uvicorn.run(app, host="0.0.0.0", port=port)
