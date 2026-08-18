import os
import json
import re
import copy
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

from utils.config import get_llm_config
from reasoning.prompts import SYSTEM_PROMPT, build_analysis_prompt
from reasoning.evidence_engine import sanitize_or_raise_analysis


# =====================================================================
# ADAPTER: UNIFIED TIMELINE -> REASONING DICTIONARIES
# =====================================================================

def timeline_to_reasoning_dicts(unified_timeline: Any) -> List[Dict[str, Any]]:
    """Convert Member B UnifiedTimeline or event collection into reasoning-compatible dictionaries."""
    if unified_timeline is None:
        return []

    if hasattr(unified_timeline, "entries") and isinstance(unified_timeline.entries, list):
        raw_entries = unified_timeline.entries
    elif isinstance(unified_timeline, dict) and "entries" in unified_timeline and isinstance(unified_timeline["entries"], list):
        raw_entries = unified_timeline["entries"]
    elif isinstance(unified_timeline, list):
        raw_entries = unified_timeline
    else:
        raw_entries = [unified_timeline]

    result: List[Dict[str, Any]] = []

    for entry in raw_entries:
        if isinstance(entry, dict):
            ev_id = entry.get("id") or entry.get("event_id") or entry.get("signal_id")
            if not ev_id:
                continue
            ev_id_str = str(ev_id)
            ts = entry.get("timestamp") or entry.get("parsed_timestamp")
            if isinstance(ts, datetime):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts or "")

            inc_id = entry.get("incident_id", "inc_unknown")
            source = entry.get("source") or entry.get("signal_type", "unknown")
            component = entry.get("component") or entry.get("service", "unknown")
            severity = entry.get("severity") or entry.get("level", "INFO")
            description = entry.get("description") or entry.get("message", "")
            raw_meta = entry.get("metadata", {})
            metadata = copy.deepcopy(raw_meta) if isinstance(raw_meta, dict) else {}

        else:
            ev_id = getattr(entry, "event_id", getattr(entry, "signal_id", getattr(entry, "id", None)))
            if not ev_id:
                continue
            ev_id_str = str(ev_id)
            ts = getattr(entry, "timestamp", getattr(entry, "parsed_timestamp", None))
            if isinstance(ts, datetime):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts or "")

            inc_id = getattr(entry, "incident_id", "inc_unknown")
            source = getattr(entry, "source", getattr(entry, "signal_type", "unknown"))
            component = getattr(entry, "component", getattr(entry, "service", "unknown"))
            severity = getattr(entry, "severity", getattr(entry, "level", "INFO"))
            description = getattr(entry, "description", getattr(entry, "message", ""))
            raw_meta = getattr(entry, "metadata", {})
            metadata = copy.deepcopy(raw_meta) if isinstance(raw_meta, dict) else {}

        result.append({
            "id": ev_id_str,
            "event_id": ev_id_str,
            "incident_id": str(inc_id),
            "timestamp": ts_str,
            "source": str(source),
            "component": str(component),
            "severity": str(severity),
            "description": str(description),
            "metadata": metadata,
        })

    return result


# =====================================================================
# LLM API CALLER & CLEANER
# =====================================================================

def _call_llm_api(prompt: str, config: dict) -> str:
    """Execute a single LLM API call using configured provider (Gemini)."""
    api_key = config.get("gemini_api_key")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    if not HAS_GENAI:
        raise ImportError("google-genai package is not installed.")

    client = genai.Client(api_key=api_key)
    model_name = config.get("model", "gemini-2.5-flash")
    
    response = client.models.generate_content(
        model=model_name,
        contents=[SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return response.text


def _clean_json_text(text: str) -> str:
    """Extract valid JSON string from potential markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


# =====================================================================
# PUBLIC ENTRYPOINTS (MEMBER C)
# =====================================================================

def analyze_incident(timeline: Any, source_repo_path: Optional[str] = None) -> Dict[str, Any]:
    """Public entrypoint for Member C reasoning engine.
    Consumes a structured incident timeline (UnifiedTimeline, List[TimelineEntry], or List[Dict]).

    Returns structured incident analysis dictionary containing:
    - incident_summary
    - hypotheses (2 to 4 ranked, with supporting & contradicting evidence IDs)
    - diagnostic_sequence
    - recommended_fix (with file, explanation, and diffs)
    """
    formatted_timeline = timeline_to_reasoning_dicts(timeline)
    config = get_llm_config()

    source_code_str = None
    if source_repo_path and os.path.exists(source_repo_path):
        source_code_str = ""
        for root, _, files in os.walk(source_repo_path):
            for file in files:
                if file.endswith((".py", ".yaml", ".json", ".txt", ".md", ".sh")):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r') as f:
                            rel_path = os.path.relpath(filepath, source_repo_path)
                            source_code_str += f"--- {rel_path} ---\n{f.read()}\n\n"
                    except Exception:
                        pass
        if not source_code_str:
            source_code_str = None

    prompt = build_analysis_prompt(formatted_timeline, source_code_str=source_code_str)

    try:
        raw_output = _call_llm_api(prompt, config)
        cleaned_json = _clean_json_text(raw_output)
        analysis_data = json.loads(cleaned_json)
    except Exception as exc:
        raise RuntimeError(f"Incident analysis failed: {exc}")

    return sanitize_or_raise_analysis(analysis_data, formatted_timeline)


def analyze_unified_timeline(unified_timeline: Any, source_repo_path: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function: Converts UnifiedTimeline to reasoning dicts and runs analyze_incident."""
    return analyze_incident(unified_timeline, source_repo_path)
