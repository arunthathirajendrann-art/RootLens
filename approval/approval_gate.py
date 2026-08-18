# ==========================================
# OWNED BY: MEMBER D (UI & Operator Gate)
# Responsibility: Record operator decisions (APPROVED/REJECTED)
# ==========================================

from datetime import datetime
from typing import Dict, Any

def record_approval_gate_decision(action_name: str, status: str, operator: str, comments: str = "") -> Dict[str, Any]:
    """
    Submits and structures a decision log entry for the approval portal.
    status values: APPROVED, REJECTED, MORE_DIAGNOSTICS
    """
    return {
        "action": action_name,
        "status": status,
        "operator": operator,
        "timestamp": datetime.now().isoformat(),
        "comments": comments
    }
