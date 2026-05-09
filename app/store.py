from copy import deepcopy
from threading import RLock
from typing import Dict, List
from app.config import DEFAULT_CONFIG, MAX_HISTORY

state_lock = RLock()

config = DEFAULT_CONFIG.copy()

def get_config():
    with state_lock:
        return config.copy()

def set_config(new_config: dict):
    with state_lock:
        if new_config.get("check_interval_seconds") is not None:
            config["check_interval_seconds"] = int(new_config["check_interval_seconds"])
        if new_config.get("request_timeout_ms") is not None:
            config["request_timeout_ms"] = int(new_config["request_timeout_ms"])

proxy_map: Dict[str, dict] = {}

def add_proxy(proxy_id: str, url: str):
    with state_lock:
        proxy_map[proxy_id] = {
            "id": proxy_id,
            "url": url,
            "status": "pending",
            "last_checked_at": None,
            "consecutive_failures": 0,
            "total_checks": 0,
            "history": []
        }
        return deepcopy(proxy_map[proxy_id])

def clear_pool():
    with state_lock:
        proxy_map.clear()

def get_all_proxies() -> List[dict]:
    with state_lock:
        return deepcopy(list(proxy_map.values()))

def get_proxy_snapshot() -> List[dict]:
    with state_lock:
        return [p.copy() for p in proxy_map.values()]

def get_proxy(proxy_id: str) -> dict | None:
    with state_lock:
        proxy = proxy_map.get(proxy_id)
        return deepcopy(proxy) if proxy else None

def update_proxy_status(proxy_id: str, status: str, checked_at: str):
    with state_lock:
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
    with state_lock:
        for update in updates:
            update_proxy_status(update["id"], update["status"], update["checked_at"])

def get_pool_stats():
    with state_lock:
        pool = list(proxy_map.values())
        total = len(pool)
        up = sum(1 for p in pool if p["status"] == "up")
        down = sum(1 for p in pool if p["status"] == "down")
        failure_rate = (down / total) if total > 0 else 0.0
        return {"total": total, "up": up, "down": down, "failure_rate": failure_rate}

metrics = {
    "total_checks": 0,
    "webhook_deliveries": 0
}

def increment_checks():
    with state_lock:
        metrics["total_checks"] += 1

def increment_webhook_deliveries():
    with state_lock:
        metrics["webhook_deliveries"] += 1

def get_metrics():
    with state_lock:
        return metrics.copy()
