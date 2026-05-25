# Building JarvisOS GhostMesh — Desktop App

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 20+ | https://nodejs.org |
| Python | 3.10+ | https://python.org |
| npm | 10+ | bundled with Node.js |

On macOS you also need Xcode command line tools:
```
xcode-select --install
```

---

## Quick start (dev mode — no build step)

```bash
# Terminal 1 — start the React dev server
cd ghostmesh/frontend
npm install
npm run dev          # serves on http://localhost:5173

# Terminal 2 — start the Electron shell pointing at dev server
cd ghostmesh/electron
npm install
npm run start:dev    # opens a native window loading localhost:5173
                     # also auto-starts the FastAPI backend on port 8080
```

The FastAPI backend is launched automatically by Electron. If it doesn't start
(e.g. no `uvicorn` installed), the frontend still loads and shows "API offline"
in the status bar — use `ghostmesh/dev.sh` to start the backend independently.

---

## Production build (macOS .dmg)

### Step 1 — Prepare the Python backend venv

```bash
cd ghostmesh/electron
./setup-backend.sh
```

This creates `ghostmesh/backend/venv/` with all Python dependencies bundled.

### Step 2 — Add an app icon

Place your icon files in `ghostmesh/electron/assets/`:
- `icon.icns`  — macOS (use `iconutil` or [electron-icon-maker](https://github.com/jaretburkett/electron-icon-maker))
- `icon.ico`   — Windows (optional)
- `icon.png`   — 512×512 fallback

Generating `icon.icns` from a 1024×1024 PNG:
```bash
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
cp icon.png            icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
mv icon.icns assets/
```

### Step 3 — Build

```bash
# Build React app + package for macOS (arm64 + x64 universal)
npm run build:all
```

Output is in `ghostmesh/electron/dist/`:
- `JarvisOS GhostMesh-0.1.0-arm64.dmg` (Apple Silicon)
- `JarvisOS GhostMesh-0.1.0.dmg` (Intel)
- `JarvisOS GhostMesh-0.1.0-arm64-mac.zip`

---

## How it works

```
JarvisOS GhostMesh.app/
└── Contents/
    ├── MacOS/
    │   └── JarvisOS GhostMesh      ← Electron binary
    ├── Resources/
    │   ├── app.asar                 ← main.js + preload.js (packed)
    │   ├── frontend-dist/           ← built React app (index.html + assets)
    │   └── backend/                 ← FastAPI source + venv/
    └── Info.plist
```

On launch, `main.js`:
1. Reads `backend/.env` (if present) and merges into the subprocess environment
2. Spawns `backend/venv/bin/python3 -m uvicorn main:app --port 8080 --host 127.0.0.1`
3. Polls `http://127.0.0.1:8080/api/health` until it responds (up to 20 s)
4. Opens a `BrowserWindow` loading `frontend-dist/index.html`
5. The React app proxies `/api/*` requests to the local backend

---

## Code signing (optional, for distribution outside MAS)

```bash
# Set your Apple Developer identity
export CSC_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export APPLE_TEAM_ID="YOURTEAMID"

npm run dist:mac
```

For notarization, electron-builder handles it automatically when the Apple
credentials above are set.

---

## API key configuration

Copy `ghostmesh/backend/.env.example` to `ghostmesh/backend/.env` and fill in
your keys before building. The packaged app reads `.env` from the bundled
backend resource directory at runtime.
