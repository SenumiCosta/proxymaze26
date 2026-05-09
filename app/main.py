import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.store import (
    add_proxy,
    clear_pool,
    get_all_proxies,
    get_config,
    get_metrics,
    get_pool_stats,
    get_proxy,
    set_config,
    state_lock,
)
from app.alert_manager import get_alerts, evaluate
from app.webhook_manager import register_webhook, register_integration
from app.monitor import start_monitor, stop_monitor, trigger_monitor
from app.utils import extract_proxy_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_monitor()
    yield
    await stop_monitor()

app = FastAPI(lifespan=lifespan)

@app.get("/")
@app.head("/")
def root():
    return {"message": "ProxyMaze'26 API is running!"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/config")
def read_config():
    return get_config()

@app.post("/config")
async def update_config(req: Request):
    data = await read_json_object(req)
    config_data = {}
    for key in ["check_interval_seconds", "request_timeout_ms"]:
        if key not in data or data[key] is None:
            continue
        try:
            value = int(data[key])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} must be an integer")
        if value <= 0:
            raise HTTPException(status_code=400, detail=f"{key} must be positive")
        config_data[key] = value

    set_config(config_data)
    trigger_monitor()
    return get_config()

@app.post("/proxies", status_code=201)
async def load_proxies(req: Request):
    data = await read_json_object(req)
    replace = data.get("replace", False)
    proxies = data.get("proxies", [])
    if proxies is None:
        proxies = []
    if not isinstance(proxies, list):
        raise HTTPException(status_code=400, detail="proxies must be an array")

    accepted = 0
    added_proxies = []

    with state_lock:
        if replace:
            clear_pool()

        for url in proxies:
            if not isinstance(url, str) or not url.strip():
                continue
            clean_url = url.strip()
            pid = extract_proxy_id(clean_url)
            if not pid:
                continue
            proxy = add_proxy(pid, clean_url)
            accepted += 1
            added_proxies.append({"id": proxy["id"], "url": proxy["url"], "status": proxy["status"]})

        evaluate(get_all_proxies())

    if accepted > 0 or replace:
        trigger_monitor()
    return {"accepted": accepted, "proxies": added_proxies}

@app.get("/proxies")
def read_proxies():
    with state_lock:
        stats = get_pool_stats()
        current_proxies = get_all_proxies()

    proxies = []
    for p in current_proxies:
        proxies.append({
            "id": p["id"],
            "url": p["url"],
            "status": p["status"],
            "last_checked_at": p["last_checked_at"],
            "consecutive_failures": p["consecutive_failures"]
        })
    return {**stats, "proxies": proxies}

@app.get("/proxies/{proxy_id}")
def read_proxy(proxy_id: str):
    proxy = get_proxy(proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Not Found")
    
    up_checks = sum(1 for h in proxy["history"] if h["status"] == "up")
    uptime_percentage = (up_checks / proxy["total_checks"] * 100) if proxy["total_checks"] > 0 else 0.0
    
    return {
        "id": proxy["id"],
        "url": proxy["url"],
        "status": proxy["status"],
        "last_checked_at": proxy["last_checked_at"],
        "consecutive_failures": proxy["consecutive_failures"],
        "total_checks": proxy["total_checks"],
        "uptime_percentage": uptime_percentage,
        "history": proxy["history"]
    }

@app.get("/proxies/{proxy_id}/history")
def read_proxy_history(proxy_id: str):
    proxy = get_proxy(proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Not Found")
    return proxy["history"]

@app.delete("/proxies", status_code=204)
async def delete_proxies():
    with state_lock:
        clear_pool()
        evaluate([])
    trigger_monitor()

@app.get("/alerts")
def read_alerts():
    return get_alerts()

@app.post("/webhooks", status_code=201)
async def add_webhook(req: Request):
    data = await read_json_object(req)
    try:
        return register_webhook(data.get("url"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/integrations", status_code=201)
async def add_integration(req: Request):
    data = await read_json_object(req)
    try:
        return register_integration(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/metrics")
def read_metrics():
    with state_lock:
        stats = get_pool_stats()
        alerts = get_alerts()
        current_metrics = get_metrics()

    active_alerts = sum(1 for a in alerts if a["status"] == "active")
    
    return {
        "total_checks": current_metrics["total_checks"],
        "current_pool_size": stats["total"],
        "active_alerts": active_alerts,
        "total_alerts": len(alerts),
        "webhook_deliveries": current_metrics["webhook_deliveries"]
    }

async def read_json_object(req: Request):
    body = await req.body()
    if not body:
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return data
