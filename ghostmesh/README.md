# GhostMesh

GhostMesh is the open source intelligence (OSINT) workstation module for JarvisOS. It provides a professional dark-theme intelligence dashboard for passive and active reconnaissance, entity extraction, search aggregation, and threat investigation.

## Architecture

```
ghostmesh/
  frontend/   React + Vite + TypeScript + TailwindCSS
  backend/    Python FastAPI
```

## Quick Start

### Backend

```bash
cd ghostmesh/backend
cp .env.example .env
# Edit .env to add your API keys
./start.sh
```

Backend runs on http://localhost:8000

### Frontend

```bash
cd ghostmesh/frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173

## Modules

| Module | Path | Description |
|--------|------|-------------|
| Overview | / | System status, engine health, recent searches |
| Search | /search | Multi-engine OSINT search |
| Browser | /recon/browser | Disposable isolated browser sessions |
| Tech Sniper | /recon/tech | Technology stack detection |
| Archive | /recon/archive | Wayback Machine search |
| Metadata | /recon/metadata | Document/image metadata extraction |
| People Finder | /entities/people | Public record and profile search |
| Image Search | /entities/images | Reverse image search |
| Entity Extract | /entities/extract | Regex-based entity extraction from text |
| Entity Graph | /entities/graph | SVG relationship graph |
| OSINT Framework | /framework | Curated tool directory |
| Reports | /reports | Saved export library |
| Settings | /settings | Engine config, diagnostics, audit log |

## Safety

GhostMesh is designed for **passive, public-source intelligence** by default:
- Active scanning is disabled by default
- No private account access
- No credential extraction
- All results link to publicly accessible sources
- Audit logging stored locally

## API Keys (all optional)

Configure in `backend/.env`:

| Engine | Variable | Notes |
|--------|----------|-------|
| SearXNG | `SEARXNG_URL` | Self-hosted required |
| Shodan | `SHODAN_API_KEY` | shodan.io |
| VirusTotal | `VT_API_KEY` | virustotal.com |
| HaveIBeenPwned | `HIBP_API_KEY` | haveibeenpwned.com |
| Hunter.io | `HUNTER_API_KEY` | hunter.io |

DuckDuckGo requires no key and is available by default.
