"""Timestamp parsing and formatting utilities for RootLens."""

from __future__ import annotations

import datetime
from typing import Union


def parse_iso_utc(ts: Union[str, datetime.datetime]) -> datetime.datetime:
    """Parse an ISO-8601 string or datetime into a UTC timezone-aware datetime object."""
    if isinstance(ts, datetime.datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=datetime.timezone.utc)
        return ts.astimezone(datetime.timezone.utc)

    # Normalize trailing Z to UTC offset for standard parsing
    clean_ts = ts.strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(clean_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt


def format_iso_utc(ts: Union[str, datetime.datetime]) -> str:
    """Format a timestamp into canonical ISO-8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)."""
    dt = parse_iso_utc(ts)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# Compatibility aliases
parse_datetime = parse_iso_utc
format_datetime = format_iso_utc
