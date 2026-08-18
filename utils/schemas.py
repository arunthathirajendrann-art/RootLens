from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

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
    signal_type: str  # alert, log, metric, complaint, deploy
    source: str
    timestamp: str
    parsed_timestamp: datetime
    component: str
    severity: str
    message: str
    metadata: Dict[str, Any] = {}

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
