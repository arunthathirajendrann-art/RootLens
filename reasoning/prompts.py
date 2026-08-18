# ==========================================
# OWNED BY: MEMBER C (AI Reasoning Engine)
# Responsibility: Define system prompts and JSON templates
# ==========================================

# Prompt templates for root cause analysis, diagnostics, and recovery plans

HYPOTHESIS_PROMPT = """
You are an expert Incident Response AI agent.
Analyze the following production incident timeline and compare it against the provided list of past incidents to generate 2 to 4 competing root-cause hypotheses.

For each hypothesis, you must provide:
1. Title
2. Description
3. Confidence score (between 0.0 and 1.0)
4. Evidence FOR the hypothesis (bullet points)
5. Evidence AGAINST the hypothesis (bullet points)

---
PAST INCIDENTS MEMORY:
{past_incidents}

---
CURRENT INCIDENT TIMELINE:
{timeline}

---
Return ONLY a valid JSON object matching this schema:
{{
  "hypotheses": [
    {{
      "title": "string",
      "description": "string",
      "confidence": float,
      "evidence_for": ["string"],
      "evidence_against": ["string"]
    }}
  ]
}}
Do NOT wrap the output in markdown block codes or include extra text. Just return the JSON block.
"""

DIAGNOSTIC_PROMPT = """
Based on the current incident timeline and the proposed hypotheses, generate a prioritized list of diagnostic checks (CLI commands, DB queries, code checks) to verify or invalidate the root cause.

TIMELINE:
{timeline}

HYPOTHESES:
{hypotheses}

Return ONLY a valid JSON object matching this schema:
{{
  "diagnostic_steps": [
    {{
      "step": int,
      "command_or_action": "string",
      "purpose": "string",
      "priority": "HIGH" | "MEDIUM" | "LOW"
    }}
  ]
}}
Do NOT wrap the output in markdown block codes.
"""

RECOVERY_PROMPT = """
Based on the current incident timeline and the leading hypotheses, recommend 2-3 recovery actions.
For each action, specify:
1. Action name
2. Detailed reason
3. Risk level (LOW, MEDIUM, HIGH)
4. Execution instructions (commands or scripts)

TIMELINE:
{timeline}

HYPOTHESES:
{hypotheses}

Return ONLY a valid JSON object matching this schema:
{{
  "recovery_actions": [
    {{
      "action": "string",
      "reason": "string",
      "risk": "LOW" | "MEDIUM" | "HIGH",
      "instructions": "string"
    }}
  ]
}}
Do NOT wrap the output in markdown block codes.
"""
