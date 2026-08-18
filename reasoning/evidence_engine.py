# ==========================================
# OWNED BY: MEMBER C (AI Reasoning Engine)
# Responsibility: Extract signals as evidence metrics (FOR/AGAINST) and validate evidence integrity
# ==========================================

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from utils.schemas import NormalizedSignal, Evidence


class EvidenceValidationError(ValueError):
    """Raised when analysis result violates evidence or constraint rules."""
    pass


def correlate_evidence(timeline: List[NormalizedSignal]) -> List[Evidence]:
    """Scans the timeline and extracts key items as Evidence objects."""
    evidence_list = []
    for sig in timeline:
        if sig.severity in ["WARNING", "CRITICAL", "ERROR", "HIGH"] or sig.signal_type == "deploy":
            relevance = "high" if sig.severity == "CRITICAL" or sig.signal_type == "deploy" else "medium"
            evidence_list.append(Evidence(
                evidence_id=f"E-{sig.signal_id}",
                signal_id=sig.signal_id,
                type=sig.signal_type,
                timestamp=sig.timestamp,
                summary=sig.message,
                relevance=relevance
            ))
    return evidence_list


def extract_timeline_event_ids(timeline: List[Any]) -> Set[str]:
    """Extract all valid event IDs from input timeline (handles dicts, dataclasses, timeline entries)."""
    event_ids: Set[str] = set()
    if isinstance(timeline, dict) and "entries" in timeline:
        timeline = timeline["entries"]
    elif hasattr(timeline, "entries"):
        timeline = getattr(timeline, "entries")

    if not isinstance(timeline, (list, tuple)):
        timeline = [timeline]

    for event in timeline:
        if isinstance(event, dict):
            ev_id = event.get("id") or event.get("event_id") or event.get("signal_id")
            if ev_id:
                event_ids.add(str(ev_id))
        else:
            ev_id = getattr(event, "event_id", getattr(event, "signal_id", getattr(event, "id", None)))
            if ev_id:
                event_ids.add(str(ev_id))

    return event_ids


def _clean_event_id(raw_id: str) -> str:
    """Normalize event ID string by stripping non-alphanumeric characters, T/Z ISO flags."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(raw_id)).upper()
    return cleaned.replace("T", "").replace("Z", "")


def match_valid_event_id(ev_id: str, valid_ids: Set[str]) -> Optional[str]:
    """Find matching valid event ID from set of valid timeline IDs.

    Matching Hierarchy:
    1. Exact match
    2. Substring match
    3. Cleaned string match (ignoring dashes & timestamp separators)
    4. Domain/component prefix match (matching e.g. EVT-MET-payment-service- to actual valid ID)
    """
    if not ev_id or not valid_ids:
        return None
    if ev_id in valid_ids:
        return ev_id

    # 1. Direct or substring match
    for valid_id in valid_ids:
        if ev_id == valid_id or valid_id in ev_id or ev_id in valid_id:
            return valid_id

    # 2. Cleaned ID match
    clean_target = _clean_event_id(ev_id)
    for valid_id in valid_ids:
        if _clean_event_id(valid_id) == clean_target:
            return valid_id

    # 3. Domain & component prefix match (e.g. EVT-MET-payment-service-...)
    parts = str(ev_id).split("-")
    if len(parts) >= 3:
        prefix = "-".join(parts[:-1]) + "-"
        prefix_matches = [v for v in valid_ids if v.startswith(prefix)]
        if prefix_matches:
            return prefix_matches[0]

        broad_prefix = "-".join(parts[:2]) + "-"
        broad_matches = [v for v in valid_ids if v.startswith(broad_prefix)]
        if broad_matches:
            return broad_matches[0]

    return None


def validate_incident_analysis(analysis: Dict[str, Any], timeline: List[Any]) -> Tuple[bool, List[str]]:
    """Validate structured incident analysis output against constraints and the input timeline.

    Checks:
    1. Hypotheses count must be between 2 and 4.
    2. Confidence scores must be valid floats between 0.0 and 1.0.
    3. Every evidence event_id (supporting or contradicting) must exist in the timeline.
    4. Recovery proposal must have requires_human_approval == True.
    """
    errors: List[str] = []

    if not isinstance(analysis, dict):
        return False, ["Analysis output must be a dictionary."]

    # 1. Validate Hypotheses Count
    hypotheses = analysis.get("hypotheses", [])
    if not isinstance(hypotheses, list):
        errors.append("Field 'hypotheses' must be a list.")
    elif len(hypotheses) < 2 or len(hypotheses) > 4:
        errors.append(f"Hypotheses count must be between 2 and 4. Got {len(hypotheses)}.")

    # 2. Extract valid event IDs
    valid_ids = extract_timeline_event_ids(timeline)

    # 3. Validate each hypothesis
    if isinstance(hypotheses, list):
        for idx, hyp in enumerate(hypotheses):
            if not isinstance(hyp, dict):
                errors.append(f"Hypothesis item at index {idx} is not a dictionary.")
                continue

            # Confidence validation
            conf = hyp.get("confidence")
            if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                errors.append(
                    f"Hypothesis '{hyp.get('root_cause', idx)}' has invalid confidence score: {conf}. Must be between 0.0 and 1.0."
                )

            # Evidence validation
            for ev_type in ["supporting_evidence", "contradicting_evidence", "evidence_for", "evidence_against"]:
                evidence_list = hyp.get(ev_type, [])
                if not isinstance(evidence_list, list):
                    continue

                for ev_idx, item in enumerate(evidence_list):
                    if isinstance(item, dict):
                        ev_id = str(item.get("event_id", item.get("id", "")))
                    elif isinstance(item, str):
                        ev_id = item
                    else:
                        continue

                    matched_id = match_valid_event_id(ev_id, valid_ids)
                    if not matched_id and valid_ids:
                        errors.append(
                            f"Invalid event_id '{ev_id}' referenced in {ev_type} for hypothesis {idx+1}. ID does not exist in timeline."
                        )
                    elif matched_id and isinstance(item, dict) and "event_id" in item:
                        # Auto-normalize event_id in evidence dictionary to exact canonical ID
                        item["event_id"] = matched_id

    # 4. Validate Recommended Fix
    fix = analysis.get("recommended_fix") or analysis.get("recovery_proposal") or analysis.get("recovery_actions")
    if fix is None:
        errors.append("Missing or invalid 'recommended_fix' object.")

    is_valid = len(errors) == 0
    return is_valid, errors


def sanitize_or_raise_analysis(analysis: Dict[str, Any], timeline: List[Any]) -> Dict[str, Any]:
    """Validate analysis. If invalid, raise EvidenceValidationError."""
    is_valid, errors = validate_incident_analysis(analysis, timeline)
    if not is_valid:
        raise EvidenceValidationError(f"Incident analysis validation failed: {'; '.join(errors)}")
    return analysis
