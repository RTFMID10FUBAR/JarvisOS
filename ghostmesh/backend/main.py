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
    "duckduckgo":     {"name": "DuckDuckGo",    "requires_key": False, "env_var": None},
    "marginalia":     {"name": "Marginalia",     "requires_key": False, "env_var": None},
    "urlscan":        {"name": "URLScan.io",     "requires_key": False, "env_var": None},
    "crtsh":          {"name": "Crt.sh",         "requires_key": False, "env_var": None},
    "searxng":        {"name": "SearXNG",        "requires_key": False, "env_var": "SEARXNG_URL"},
    "brave":          {"name": "Brave Search",   "requires_key": True,  "env_var": "BRAVE_SEARCH_API_KEY"},
    "otx":            {"name": "AlienVault OTX", "requires_key": True,  "env_var": "OTX_API_KEY"},
    "shodan":         {"name": "Shodan",         "requires_key": True,  "env_var": "SHODAN_API_KEY"},
    "virustotal":     {"name": "VirusTotal",     "requires_key": True,  "env_var": "VT_API_KEY"},
    "haveibeenpwned": {"name": "HaveIBeenPwned", "requires_key": True,  "env_var": "HIBP_API_KEY"},
    "hunter":         {"name": "Hunter.io",      "requires_key": True,  "env_var": "HUNTER_API_KEY"},
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

    async def _run(engine_id: str, coro):
        try:
            res = await coro
            results.extend(res)
            engines_used.append(engine_id)
        except Exception:
            engines_failed.append(engine_id)

    if "duckduckgo" in body.engines:
        await _run("duckduckgo", search_duckduckgo(body.query, body.max_results))

    if "marginalia" in body.engines:
        await _run("marginalia", search_marginalia(body.query, body.max_results))

    if "urlscan" in body.engines:
        await _run("urlscan", search_urlscan(body.query, body.max_results))

    if "crtsh" in body.engines:
        await _run("crtsh", search_crtsh(body.query, body.max_results))

    searxng_url = os.getenv("SEARXNG_URL")
    if "searxng" in body.engines:
        if searxng_url:
            await _run("searxng", search_searxng(body.query, searxng_url, body.max_results))
        else:
            engines_failed.append("searxng")

    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if "brave" in body.engines:
        if brave_key:
            await _run("brave", search_brave(body.query, brave_key, body.max_results))
        else:
            engines_failed.append("brave")

    otx_key = os.getenv("OTX_API_KEY")
    if "otx" in body.engines:
        if otx_key:
            await _run("otx", search_otx(body.query, otx_key, body.max_results))
        else:
            engines_failed.append("otx")

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


async def search_marginalia(query: str, max_results: int) -> list[dict]:
    """Marginalia Search — independent web index, no key required."""
    import urllib.parse
    encoded = urllib.parse.quote(query)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.marginalia.nu/search/{encoded}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict] = []
        for i, item in enumerate(data.get("results", [])[:max_results]):
            results.append({
                "id": f"mg-{i}",
                "title": item.get("title") or item.get("url", ""),
                "snippet": item.get("description") or "",
                "url": item.get("url", ""),
                "source_engine": "marginalia",
                "timestamp": None,
                "confidence": 65,
                "tags": ["web"],
                "category": "general",
                "archived": False,
            })
        return results


async def search_urlscan(query: str, max_results: int) -> list[dict]:
    """URLScan.io public search — no key required for public results."""
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://urlscan.io/api/v1/search/",
            params={"q": query, "size": min(max_results, 100)},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict] = []
        for i, item in enumerate(data.get("results", [])[:max_results]):
            page = item.get("page", {})
            results.append({
                "id": f"us-{i}",
                "title": page.get("title") or page.get("domain", query),
                "snippet": f"Scanned: {page.get('url', '')} — {page.get('domain', '')}",
                "url": item.get("result", page.get("url", "")),
                "source_engine": "urlscan",
                "timestamp": item.get("task", {}).get("time"),
                "confidence": 70,
                "tags": ["url", "scan"],
                "category": "security",
                "archived": False,
            })
        return results


async def search_crtsh(query: str, max_results: int) -> list[dict]:
    """Crt.sh certificate transparency search — no key required."""
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://crt.sh/",
            params={"q": query, "output": "json"},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        seen: set[str] = set()
        results: list[dict] = []
        for item in data[:max_results * 3]:
            name = item.get("name_value", "")
            for domain in name.split("\n"):
                domain = domain.strip().lstrip("*.")
                if domain and domain not in seen:
                    seen.add(domain)
                    results.append({
                        "id": f"crt-{len(results)}",
                        "title": domain,
                        "snippet": (
                            f"Issuer: {item.get('issuer_name', 'unknown')} — "
                            f"Logged: {item.get('entry_timestamp', '')[:10]}"
                        ),
                        "url": f"https://crt.sh/?q={domain}",
                        "source_engine": "crtsh",
                        "timestamp": item.get("entry_timestamp"),
                        "confidence": 75,
                        "tags": ["certificate", "domain"],
                        "category": "infrastructure",
                        "archived": False,
                    })
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
        return results


async def search_brave(query: str, api_key: str, max_results: int) -> list[dict]:
    """Brave Search API — requires BRAVE_SEARCH_API_KEY."""
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict] = []
        for i, item in enumerate(data.get("web", {}).get("results", [])[:max_results]):
            results.append({
                "id": f"bv-{i}",
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
                "url": item.get("url", ""),
                "source_engine": "brave",
                "timestamp": item.get("age"),
                "confidence": 75,
                "tags": ["web"],
                "category": "general",
                "archived": False,
            })
        return results


async def search_otx(query: str, api_key: str, max_results: int) -> list[dict]:
    """AlienVault OTX threat intelligence search — requires OTX_API_KEY."""
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://otx.alienvault.com/api/v1/search/pulses",
            params={"q": query, "page_size": min(max_results, 20)},
            headers={"X-OTX-API-KEY": api_key, "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict] = []
        for i, item in enumerate(data.get("results", [])[:max_results]):
            results.append({
                "id": f"otx-{i}",
                "title": item.get("name", ""),
                "snippet": item.get("description", "")[:200],
                "url": f"https://otx.alienvault.com/pulse/{item.get('id', '')}",
                "source_engine": "otx",
                "timestamp": item.get("created"),
                "confidence": 72,
                "tags": item.get("tags", [])[:5],
                "category": "threat-intel",
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
