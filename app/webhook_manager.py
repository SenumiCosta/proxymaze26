import asyncio
import httpx
import uuid
import json
from app.store import increment_webhook_deliveries
from app.utils import to_unix_epoch

receivers = {}
delivered_ids = set()

def format_slack_fired(receiver, alert):
    return {
        "username": receiver["username"],
        "text": "🚨 Proxy pool failure rate exceeded threshold",
        "attachments": [{
            "color": "#FF0000",
            "fields": [
                {"title": "Alert ID", "value": alert["alert_id"]},
                {"title": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"title": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"title": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"title": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"},
                {"title": "Fired At", "value": alert["fired_at"]}
            ],
            "footer": "ProxyMaze Alert System",
            "ts": to_unix_epoch(alert["fired_at"])
        }]
    }

def format_slack_resolved(receiver, alert):
    return {
        "username": receiver["username"],
        "text": "✅ Proxy pool alert resolved",
        "attachments": [{
            "color": "#00FF00",
            "fields": [
                {"title": "Alert ID", "value": alert["alert_id"]},
                {"title": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"title": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"title": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"title": "Failed IDs", "value": "none"},
                {"title": "Fired At", "value": alert["fired_at"]}
            ],
            "footer": "ProxyMaze Alert System",
            "ts": to_unix_epoch(alert["resolved_at"])
        }]
    }

def format_discord_fired(receiver, alert):
    return {
        "username": receiver["username"],
        "embeds": [{
            "title": "🚨 Proxy Alert Fired",
            "description": "Proxy pool failure rate exceeded threshold",
            "color": 16711680,
            "fields": [
                {"name": "Alert ID", "value": alert["alert_id"]},
                {"name": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"name": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"name": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"name": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"}
            ],
            "footer": {"text": "ProxyMaze Alert System"}
        }]
    }

def format_discord_resolved(receiver, alert):
    return {
        "username": receiver["username"],
        "embeds": [{
            "title": "✅ Proxy Alert Resolved",
            "description": "Proxy pool alert resolved",
            "color": 65280,
            "fields": [
                {"name": "Alert ID", "value": alert["alert_id"]},
                {"name": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"name": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"name": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"name": "Failed IDs", "value": "none"}
            ],
            "footer": {"text": "ProxyMaze Alert System"}
        }]
    }

async def process_queue(receiver):
    async with httpx.AsyncClient() as client:
        while True:
            task = await receiver["queue"].get()
            
            idempotency_key = f"{task['alertId']}:{task['event']}:{receiver['id']}"
            if idempotency_key in delivered_ids:
                receiver["queue"].task_done()
                continue
            
            attempts = 0
            success = False
            
            while attempts < 10:
                attempts += 1
                try:
                    res = await client.post(
                        receiver["url"], 
                        json=task["payload"],
                        timeout=5.0
                    )
                    
                    if 200 <= res.status_code < 300:
                        success = True
                        break
                    
                    if res.status_code in [500, 502, 503, 504]:
                        pass # transient
                    else:
                        break # non-transient
                        
                except Exception:
                    pass
                
                if attempts < 10:
                    backoff = min((2 ** (attempts - 1)), 30)
                    await asyncio.sleep(backoff)
            
            if success:
                delivered_ids.add(idempotency_key)
                increment_webhook_deliveries()
                
            receiver["queue"].task_done()

def register_webhook(url: str):
    wid = f"wh-{uuid.uuid4()}"
    queue = asyncio.Queue(maxsize=100)
    receiver = {
        "id": wid,
        "type": "webhook",
        "url": url,
        "events": ["alert.fired", "alert.resolved"],
        "queue": queue
    }
    receivers[wid] = receiver
    asyncio.create_task(process_queue(receiver))
    return {"webhook_id": wid, "url": url}

def register_integration(integration: dict):
    wid = f"int-{uuid.uuid4()}"
    queue = asyncio.Queue(maxsize=100)
    receiver = {
        "id": wid,
        "type": integration["type"],
        "url": integration["webhook_url"],
        "username": integration["username"],
        "events": integration.get("events") or ["alert.fired", "alert.resolved"],
        "queue": queue
    }
    receivers[wid] = receiver
    asyncio.create_task(process_queue(receiver))
    return {"status": "Integration registered"}

def enqueue(event: str, webhook_payload: dict, active_alert: dict):
    for receiver in receivers.values():
        if event not in receiver["events"]:
            continue
            
        if receiver["type"] == "slack":
            payload = format_slack_fired(receiver, active_alert) if event == "alert.fired" else format_slack_resolved(receiver, active_alert)
        elif receiver["type"] == "discord":
            payload = format_discord_fired(receiver, active_alert) if event == "alert.fired" else format_discord_resolved(receiver, active_alert)
        else:
            payload = webhook_payload

        task = {
            "alertId": active_alert["alert_id"],
            "event": event,
            "payload": payload
        }
        
        try:
            receiver["queue"].put_nowait(task)
        except asyncio.QueueFull:
            receiver["queue"].get_nowait()
            receiver["queue"].put_nowait(task)
