"""Canonical event schemas, Pydantic models, dataclasses, and constants for RootLens."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Tuple, TypedDict, Union

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
# PYDANTIC MODELS FOR INGESTION, REASONING & RECOVERY
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


# =====================================================================
# MEMBER B: CORRELATION, TIMELINE & RE-CORRELATION CONTRACTS
# =====================================================================

@dataclass
class NormalizedEvent:
    """Normalized representation of an observability signal (alert, log, metric, deploy, complaint).

    Attributes:
        event_id: Unique identifier for the event.
        timestamp: Timezone-aware UTC datetime of the event.
        source: Origin domain/system (e.g. 'alerts', 'logs', 'metrics', 'deploys', 'complaints').
        component: Target service, host, or component name.
        severity: Severity level (e.g. 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO').
        description: Human-readable message or summary text.
        metadata: Optional dictionary with additional contextual attributes.
    """

    event_id: str
    timestamp: datetime
    source: str
    component: str
    severity: str
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentCluster:
    """A cluster of correlated events grouped by component and temporal proximity.

    Attributes:
        incident_id: Unique deterministic or generated identifier for the incident.
        component: The service or system component associated with this cluster.
        start_time: Timestamp of the earliest event in the cluster.
        end_time: Timestamp of the latest event in the cluster.
        event_ids: List of unique IDs of all events contained in the cluster.
        events: List[Any]: List of event objects/records belonging to the cluster.
        event_count: Total number of events in this cluster.
    """

    incident_id: str
    component: str
    start_time: datetime
    end_time: datetime
    event_ids: List[str] = field(default_factory=list)
    events: List[Any] = field(default_factory=list)
    event_count: int = 0

    def __post_init__(self) -> None:
        if self.events and not self.event_ids:
            self.event_ids = [
                getattr(e, "event_id", e.get("event_id") if isinstance(e, dict) else str(e))
                for e in self.events
            ]
        if not self.event_count:
            self.event_count = len(self.events) if self.events else len(self.event_ids)


@dataclass
class TimelineEntry:
    """A single chronological entry in the Unified Incident Timeline.

    Attributes:
        event_id: Unique identifier for the event.
        incident_id: Associated incident cluster identifier.
        timestamp: Timezone-aware UTC datetime of the event.
        source: Origin domain/system (alerts, logs, metrics, deploys, complaints).
        component: Target service or system component.
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO).
        description: Human-readable summary or log text.
        metadata: Optional dictionary with additional context.
    """

    event_id: str
    incident_id: str
    timestamp: datetime
    source: str
    component: str
    severity: str
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedTimeline:
    """Unified chronological incident timeline across correlated incident clusters.

    Attributes:
        entries: Chronologically ordered list of TimelineEntry objects.
        start_time: Timestamp of the earliest event in the timeline.
        end_time: Timestamp of the latest event in the timeline.
        event_count: Total number of timeline entries.
        incident_ids: List of unique incident cluster IDs represented in the timeline.
        components: List of unique component names represented in the timeline.
    """

    entries: List[TimelineEntry] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_count: int = 0
    incident_ids: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.entries:
            if self.start_time is None:
                self.start_time = self.entries[0].timestamp
            if self.end_time is None:
                self.end_time = self.entries[-1].timestamp
            if not self.event_count:
                self.event_count = len(self.entries)
            if not self.incident_ids:
                # Maintain order of first appearance
                seen_incidents = set()
                inc_list = []
                for entry in self.entries:
                    if entry.incident_id not in seen_incidents:
                        seen_incidents.add(entry.incident_id)
                        inc_list.append(entry.incident_id)
                self.incident_ids = inc_list
            if not self.components:
                seen_comps = set()
                comp_list = []
                for entry in self.entries:
                    if entry.component not in seen_comps:
                        seen_comps.add(entry.component)
                        comp_list.append(entry.component)
                self.components = comp_list
        else:
            self.event_count = 0
            if self.incident_ids is None:
                self.incident_ids = []
            if self.components is None:
                self.components = []


@dataclass
class ReCorrelationResult:
    """Result of a re-correlation operation when new observability signals arrive.

    Supports tuple unpacking: `clusters, timeline = result`

    Attributes:
        clusters: List of updated IncidentCluster objects.
        timeline: Updated UnifiedTimeline containing all sorted events.
        total_events: Total count of unique events correlated.
        new_events_count: Count of new events successfully incorporated.
    """

    clusters: List[IncidentCluster] = field(default_factory=list)
    timeline: UnifiedTimeline = field(default_factory=UnifiedTimeline)
    total_events: int = 0
    new_events_count: int = 0

    def __iter__(self) -> Iterator[Any]:
        """Support unpacking into `clusters, timeline = result`."""
        yield self.clusters
        yield self.timeline
