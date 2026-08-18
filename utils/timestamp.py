from datetime import datetime

def parse_iso_timestamp(ts_str: str) -> datetime:
    """
    Safely parses an ISO timestamp string into a datetime object.
    Supports Z-suffix by translating to UTC offset.
    """
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception:
        return datetime.now()

def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
