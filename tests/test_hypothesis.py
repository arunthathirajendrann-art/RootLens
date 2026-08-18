import os
import pytest
from datetime import datetime, timezone

from ingestion.normalizer import normalize_initial_incident_signals, normalize_late_evidence
from correlation.correlation_engine import correlate_events, re_correlate
from correlation.timeline_builder import build_timeline
from utils.schemas import UnifiedTimeline, TimelineEntry
from reasoning.hypothesis_engine import (
    timeline_to_reasoning_dicts,
    analyze_incident,
    analyze_unified_timeline,
)
from reasoning.evidence_engine import validate_incident_analysis, EvidenceValidationError

@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK_MODE", "true")


@pytest.fixture
def sample_unified_timeline():
    entry1 = TimelineEntry(
        event_id="EVT-DEP-4101",
        incident_id="inc_checkout_01",
        timestamp=datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc),
        source="deploys",
        component="checkout-service",
        severity="INFO",
        description="Deployment v2.4.1 completed",
        metadata={"version": "v2.4.1", "commit_hash": "a1b2c3d"}
    )
    entry2 = TimelineEntry(
        event_id="EVT-ALT-101",
        incident_id="inc_checkout_01",
        timestamp=datetime(2026, 8, 18, 10, 2, tzinfo=timezone.utc),
        source="alerts",
        component="checkout-service",
        severity="CRITICAL",
        description="HTTP 500 error rate spiked to 8%",
        metadata={"threshold": 0.05, "observed_value": 0.08}
    )
    return UnifiedTimeline(entries=[entry1, entry2])


def test_a_timeline_to_reasoning_dicts(sample_unified_timeline):
    """Test A: UnifiedTimeline converts to reasoning dictionaries correctly."""
    dicts = timeline_to_reasoning_dicts(sample_unified_timeline)
    assert isinstance(dicts, list)
    assert len(dicts) == 2
    assert isinstance(dicts[0], dict)
    assert dicts[0]["component"] == "checkout-service"
    assert dicts[0]["source"] == "deploys"


def test_b_event_id_preservation(sample_unified_timeline):
    """Test B: event_id is preserved exactly in both 'id' and 'event_id' fields."""
    dicts = timeline_to_reasoning_dicts(sample_unified_timeline)
    assert dicts[0]["id"] == "EVT-DEP-4101"
    assert dicts[0]["event_id"] == "EVT-DEP-4101"
    assert dicts[1]["id"] == "EVT-ALT-101"
    assert dicts[1]["event_id"] == "EVT-ALT-101"


def test_c_timestamp_conversion(sample_unified_timeline):
    """Test C: datetime timestamp is safely converted to ISO-8601 string."""
    dicts = timeline_to_reasoning_dicts(sample_unified_timeline)
    assert dicts[0]["timestamp"] == "2026-08-18T10:00:00+00:00"
    assert dicts[1]["timestamp"] == "2026-08-18T10:02:00+00:00"


def test_d_metadata_preservation(sample_unified_timeline):
    """Test D: metadata is preserved without mutation."""
    dicts = timeline_to_reasoning_dicts(sample_unified_timeline)
    assert dicts[0]["metadata"] == {"version": "v2.4.1", "commit_hash": "a1b2c3d"}
    assert dicts[1]["metadata"] == {"threshold": 0.05, "observed_value": 0.08}


def test_e_full_member_b_to_member_c_integration():
    """Test E: Full Member B -> Member C integration pipeline using project data."""
    # 1. Ingest initial signals
    raw_events = normalize_initial_incident_signals()
    assert len(raw_events) > 0

    # 2. Correlate events
    clusters = correlate_events(raw_events)
    assert len(clusters) > 0

    # 3. Build UnifiedTimeline
    timeline = build_timeline(clusters)
    assert isinstance(timeline, UnifiedTimeline)
    assert timeline.event_count > 0

    # 4. Analyze via Member C entrypoint
    analysis = analyze_unified_timeline(timeline)

    # 5. Verify structure & safety constraints
    assert isinstance(analysis, dict)
    assert "hypotheses" in analysis
    assert "diagnostic_sequence" in analysis
    assert "recovery_proposal" in analysis

    hypotheses = analysis["hypotheses"]
    assert 2 <= len(hypotheses) <= 4

    # Verify ranking and confidence
    for idx, hyp in enumerate(hypotheses, start=1):
        assert hyp["rank"] == idx
        assert 0.0 <= hyp["confidence"] <= 1.0

    # Verify evidence references valid event IDs
    valid_ids = {entry.event_id for entry in timeline.entries}
    for hyp in hypotheses:
        for item in hyp.get("supporting_evidence", []) + hyp.get("contradicting_evidence", []):
            ev_id = item.get("event_id") if isinstance(item, dict) else str(item)
            assert ev_id in valid_ids or any(v in ev_id for v in valid_ids)

    # Verify recovery proposal safety boundary
    recovery = analysis["recovery_proposal"]
    assert recovery.get("requires_human_approval") is True


def test_f_recorrelation_updated_member_c_analysis():
    """Test F: Re-correlation with late-arriving evidence triggers updated analysis."""
    # 1. Initial timeline V1
    raw_events = normalize_initial_incident_signals()
    clusters_v1 = correlate_events(raw_events)
    timeline_v1 = build_timeline(clusters_v1)
    analysis_v1 = analyze_unified_timeline(timeline_v1)

    # 2. Late arriving evidence
    late_events = normalize_late_evidence()
    assert len(late_events) > 0

    # 3. Re-correlate to produce V2
    re_result = re_correlate(timeline_v1, late_events)
    timeline_v2 = re_result.timeline
    assert timeline_v2.event_count > timeline_v1.event_count

    # 4. Analyze V2 timeline
    analysis_v2 = analyze_unified_timeline(timeline_v2)
    assert isinstance(analysis_v2, dict)
    assert 2 <= len(analysis_v2["hypotheses"]) <= 4

    # Verify late-arriving event IDs exist in V2 and are valid for evidence references
    valid_ids_v2 = {entry.event_id for entry in timeline_v2.entries}
    late_ids = {e["event_id"] for e in late_events}
    assert late_ids.issubset(valid_ids_v2)


def test_validation_rejects_invalid_event_id():
    """Test that evidence validation fails if a non-existent event ID is referenced."""
    timeline = [{"id": "EVT-01", "description": "Alert"}]
    invalid_analysis = {
        "incident_summary": "Test",
        "hypotheses": [
            {
                "rank": 1,
                "root_cause": "Cause 1",
                "confidence": 0.9,
                "supporting_evidence": [{"event_id": "EVT-NON-EXISTENT", "reason": "Fake ID"}],
                "contradicting_evidence": []
            },
            {
                "rank": 2,
                "root_cause": "Cause 2",
                "confidence": 0.5,
                "supporting_evidence": [{"event_id": "EVT-01", "reason": "Valid ID"}],
                "contradicting_evidence": []
            }
        ],
        "diagnostic_sequence": [],
        "recovery_proposal": {"action": "Fix", "reason": "Test", "risk": "Low", "requires_human_approval": True}
    }
    is_valid, errors = validate_incident_analysis(invalid_analysis, timeline)
    assert not is_valid
    assert any("Invalid event_id" in err for err in errors)
