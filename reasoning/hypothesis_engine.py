# ==========================================
# OWNED BY: MEMBER C (AI Reasoning Engine)
# Responsibility: Generate competing root-cause hypotheses using LLM or fallback mock data
# ==========================================

import os
import json
import re
import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

from utils.config import get_llm_config, is_gemini_active, GEMINI_MODEL, PAST_INCIDENTS_PATH
from reasoning.prompts import SYSTEM_PROMPT, HYPOTHESIS_PROMPT, build_analysis_prompt
from reasoning.evidence_engine import validate_incident_analysis, sanitize_or_raise_analysis


# =====================================================================
# ADAPTER: UNIFIED TIMELINE -> REASONING DICTIONARIES
# =====================================================================

def timeline_to_reasoning_dicts(unified_timeline: Any) -> List[Dict[str, Any]]:
    """Convert Member B UnifiedTimeline or event collection into reasoning-compatible dictionaries.

    Guarantees:
    - Preserves exact event_id as both 'id' and 'event_id'.
    - Preserves metadata dictionary without mutation.
    - Safely converts datetime objects to ISO-8601 strings.
    - Preserves chronological ordering.
    - Does not mutate input objects.
    """
    if unified_timeline is None:
        return []

    # Handle UnifiedTimeline object or dict containing entries
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
# DETERMINISTIC MOCK ANALYSIS GENERATOR
# =====================================================================

def _generate_mock_analysis(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic mock analyzer for Member C offline testing.
    Parses actual timeline events and references ONLY valid event IDs from input.
    """
    if not timeline:
        return {
            "incident_summary": "No timeline events provided.",
            "hypotheses": [
                {
                    "rank": 1,
                    "root_cause": "Insufficient telemetry data",
                    "confidence": 0.50,
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "reasoning_summary": "Empty timeline provided."
                },
                {
                    "rank": 2,
                    "root_cause": "Monitoring ingestion delay",
                    "confidence": 0.30,
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "reasoning_summary": "No active events detected."
                }
            ],
            "diagnostic_sequence": [
                {
                    "priority": 1,
                    "diagnostic": "Verify telemetry pipeline health.",
                    "tests_hypothesis": "Insufficient telemetry data",
                    "expected_signal": "New events appearing in ingestion stream."
                }
            ],
            "recovery_proposal": {
                "action": "Trigger manual monitoring health check.",
                "reason": "Timeline is currently empty.",
                "risk": "None.",
                "requires_human_approval": True
            }
        }

    all_ids = [e["id"] for e in timeline if isinstance(e, dict) and "id" in e]
    if not all_ids:
        all_ids = [f"EVT-{i}" for i in range(len(timeline))]

    deploy_events = [e for e in timeline if str(e.get("source", "")).lower() in ("deploy", "deploys", "config")]
    alert_events = [e for e in timeline if str(e.get("source", "")).lower() in ("alert", "alerts")]
    metric_events = [e for e in timeline if str(e.get("source", "")).lower() in ("metric", "metrics", "gc_profiler")]
    comp_events = [e for e in timeline if str(e.get("source", "")).lower() in ("complaint", "complaints")]

    primary_component = timeline[0].get("component", "system") if timeline else "system"
    summary_desc = timeline[-1].get("description", "System anomaly observed")

    hypotheses = []

    # H1: Deployment / Configuration Regression
    if deploy_events:
        d_ev = deploy_events[0]
        supp = [{"event_id": str(d_ev["id"]), "reason": f"Change event observed: {d_ev.get('description')}"}]
        if alert_events:
            supp.append({"event_id": str(alert_events[0]["id"]), "reason": "Alert triggered shortly after change."})
        contra = []
        if metric_events:
            contra.append({"event_id": str(metric_events[-1]["id"]), "reason": "Telemetry trends show pre-existing resource pressure."})

        hypotheses.append({
            "rank": 1,
            "root_cause": f"Regression introduced in {primary_component} deployment or config change",
            "confidence": 0.82,
            "supporting_evidence": supp,
            "contradicting_evidence": contra,
            "reasoning_summary": f"Recent change event {d_ev['id']} directly correlates with operational degradation in {primary_component}."
        })

    # H2: Resource Saturation / Memory Leak
    supp_h2 = []
    if metric_events:
        supp_h2.append({"event_id": str(metric_events[0]["id"]), "reason": f"Metric signal in {metric_events[0]['id']} indicates high resource pressure."})
    else:
        supp_h2.append({"event_id": all_ids[0], "reason": f"Anomaly signal observed in initial event {all_ids[0]}."})

    contra_h2 = []
    if deploy_events:
        contra_h2.append({"event_id": str(deploy_events[0]["id"]), "reason": "Timing strongly points to deployment change rather than steady resource accumulation."})

    hypotheses.append({
        "rank": len(hypotheses) + 1,
        "root_cause": f"Resource exhaustion or connection saturation in {primary_component}",
        "confidence": 0.65 if not deploy_events else 0.40,
        "supporting_evidence": supp_h2,
        "contradicting_evidence": contra_h2,
        "reasoning_summary": f"Telemetry signals point to resource pressure across {primary_component}."
    })

    # H3: Downstream Service / Dependency Failure
    if len(hypotheses) < 3:
        supp_h3 = []
        if comp_events:
            supp_h3.append({"event_id": str(comp_events[0]["id"]), "reason": f"User complaint {comp_events[0]['id']} reports client-facing impact."})
        elif alert_events:
            supp_h3.append({"event_id": str(alert_events[-1]["id"]), "reason": f"Alert {alert_events[-1]['id']} highlights elevated latency or error rate."})
        else:
            supp_h3.append({"event_id": all_ids[-1], "reason": f"Latest timeline event {all_ids[-1]} reflects upstream client impact."})

        hypotheses.append({
            "rank": len(hypotheses) + 1,
            "root_cause": f"Downstream dependency latency or connection pool timeout in {primary_component}",
            "confidence": 0.30,
            "supporting_evidence": supp_h3,
            "contradicting_evidence": [],
            "reasoning_summary": "Downstream database or API connectivity issues produce similar operational symptoms."
        })

    hypotheses.sort(key=lambda h: h["confidence"], reverse=True)
    for idx, hyp in enumerate(hypotheses, start=1):
        hyp["rank"] = idx

    diagnostics = [
        {
            "priority": 1,
            "diagnostic": f"Inspect application logs and stack traces for {primary_component} near incident onset.",
            "tests_hypothesis": hypotheses[0]["root_cause"],
            "expected_signal": "Stack traces or connection pool timeout warnings."
        },
        {
            "priority": 2,
            "diagnostic": f"Verify database connection counts and memory profiler traces for {primary_component}.",
            "tests_hypothesis": hypotheses[1]["root_cause"] if len(hypotheses) > 1 else hypotheses[0]["root_cause"],
            "expected_signal": "High connection pool utilization or heap allocation spikes."
        }
    ]

    recovery = {
        "action": f"Roll back deployment or restart {primary_component} service pods.",
        "reason": f"Timeline evidence correlates change events with error escalation in {primary_component}.",
        "risk": "Temporary disruption during pod restart.",
        "requires_human_approval": True
    }

    return {
        "incident_summary": f"Incident in {primary_component}: {summary_desc} across {len(timeline)} timeline events.",
        "hypotheses": hypotheses,
        "diagnostic_sequence": diagnostics,
        "recovery_proposal": recovery
    }


# =====================================================================
# LLM API CALLER & CLEANER
# =====================================================================

def _call_llm_api(prompt: str, config: dict) -> str:
    """Execute a single LLM API call using configured provider (Gemini)."""
    provider = config.get("provider", "gemini")
    model = config.get("model", "gemini-3.6-flash")

    if provider == "gemini":
        api_key = config.get("gemini_api_key")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        if HAS_REQUESTS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2
                }
            }
            response = requests.post(url, json=payload, timeout=45)
            if response.status_code != 200:
                raise RuntimeError(f"Gemini API request failed ({response.status_code}): {response.text}")
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as err:
                raise RuntimeError(f"Failed to extract response text from Gemini API output: {data}") from err

        elif HAS_GENAI:
            genai.configure(api_key=api_key)
            g_model = genai.GenerativeModel(model)
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
            res = g_model.generate_content(full_prompt)
            return res.text
        else:
            raise ImportError("Neither 'requests' nor 'google.generativeai' package is available to call Gemini API.")
    else:
        raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported values: 'gemini'.")


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

def analyze_incident(timeline: Any) -> Dict[str, Any]:
    """Public entrypoint for Member C reasoning engine.
    Consumes a structured incident timeline (UnifiedTimeline, List[TimelineEntry], or List[Dict]).

    Returns structured incident analysis dictionary containing:
    - incident_summary
    - hypotheses (2 to 4 ranked, with supporting & contradicting evidence IDs)
    - diagnostic_sequence
    - recovery_proposal (requires_human_approval = True)
    """
    formatted_timeline = timeline_to_reasoning_dicts(timeline)
    config = get_llm_config()

    if config.get("mock_mode", True):
        analysis = _generate_mock_analysis(formatted_timeline)
        return sanitize_or_raise_analysis(analysis, formatted_timeline)

    prompt = build_analysis_prompt(formatted_timeline)

    try:
        raw_output = _call_llm_api(prompt, config)
        cleaned_json = _clean_json_text(raw_output)
        analysis_data = json.loads(cleaned_json)
    except Exception as exc:
        print(f"[Warning] LLM call failed ({exc}), falling back to deterministic mock analyzer.")
        analysis_data = _generate_mock_analysis(formatted_timeline)

    return sanitize_or_raise_analysis(analysis_data, formatted_timeline)


def analyze_unified_timeline(unified_timeline: Any) -> Dict[str, Any]:
    """Convenience function: Converts UnifiedTimeline to reasoning dicts and runs analyze_incident."""
    return analyze_incident(unified_timeline)


# Legacy interface functions preserved for app.py compatibility

def get_mock_hypotheses() -> dict:
    return {
        "hypotheses": [
            {
                "title": "Database connection pool leak in payment-api version v1.4.2",
                "description": "The deployment DEP-772 at 10:00:00Z introduced payment-api v1.4.2. A suspected connection leak exists where database connections are not properly released back to the pool, saturating the PostgreSQL maximum connection limit (200) by 10:08:00Z.",
                "confidence": 0.92,
                "evidence_for": [
                    "payment-api v1.4.2 deployed at 10:00:00Z",
                    "db_connections metric starts rising immediately after, peaking at 200 at 10:08:00Z",
                    "Log messages warn of connection pool utilization at 85% and 95% shortly after deploy",
                    "SQLExceptions show cannot acquire connection from pool",
                    "Matches past incident INC-001 where auth-service had a redis connection leak"
                ],
                "evidence_against": [
                    "Other database services (e.g. auth-service) are not throwing connection pool warnings, suggesting the DB itself is healthy but the payment-api pool is exhausted."
                ]
            },
            {
                "title": "Sudden checkout traffic spike flooding payment service",
                "description": "A high volume of concurrent checkout requests overwhelmed the payment-api, exhausting all available database connection pool slots.",
                "confidence": 0.35,
                "evidence_for": [
                    "High HTTP 5xx rates and user complaints about slow payments started around 10:11:00Z",
                    "Database CPU utilization reached high levels (50.1%) under load"
                ],
                "evidence_against": [
                    "Metrics do not show a corresponding spike in request throughput; rather, latency rose first, which is indicative of blocking behavior rather than external load spike.",
                    "Normal traffic does not justify exhaustion of 200 connection threads in 8 minutes."
                ]
            },
            {
                "title": "PostgreSQL database server lock/hang",
                "description": "The core database instance db-primary-01.internal is hung or has locked tables, preventing payment-api from finishing queries and holding connections open.",
                "confidence": 0.20,
                "evidence_for": [
                    "Log shows PostgreSQL warning: Client connection limit reached",
                    "User tickets complain that loading spinner spins forever (queries hung)"
                ],
                "evidence_against": [
                    "Auth-service is still functioning normally without DB timeout warnings, meaning PostgreSQL is still responding, just refusing new connections due to maxing out."
                ]
            }
        ]
    }


def analyze_hypotheses(timeline_str: str, past_incidents_str: str) -> dict:
    if is_gemini_active():
        try:
            if HAS_GENAI:
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel(GEMINI_MODEL)
                prompt = HYPOTHESIS_PROMPT.format(
                    timeline=timeline_str,
                    past_incidents=past_incidents_str
                )
                response = model.generate_content(prompt)
                text = response.text.strip()

                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]

                return json.loads(text.strip())
        except Exception as e:
            print(f"Error calling Gemini: {e}. Falling back to mock hypotheses.")

    return get_mock_hypotheses()
