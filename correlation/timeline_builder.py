# ==========================================
# OWNED BY: MEMBER B (Correlation Engine)
# Responsibility: Sort and format unified incident timeline
# ==========================================

from typing import List
from utils.schemas import NormalizedSignal
from utils.timestamp import format_datetime

def build_chronological_timeline(signals: List[NormalizedSignal]) -> List[NormalizedSignal]:
    return sorted(signals, key=lambda s: s.parsed_timestamp)

def format_timeline_for_prompt(timeline: List[NormalizedSignal]) -> str:
    lines = []
    for sig in timeline:
        ts_str = format_datetime(sig.parsed_timestamp)
        lines.append(
            f"[{ts_str}] [{sig.signal_type.upper()}] Component: {sig.component} | "
            f"Severity: {sig.severity} | Message: {sig.message}"
        )
    return "\n".join(lines)
