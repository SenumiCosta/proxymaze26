from fastapi import FastAPI, HTTPException, Request
from contextlib import asynccontextmanager

from app.store import get_config, set_config, add_proxy, clear_pool, get_pool_stats, get_all_proxies, get_proxy, metrics
from app.alert_manager import get_alerts, evaluate
from app.webhook_manager import register_webhook, register_integration
from app.monitor import start_monitor, stop_monitor, trigger_monitor
from app.utils import extract_proxy_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_monitor()
    yield
    stop_monitor()

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
    try:
        data = await req.json()
    except Exception:
        data = {}
        
    config_data = {}
    if "check_interval_seconds" in data:
        try:
            config_data["check_interval_seconds"] = int(data["check_interval_seconds"])
        except (ValueError, TypeError):
            pass
    if "request_timeout_ms" in data:
        try:
            config_data["request_timeout_ms"] = int(data["request_timeout_ms"])
        except (ValueError, TypeError):
            pass
            
    set_config(config_data)
    trigger_monitor()
    return get_config()

@app.post("/proxies", status_code=201)
async def load_proxies(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {}
    replace = data.get("replace", False)
    proxies = data.get("proxies", [])
    
    if replace:
        clear_pool()
    
    accepted = 0
    added_proxies = []
    
    for url in proxies:
        pid = extract_proxy_id(url)
        if not pid:
            continue
        proxy = add_proxy(pid, url)
        accepted += 1
        added_proxies.append({"id": proxy["id"], "url": proxy["url"], "status": proxy["status"]})
        
    evaluate(get_all_proxies())
    return {"accepted": accepted, "proxies": added_proxies}

@app.get("/proxies")
def read_proxies():
    stats = get_pool_stats()
    proxies = []
    for p in get_all_proxies():
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
def delete_proxies():
    clear_pool()
    evaluate(get_all_proxies())

@app.get("/alerts")
def read_alerts():
    return get_alerts()

@app.post("/webhooks", status_code=201)
async def add_webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {}
    return register_webhook(data.get("url"))

@app.post("/integrations", status_code=201)
async def add_integration(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {}
    return register_integration(data)

@app.get("/metrics")
def read_metrics():
    stats = get_pool_stats()
    alerts = get_alerts()
    active_alerts = sum(1 for a in alerts if a["status"] == "active")
    
    return {
        "total_checks": metrics["total_checks"],
        "current_pool_size": stats["total"],
        "active_alerts": active_alerts,
        "total_alerts": len(alerts),
        "webhook_deliveries": metrics["webhook_deliveries"]
    }
