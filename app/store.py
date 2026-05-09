from typing import Dict, List, Any
from app.config import DEFAULT_CONFIG, MAX_HISTORY

# Config
config = DEFAULT_CONFIG.copy()

def get_config():
    return config.copy()

def set_config(new_config: dict):
    if new_config.get("check_interval_seconds") is not None:
        config["check_interval_seconds"] = new_config["check_interval_seconds"]
    if new_config.get("request_timeout_ms") is not None:
        config["request_timeout_ms"] = new_config["request_timeout_ms"]

# Proxy Pool
proxy_map: Dict[str, dict] = {}

def add_proxy(proxy_id: str, url: str):
    proxy_map[proxy_id] = {
        "id": proxy_id,
        "url": url,
        "status": "pending",
        "last_checked_at": None,
        "consecutive_failures": 0,
        "total_checks": 0,
        "history": []
    }
    return proxy_map[proxy_id]

def clear_pool():
    proxy_map.clear()

def get_all_proxies() -> List[dict]:
    return list(proxy_map.values())

def get_proxy(proxy_id: str) -> dict | None:
    return proxy_map.get(proxy_id)

def update_proxy_status(proxy_id: str, status: str, checked_at: str):
    proxy = proxy_map.get(proxy_id)
    if not proxy:
        return
    
    proxy["status"] = status
    proxy["last_checked_at"] = checked_at
    proxy["total_checks"] += 1
    
    if status == "down":
        proxy["consecutive_failures"] += 1
    elif status == "up":
        proxy["consecutive_failures"] = 0
        
    proxy["history"].append({"checked_at": checked_at, "status": status})
    if len(proxy["history"]) > MAX_HISTORY:
        proxy["history"].pop(0)

def apply_updates(updates: List[dict]):
    for update in updates:
        update_proxy_status(update["id"], update["status"], update["checked_at"])

def get_pool_stats():
    pool = get_all_proxies()
    total = len(pool)
    up = sum(1 for p in pool if p["status"] == "up")
    down = sum(1 for p in pool if p["status"] == "down")
    failure_rate = (down / total) if total > 0 else 0.0
    return {"total": total, "up": up, "down": down, "failure_rate": failure_rate}

# Metrics
metrics = {
    "total_checks": 0,
    "webhook_deliveries": 0
}

def increment_checks():
    metrics["total_checks"] += 1

def increment_webhook_deliveries():
    metrics["webhook_deliveries"] += 1
