# ==========================================
# OWNED BY: MEMBER D (UI & Operator Gate)
# Responsibility: Save operational outcomes back to historical memory
# ==========================================

import os
import json
from datetime import datetime
from utils.config import PAST_INCIDENTS_PATH

def append_to_incident_memory(component: str, symptoms: str, root_cause: str, recovery_action: str, status: str, operator_notes: str) -> dict:
    incidents = []
    if os.path.exists(PAST_INCIDENTS_PATH):
        with open(PAST_INCIDENTS_PATH, 'r') as f:
            try:
                incidents = json.load(f)
            except Exception:
                incidents = []
                
    next_id = f"INC-{len(incidents) + 1:03d}"
    
    new_entry = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "incident_id": next_id,
        "component": component,
        "symptoms": symptoms,
        "root_cause": root_cause,
        "recovery_action": recovery_action,
        "status": status,
        "operator_notes": operator_notes
    }
    
    incidents.append(new_entry)
    
    with open(PAST_INCIDENTS_PATH, 'w') as f:
        json.dump(incidents, f, indent=2)
        
    return new_entry
