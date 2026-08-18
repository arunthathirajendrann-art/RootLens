"""RootLens Ingestion Loaders Module (Member A).

Responsible for loading raw telemetry, event logs, metrics time series,
customer feedback, deployment histories, and late-arriving demo evidence
from source files with basic schema validation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _validate_path(path: Union[Path, str], file_desc: str) -> Path:
    """Validate that a path exists and points to a file."""
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Missing {file_desc} file at path: {p}")
    if not p.is_file():
        raise ValueError(f"Path for {file_desc} is not a valid file: {p}")
    return p


def _read_json_list(
    file_path: Path,
    expected_name: str,
    required_fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Read a JSON file, validate list structure, and check required fields."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError(f"Malformed JSON in {expected_name} ({file_path}): {err}") from err
    except Exception as err:
        raise RuntimeError(f"Error reading {expected_name} ({file_path}): {err}") from err

    if not isinstance(data, list):
        raise ValueError(
            f"Expected top-level JSON array in {expected_name} ({file_path}), got {type(data).__name__}"
        )

    if required_fields:
        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                raise ValueError(
                    f"Record #{idx} in {expected_name} is not a valid JSON object"
                )
            missing = [f for f in required_fields if f not in record]
            if missing:
                raise ValueError(
                    f"Record #{idx} in {expected_name} is missing required fields: {missing}"
                )

    return data


def _read_csv_records(
    file_path: Path,
    expected_name: str,
    required_columns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Read a CSV file into a list of raw string dictionaries with column validation."""
    records: List[Dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"Empty or missing header in CSV file {expected_name} ({file_path})")

            if required_columns:
                header_set = set(reader.fieldnames)
                missing = [col for col in required_columns if col not in header_set]
                if missing:
                    raise ValueError(
                        f"CSV {expected_name} ({file_path}) is missing required columns: {missing}"
                    )

            for idx, row in enumerate(reader):
                if not row.get("timestamp"):
                    raise ValueError(
                        f"Row #{idx} in CSV {expected_name} has empty timestamp"
                    )
                records.append(dict(row))
    except (csv.Error, UnicodeDecodeError) as err:
        raise ValueError(f"Failed to parse CSV in {expected_name} ({file_path}): {err}") from err

    return records


# =====================================================================
# INDIVIDUAL RAW LOADERS
# =====================================================================

def load_alerts(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load raw monitoring alerts from alerts.json."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "alerts.json", "alerts")
    return _read_json_list(
        path,
        expected_name="alerts.json",
        required_fields=["alert_id", "timestamp", "service", "severity", "status"],
    )


def load_logs(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load raw application log events from logs.json."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "logs.json", "logs")
    return _read_json_list(
        path,
        expected_name="logs.json",
        required_fields=["log_id", "timestamp", "service", "level", "message"],
    )


def load_metrics(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load raw time-series metric samples from metrics.csv."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "metrics.csv", "metrics")
    return _read_csv_records(
        path,
        expected_name="metrics.csv",
        required_columns=[
            "timestamp",
            "service",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "error_rate_pct",
            "cpu_utilization_pct",
            "memory_utilization_pct",
            "gc_pause_ms",
        ],
    )


def load_complaints(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load raw customer complaints/tickets from complaints.json."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "complaints.json", "complaints")
    return _read_json_list(
        path,
        expected_name="complaints.json",
        required_fields=["ticket_id", "timestamp", "channel", "description"],
    )


def load_deployments(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load raw deployment records from deploys.json."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "deploys.json", "deploys")
    return _read_json_list(
        path,
        expected_name="deploys.json",
        required_fields=["deploy_id", "timestamp", "service", "version", "status"],
    )


def load_past_incidents(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load historical incident memory context from past_incidents.json."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "past_incidents.json", "past_incidents")
    return _read_json_list(
        path,
        expected_name="past_incidents.json",
        required_fields=["incident_id", "title", "service", "root_cause", "resolution"],
    )


# =====================================================================
# LATE-ARRIVING EVIDENCE LOADERS (Separately Injected During Demo)
# =====================================================================

def load_audit_config_changes(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load late-arriving centralized config change audit logs."""
    path = _validate_path(
        file_path or DEFAULT_DATA_DIR / "audit_config_changes.json", "audit_config_changes"
    )
    return _read_json_list(
        path,
        expected_name="audit_config_changes.json",
        required_fields=["change_id", "timestamp", "service", "parameter"],
    )


def load_gc_profiler(file_path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Load late-arriving JVM GC profiler runtime traces."""
    path = _validate_path(file_path or DEFAULT_DATA_DIR / "gc_profiler.json", "gc_profiler")
    return _read_json_list(
        path,
        expected_name="gc_profiler.json",
        required_fields=["trace_id", "timestamp", "service", "heap_used_mb", "gc_pause_ms"],
    )


# =====================================================================
# AGGREGATION & INGESTION FACADES
# =====================================================================

def load_initial_incident_signals(
    data_dir: Optional[Union[Path, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load all initial operational signals available during live incident onset.

    Excludes late-arriving evidence (audit logs and GC profiler traces) as well
    as historical incident context.
    """
    base_dir = Path(data_dir).resolve() if data_dir else DEFAULT_DATA_DIR
    return {
        "alerts": load_alerts(base_dir / "alerts.json"),
        "logs": load_logs(base_dir / "logs.json"),
        "metrics": load_metrics(base_dir / "metrics.csv"),
        "complaints": load_complaints(base_dir / "complaints.json"),
        "deployments": load_deployments(base_dir / "deploys.json"),
    }


def load_late_evidence(
    data_dir: Optional[Union[Path, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load late-arriving evidence intended for injection during mid-incident re-evaluation."""
    base_dir = Path(data_dir).resolve() if data_dir else DEFAULT_DATA_DIR
    return {
        "audit_config_changes": load_audit_config_changes(base_dir / "audit_config_changes.json"),
        "gc_profiler": load_gc_profiler(base_dir / "gc_profiler.json"),
    }
