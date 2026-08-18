# ==========================================
# OWNED BY: MEMBER B (Correlation Engine)
# Responsibility: Correlate signals using temporal and component rules
# ==========================================

"""Core Correlation Engine and Re-Correlation for RootLens.

Correlates normalized observability signals (alerts, logs, metrics, deploys, complaints)
into incident clusters using:
1. Shared component/service identity
2. Temporal proximity (sliding time window)

Boundary rule:
- Events on the exact boundary (delta == time_window) are considered within the window (inclusive).

Supports dynamic re-correlation when new signals arrive mid-incident.
"""

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Union

from utils.schemas import (
    IncidentCluster,
    NormalizedEvent,
    NormalizedSignal,
    ReCorrelationResult,
    TimelineEntry,
    UnifiedTimeline,
)


# =====================================================================
# QUICK UTILITY FUNCTIONS FOR APP / DOWNSTREAM CONSUMERS
# =====================================================================

def get_signals_by_component(signals: List[NormalizedSignal], component: str) -> List[NormalizedSignal]:
    """Filter signals by component name."""
    return [s for s in signals if getattr(s, "component", None) == component]


def get_signals_in_window(
    signals: List[NormalizedSignal], anchor_time: datetime, window_minutes: int = 15
) -> List[NormalizedSignal]:
    """Filter signals within a given time window around an anchor time."""
    start = anchor_time - timedelta(minutes=window_minutes)
    end = anchor_time + timedelta(minutes=window_minutes)
    result = []
    for s in signals:
        ts = getattr(s, "parsed_timestamp", getattr(s, "timestamp", None))
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
        if ts and start <= ts <= end:
            result.append(s)
    return result


def correlate_incident_context(
    signals: List[NormalizedSignal], target_component: str = "payment-api"
) -> List[NormalizedSignal]:
    """Correlates signals related to a target incident for prompt context."""
    correlated = []
    deploys = [s for s in signals if getattr(s, "signal_type", getattr(s, "source", None)) == "deploy" or getattr(s, "source", None) == "deploys"]
    anchor_deploys = [d for d in deploys if getattr(d, "component", None) == target_component]

    if anchor_deploys:
        latest_deploy = max(
            anchor_deploys,
            key=lambda d: getattr(d, "parsed_timestamp", getattr(d, "timestamp", datetime.min)),
        )
        deploy_ts = getattr(latest_deploy, "parsed_timestamp", getattr(latest_deploy, "timestamp", None))
        if isinstance(deploy_ts, datetime):
            start_time = deploy_ts - timedelta(minutes=5)
            end_time = deploy_ts + timedelta(minutes=30)
            for s in signals:
                s_ts = getattr(s, "parsed_timestamp", getattr(s, "timestamp", None))
                if isinstance(s_ts, datetime) and start_time <= s_ts <= end_time:
                    correlated.append(s)
        else:
            correlated = [s for s in signals if getattr(s, "severity", "") in ["WARNING", "CRITICAL", "ERROR", "HIGH"]]
    else:
        correlated = [s for s in signals if getattr(s, "severity", "") in ["WARNING", "CRITICAL", "ERROR", "HIGH"]]

    return correlated


# =====================================================================
# CORE CORRELATION ENGINE (MEMBER B)
# =====================================================================

def _normalize_timestamp(ts: Any, event_id: str) -> datetime:
    """Validate and convert an input timestamp to a timezone-aware UTC datetime.

    Args:
        ts: Datetime object, ISO 8601 formatted string, or numeric Unix timestamp.
        event_id: The ID of the event for error context.

    Returns:
        Timezone-aware datetime in UTC.

    Raises:
        ValueError: If timestamp is missing, None, or cannot be parsed.
    """
    if ts is None:
        raise ValueError(f"Event '{event_id}' has missing/None timestamp.")

    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            # Naive datetime: assume UTC
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    if isinstance(ts, str):
        cleaned_ts = ts.strip()
        if not cleaned_ts:
            raise ValueError(f"Event '{event_id}' has empty timestamp string.")
        try:
            # Handle standard ISO formats, including Z suffix
            normalized_iso = cleaned_ts.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized_iso)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Event '{event_id}' has unparseable ISO timestamp '{ts}': {exc}") from exc

    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError(f"Event '{event_id}' has invalid Unix timestamp '{ts}': {exc}") from exc

    raise ValueError(f"Event '{event_id}' has unsupported timestamp type: {type(ts).__name__}")


def extract_normalized_event(event: Any) -> NormalizedEvent:
    """Extract and validate a NormalizedEvent from a dataclass, Pydantic model, object, dictionary, or timeline entry.

    Args:
        event: Instance of NormalizedEvent, NormalizedSignal, TimelineEntry, dict, or object.

    Returns:
        NormalizedEvent instance with UTC timezone-aware timestamp.

    Raises:
        TypeError: If event is not an object or dictionary.
        ValueError: If required fields are missing or invalid.
    """
    if isinstance(event, NormalizedEvent):
        # Ensure timestamp is timezone-aware UTC
        ts = _normalize_timestamp(event.timestamp, event.event_id)
        if not event.event_id:
            raise ValueError("Event is missing required field 'event_id'.")
        if not event.component:
            raise ValueError(f"Event '{event.event_id}' is missing required field 'component'.")
        if not event.source:
            raise ValueError(f"Event '{event.event_id}' is missing required field 'source'.")
        if not event.severity:
            raise ValueError(f"Event '{event.event_id}' is missing required field 'severity'.")
        if event.description is None:
            raise ValueError(f"Event '{event.event_id}' is missing required field 'description'.")

        if ts != event.timestamp:
            return NormalizedEvent(
                event_id=str(event.event_id),
                timestamp=ts,
                source=str(event.source),
                component=str(event.component),
                severity=str(event.severity),
                description=str(event.description),
                metadata=dict(event.metadata) if event.metadata else {},
            )
        return event

    if isinstance(event, NormalizedSignal):
        raw_ts = getattr(event, "parsed_timestamp", getattr(event, "timestamp", None))
        ts = _normalize_timestamp(raw_ts, event.signal_id)
        return NormalizedEvent(
            event_id=str(event.signal_id),
            timestamp=ts,
            source=str(event.source or event.signal_type),
            component=str(event.component),
            severity=str(event.severity),
            description=str(event.message),
            metadata=dict(event.metadata) if event.metadata else {},
        )

    if isinstance(event, TimelineEntry):
        ts = _normalize_timestamp(event.timestamp, event.event_id)
        return NormalizedEvent(
            event_id=str(event.event_id),
            timestamp=ts,
            source=str(event.source),
            component=str(event.component),
            severity=str(event.severity),
            description=str(event.description),
            metadata=dict(event.metadata) if event.metadata else {},
        )

    if isinstance(event, dict):
        event_id = event.get("event_id") or event.get("signal_id") or event.get("id")
        if event_id is None or str(event_id).strip() == "":
            raise ValueError(f"Dictionary event is missing 'event_id': {event}")

        event_id_str = str(event_id).strip()
        raw_ts = event.get("timestamp") or event.get("parsed_timestamp")
        ts = _normalize_timestamp(raw_ts, event_id_str)

        source = event.get("source") or event.get("signal_type")
        if source is None or str(source).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'source'.")

        component = event.get("component") or event.get("service")
        if component is None or str(component).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'component'.")

        severity = event.get("severity") or event.get("level")
        if severity is None or str(severity).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'severity'.")

        description = event.get("description") or event.get("message")
        if description is None:
            raise ValueError(f"Event '{event_id_str}' is missing required field 'description'.")

        metadata = event.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"Event '{event_id_str}' metadata must be a dictionary.")

        return NormalizedEvent(
            event_id=event_id_str,
            timestamp=ts,
            source=str(source).strip(),
            component=str(component).strip(),
            severity=str(severity).strip(),
            description=str(description),
            metadata=dict(metadata) if metadata else {},
        )

    # Generic object with attributes
    if hasattr(event, "event_id") or hasattr(event, "signal_id"):
        event_id = getattr(event, "event_id", getattr(event, "signal_id", None))
        if event_id is None or str(event_id).strip() == "":
            raise ValueError(f"Object event is missing 'event_id': {event}")

        event_id_str = str(event_id).strip()
        raw_ts = getattr(event, "parsed_timestamp", getattr(event, "timestamp", None))
        ts = _normalize_timestamp(raw_ts, event_id_str)

        source = getattr(event, "source", getattr(event, "signal_type", None))
        if source is None or str(source).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'source'.")

        component = getattr(event, "component", getattr(event, "service", None))
        if component is None or str(component).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'component'.")

        severity = getattr(event, "severity", getattr(event, "level", None))
        if severity is None or str(severity).strip() == "":
            raise ValueError(f"Event '{event_id_str}' is missing required field 'severity'.")

        description = getattr(event, "description", getattr(event, "message", None))
        if description is None:
            raise ValueError(f"Event '{event_id_str}' is missing required field 'description'.")

        metadata = getattr(event, "metadata", {})
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"Event '{event_id_str}' metadata must be a dictionary.")

        return NormalizedEvent(
            event_id=event_id_str,
            timestamp=ts,
            source=str(source).strip(),
            component=str(component).strip(),
            severity=str(severity).strip(),
            description=str(description),
            metadata=dict(metadata) if metadata else {},
        )

    raise TypeError(
        f"Event must be a NormalizedEvent, NormalizedSignal, dict, or compatible object. Got {type(event).__name__}"
    )


def _flatten_event_collection(
    items: Union[Iterable[Any], IncidentCluster, UnifiedTimeline, None]
) -> List[NormalizedEvent]:
    """Flatten heterogeneous inputs (list of events, IncidentClusters, UnifiedTimeline) into NormalizedEvents.

    Args:
        items: Collection of events, clusters, timeline, or None.

    Returns:
        List of NormalizedEvent objects.
    """
    if items is None:
        return []

    if isinstance(items, UnifiedTimeline):
        return [extract_normalized_event(entry) for entry in items.entries]

    if isinstance(items, IncidentCluster):
        return [extract_normalized_event(e) for e in items.events]

    if isinstance(items, (NormalizedEvent, TimelineEntry, NormalizedSignal)):
        return [extract_normalized_event(items)]

    if isinstance(items, dict) and ("event_id" in items or "signal_id" in items):
        return [extract_normalized_event(items)]

    try:
        iterator = iter(items)
    except TypeError:
        return [extract_normalized_event(items)]

    flattened: List[NormalizedEvent] = []
    for item in iterator:
        if isinstance(item, IncidentCluster):
            for e in item.events:
                flattened.append(extract_normalized_event(e))
        elif isinstance(item, UnifiedTimeline):
            for entry in item.entries:
                flattened.append(extract_normalized_event(entry))
        else:
            flattened.append(extract_normalized_event(item))

    return flattened


class CorrelationEngine:
    """Correlates normalized observability signals into incident clusters.

    Clustering rules:
    1. Events must share the same component identifier.
    2. An event is added to an active cluster if its timestamp is within the configured
       temporal window of the cluster's most recent event (sliding window chaining).
    3. Events exactly on the window boundary (delta == time_window) are included (inclusive).
    4. Events with time gap > time_window start a new separate incident cluster.
    """

    def __init__(
        self,
        time_window: Union[timedelta, int, float] = timedelta(minutes=10),
        time_window_seconds: Optional[float] = None,
    ) -> None:
        """Initialize the CorrelationEngine with a configurable time window.

        Args:
            time_window: Max time delta between consecutive events in a cluster.
                Can be a timedelta or numeric seconds (default: 10 minutes).
            time_window_seconds: Optional explicit duration in seconds.

        Raises:
            ValueError: If the resulting time window is not strictly positive.
        """
        if time_window_seconds is not None:
            if time_window_seconds <= 0:
                raise ValueError("time_window_seconds must be positive.")
            self.time_window = timedelta(seconds=time_window_seconds)
        elif isinstance(time_window, timedelta):
            if time_window <= timedelta(0):
                raise ValueError("time_window must be a positive timedelta.")
            self.time_window = time_window
        elif isinstance(time_window, (int, float)):
            if time_window <= 0:
                raise ValueError("Numeric time_window must be positive seconds.")
            self.time_window = timedelta(seconds=float(time_window))
        else:
            raise TypeError(
                f"time_window must be timedelta or numeric seconds. Got {type(time_window).__name__}"
            )

    def correlate(
        self, events: Iterable[Union[NormalizedEvent, Dict[str, Any], Any]]
    ) -> List[IncidentCluster]:
        """Group normalized events into incident clusters based on component and time window.

        Args:
            events: Iterable of normalized event objects, dictionaries, or dataclasses.

        Returns:
            List of IncidentCluster objects sorted deterministically by start_time,
            component, and incident_id.
        """
        if events is None:
            return []

        # 1. Normalize and validate all events
        normalized_list: List[NormalizedEvent] = [
            extract_normalized_event(e) for e in events
        ]

        if not normalized_list:
            return []

        # 2. Sort all events deterministically (chronological primary, event_id secondary)
        sorted_events = sorted(normalized_list, key=lambda e: (e.timestamp, e.event_id))

        # 3. Group sorted events by component
        by_component: Dict[str, List[NormalizedEvent]] = defaultdict(list)
        for ev in sorted_events:
            by_component[ev.component].append(ev)

        # 4. Perform temporal clustering per component
        clusters: List[IncidentCluster] = []

        # Sort component keys to ensure deterministic processing order
        for component in sorted(by_component.keys()):
            comp_events = by_component[component]
            comp_clusters = self._cluster_component_events(component, comp_events)
            clusters.extend(comp_clusters)

        # 5. Sort final clusters deterministically by (start_time, component, incident_id)
        clusters.sort(key=lambda c: (c.start_time, c.component, c.incident_id))

        return clusters

    def re_correlate(
        self,
        existing_events: Union[Iterable[Any], IncidentCluster, UnifiedTimeline, None],
        new_events: Union[Iterable[Any], Any, None],
    ) -> ReCorrelationResult:
        """Re-correlate existing events with newly arrived signals.

        Merges existing and new events, runs identical component + temporal correlation
        rules, and constructs both updated IncidentClusters and an updated UnifiedTimeline.

        Duplicate Handling:
        - If an event_id is present in both existing_events and new_events, the existing
          event record is preserved and the duplicate is skipped deterministically.
        - If new_events contains duplicate event_ids among themselves, the first instance
          is preserved.

        Args:
            existing_events: Previously known events (NormalizedEvents, clusters, timeline, or dicts).
            new_events: Newly arrived signal(s) (single event, list of events, or dicts).

        Returns:
            ReCorrelationResult containing updated clusters, updated timeline, total_events,
            and new_events_count. Supports unpacking: `clusters, timeline = result`.
        """
        # Late import to prevent circular dependency
        from correlation.timeline_builder import TimelineBuilder

        # 1. Flatten and normalize existing events
        existing_flat = _flatten_event_collection(existing_events)

        # 2. Flatten and normalize new events
        new_flat = _flatten_event_collection(new_events)

        # 3. Combine without mutating inputs; deduplicate by event_id
        combined_events: List[NormalizedEvent] = []
        seen_event_ids: Set[str] = set()

        for event in existing_flat:
            if event.event_id not in seen_event_ids:
                seen_event_ids.add(event.event_id)
                combined_events.append(event)

        new_accepted_count = 0
        for event in new_flat:
            if event.event_id not in seen_event_ids:
                seen_event_ids.add(event.event_id)
                combined_events.append(event)
                new_accepted_count += 1

        # 4. Correlate using identical deterministic rules
        updated_clusters = self.correlate(combined_events)

        # 5. Build updated unified timeline
        timeline_builder = TimelineBuilder()
        updated_timeline = timeline_builder.build(updated_clusters)

        return ReCorrelationResult(
            clusters=updated_clusters,
            timeline=updated_timeline,
            total_events=len(combined_events),
            new_events_count=new_accepted_count,
        )

    def _cluster_component_events(
        self, component: str, sorted_comp_events: Sequence[NormalizedEvent]
    ) -> List[IncidentCluster]:
        """Perform temporal clustering on pre-sorted events for a single component.

        Args:
            component: Component name.
            sorted_comp_events: Chronologically sorted list of events for this component.

        Returns:
            List of IncidentCluster objects for this component.
        """
        if not sorted_comp_events:
            return []

        component_clusters: List[IncidentCluster] = []
        current_cluster_events: List[NormalizedEvent] = []
        cluster_index = 1

        for event in sorted_comp_events:
            if not current_cluster_events:
                current_cluster_events.append(event)
            else:
                last_event_time = current_cluster_events[-1].timestamp
                delta = event.timestamp - last_event_time

                # Boundary rule: delta <= self.time_window is inclusive
                if delta <= self.time_window:
                    current_cluster_events.append(event)
                else:
                    # Finalize current cluster
                    cluster = self._build_cluster(
                        component=component,
                        cluster_events=current_cluster_events,
                        sequence_num=cluster_index,
                    )
                    component_clusters.append(cluster)
                    cluster_index += 1

                    # Start new cluster with current event
                    current_cluster_events = [event]

        # Finalize trailing cluster
        if current_cluster_events:
            cluster = self._build_cluster(
                component=component,
                cluster_events=current_cluster_events,
                sequence_num=cluster_index,
            )
            component_clusters.append(cluster)

        return component_clusters

    def _build_cluster(
        self, component: str, cluster_events: List[NormalizedEvent], sequence_num: int
    ) -> IncidentCluster:
        """Construct an IncidentCluster with deterministic identifier and metadata.

        Args:
            component: Component name.
            cluster_events: Non-empty list of events belonging to this cluster.
            sequence_num: Sequential index for this component's clusters in current run.

        Returns:
            IncidentCluster instance.
        """
        start_time = cluster_events[0].timestamp
        end_time = cluster_events[-1].timestamp
        event_ids = [e.event_id for e in cluster_events]

        # Clean component slug for ID readability
        comp_slug = (
            component.lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
            .replace(":", "_")
        )
        time_slug = start_time.strftime("%Y%m%d_%H%M%S")
        incident_id = f"inc_{comp_slug}_{time_slug}_{sequence_num:02d}"

        return IncidentCluster(
            incident_id=incident_id,
            component=component,
            start_time=start_time,
            end_time=end_time,
            event_ids=event_ids,
            events=list(cluster_events),
            event_count=len(cluster_events),
        )


def correlate_events(
    events: Iterable[Union[NormalizedEvent, Dict[str, Any], Any]],
    time_window: Union[timedelta, int, float] = timedelta(minutes=10),
) -> List[IncidentCluster]:
    """Convenience function to correlate normalized events into incident clusters.

    Args:
        events: Collection of normalized events or event dictionaries.
        time_window: Temporal correlation window (default: 10 minutes).

    Returns:
        List of IncidentCluster instances.
    """
    engine = CorrelationEngine(time_window=time_window)
    return engine.correlate(events)


def re_correlate(
    existing_events: Union[Iterable[Any], IncidentCluster, UnifiedTimeline, None],
    new_events: Union[Iterable[Any], Any, None],
    time_window: Union[timedelta, int, float] = timedelta(minutes=10),
) -> ReCorrelationResult:
    """Convenience function to re-correlate existing events with newly arrived signals.

    Args:
        existing_events: Previously known events, clusters, or timeline.
        new_events: New signal or collection of signals.
        time_window: Temporal correlation window (default: 10 minutes).

    Returns:
        ReCorrelationResult with updated clusters and timeline.
    """
    engine = CorrelationEngine(time_window=time_window)
    return engine.re_correlate(existing_events, new_events)
