# ==========================================
# OWNED BY: MEMBER B (Correlation Engine)
# Responsibility: Correlate signals using time + namespace rules
# ==========================================

from typing import List
from datetime import datetime, timedelta
from utils.schemas import NormalizedSignal

def get_signals_by_component(signals: List[NormalizedSignal], component: str) -> List[NormalizedSignal]:
    return [s for s in signals if s.component == component]

def get_signals_in_window(signals: List[NormalizedSignal], anchor_time: datetime, window_minutes: int = 15) -> List[NormalizedSignal]:
    start = anchor_time - timedelta(minutes=window_minutes)
    end = anchor_time + timedelta(minutes=window_minutes)
    return [s for s in signals if start <= s.parsed_timestamp <= end]

def correlate_incident_context(signals: List[NormalizedSignal], target_component: str = "payment-api") -> List[NormalizedSignal]:
    """
    Correlates signals related to a target incident. Looks at all deployment events 
    and clusters warning/critical signals within a window.
    """
    correlated = []
    deploys = [s for s in signals if s.signal_type == "deploy"]
    
    # Anchor to the latest deployment of the target component
    anchor_deploys = [d for d in deploys if d.component == target_component]
    
    if anchor_deploys:
        latest_deploy = max(anchor_deploys, key=lambda d: d.parsed_timestamp)
        # Pull all signals within 30 minutes after that deployment
        start_time = latest_deploy.parsed_timestamp - timedelta(minutes=5)
        end_time = latest_deploy.parsed_timestamp + timedelta(minutes=30)
        
        for s in signals:
            if start_time <= s.parsed_timestamp <= end_time:
                correlated.append(s)
    else:
        # Fallback: pull all non-INFO signals as they represent active incident signatures
        correlated = [s for s in signals if s.severity in ["WARNING", "CRITICAL", "ERROR", "HIGH"]]
        
    return correlated
