# ==========================================
# OWNED BY: MEMBER B (Correlation Engine)
# Responsibility: Sort and format unified incident timeline
# ==========================================

"""Unified Incident Timeline Builder for RootLens.

Transforms IncidentCluster objects produced by the CorrelationEngine into a
single, deterministic, chronologically ordered UnifiedTimeline.

This module acts strictly as an evidence organization layer. It does NOT perform:
- Root-cause analysis
- Hypothesis generation
- Causal interpretation
- Severity scoring / diagnosis
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from correlation.correlation_engine import _normalize_timestamp, extract_normalized_event
from utils.schemas import IncidentCluster, NormalizedEvent, NormalizedSignal, TimelineEntry, UnifiedTimeline
from utils.timestamp import format_datetime


# =====================================================================
# APP / DOWNSTREAM COMPATIBILITY HELPERS
# =====================================================================

def build_chronological_timeline(signals: List[Any]) -> List[Any]:
    """Sort signals chronologically for UI display."""
    def get_ts(s: Any) -> datetime:
        if hasattr(s, "parsed_timestamp") and isinstance(s.parsed_timestamp, datetime):
            return s.parsed_timestamp
        if hasattr(s, "timestamp"):
            ts = s.timestamp
            if isinstance(ts, datetime):
                return ts
            if isinstance(ts, str):
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass
        if isinstance(s, dict):
            raw = s.get("parsed_timestamp") or s.get("timestamp")
            if isinstance(raw, datetime):
                return raw
            if isinstance(raw, str):
                try:
                    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except Exception:
                    pass
        return datetime.min

    return sorted(signals, key=get_ts)


def format_timeline_for_prompt(timeline: List[Any]) -> str:
    """Format a timeline of signals or timeline entries into human-readable prompt lines."""
    lines = []
    for sig in timeline:
        if isinstance(sig, TimelineEntry):
            ts_str = format_datetime(sig.timestamp)
            lines.append(
                f"[{ts_str}] [{sig.source.upper()}] Component: {sig.component} | "
                f"Severity: {sig.severity} | Message: {sig.description}"
            )
        elif hasattr(sig, "parsed_timestamp") or hasattr(sig, "component"):
            ts_raw = getattr(sig, "parsed_timestamp", getattr(sig, "timestamp", None))
            ts_str = format_datetime(ts_raw) if ts_raw else "UNKNOWN"
            sig_type = getattr(sig, "signal_type", getattr(sig, "source", "EVENT"))
            comp = getattr(sig, "component", getattr(sig, "service", "unknown"))
            sev = getattr(sig, "severity", "INFO")
            msg = getattr(sig, "message", getattr(sig, "description", ""))
            lines.append(
                f"[{ts_str}] [{str(sig_type).upper()}] Component: {comp} | "
                f"Severity: {sev} | Message: {msg}"
            )
        elif isinstance(sig, dict):
            ts_raw = sig.get("parsed_timestamp") or sig.get("timestamp")
            ts_str = format_datetime(ts_raw) if ts_raw else "UNKNOWN"
            sig_type = sig.get("signal_type") or sig.get("source", "EVENT")
            comp = sig.get("component") or sig.get("service", "unknown")
            sev = sig.get("severity", "INFO")
            msg = sig.get("message") or sig.get("description", "")
            lines.append(
                f"[{ts_str}] [{str(sig_type).upper()}] Component: {comp} | "
                f"Severity: {sev} | Message: {msg}"
            )
    return "\n".join(lines)


# =====================================================================
# CORE TIMELINE BUILDER (MEMBER B)
# =====================================================================

class TimelineBuilder:
    """Constructs a unified, chronologically sorted timeline from incident clusters.

    Preserves every unique event exactly once, associates each event with its
    originating incident_id, and guarantees deterministic ordering.
    """

    def build(
        self, clusters: Union[IncidentCluster, Iterable[IncidentCluster], None]
    ) -> UnifiedTimeline:
        """Flatten and sort events from one or more IncidentClusters into a UnifiedTimeline.

        Args:
            clusters: A single IncidentCluster, an iterable of IncidentClusters, or None.

        Returns:
            UnifiedTimeline containing sorted TimelineEntry objects and aggregate metadata.
        """
        if clusters is None:
            return UnifiedTimeline()

        # Handle a single IncidentCluster instance passed directly
        if isinstance(clusters, IncidentCluster):
            cluster_list = [clusters]
        elif isinstance(clusters, dict) and "incident_id" in clusters:
            cluster_list = [clusters]
        else:
            try:
                cluster_list = list(clusters)
            except TypeError:
                cluster_list = [clusters]

        if not cluster_list:
            return UnifiedTimeline()

        raw_entries: List[TimelineEntry] = []
        seen_event_ids: Set[str] = set()

        for cluster in cluster_list:
            # Safely extract cluster attributes
            incident_id = self._extract_incident_id(cluster)
            events = self._extract_cluster_events(cluster)

            for raw_event in events:
                event = self._normalize_event(raw_event, incident_id)

                # Prevent duplicate event entries if an event appears in multiple clusters
                if event.event_id in seen_event_ids:
                    continue

                seen_event_ids.add(event.event_id)

                entry = TimelineEntry(
                    event_id=event.event_id,
                    incident_id=incident_id,
                    timestamp=event.timestamp,
                    source=event.source,
                    component=event.component,
                    severity=event.severity,
                    description=event.description,
                    metadata=deepcopy(event.metadata) if event.metadata else {},
                )
                raw_entries.append(entry)

        if not raw_entries:
            return UnifiedTimeline()

        # Deterministic chronological sort:
        # Primary key: timestamp
        # Secondary key (tie-breaker): event_id
        # Tertiary key: incident_id
        sorted_entries = sorted(
            raw_entries, key=lambda e: (e.timestamp, e.event_id, e.incident_id)
        )

        start_time = sorted_entries[0].timestamp
        end_time = sorted_entries[-1].timestamp
        event_count = len(sorted_entries)

        # Track unique incident IDs and components in chronological order of first appearance
        incident_ids: List[str] = []
        seen_incidents: Set[str] = set()
        components: List[str] = []
        seen_components: Set[str] = set()

        for entry in sorted_entries:
            if entry.incident_id not in seen_incidents:
                seen_incidents.add(entry.incident_id)
                incident_ids.append(entry.incident_id)

            if entry.component not in seen_components:
                seen_components.add(entry.component)
                components.append(entry.component)

        return UnifiedTimeline(
            entries=sorted_entries,
            start_time=start_time,
            end_time=end_time,
            event_count=event_count,
            incident_ids=incident_ids,
            components=components,
        )

    def _extract_incident_id(self, cluster: Any) -> str:
        """Safely extract incident_id from cluster object or dictionary."""
        if isinstance(cluster, IncidentCluster):
            return cluster.incident_id
        if isinstance(cluster, dict):
            inc_id = cluster.get("incident_id")
            if inc_id:
                return str(inc_id)
        if hasattr(cluster, "incident_id"):
            inc_id = getattr(cluster, "incident_id")
            if inc_id:
                return str(inc_id)
        return "inc_unknown"

    def _extract_cluster_events(self, cluster: Any) -> List[Any]:
        """Safely extract event collection from cluster object or dictionary."""
        if isinstance(cluster, IncidentCluster):
            return cluster.events or []
        if isinstance(cluster, dict):
            return cluster.get("events") or []
        if hasattr(cluster, "events"):
            return getattr(cluster, "events") or []
        return []

    def _normalize_event(self, raw_event: Any, incident_id: str) -> NormalizedEvent:
        """Extract and validate normalized event data without mutating input."""
        if isinstance(raw_event, NormalizedEvent):
            # Ensure timestamp is timezone-aware UTC
            ts = _normalize_timestamp(raw_event.timestamp, raw_event.event_id)
            if ts != raw_event.timestamp:
                return NormalizedEvent(
                    event_id=raw_event.event_id,
                    timestamp=ts,
                    source=raw_event.source,
                    component=raw_event.component,
                    severity=raw_event.severity,
                    description=raw_event.description,
                    metadata=dict(raw_event.metadata) if raw_event.metadata else {},
                )
            return raw_event

        # Use helper from correlation_engine for dictionaries or generic objects
        return extract_normalized_event(raw_event)


def build_timeline(
    clusters: Union[IncidentCluster, Iterable[IncidentCluster], None]
) -> UnifiedTimeline:
    """Convenience function to build a UnifiedTimeline from incident clusters.

    Args:
        clusters: A single IncidentCluster, an iterable of IncidentClusters, or None.

    Returns:
        UnifiedTimeline containing chronologically sorted TimelineEntry objects.
    """
    builder = TimelineBuilder()
    return builder.build(clusters)
