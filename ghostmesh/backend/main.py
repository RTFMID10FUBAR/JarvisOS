from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx
import os
import time
from datetime import datetime, timezone

app = FastAPI(title="GhostMesh API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TIME = time.time()

ENGINES = {
    "duckduckgo": {"name": "DuckDuckGo", "requires_key": False, "env_var": None},
    "searxng": {"name": "SearXNG", "requires_key": False, "env_var": "SEARXNG_URL"},
    "shodan": {"name": "Shodan", "requires_key": True, "env_var": "SHODAN_API_KEY"},
    "virustotal": {"name": "VirusTotal", "requires_key": True, "env_var": "VT_API_KEY"},
    "haveibeenpwned": {"name": "HaveIBeenPwned", "requires_key": True, "env_var": "HIBP_API_KEY"},
    "hunter": {"name": "Hunter.io", "requires_key": True, "env_var": "HUNTER_API_KEY"},
}


def get_engine_status():
    configured = []
    unavailable = []
    missing_vars = []

    for engine_id, info in ENGINES.items():
        env_var = info["env_var"]
        if env_var is None:
            configured.append(engine_id)
        elif os.getenv(env_var):
            configured.append(engine_id)
        else:
            missing_vars.append(env_var)
            unavailable.append({
                "name": info["name"],
                "reason": f"Environment variable {env_var} not set",
                "missing_key": env_var,
            })

    return configured, unavailable, list(set(missing_vars))


@app.get("/api/health")
async def health():
    configured, unavailable, missing_vars = get_engine_status()
    uptime = int(time.time() - START_TIME)
    registry_status = "online" if configured else "degraded"
    return {
        "ui_status": "online",
        "api_status": "online",
        "engine_registry_status": registry_status,
        "configured_engines": configured,
        "unavailable_engines": unavailable,
        "missing_env_vars": missing_vars,
        "last_query_time": None,
        "service_versions": {"ghostmesh": "0.1.0", "api": "0.1.0"},
        "uptime_seconds": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class SearchQuery(BaseModel):
    query: str
    engines: list[str]
    mode: str = "passive"
    max_results: int = 25


@app.post("/api/search")
async def search(body: SearchQuery):
    if not body.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if not body.engines:
        raise HTTPException(400, "Select at least one engine")

    results = []
    engines_used = []
    engines_failed = []
    start = time.time()

    if "duckduckgo" in body.engines:
        try:
            ddg_results = await search_duckduckgo(body.query, body.max_results)
            results.extend(ddg_results)
            engines_used.append("duckduckgo")
        except Exception:
            engines_failed.append("duckduckgo")

    searxng_url = os.getenv("SEARXNG_URL")
    if "searxng" in body.engines and searxng_url:
        try:
            sx_results = await search_searxng(body.query, searxng_url, body.max_results)
            results.extend(sx_results)
            engines_used.append("searxng")
        except Exception:
            engines_failed.append("searxng")
    elif "searxng" in body.engines:
        engines_failed.append("searxng")

    duration_ms = int((time.time() - start) * 1000)
    return {
        "query": body.query,
        "results": results[: body.max_results],
        "engines_used": engines_used,
        "engines_failed": engines_failed,
        "total": len(results),
        "duration_ms": duration_ms,
    }


async def search_duckduckgo(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append({
                "id": "ddg-abstract",
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
                "source_engine": "duckduckgo",
                "timestamp": None,
                "confidence": 80,
                "tags": ["abstract"],
                "category": "information",
                "archived": False,
            })
        for topic in data.get("RelatedTopics", [])[: max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "id": f"ddg-{len(results)}",
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "source_engine": "duckduckgo",
                    "timestamp": None,
                    "confidence": 60,
                    "tags": ["related"],
                    "category": "general",
                    "archived": False,
                })
        return results


async def search_searxng(query: str, base_url: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "pageno": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "id": f"sx-{len(results)}",
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "url": item.get("url", ""),
                "source_engine": "searxng",
                "timestamp": item.get("publishedDate"),
                "confidence": 70,
                "tags": item.get("tags", []),
                "category": item.get("category", "general"),
                "archived": False,
            })
        return results


class ArchiveQuery(BaseModel):
    url: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None


@app.post("/api/recon/archive")
async def search_archive(body: ArchiveQuery):
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params: dict = {
                "url": body.url,
                "output": "json",
                "limit": 10,
                "fl": "timestamp,statuscode,mimetype",
            }
            if body.from_date:
                params["from"] = body.from_date.replace("-", "")
            if body.to_date:
                params["to"] = body.to_date.replace("-", "")
            resp = await client.get(
                "http://web.archive.org/cdx/search/cdx", params=params
            )
            resp.raise_for_status()
            lines = [l for l in resp.text.strip().split("\n") if l]
            snapshots = []
            for line in lines[1:]:  # skip header
                parts = line.split(" ")
                if len(parts) >= 3:
                    ts = parts[0]
                    status = parts[1]
                    formatted = (
                        f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                        f"T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}Z"
                    )
                    snapshots.append({
                        "url": body.url,
                        "snapshot_url": f"https://web.archive.org/web/{ts}/{body.url}",
                        "timestamp": formatted,
                        "http_status": int(status) if status.isdigit() else 0,
                    })
            return {"url": body.url, "snapshots": snapshots, "total": len(snapshots)}
    except Exception as e:
        raise HTTPException(503, f"Archive service unavailable: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
