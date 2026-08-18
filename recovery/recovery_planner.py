# ==========================================
# OWNED BY: MEMBER C (Triage & Recovery)
# Responsibility: Recommend playbooks with risk assessments
# ==========================================

import os
import json
import google.generativeai as genai
from utils.config import is_gemini_active, GEMINI_MODEL
from reasoning.prompts import RECOVERY_PROMPT

def get_mock_recovery() -> dict:
    return {
      "recovery_actions": [
        {
          "action": "Roll back payment-api deployment to v1.4.1",
          "reason": "Since the connection leak was introduced in deployment DEP-772 (v1.4.2), reverting to the previous stable release will restore connection stability and release leaked sockets safely.",
          "risk": "LOW",
          "instructions": "kubectl set image deployment/payment-api payment-api=registry.tcs.internal/payment-api:v1.4.1"
        },
        {
          "action": "Restart the payment-api application pods",
          "reason": "This will close all active network sockets, temporarily clearing the leaked connections and restoring availability. However, the leak will recur if the underlying code is still running.",
          "risk": "MEDIUM",
          "instructions": "kubectl rollout restart deployment/payment-api"
        },
        {
          "action": "Temporarily increase PostgreSQL max_connections",
          "reason": "Allows more active connections, but is highly risky as it can crash the database instance due to RAM/CPU exhaustion.",
          "risk": "HIGH",
          "instructions": "psql -c 'ALTER SYSTEM SET max_connections = 300;' && psql -c 'SELECT pg_reload_conf();'"
        }
      ]
    }

def plan_recovery(timeline_str: str, hypotheses_str: str) -> dict:
    if is_gemini_active():
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel(GEMINI_MODEL)
            prompt = RECOVERY_PROMPT.format(
                timeline=timeline_str,
                hypotheses=hypotheses_str
            )
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
                
            return json.loads(text.strip())
        except Exception as e:
            print(f"Error calling Gemini: {e}. Falling back to mock recovery.")
            
    return get_mock_recovery()
