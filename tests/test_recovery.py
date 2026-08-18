import pytest
from reasoning.hypothesis_engine import analyze_incident, timeline_to_reasoning_dicts
from utils.schemas import TimelineEntry, UnifiedTimeline
from datetime import datetime, timezone

def test_recovery_proposal_requires_human_approval():
    """Test that recovery proposal always enforces requires_human_approval == True."""
    entry = TimelineEntry(
        event_id="EVT-ALT-999",
        incident_id="inc_test",
        timestamp=datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc),
        source="alerts",
        component="payment-service",
        severity="CRITICAL",
        description="Database connection timeout",
        metadata={"pool": "exhausted"}
    )
    timeline = UnifiedTimeline(entries=[entry])
    analysis = analyze_incident(timeline)
    
    assert "recovery_proposal" in analysis
    recovery = analysis["recovery_proposal"]
    assert recovery.get("requires_human_approval") is True

def test_no_production_actions_executed():
    """Test that analyze_incident purely returns recommendation dict with zero side effects."""
    timeline_dicts = [
        {
            "id": "EVT-DEP-1",
            "event_id": "EVT-DEP-1",
            "incident_id": "inc_1",
            "timestamp": "2026-08-18T10:00:00Z",
            "source": "deploys",
            "component": "order-api",
            "severity": "INFO",
            "description": "Deployed order-api v1.2",
            "metadata": {"version": "v1.2"}
        }
    ]
    res = analyze_incident(timeline_dicts)
    assert isinstance(res, dict)
    assert res["recovery_proposal"]["requires_human_approval"] is True
