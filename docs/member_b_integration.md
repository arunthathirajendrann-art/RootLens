# Member B Integration & Public Contract Specification

This document details the data contracts, pipeline architecture, public APIs, and integration handoff instructions for **Member B** (Correlation Engine, Unified Incident Timeline, Dynamic Re-correlation).

---

## 1. Upstream Contract: What Member B Receives from Member A (Ingestion)

Member B consumes normalized observability signals from Member A. Events can be passed either as `NormalizedEvent` dataclass instances or as standard dictionaries matching the schema.

### Canonical `NormalizedEvent` Schema ([utils/schemas.py](file:///c:/Users/abinaya/OneDrive/Desktop/RootLens/utils/schemas.py))

```python
@dataclass
class NormalizedEvent:
    event_id: str                      # Unique identifier (string / UUID)
    timestamp: datetime                # Timezone-aware UTC datetime
    source: str                        # 'alerts', 'logs', 'metrics', 'deploys', 'complaints'
    component: str                     # Target service or component name (e.g. 'auth-service')
    severity: str                      # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'
    description: str                   # Human-readable summary or log payload
    metadata: Dict[str, Any] = field(default_factory=dict) # Key-value context
```

### Timestamp Requirements:
- **Canonical Representation**: Timezone-aware UTC `datetime.datetime` object.
- **String Support**: ISO 8601 strings (e.g. `"2026-08-18T10:00:00Z"` or `"2026-08-18T10:00:00+00:00"`) are automatically parsed and normalized to UTC.
- **Numeric Support**: Unix epoch timestamps (seconds as int/float) are accepted and converted to UTC.

---

## 2. Pipeline Stage 1: How Events Enter `CorrelationEngine`

Events are grouped into incident clusters using a deterministic two-factor algorithm:
1. **Shared Component Identity**: Signals from different services are never merged, isolating blast radii.
2. **Temporal Proximity (Sliding Window)**: Within a component, an event is grouped into the active incident cluster if its timestamp is within the configured window of the cluster's most recent event ($\Delta t \le \text{time\_window}$).

### Boundary Rule:
- The time window is **inclusive** ($\Delta t \le \text{window}$).
- Default window: **10 minutes** (`datetime.timedelta(minutes=10)`).

---

## 3. Data Structure: `IncidentCluster`

Output produced by `CorrelationEngine.correlate(...)`:

```python
@dataclass
class IncidentCluster:
    incident_id: str                   # e.g. 'inc_auth_service_20260818_100000_01'
    component: str                     # Affected service name
    start_time: datetime               # Earliest event timestamp in cluster (UTC)
    end_time: datetime                 # Latest event timestamp in cluster (UTC)
    event_ids: List[str]               # Ordered list of contained event IDs
    events: List[NormalizedEvent]      # Ordered list of normalized event objects
    event_count: int                   # Total count of events in cluster
```

---

## 4. Pipeline Stage 2: How `UnifiedTimeline` is Generated

`TimelineBuilder` takes one or more `IncidentCluster` objects and constructs a global chronological timeline:

```
[IncidentCluster 1, IncidentCluster 2, ...]
                    │
                    ▼
Flatten events & bind incident_id
                    │
                    ▼
Deterministic Sort Key: (timestamp, event_id, incident_id)
                    │
                    ▼
Deduplicate by event_id (preserve unique events)
                    │
                    ▼
             UnifiedTimeline
```

### `TimelineEntry` ([utils/schemas.py](file:///c:/Users/abinaya/OneDrive/Desktop/RootLens/utils/schemas.py))
```python
@dataclass
class TimelineEntry:
    event_id: str                      # Event ID
    incident_id: str                   # Associated IncidentCluster ID
    timestamp: datetime                # Event timestamp (UTC)
    source: str                        # alerts, logs, metrics, deploys, complaints
    component: str                     # Service name
    severity: str                      # Severity level
    description: str                   # Message / description
    metadata: Dict[str, Any]           # Deep-copied contextual attributes
```

### `UnifiedTimeline` ([utils/schemas.py](file:///c:/Users/abinaya/OneDrive/Desktop/RootLens/utils/schemas.py))
```python
@dataclass
class UnifiedTimeline:
    entries: List[TimelineEntry]       # Chronologically sorted entries
    start_time: Optional[datetime]     # Earliest event timestamp across all incidents
    end_time: Optional[datetime]       # Latest event timestamp across all incidents
    event_count: int                   # Total entry count
    incident_ids: List[str]            # Unique incident IDs in order of first appearance
    components: List[str]              # Unique components in order of first appearance
```

---

## 5. Pipeline Stage 3: Dynamic Re-Correlation on New Signals

When new observability evidence arrives mid-incident (e.g. late log, new deployment, customer complaint):

```python
from correlation.correlation_engine import CorrelationEngine, re_correlate

# Option A: Functional API (supports tuple unpacking)
updated_clusters, updated_timeline = re_correlate(
    existing_events=current_timeline,  # or current_clusters or raw events
    new_events=new_incoming_signals,    # single event or list
)

# Option B: Object-Oriented API
engine = CorrelationEngine(time_window_seconds=600)
result = engine.re_correlate(existing_events=current_timeline, new_events=new_signal)
# result.clusters -> List[IncidentCluster]
# result.timeline -> UnifiedTimeline
```

---

## 6. Downstream Handoff: Instructions for Member C (Hypothesis Engine)

Member C can consume the `UnifiedTimeline` directly as the structured chronological context for LLM prompts:

```python
from correlation.correlation_engine import correlate_events
from correlation.timeline_builder import build_timeline

# 1. Correlate normalized events from Member A
clusters = correlate_events(normalized_events)

# 2. Build the unified timeline
timeline = build_timeline(clusters)

# 3. Format timeline for LLM prompt context:
for entry in timeline.entries:
    print(f"[{entry.timestamp.isoformat()}] [{entry.component}] ({entry.source}/{entry.severity}): {entry.description}")
```

---

## 7. Downstream Handoff: Instructions for Member D (Recovery Planner & UI)

Member D can render `timeline.entries` directly into Streamlit or UI timeline components:
- `entry.timestamp`: Display time
- `entry.component`: Service tag / badge
- `entry.source`: Signal type icon (alert 🚨, log 📋, metric 📈, deploy 🚀, complaint 👤)
- `entry.severity`: Color coding (CRITICAL: Red, HIGH: Orange, INFO: Blue)
- `entry.description`: Event message

---

## 8. Summary of Public Member B APIs

| Module | Function / Class | Description |
| :--- | :--- | :--- |
| `correlation.correlation_engine` | `CorrelationEngine(time_window=...)` | Core engine class with `.correlate()` and `.re_correlate()` methods. |
| `correlation.correlation_engine` | `correlate_events(events, time_window=...)` | Functional entrypoint to correlate events into `List[IncidentCluster]`. |
| `correlation.correlation_engine` | `re_correlate(existing, new, time_window=...)` | Functional entrypoint to re-correlate and return `ReCorrelationResult`. |
| `correlation.correlation_engine` | `extract_normalized_event(event)` | Safe validator & normalizer for raw dicts and objects. |
| `correlation.timeline_builder` | `TimelineBuilder()` | Builder class with `.build(clusters)` method. |
| `correlation.timeline_builder` | `build_timeline(clusters)` | Functional entrypoint to build `UnifiedTimeline`. |

---

## 9. Known Assumptions & Invariants

1. **No Causal / Root-Cause Claims**: Member B strictly provides evidence organization based on time and component identity. Causal reasoning is delegated to Member C.
2. **Immutable Input Handling**: Input event and cluster objects are never mutated.
3. **Deterministic Deduplication**: If duplicate `event_id`s are passed, the first occurrence is preserved.
