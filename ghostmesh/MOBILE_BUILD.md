# Building JarvisOS GhostMesh — Mobile (Android S24 + iOS)

GhostMesh uses [Capacitor](https://capacitorjs.com) to package the React frontend
as a native Android (APK/AAB) or iOS app. The FastAPI backend runs separately —
either on your Mac or a cloud server — and the app connects to it over the network.

---

## Prerequisites

### Android (Samsung S24)
| Tool | Install |
|------|---------|
| Android Studio (Ladybug or later) | https://developer.android.com/studio |
| JDK 17+ | bundled with Android Studio |
| Node.js 20+ | https://nodejs.org |

### iOS
| Tool | Install |
|------|---------|
| Xcode 15+ (macOS only) | Mac App Store |
| CocoaPods | `sudo gem install cocoapods` |
| Node.js 20+ | https://nodejs.org |

---

## Quick setup

```bash
cd ghostmesh/frontend
npm install          # installs Capacitor + all deps

# Add native platforms (one-time)
npm run cap:add:android   # creates android/ folder
npm run cap:add:ios       # creates ios/ folder (macOS only)
```

---

## Build for Android (S24)

```bash
cd ghostmesh/frontend

# 1. Build the React app and sync to Android
npm run build:android     # equivalent to: npm run build && npx cap sync android

# 2. Open in Android Studio
npm run cap:open:android
```

In Android Studio:
- **Run on device**: connect your S24 via USB (enable Developer Mode + USB Debugging)
  `Settings → About phone → tap Build number 7 times → Developer options → USB debugging ON`
  Then click the green ▶ Run button in Android Studio
- **Build APK**: Build → Build Bundle(s) / APK(s) → Build APK(s)
  Output: `android/app/build/outputs/apk/debug/app-debug.apk`
- **Build AAB** (for Google Play): Build → Generate Signed Bundle / APK

---

## Build for iOS

```bash
cd ghostmesh/frontend
npm run build:ios         # builds React + syncs to iOS

# Open in Xcode
npm run cap:open:ios
```

In Xcode:
- Select your device or simulator from the dropdown
- Click ▶ Run
- For device deployment: Signing & Capabilities → add your Apple Developer account

---

## Connecting to the backend

The mobile app needs to reach the GhostMesh FastAPI backend over the network.

### Option A — Same WiFi (recommended for testing)

1. Start the backend on your Mac: `cd ghostmesh/backend && ./start.sh`
2. Find your Mac's LAN IP: `ifconfig | grep "inet " | grep -v 127.0.0.1`
   e.g. `192.168.1.42`
3. In the app: **Settings → Engine Config → Backend URL** → enter `http://192.168.1.42:8080`
4. Tap Save — all API calls immediately route to your Mac

### Option B — Android emulator (no real device)
The emulator's `10.0.2.2` automatically routes to the host machine.
The app uses this by default when no custom URL is configured — just start the
backend and the emulator will reach it.

### Option C — ngrok / Cloudflare tunnel (anywhere)
```bash
# Expose your local backend to the internet temporarily
npx ngrok http 8000
# Copy the https URL (e.g. https://abc123.ngrok.io)
# Paste it into Settings → Backend URL
```

---

## Features available without backend

These pages work fully offline (no backend needed):
- **Image Search** — opens reverse-image tabs in your browser
- **Entity Extract** — client-side regex, runs locally
- **Entity Graph** — fully local SVG canvas
- **OSINT Framework** — local data, no API calls
- **Reports** — reads localStorage

These pages need the backend:
- Search (multi-engine)
- People Finder (username checker)
- Tech Sniper (tech detection)
- Archive (Wayback Machine proxy)

---

## Updating the app

After making code changes:
```bash
cd ghostmesh/frontend
npm run build:android   # or build:ios
# Android Studio / Xcode will hot-reload on next run
```

---

## Signing for distribution

### Android (Play Store / side-load)
```bash
# Generate keystore (one-time)
keytool -genkey -v -keystore jarvisos.keystore -alias jarvisos -keyalg RSA -keysize 2048 -validity 10000

# In Android Studio: Build → Generate Signed Bundle / APK
```

### iOS (App Store / TestFlight)
- Requires Apple Developer Program ($99/year)
- In Xcode: Product → Archive → Distribute App
