import uuid
from app.utils import now_iso
from app.webhook_manager import enqueue

active_alert = None
alert_archive = []

def evaluate(pool: list):
    global active_alert
    
    total = len(pool)
    down_proxies = [p for p in pool if p["status"] == "down"]
    down_count = len(down_proxies)
    failure_rate = (down_count / total) if total > 0 else 0.0
    down_ids = [p["id"] for p in down_proxies]
    
    if failure_rate >= 0.20 and not active_alert:
        active_alert = {
            "alert_id": f"alert-{uuid.uuid4()}",
            "status": "active",
            "failure_rate": failure_rate,
            "total_proxies": total,
            "failed_proxies": down_count,
            "failed_proxy_ids": down_ids,
            "threshold": 0.20,
            "fired_at": now_iso(),
            "resolved_at": None,
            "message": "Proxy pool failure rate exceeded threshold"
        }
        alert_archive.append(active_alert)
        
        enqueue("alert.fired", {
            "event": "alert.fired",
            "alert_id": active_alert["alert_id"],
            "fired_at": active_alert["fired_at"],
            "failure_rate": active_alert["failure_rate"],
            "total_proxies": active_alert["total_proxies"],
            "failed_proxies": active_alert["failed_proxies"],
            "failed_proxy_ids": active_alert["failed_proxy_ids"],
            "threshold": active_alert["threshold"],
            "message": active_alert["message"]
        }, active_alert)
        
    elif failure_rate < 0.20 and active_alert:
        active_alert["status"] = "resolved"
        active_alert["resolved_at"] = now_iso()
        active_alert["failed_proxies"] = down_count
        active_alert["failed_proxy_ids"] = down_ids
        
        enqueue("alert.resolved", {
            "event": "alert.resolved",
            "alert_id": active_alert["alert_id"],
            "resolved_at": active_alert["resolved_at"]
        }, active_alert)
        
        active_alert = None
        
    elif failure_rate >= 0.20 and active_alert:
        active_alert["failed_proxies"] = down_count
        active_alert["failed_proxy_ids"] = down_ids

def get_alerts():
    return alert_archive

def get_active_alert():
    return active_alert
