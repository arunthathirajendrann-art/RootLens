"""Canonical event schemas and constants for RootLens."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, TypedDict


class CanonicalSource(str, Enum):
    """Canonical signal sources across telemetry streams."""
    ALERTS = "alerts"
    LOGS = "logs"
    METRICS = "metrics"
    COMPLAINTS = "complaints"
    DEPLOYS = "deploys"
    CONFIG = "config"
    GC_PROFILER = "gc_profiler"


class CanonicalSeverity(str, Enum):
    """Normalized operational severity values."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CanonicalEvent(TypedDict):
    """Canonical normalized event contract."""
    event_id: str
    timestamp: str
    source: str
    service: str
    severity: str
    event_type: str
    description: str
    metadata: Dict[str, Any]
