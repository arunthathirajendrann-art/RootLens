# ==========================================
# OWNED BY: MEMBER C (Triage & Recovery)
# Responsibility: Generate diagnostic verification procedures
# ==========================================

import os
import json
import google.generativeai as genai
from utils.config import is_gemini_active, GEMINI_MODEL
from reasoning.prompts import DIAGNOSTIC_PROMPT

def get_mock_diagnostics() -> dict:
    return {
      "diagnostic_steps": [
        {
          "step": 1,
          "command_or_action": "kubectl logs -l app=payment-api --tail=200 | grep -iE 'conn|pool|leak|sql'",
          "purpose": "Check logs specifically for stack traces showing where db connection acquisition is blocking or leaking.",
          "priority": "HIGH"
        },
        {
          "step": 2,
          "command_or_action": "SELECT pid, age(query_start), query, state FROM pg_stat_activity WHERE state != 'idle';",
          "purpose": "Identify any active queries running for an unusually long time that are locking database connections.",
          "priority": "HIGH"
        },
        {
          "step": 3,
          "command_or_action": "git diff v1.4.1..v1.4.2 -- ingestion/ db/ connection/",
          "purpose": "Review code changes in deployment DEP-772 to find unclosed database session contexts or connection managers.",
          "priority": "MEDIUM"
        }
      ]
    }

def plan_diagnostics(timeline_str: str, hypotheses_str: str) -> dict:
    if is_gemini_active():
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel(GEMINI_MODEL)
            prompt = DIAGNOSTIC_PROMPT.format(
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
            print(f"Error calling Gemini: {e}. Falling back to mock diagnostics.")
            
    return get_mock_diagnostics()
