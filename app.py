# ==========================================
# OWNED BY: MEMBER D (UI & Operator Gate)
# Responsibility: Orchestrate visual timeline tabs and dashboards
# ==========================================

import os
import json
import pandas as pd
import streamlit as st
from datetime import datetime

from ingestion.normalizer import normalize_initial_incident_signals, normalize_late_evidence
from correlation.correlation_engine import correlate_events, re_correlate
from correlation.timeline_builder import build_timeline
from reasoning.hypothesis_engine import (
    analyze_unified_timeline,
    timeline_to_reasoning_dicts,
    _generate_mock_analysis,
)
from utils.config import PAST_INCIDENTS_PATH, is_gemini_active

import ui.timeline_view as timeline_view
import ui.hypothesis_view as hypothesis_view
import ui.diagnostic_view as diagnostic_view
import ui.approval_view as approval_view

# Page configurations for a clean interface
st.set_page_config(
    page_title="RootLens Incident Commander",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom minimalist light-theme CSS
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
        background-color: #ffffff;
    }
    
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    
    .timeline-item {
        border-left: 2px solid #cbd5e1;
        padding-left: 16px;
        margin-bottom: 14px;
        position: relative;
    }
    
    .timeline-item.critical { border-left-color: #ef4444; }
    .timeline-item.warning { border-left-color: #f59e0b; }
    .timeline-item.info { border-left-color: #10b981; }
    .timeline-item.deploy { border-left-color: #a855f7; }
    
    .timeline-time {
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 500;
    }
    
    .timeline-source {
        font-size: 0.7rem;
        text-transform: uppercase;
        font-weight: 700;
        padding: 2px 6px;
        border-radius: 4px;
        margin-right: 6px;
    }
    
    .bg-critical { background-color: #fef2f2; color: #991b1b; border: 1px solid #fee2e2; }
    .bg-warning { background-color: #fffbeb; color: #92400e; border: 1px solid #fef3c7; }
    .bg-info { background-color: #f0fdf4; color: #166534; border: 1px solid #dcfce7; }
    .bg-deploy { background-color: #faf5ff; color: #6b21a8; border: 1px solid #f3e8ff; }
    .bg-complaint { background-color: #fdf2f8; color: #9d174d; border: 1px solid #fce7f3; }
    
    .terminal-block {
        font-family: 'JetBrains Mono', monospace;
        background: #f1f5f9;
        color: #0f172a;
        padding: 12px;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
        margin: 8px 0;
        font-size: 0.85rem;
    }
    
    .hypothesis-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
</style>
""",
    unsafe_allow_html=True,
)

# Main Title & Subheader
st.markdown(
    """
<div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 20px;">
    <div style="display: flex; align-items: center; gap: 10px;">
        <h2 style="margin:0; font-weight:700; color: #0f172a;">RootLens Incident Commander</h2>
        <span style="background-color: #fef2f2; color: #b91c1c; border: 1px solid #fee2e2; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">
            ACTIVE INCIDENT
        </span>
    </div>
    <div style="color: #64748b; font-size: 0.85rem;">
        Active ID: <strong>ACT-0921</strong> | Target: <strong>payment-service</strong>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


def load_historical_memory():
    if os.path.exists(PAST_INCIDENTS_PATH):
        with open(PAST_INCIDENTS_PATH, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []


# 1. Pipeline Initialization (Member A -> Member B -> Member C)
if "unified_timeline" not in st.session_state:
    raw_events = normalize_initial_incident_signals()
    clusters = correlate_events(raw_events)
    st.session_state.unified_timeline = build_timeline(clusters)

if "late_evidence_injected" not in st.session_state:
    st.session_state.late_evidence_injected = False

if "analysis_result" not in st.session_state:
    with st.spinner("AI is analyzing Member B UnifiedTimeline..."):
        try:
            st.session_state.analysis_result = analyze_unified_timeline(st.session_state.unified_timeline)
        except Exception as exc:
            st.warning(f"AI Reasoning warning: {exc}. Using deterministic fallback analyzer.")
            formatted_dicts = timeline_to_reasoning_dicts(st.session_state.unified_timeline)
            st.session_state.analysis_result = _generate_mock_analysis(formatted_dicts)

# 2. Extract analysis structures for Member D views
analysis = st.session_state.analysis_result
hypotheses_data = {"hypotheses": analysis.get("hypotheses", [])}
diagnostics_data = {"diagnostic_steps": analysis.get("diagnostic_sequence", [])}

recovery_prop = analysis.get("recovery_proposal", {})
if isinstance(recovery_prop, dict) and recovery_prop:
    recovery_data = {"recovery_actions": [recovery_prop]}
else:
    recovery_data = {"recovery_actions": analysis.get("recovery_actions", [])}

# 3. Late Evidence Demo Control (Member B Re-Correlation -> Member C Re-Analysis)
st.markdown("### ⚡ Live Incident Operations Control")
col_ctrl1, col_ctrl2 = st.columns([2, 1])

with col_ctrl1:
    if not st.session_state.late_evidence_injected:
        if st.button("⚡ Inject Late-Arriving Evidence & Re-correlate", type="secondary"):
            with st.spinner("Re-correlating with late-arriving evidence & updating analysis..."):
                late_events = normalize_late_evidence()
                re_result = re_correlate(st.session_state.unified_timeline, late_events)
                st.session_state.unified_timeline = re_result.timeline
                st.session_state.late_evidence_injected = True
                try:
                    st.session_state.analysis_result = analyze_unified_timeline(st.session_state.unified_timeline)
                except Exception as exc:
                    st.warning(f"AI Reasoning update warning: {exc}. Using fallback analyzer.")
                    formatted_dicts = timeline_to_reasoning_dicts(st.session_state.unified_timeline)
                    st.session_state.analysis_result = _generate_mock_analysis(formatted_dicts)
                st.rerun()
    else:
        st.success(
            f"⚡ Late-arriving evidence injected! UnifiedTimeline updated to {st.session_state.unified_timeline.event_count} events across components: {', '.join(st.session_state.unified_timeline.components)}"
        )

with col_ctrl2:
    if st.button("🔄 Reset Initial Timeline"):
        st.session_state.clear()
        st.rerun()

st.markdown("---")

# 4. Member D UI Layout
col_left, col_right = st.columns([1, 1], gap="medium")

with col_left:
    st.markdown("### 🛡️ Operational Gate")
    approval_view.render_approval_portal(recovery_data, hypotheses_data)

    st.markdown("---")

    st.markdown("### 🧠 AI Root-Cause Analysis")
    hypothesis_view.render_hypotheses(hypotheses_data)

    st.markdown("---")
    diagnostic_view.render_diagnostics(diagnostics_data)

with col_right:
    timeline_view.render_timeline(st.session_state.unified_timeline)

    st.markdown("---")
    st.subheader("System Metrics")
    metrics_csv_path = os.path.join(os.path.dirname(__file__), "data", "metrics.csv")
    if os.path.exists(metrics_csv_path):
        df_metrics = pd.read_csv(metrics_csv_path)
        services = df_metrics["service"].unique().tolist()
        selected_service = st.selectbox(
            "Select Target Service",
            services,
            index=services.index("payment-service") if "payment-service" in services else 0,
        )
        df_svc = df_metrics[df_metrics["service"] == selected_service]

        st.write(f"CPU Utilization % ({selected_service})")
        st.line_chart(data=df_svc, x="timestamp", y="cpu_utilization_pct", color="#6366f1")

        st.write(f"p99 Response Latency ({selected_service})")
        st.line_chart(data=df_svc, x="timestamp", y="p99_latency_ms", color="#f59e0b")
    else:
        st.info("No metrics file found.")

st.markdown("---")
with st.expander("📚 Operational Memory Log History (RAG Reference List)"):
    fresh_history = load_historical_memory()
    for inc in fresh_history:
        st.markdown(
            f"""
        <div class="metric-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <strong>Incident {inc.get('incident_id')} ({inc.get('component')})</strong>
                <span style="font-size:0.75rem; color:#1e293b; background:#f1f5f9; padding:2px 6px; border-radius:4px; font-weight:600;">{inc.get('status')}</span>
            </div>
            <div style="font-size:0.85rem; color:#475569;">
                <p style="margin:4px 0;"><strong>Symptoms:</strong> {inc.get('symptoms')}</p>
                <p style="margin:4px 0;"><strong>Root Cause:</strong> {inc.get('root_cause')}</p>
                <p style="margin:4px 0;"><strong>Remediation:</strong> {inc.get('recovery_action')}</p>
                <p style="margin:4px 0; color:#64748b; font-style:italic;"><strong>Operator Notes:</strong> {inc.get('operator_notes')}</p>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
