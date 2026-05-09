from urllib.parse import urlparse
from datetime import datetime, timezone
import math

def extract_proxy_id(url_str: str) -> str | None:
    try:
        parsed = urlparse(url_str)
        path = parsed.path
        segments = [s for s in path.split('/') if s]
        if not segments:
            return parsed.hostname or None
        return segments[-1]
    except Exception:
        return None

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def to_unix_epoch(iso_string: str) -> int:
    try:
        if iso_string.endswith("Z"):
            iso_string = iso_string[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_string)
        return math.floor(dt.timestamp())
    except Exception:
        return 0
