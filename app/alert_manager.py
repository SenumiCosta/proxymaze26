from copy import deepcopy
import uuid
from app.config import ALERT_THRESHOLD
from app.store import state_lock
from app.utils import now_iso
from app.webhook_manager import enqueue

active_alert = None
alert_archive = []

def evaluate(pool: list):
    global active_alert

    with state_lock:
        total = len(pool)
        down_proxies = [p for p in pool if p.get("status") == "down"]
        down_count = len(down_proxies)
        failure_rate = (down_count / total) if total > 0 else 0.0
        down_ids = sorted(p["id"] for p in down_proxies)

        if failure_rate >= ALERT_THRESHOLD and not active_alert:
            active_alert = {
                "alert_id": f"alert-{uuid.uuid4().hex[:8]}",
                "status": "active",
                "failure_rate": failure_rate,
                "total_proxies": total,
                "failed_proxies": down_count,
                "failed_proxy_ids": down_ids,
                "threshold": ALERT_THRESHOLD,
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
                "failed_proxy_ids": active_alert["failed_proxy_ids"].copy(),
                "threshold": active_alert["threshold"],
                "message": active_alert["message"]
            }, deepcopy(active_alert))

        elif failure_rate < ALERT_THRESHOLD and active_alert:
            active_alert["status"] = "resolved"
            active_alert["resolved_at"] = now_iso()
            active_alert["failed_proxies"] = down_count
            active_alert["failed_proxy_ids"] = down_ids

            enqueue("alert.resolved", {
                "event": "alert.resolved",
                "alert_id": active_alert["alert_id"],
                "resolved_at": active_alert["resolved_at"]
            }, deepcopy(active_alert))

            active_alert = None

        elif failure_rate >= ALERT_THRESHOLD and active_alert:
            active_alert["failure_rate"] = failure_rate
            active_alert["total_proxies"] = total
            active_alert["failed_proxies"] = down_count
            active_alert["failed_proxy_ids"] = down_ids

def get_alerts():
    with state_lock:
        return deepcopy(alert_archive)

def get_active_alert():
    with state_lock:
        return deepcopy(active_alert)
