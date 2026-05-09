import asyncio
from contextlib import suppress

import httpx
from app.config import MAX_MONITOR_CONCURRENCY
from app.store import (
    apply_updates,
    get_all_proxies,
    get_config,
    get_proxy_snapshot,
    increment_checks,
    state_lock,
)
from app.alert_manager import evaluate
from app.utils import now_iso

monitor_task = None
is_running = False
monitor_loop_ref = None
config_event = None
semaphore = asyncio.Semaphore(MAX_MONITOR_CONCURRENCY)

def trigger_monitor():
    if config_event and monitor_loop_ref and monitor_loop_ref.is_running():
        monitor_loop_ref.call_soon_threadsafe(config_event.set)

async def check_proxy(client: httpx.AsyncClient, proxy: dict, config: dict):
    async with semaphore:
        status = "down"
        checked_at = now_iso()
        increment_checks()
        try:
            res = await client.get(
                proxy["url"],
                timeout=config["request_timeout_ms"] / 1000.0
            )
            if 200 <= res.status_code < 300:
                status = "up"
        except Exception:
            pass # network error, timeout -> down
            
        return {
            "id": proxy["id"],
            "status": status,
            "checked_at": checked_at
        }

async def monitor_loop():
    global is_running
    is_running = True

    async with httpx.AsyncClient(follow_redirects=False, verify=False, trust_env=False) as client:
        while is_running:
            config_event.clear()
            config = get_config()
            snapshot = get_proxy_snapshot()

            if snapshot:
                tasks = [check_proxy(client, p, config) for p in snapshot]
                updates = await asyncio.gather(*tasks, return_exceptions=True)

                valid_updates = [u for u in updates if not isinstance(u, Exception)]
                with state_lock:
                    apply_updates(valid_updates)
                    evaluate(get_all_proxies())
            else:
                with state_lock:
                    evaluate([])

            config = get_config()
            try:
                await asyncio.wait_for(config_event.wait(), timeout=config["check_interval_seconds"])
            except asyncio.TimeoutError:
                pass

def start_monitor():
    global config_event, monitor_loop_ref, monitor_task
    monitor_loop_ref = asyncio.get_running_loop()
    if config_event is None:
        config_event = asyncio.Event()
    if not monitor_task or monitor_task.done():
        monitor_task = asyncio.create_task(monitor_loop())

async def stop_monitor():
    global is_running, monitor_task
    is_running = False
    trigger_monitor()
    if monitor_task:
        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task
        monitor_task = None
