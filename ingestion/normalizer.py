import os
import pandas as pd
from typing import List
from utils.schemas import NormalizedSignal
from utils.timestamp import parse_iso_timestamp
from ingestion.loaders import load_json_file, load_csv_file
from utils.config import DATA_DIR

def normalize_alerts(data: List[dict]) -> List[NormalizedSignal]:
    normalized = []
    for item in data:
        normalized.append(NormalizedSignal(
            signal_id=item.get("alert_id", ""),
            signal_type="alert",
            source="monitoring",
            timestamp=item.get("timestamp", ""),
            parsed_timestamp=parse_iso_timestamp(item.get("timestamp", "")),
            component=item.get("component", ""),
            severity=item.get("severity", "INFO"),
            message=item.get("message", ""),
            metadata={"alert_name": item.get("name", "")}
        ))
    return normalized

def normalize_logs(data: List[dict]) -> List[NormalizedSignal]:
    normalized = []
    for idx, item in enumerate(data):
        normalized.append(NormalizedSignal(
            signal_id=f"LOG-{idx:03d}",
            signal_type="log",
            source="syslog",
            timestamp=item.get("timestamp", ""),
            parsed_timestamp=parse_iso_timestamp(item.get("timestamp", "")),
            component=item.get("component", ""),
            severity=item.get("level", "INFO"),
            message=item.get("message", ""),
            metadata={}
        ))
    return normalized

def normalize_deploys(data: List[dict]) -> List[NormalizedSignal]:
    normalized = []
    for item in data:
        normalized.append(NormalizedSignal(
            signal_id=item.get("deploy_id", ""),
            signal_type="deploy",
            source="deployer",
            timestamp=item.get("timestamp", ""),
            parsed_timestamp=parse_iso_timestamp(item.get("timestamp", "")),
            component=item.get("component", ""),
            severity="INFO",
            message=f"Version {item.get('version')} deployed by {item.get('deployed_by')}. Change: {item.get('change_log')}",
            metadata={"version": item.get("version"), "deploy_id": item.get("deploy_id")}
        ))
    return normalized

def normalize_complaints(data: List[dict]) -> List[NormalizedSignal]:
    normalized = []
    for item in data:
        normalized.append(NormalizedSignal(
            signal_id=item.get("complaint_id", ""),
            signal_type="complaint",
            source="ticketing",
            timestamp=item.get("timestamp", ""),
            parsed_timestamp=parse_iso_timestamp(item.get("timestamp", "")),
            component="user-experience",
            severity=item.get("severity", "MEDIUM"),
            message=item.get("message", ""),
            metadata={"user_id": item.get("user_id")}
        ))
    return normalized

def normalize_metrics(df: pd.DataFrame) -> List[NormalizedSignal]:
    normalized = []
    if df.empty:
        return normalized
    for idx, row in df.iterrows():
        val = row['value']
        metric = row['metric_name']
        comp = row['component']
        
        severity = "INFO"
        status_suffix = ""
        if metric == "cpu_utilization" and val > 80:
            severity = "WARNING"
            status_suffix = " (HIGH CPU)"
        elif metric == "db_connections" and val >= 200:
            severity = "CRITICAL"
            status_suffix = " (POOL EXHAUSTED)"
        elif metric == "db_connections" and val > 150:
            severity = "WARNING"
            status_suffix = " (HIGH CONNS)"
        elif metric == "latency_ms" and val > 5000:
            severity = "CRITICAL"
            status_suffix = " (SEVERE LATENCY)"
        elif metric == "latency_ms" and val > 1000:
            severity = "WARNING"
            status_suffix = " (HIGH LATENCY)"
            
        normalized.append(NormalizedSignal(
            signal_id=f"MET-{idx:03d}",
            signal_type="metric",
            source="prometheus",
            timestamp=row['timestamp'],
            parsed_timestamp=parse_iso_timestamp(row['timestamp']),
            component=comp,
            severity=severity,
            message=f"Metric {metric} = {val}{status_suffix}",
            metadata={"metric_name": metric, "value": val}
        ))
    return normalized

def ingest_all_signals(data_dir: str = DATA_DIR) -> List[NormalizedSignal]:
    alerts_raw = load_json_file(os.path.join(data_dir, "alerts.json"))
    logs_raw = load_json_file(os.path.join(data_dir, "logs.json"))
    deploys_raw = load_json_file(os.path.join(data_dir, "deploys.json"))
    complaints_raw = load_json_file(os.path.join(data_dir, "complaints.json"))
    metrics_df = load_csv_file(os.path.join(data_dir, "metrics.csv"))
    
    signals = []
    signals.extend(normalize_alerts(alerts_raw))
    signals.extend(normalize_logs(logs_raw))
    signals.extend(normalize_deploys(deploys_raw))
    signals.extend(normalize_complaints(complaints_raw))
    signals.extend(normalize_metrics(metrics_df))
    
    return signals
