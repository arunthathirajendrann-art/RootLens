# ==========================================
# OWNED BY: MEMBER C (AI Reasoning Engine)
# Responsibility: Define system prompts and JSON templates
# ==========================================

import json
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You are an expert SRE and Incident Response Lead AI.
Your task is to analyze a production incident timeline built from heterogeneous telemetry streams (alerts, logs, metrics, complaints, deploys, config changes, gc_profiler).

CRITICAL CONSTRAINTS:
1. Return ONLY valid, raw JSON matching the schema below. Do NOT wrap output in markdown fences (```json ... ```) or add commentary outside the JSON.
2. Analyze ONLY the supplied incident timeline and metadata. Do not invent background facts or event IDs.
3. Generate between 2 and 4 competing root-cause hypotheses (rank 1 = most likely).
4. Assign a confidence score between 0.00 and 1.00 for each hypothesis.
5. EVERY evidence item (supporting_evidence and contradicting_evidence) MUST reference a real "event_id" present in the VALID EVENT IDs list.
6. Note that correlation does not imply causation; deployment or configuration changes may be red herrings.
7. Produce a prioritized diagnostic_sequence that tests competing hypotheses.
8. Produce EXACTLY ONE recovery_proposal with "requires_human_approval": true. NEVER claim remediation was executed and NEVER execute any production action.

JSON OUTPUT SCHEMA:
{
  "incident_summary": "High-level summary of the incident based strictly on timeline events",
  "hypotheses": [
    {
      "rank": 1,
      "root_cause": "Short description of hypothesized root cause",
      "confidence": 0.85,
      "supporting_evidence": [
        {
          "event_id": "EVT-DEP-4101",
          "reason": "Why this specific timeline event supports this hypothesis"
        }
      ],
      "contradicting_evidence": [
        {
          "event_id": "EVT-ALT-101",
          "reason": "Why this specific timeline event contradicts this hypothesis"
        }
      ],
      "reasoning_summary": "Explanation of why this hypothesis ranks where it does",
      "implicated_file": "path/to/source/file.py",
      "implicated_line": 12,
      "source_snippet": "def broken_code():..."
    }
  ],
  "recommended_fix": {
    "file": "path/to/source/file.py",
    "diff_before": "old line of code",
    "diff_after": "fixed line of code",
    "explanation": "Plain language explanation of why this fix works",
    "risk": "Risk impact note (e.g. config-only change, safe)"
  }
}
"""


def build_analysis_prompt(
    timeline: List[Dict[str, Any]],
    past_incidents: Optional[List[Dict[str, Any]]] = None,
    source_code_str: Optional[str] = None,
) -> str:
    """Build user prompt containing the structured incident timeline and valid event IDs."""
    valid_event_ids = [
        str(item.get("id") or item.get("event_id"))
        for item in timeline
        if isinstance(item, dict) and (item.get("id") or item.get("event_id"))
    ]
    formatted_timeline = json.dumps(timeline, indent=2)

    prompt = f"""INCIDENT TIMELINE EVENTS (Total: {len(timeline)}):
{formatted_timeline}

VALID EVENT IDs THAT YOU MAY REFERENCE:
{json.dumps(valid_event_ids)}
"""
    if source_code_str:
        prompt += f"\nSOURCE CODE REPOSITORY CONTENT:\n{source_code_str}\n"

    if past_incidents:
        prompt += f"\nHISTORICAL INCIDENT MEMORY:\n{json.dumps(past_incidents, indent=2)}\n"

    prompt += """
Instructions:
Analyze the timeline events and metadata above, along with the source code, and output structured JSON following all constraints.
Ensure all referenced event_ids exist in the VALID EVENT IDs list above.
"""
    return prompt


# Prompt templates for root cause analysis, diagnostics, and recovery plans (Used by app.py)

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
