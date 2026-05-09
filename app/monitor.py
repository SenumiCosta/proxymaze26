import asyncio
import httpx
from app.store import get_config, get_all_proxies, apply_updates, increment_checks
from app.alert_manager import evaluate
from app.utils import now_iso

monitor_task = None
is_running = False
semaphore = asyncio.Semaphore(50)
config_event = asyncio.Event()

def trigger_monitor():
    config_event.set()

async def check_proxy(client: httpx.AsyncClient, proxy: dict, config: dict):
    async with semaphore:
        status = "down"
        checked_at = now_iso()
        increment_checks()
        try:
            timeout_sec = int(config.get("request_timeout_ms", 5000)) / 1000.0
            res = await client.get(
                proxy["url"],
                timeout=timeout_sec
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
    
    async with httpx.AsyncClient() as client:
        while is_running:
            try:
                config = get_config()
                snapshot = get_all_proxies()
                
                if snapshot:
                    tasks = [check_proxy(client, p, config) for p in snapshot]
                    updates = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    valid_updates = [u for u in updates if not isinstance(u, Exception)]
                    apply_updates(valid_updates)
                    evaluate(get_all_proxies())
                    
                config_event.clear()
                try:
                    interval = int(config.get("check_interval_seconds", 30))
                    await asyncio.wait_for(config_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            except Exception:
                await asyncio.sleep(1)

def start_monitor():
    global monitor_task
    if not monitor_task:
        monitor_task = asyncio.create_task(monitor_loop())

def stop_monitor():
    global is_running
    is_running = False
    config_event.set()
