import asyncio
import uuid
from threading import RLock

import httpx

from app.config import (
    DEFAULT_EVENTS,
    SUPPORTED_INTEGRATIONS,
    WEBHOOK_MAX_DELIVERY_SECONDS,
    WEBHOOK_PER_ATTEMPT_TIMEOUT_SECONDS,
    WEBHOOK_QUEUE_SIZE,
    WEBHOOK_RETRY_DELAYS_SECONDS,
    WEBHOOK_TRANSIENT_STATUS_CODES,
)
from app.store import increment_webhook_deliveries
from app.utils import to_unix_epoch


receivers = {}
delivered_ids = set()
delivery_lock = RLock()


def _display_username(receiver):
    username = receiver.get("username") or "ProxyMaze"
    return username.strip() if isinstance(username, str) and username.strip() else "ProxyMaze"


def format_slack_fired(receiver, alert):
    return {
        "username": _display_username(receiver),
        "text": "Proxy pool failure rate exceeded threshold",
        "attachments": [{
            "color": "#FF0000",
            "fields": [
                {"title": "Alert ID", "value": alert["alert_id"]},
                {"title": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"title": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"title": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"title": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"},
                {"title": "Fired At", "value": alert["fired_at"]},
            ],
            "footer": "ProxyMaze Alert System",
            "ts": to_unix_epoch(alert["fired_at"]),
        }],
    }


def format_slack_resolved(receiver, alert):
    return {
        "username": _display_username(receiver),
        "text": "Proxy pool alert resolved",
        "attachments": [{
            "color": "#00FF00",
            "fields": [
                {"title": "Alert ID", "value": alert["alert_id"]},
                {"title": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"title": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"title": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"title": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"},
                {"title": "Fired At", "value": alert["fired_at"]},
                {"title": "Resolved At", "value": alert["resolved_at"]},
            ],
            "footer": "ProxyMaze Alert System",
            "ts": to_unix_epoch(alert["resolved_at"]),
        }],
    }


def format_discord_fired(receiver, alert):
    return {
        "username": _display_username(receiver),
        "embeds": [{
            "title": "Proxy Alert Fired",
            "description": "Proxy pool failure rate exceeded threshold",
            "color": 16711680,
            "fields": [
                {"name": "Alert ID", "value": alert["alert_id"]},
                {"name": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"name": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"name": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"name": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"},
            ],
            "footer": {"text": "ProxyMaze Alert System"},
        }],
    }


def format_discord_resolved(receiver, alert):
    return {
        "username": _display_username(receiver),
        "embeds": [{
            "title": "Proxy Alert Resolved",
            "description": "Proxy pool alert resolved",
            "color": 65280,
            "fields": [
                {"name": "Alert ID", "value": alert["alert_id"]},
                {"name": "Failure Rate", "value": f"{alert['failure_rate'] * 100:.1f}%"},
                {"name": "Failed Proxies", "value": f"{alert['failed_proxies']} / {alert['total_proxies']}"},
                {"name": "Threshold", "value": f"{alert['threshold'] * 100:.1f}%"},
                {"name": "Failed IDs", "value": ", ".join(alert["failed_proxy_ids"]) or "none"},
                {"name": "Resolved At", "value": alert["resolved_at"]},
            ],
            "footer": {"text": "ProxyMaze Alert System"},
        }],
    }


async def process_queue(receiver):
    timeout = httpx.Timeout(WEBHOOK_PER_ATTEMPT_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=False,
        trust_env=False,
    ) as client:
        while True:
            task = await receiver["queue"].get()
            try:
                idempotency_key = f"{task['alertId']}:{task['event']}:{receiver['id']}"
                with delivery_lock:
                    if idempotency_key in delivered_ids:
                        continue

                loop = asyncio.get_running_loop()
                deadline = loop.time() + WEBHOOK_MAX_DELIVERY_SECONDS
                attempt = 0

                while loop.time() < deadline:
                    try:
                        remaining = deadline - loop.time()
                        attempt_timeout = max(0.1, min(WEBHOOK_PER_ATTEMPT_TIMEOUT_SECONDS, remaining))
                        res = await client.post(
                            receiver["url"],
                            json=task["payload"],
                            headers={"Content-Type": "application/json"},
                            timeout=attempt_timeout,
                        )

                        if 200 <= res.status_code < 300:
                            with delivery_lock:
                                delivered_ids.add(idempotency_key)
                            increment_webhook_deliveries()
                            break

                        if res.status_code not in WEBHOOK_TRANSIENT_STATUS_CODES:
                            break
                    except Exception:
                        pass

                    delay = WEBHOOK_RETRY_DELAYS_SECONDS[min(attempt, len(WEBHOOK_RETRY_DELAYS_SECONDS) - 1)]
                    attempt += 1
                    await asyncio.sleep(min(delay, max(0, deadline - loop.time())))
            finally:
                receiver["queue"].task_done()


def register_webhook(url: str):
    clean_url = _validate_url(url, "url")
    with delivery_lock:
        existing = next(
            (
                receiver for receiver in receivers.values()
                if receiver["type"] == "webhook" and receiver["url"] == clean_url
            ),
            None,
        )
        if existing:
            return {"webhook_id": existing["id"], "url": existing["url"]}

        wid = f"wh-{uuid.uuid4().hex[:8]}"
        receiver = {
            "id": wid,
            "type": "webhook",
            "url": clean_url,
            "events": DEFAULT_EVENTS.copy(),
            "queue": asyncio.Queue(maxsize=WEBHOOK_QUEUE_SIZE),
        }
        receivers[wid] = receiver

    asyncio.create_task(process_queue(receiver))
    return {"webhook_id": wid, "url": clean_url}


def register_integration(integration: dict):
    integration_type = integration.get("type")
    if integration_type not in SUPPORTED_INTEGRATIONS:
        raise ValueError("type must be slack or discord")

    clean_url = _validate_url(integration.get("webhook_url"), "webhook_url")
    username = integration.get("username") or "ProxyMaze"
    events = _clean_events(integration.get("events"))

    with delivery_lock:
        existing = next(
            (
                receiver for receiver in receivers.values()
                if receiver["type"] == integration_type and receiver["url"] == clean_url
            ),
            None,
        )
        if existing:
            existing["username"] = username
            existing["events"] = sorted(set(existing["events"]) | set(events))
            return _integration_response(existing)

        wid = f"int-{uuid.uuid4().hex[:8]}"
        receiver = {
            "id": wid,
            "type": integration_type,
            "url": clean_url,
            "username": username,
            "events": events,
            "queue": asyncio.Queue(maxsize=WEBHOOK_QUEUE_SIZE),
        }
        receivers[wid] = receiver

    asyncio.create_task(process_queue(receiver))
    return _integration_response(receiver)


def enqueue(event: str, webhook_payload: dict, active_alert: dict):
    with delivery_lock:
        target_receivers = list(receivers.values())

    for receiver in target_receivers:
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
            "payload": payload,
        }

        try:
            receiver["queue"].put_nowait(task)
        except asyncio.QueueFull:
            try:
                receiver["queue"].get_nowait()
                receiver["queue"].task_done()
            except asyncio.QueueEmpty:
                pass
            receiver["queue"].put_nowait(task)


def _integration_response(receiver):
    return {
        "integration_id": receiver["id"],
        "type": receiver["type"],
        "webhook_url": receiver["url"],
        "username": _display_username(receiver),
        "events": receiver["events"],
    }


def _validate_url(url: str, field_name: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"{field_name} is required")
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return clean_url


def _clean_events(events):
    if not events:
        return DEFAULT_EVENTS.copy()

    allowed = set(DEFAULT_EVENTS)
    clean = []
    for event in events:
        if event in allowed and event not in clean:
            clean.append(event)
    if not clean:
        raise ValueError("events must include alert.fired or alert.resolved")
    return clean
