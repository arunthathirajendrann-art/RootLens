from typing import List, Dict, Any
from utils.schemas import NormalizedSignal, Evidence

def correlate_evidence(timeline: List[NormalizedSignal]) -> List[Evidence]:
    """
    Scans the timeline and extracts key items as Evidence objects.
    """
    evidence_list = []
    for sig in timeline:
        # We focus on warnings, errors, deployments and metric anomalies
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
