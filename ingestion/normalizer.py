"""RootLens Event Normalization Layer (Member A).

Transforms raw telemetry, log records, metrics rows, customer tickets,
and deployment records into uniform, deterministic CanonicalEvent objects.

Architecture Rule:
This module is strictly evidence-neutral. It standardizes signal formats
without inferring root causes, assigning blame, or filtering hypotheses.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from utils.schemas import CanonicalEvent, CanonicalSeverity, CanonicalSource
from utils.timestamp import format_iso_utc
from .loaders import (
    load_alerts,
    load_audit_config_changes,
    load_complaints,
    load_deployments,
    load_gc_profiler,
    load_initial_incident_signals,
    load_late_evidence,
    load_logs,
    load_metrics,
)


def _clean_id_suffix(raw_id: str) -> str:
    """Strip common prefixes to build uniform deterministic event IDs."""
    return re.sub(r"^(ALT|LOG|DEP|TICK|CS|CFG|GC-TRC|GC)-", "", str(raw_id).strip())


# =====================================================================
# INDIVIDUAL NORMALIZERS
# =====================================================================

def normalize_alerts(raw_alerts: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize raw monitoring alerts into canonical events."""
    if raw_alerts is None:
        raw_alerts = load_alerts()

    normalized: List[CanonicalEvent] = []
    for raw in raw_alerts:
        suffix = _clean_id_suffix(raw.get("alert_id", "0"))
        event_id = f"EVT-ALT-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        # Severity mapping
        raw_sev = str(raw.get("severity", "INFO")).upper()
        if raw_sev in ("P1", "CRITICAL"):
            sev = CanonicalSeverity.CRITICAL.value
        elif raw_sev in ("P2", "HIGH"):
            sev = CanonicalSeverity.HIGH.value
        elif raw_sev == "MEDIUM":
            sev = CanonicalSeverity.MEDIUM.value
        elif raw_sev == "LOW":
            sev = CanonicalSeverity.LOW.value
        else:
            sev = CanonicalSeverity.INFO.value

        # Event type classification
        alert_name = raw.get("alert_name", "")
        if "Latency" in alert_name:
            event_type = "LATENCY_ALERT"
        elif "5xx" in alert_name or "Error" in alert_name:
            event_type = "ERROR_RATE_ALERT"
        elif "Throughput" in alert_name:
            event_type = "THROUGHPUT_ALERT"
        elif "Heartbeat" in alert_name or "Sync" in alert_name:
            event_type = "SERVICE_HEALTH_CHECK"
        else:
            event_type = "ALERT_TRIGGERED"

        description = raw.get("description") or f"Alert {alert_name} status: {raw.get('status')}"

        metadata = {
            "alert_id": raw.get("alert_id"),
            "alert_name": alert_name,
            "metric_name": raw.get("metric_name"),
            "threshold": raw.get("threshold"),
            "observed_value": raw.get("observed_value"),
            "status": raw.get("status"),
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.ALERTS.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


def normalize_logs(raw_logs: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize raw application log messages into canonical events."""
    if raw_logs is None:
        raw_logs = load_logs()

    normalized: List[CanonicalEvent] = []
    for raw in raw_logs:
        suffix = _clean_id_suffix(raw.get("log_id", "0"))
        event_id = f"EVT-LOG-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        # Severity mapping
        raw_level = str(raw.get("level", "INFO")).upper()
        if raw_level in ("FATAL", "PANIC"):
            sev = CanonicalSeverity.CRITICAL.value
        elif raw_level == "ERROR":
            sev = CanonicalSeverity.HIGH.value
        elif raw_level in ("WARN", "WARNING"):
            sev = CanonicalSeverity.MEDIUM.value
        elif raw_level == "LOW":
            sev = CanonicalSeverity.LOW.value
        else:
            sev = CanonicalSeverity.INFO.value

        # Event type classification
        msg = raw.get("message", "")
        logger = raw.get("logger", "")
        if "Dynamic configuration reloaded" in msg or "configuration reloaded" in msg:
            event_type = "CONFIG_RELOAD"
        elif "max capacity" in msg.lower() or "cache item count" in msg.lower():
            event_type = "CACHE_EXPANSION"
        elif "Heap utilization crossed" in msg or "Memory" in logger:
            event_type = "MEMORY_PRESSURE"
        elif "GC pause detected" in msg or "Full GC" in msg or "GC" in logger:
            event_type = "GC_PAUSE"
        elif "thread pool" in msg.lower() or "active threads" in msg.lower():
            event_type = "THREAD_STARVATION"
        elif "Request timeout" in msg or "504" in msg or "Gateway Timeout" in msg:
            event_type = "REQUEST_TIMEOUT"
        elif "Internal Server Error 500" in msg or "500" in msg:
            event_type = "SERVER_ERROR_5XX"
        elif "initialization completed" in msg:
            event_type = "SERVICE_STARTUP"
        elif "Routine catalog" in msg or "reconciliation" in msg:
            event_type = "ROUTINE_TASK"
        else:
            event_type = "LOG_EVENT"

        metadata = {
            "log_id": raw.get("log_id"),
            "level": raw.get("level"),
            "logger": logger,
            **raw.get("metadata", {}),
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.LOGS.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=msg,
                metadata=metadata,
            )
        )
    return normalized


def normalize_metrics(raw_metrics: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize raw metric time-series rows into canonical events."""
    if raw_metrics is None:
        raw_metrics = load_metrics()

    normalized: List[CanonicalEvent] = []
    for raw in raw_metrics:
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        # Build deterministic metric event ID based on service and timestamp
        clean_ts = ts.replace("-", "").replace(":", "")
        event_id = f"EVT-MET-{service}-{clean_ts}"

        # Parse numeric metric values
        p50 = float(raw.get("p50_latency_ms", 0.0))
        p95 = float(raw.get("p95_latency_ms", 0.0))
        p99 = float(raw.get("p99_latency_ms", 0.0))
        err_pct = float(raw.get("error_rate_pct", 0.0))
        cpu_pct = float(raw.get("cpu_utilization_pct", 0.0))
        mem_pct = float(raw.get("memory_utilization_pct", 0.0))
        gc_pause = float(raw.get("gc_pause_ms", 0.0))

        # Operational severity derivation
        if p99 >= 3000.0 or err_pct >= 10.0 or gc_pause >= 3000.0:
            sev = CanonicalSeverity.CRITICAL.value
        elif p99 >= 1000.0 or err_pct >= 5.0 or mem_pct >= 85.0 or gc_pause >= 1500.0:
            sev = CanonicalSeverity.HIGH.value
        elif p99 >= 300.0 or err_pct >= 1.0 or mem_pct >= 70.0 or gc_pause >= 500.0:
            sev = CanonicalSeverity.MEDIUM.value
        elif p99 >= 150.0 or mem_pct >= 55.0 or gc_pause >= 50.0:
            sev = CanonicalSeverity.LOW.value
        else:
            sev = CanonicalSeverity.INFO.value

        # Event type classification
        if p99 >= 1000.0:
            event_type = "LATENCY_SPIKE"
            description = f"{service} p99 latency elevated to {p99:.0f}ms (error rate: {err_pct:.1f}%)"
        elif err_pct >= 5.0:
            event_type = "ERROR_RATE_SPIKE"
            description = f"{service} error rate elevated to {err_pct:.1f}% (p99: {p99:.0f}ms)"
        elif mem_pct >= 75.0:
            event_type = "MEMORY_PRESSURE"
            description = f"{service} memory utilization reached {mem_pct:.1f}% (GC pause: {gc_pause:.0f}ms)"
        elif gc_pause >= 500.0:
            event_type = "GC_PAUSE"
            description = f"{service} GC pause duration elevated to {gc_pause:.0f}ms"
        elif p99 <= 150.0 and err_pct <= 0.05:
            event_type = "SERVICE_HEALTHY"
            description = f"{service} nominal telemetry (p99: {p99:.0f}ms, error rate: {err_pct:.2f}%)"
        else:
            event_type = "METRIC_OBSERVATION"
            description = f"{service} metric sample: p99={p99:.0f}ms, mem={mem_pct:.1f}%"

        metadata = {
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "error_rate_pct": err_pct,
            "cpu_utilization_pct": cpu_pct,
            "memory_utilization_pct": mem_pct,
            "gc_pause_ms": gc_pause,
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.METRICS.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


def normalize_complaints(raw_complaints: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize raw customer support tickets into canonical events."""
    if raw_complaints is None:
        raw_complaints = load_complaints()

    normalized: List[CanonicalEvent] = []
    for raw in raw_complaints:
        suffix = _clean_id_suffix(raw.get("ticket_id", "0"))
        event_id = f"EVT-CMP-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        
        # Associate clearly with checkout-service given checkout customer impact
        service = raw.get("service", "checkout-service")

        # Severity mapping
        raw_prio = str(raw.get("priority", "HIGH")).upper()
        if raw_prio == "CRITICAL":
            sev = CanonicalSeverity.CRITICAL.value
        elif raw_prio in ("URGENT", "HIGH"):
            sev = CanonicalSeverity.HIGH.value
        elif raw_prio == "MEDIUM":
            sev = CanonicalSeverity.MEDIUM.value
        elif raw_prio == "LOW":
            sev = CanonicalSeverity.LOW.value
        else:
            sev = CanonicalSeverity.INFO.value

        event_type = "CUSTOMER_COMPLAINT"
        channel = raw.get("channel", "support")
        subj = raw.get("subject", "Checkout issue")
        body = raw.get("description", "")
        description = f"Customer complaint ({channel}): {subj} - {body}"

        metadata = {
            "ticket_id": raw.get("ticket_id"),
            "customer_id": raw.get("customer_id"),
            "channel": channel,
            "platform": raw.get("platform"),
            "subject": subj,
            "reported_text": body,
            "priority": raw.get("priority"),
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.COMPLAINTS.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


def normalize_deployments(raw_deploys: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize raw deployment records into canonical events."""
    if raw_deploys is None:
        raw_deploys = load_deployments()

    normalized: List[CanonicalEvent] = []
    for raw in raw_deploys:
        suffix = _clean_id_suffix(raw.get("deploy_id", "0"))
        event_id = f"EVT-DEP-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        status = raw.get("status", "SUCCESS")
        if status == "SUCCESS":
            sev = CanonicalSeverity.INFO.value
            event_type = "DEPLOY_SUCCESS"
        else:
            sev = CanonicalSeverity.HIGH.value
            event_type = "DEPLOY_FAILURE"

        ver = raw.get("version", "unknown")
        description = f"{service} deployment {ver} completed ({status})"

        metadata = {
            "deploy_id": raw.get("deploy_id"),
            "version": ver,
            "status": status,
            "environment": raw.get("environment"),
            "deployed_by": raw.get("deployed_by"),
            "commit_hash": raw.get("commit_hash"),
            "commit_message": raw.get("commit_message"),
            "canary_passed": raw.get("canary_passed"),
            "smoke_test_results": raw.get("smoke_test_results"),
            "notes": raw.get("notes"),
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.DEPLOYS.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


# =====================================================================
# LATE-ARRIVING EVIDENCE NORMALIZERS
# =====================================================================

def normalize_audit_config_changes(
    raw_configs: Optional[List[Dict[str, Any]]] = None,
) -> List[CanonicalEvent]:
    """Normalize late-arriving centralized config change audit logs."""
    if raw_configs is None:
        raw_configs = load_audit_config_changes()

    normalized: List[CanonicalEvent] = []
    for raw in raw_configs:
        suffix = _clean_id_suffix(raw.get("change_id", "0"))
        event_id = f"EVT-CFG-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        # Dynamic configuration changes are operational actions (MEDIUM severity)
        sev = CanonicalSeverity.MEDIUM.value
        event_type = "CONFIG_CHANGE"
        
        change_id = raw.get("change_id", "")
        param = raw.get("parameter", "")
        reason = raw.get("reason", "")
        description = f"Dynamic configuration update {change_id} applied to {service}: {reason or param}"

        metadata = {
            "change_id": change_id,
            "parameter": param,
            "previous_value": raw.get("previous_value"),
            "new_value": raw.get("new_value"),
            "changed_by": raw.get("changed_by"),
            "environment": raw.get("environment"),
            "audit_source": raw.get("audit_source"),
            "restart_required": raw.get("restart_required", False),
            "reason": reason,
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.CONFIG.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


def normalize_gc_profiler(raw_gc: Optional[List[Dict[str, Any]]] = None) -> List[CanonicalEvent]:
    """Normalize late-arriving JVM GC profiler runtime traces."""
    if raw_gc is None:
        raw_gc = load_gc_profiler()

    normalized: List[CanonicalEvent] = []
    for raw in raw_gc:
        suffix = _clean_id_suffix(raw.get("trace_id", "0"))
        event_id = f"EVT-GC-{suffix}"
        ts = format_iso_utc(raw["timestamp"])
        service = raw.get("service", "unknown-service")
        
        gc_pause = float(raw.get("gc_pause_ms", 0.0))
        heap_pct = float(raw.get("heap_utilization_pct", 0.0))
        gc_type = raw.get("gc_type", "GC")

        if gc_pause >= 3000.0 or heap_pct >= 90.0:
            sev = CanonicalSeverity.CRITICAL.value
            event_type = "GC_MAJOR_PAUSE"
        elif gc_pause >= 1000.0 or heap_pct >= 80.0:
            sev = CanonicalSeverity.HIGH.value
            event_type = "GC_MAJOR_PAUSE"
        elif gc_pause >= 200.0:
            sev = CanonicalSeverity.MEDIUM.value
            event_type = "GC_ALLOCATION_PRESSURE"
        else:
            sev = CanonicalSeverity.INFO.value
            event_type = "GC_OBSERVATION"

        obs = raw.get("profiler_observation", "")
        description = f"JVM GC telemetry for {service}: {gc_type} took {gc_pause:.0f}ms (heap: {heap_pct:.1f}%). {obs}".strip()

        metadata = {
            "trace_id": raw.get("trace_id"),
            "gc_type": gc_type,
            "gc_pause_ms": gc_pause,
            "heap_used_mb": raw.get("heap_used_mb"),
            "heap_max_mb": raw.get("heap_max_mb"),
            "heap_utilization_pct": heap_pct,
            "allocation_rate_mb_s": raw.get("allocation_rate_mb_s"),
            "stalled_worker_threads": raw.get("stalled_worker_threads"),
            "profiler_observation": obs,
        }

        normalized.append(
            CanonicalEvent(
                event_id=event_id,
                timestamp=ts,
                source=CanonicalSource.GC_PROFILER.value,
                service=service,
                severity=sev,
                event_type=event_type,
                description=description,
                metadata=metadata,
            )
        )
    return normalized


# =====================================================================
# AGGREGATION & PIPELINE ENTRYPOINTS
# =====================================================================

def normalize_initial_incident_signals(
    data_dir: Optional[Union[Path, str]] = None,
) -> List[CanonicalEvent]:
    """Normalize and combine all initial operational signals.

    Loads from alerts, logs, metrics, complaints, and deploys.
    Excludes late-arriving evidence and historical incidents.
    Returns events sorted chronologically by ISO-8601 timestamp.
    """
    raw_signals = load_initial_incident_signals(data_dir)

    all_events: List[CanonicalEvent] = []
    all_events.extend(normalize_alerts(raw_signals["alerts"]))
    all_events.extend(normalize_logs(raw_signals["logs"]))
    all_events.extend(normalize_metrics(raw_signals["metrics"]))
    all_events.extend(normalize_complaints(raw_signals["complaints"]))
    all_events.extend(normalize_deployments(raw_signals["deployments"]))

    # Sort chronologically by timestamp
    all_events.sort(key=lambda evt: evt["timestamp"])
    return all_events


def normalize_late_evidence(
    data_dir: Optional[Union[Path, str]] = None,
) -> List[CanonicalEvent]:
    """Normalize and combine late-arriving demo evidence.

    Loads from audit_config_changes and gc_profiler.
    Returns events sorted chronologically by ISO-8601 timestamp.
    """
    raw_late = load_late_evidence(data_dir)

    late_events: List[CanonicalEvent] = []
    late_events.extend(normalize_audit_config_changes(raw_late["audit_config_changes"]))
    late_events.extend(normalize_gc_profiler(raw_late["gc_profiler"]))

    # Sort chronologically by timestamp
    late_events.sort(key=lambda evt: evt["timestamp"])
    return late_events
