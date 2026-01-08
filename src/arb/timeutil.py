import time
from datetime import datetime, timezone

def now_ts() -> float:
    """Return current UTC timestamp in seconds."""
    return time.time()

def now_iso() -> str:
    """Return current UTC time in ISO 8601 format with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def monotonic_now() -> float:
    """Return monotonic clock time in seconds."""
    return time.monotonic()

def format_delta_ms(delta_sec: float) -> str:
    return f"{delta_sec * 1000:.1f}ms"
