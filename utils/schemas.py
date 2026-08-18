"""Canonical event schemas, Pydantic models, and constants for RootLens."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# =====================================================================
# MEMBER A: CANONICAL SCHEMA CONTRACT
# =====================================================================

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


# =====================================================================
# PYDANTIC MODELS FOR CORRELATION, REASONING & RECOVERY
# =====================================================================

class AlertSignal(BaseModel):
    timestamp: str
    alert_id: str
    name: str
    component: str
    severity: str
    message: str


class LogSignal(BaseModel):
    timestamp: str
    component: str
    level: str
    message: str


class MetricSignal(BaseModel):
    timestamp: str
    component: str
    metric_name: str
    value: float


class UserComplaint(BaseModel):
    timestamp: str
    user_id: str
    complaint_id: str
    severity: str
    message: str


class DeploymentRecord(BaseModel):
    timestamp: str
    deploy_id: str
    component: str
    version: str
    status: str
    deployed_by: str
    change_log: str


class HistoricalIncident(BaseModel):
    timestamp: str
    incident_id: str
    component: str
    symptoms: str
    root_cause: str
    recovery_action: str
    status: str
    operator_notes: str


class NormalizedSignal(BaseModel):
    signal_id: str
    signal_type: str  # alert, log, metric, complaint, deploy, config, gc_profiler
    source: str
    timestamp: str
    parsed_timestamp: datetime
    component: str
    severity: str
    message: str
    metadata: Dict[str, Any] = {}

    @property
    def event_id(self) -> str:
        return self.signal_id

    @property
    def service(self) -> str:
        return self.component

    @property
    def event_type(self) -> str:
        return self.signal_type

    @property
    def description(self) -> str:
        return self.message


class Evidence(BaseModel):
    evidence_id: str
    signal_id: str
    type: str
    timestamp: str
    summary: str
    relevance: str


class Hypothesis(BaseModel):
    title: str
    description: str
    confidence: float
    evidence_for: List[str]
    evidence_against: List[str]


class ResponseAction(BaseModel):
    action: str
    reason: str
    risk: str
    instructions: str
    requires_human_approval: bool = True
