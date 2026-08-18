# ==========================================
# OWNED BY: MEMBER D (UI & Operator Gate)
# Responsibility: Orchestrate visual timeline tabs and dashboards
# ==========================================

import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime

from ingestion.normalizer import ingest_all_signals
from correlation.timeline_builder import build_chronological_timeline, format_timeline_for_prompt
from correlation.correlation_engine import correlate_incident_context
from reasoning.hypothesis_engine import analyze_hypotheses
from recovery.diagnostic_planner import plan_diagnostics
from recovery.recovery_planner import plan_recovery
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
    initial_sidebar_state="collapsed"
)

# Custom minimalist light-theme CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
        background-color: #ffffff;
    }
    
    /* Clean, soft grey card styling */
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
    
    .timeline-item.critical {
        border-left-color: #ef4444;
    }
    
    .timeline-item.warning {
        border-left-color: #f59e0b;
    }
    
    .timeline-item.info {
        border-left-color: #10b981;
    }
    
    .timeline-item.deploy {
        border-left-color: #a855f7;
    }
    
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
""", unsafe_allow_html=True)

# Main Title & Subheader
st.markdown("""
<div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 20px;">
    <div style="display: flex; align-items: center; gap: 10px;">
        <h2 style="margin:0; font-weight:700; color: #0f172a;">RootLens Incident Control</h2>
        <span style="background-color: #fef2f2; color: #b91c1c; border: 1px solid #fee2e2; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">
            ACTIVE INCIDENT
        </span>
    </div>
    <div style="color: #64748b; font-size: 0.85rem;">
        Active ID: <strong>ACT-0921</strong> | Target: <strong>payment-service</strong>
    </div>
</div>
""", unsafe_allow_html=True)

# Helper to load historical incident database
def load_historical_memory():
    if os.path.exists(PAST_INCIDENTS_PATH):
        with open(PAST_INCIDENTS_PATH, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

# Initialize state
if 'all_signals' not in st.session_state:
    st.session_state.all_signals = ingest_all_signals()

if 'timeline' not in st.session_state:
    st.session_state.timeline = build_chronological_timeline(st.session_state.all_signals)

past_incidents = load_historical_memory()

# Setup reasoning data once
timeline_str = format_timeline_for_prompt(st.session_state.timeline)
past_incidents_str = json.dumps(past_incidents, indent=2)

if 'hypotheses_data' not in st.session_state:
    with st.spinner("AI is generating competing root-cause hypotheses..."):
        st.session_state.hypotheses_data = analyze_hypotheses(timeline_str, past_incidents_str)
        st.session_state.diagnostics_data = plan_diagnostics(timeline_str, json.dumps(st.session_state.hypotheses_data))
        st.session_state.recovery_data = plan_recovery(timeline_str, json.dumps(st.session_state.hypotheses_data))

# Layout the page cleanly - Triage & Approval right in the front
col_left, col_right = st.columns([1, 1], gap="medium")

# LEFT COLUMN: Approval Gate, AI Hypotheses & Troubleshooting (Action Items)
with col_left:
    st.markdown("### 🛡️ Operational Gate")
    # Interactive portal right in front
    approval_view.render_approval_portal(st.session_state.recovery_data, st.session_state.hypotheses_data)
    
    st.markdown("---")
    
    st.markdown("### 🧠 AI Root-Cause Analysis")
    hypothesis_view.render_hypotheses(st.session_state.hypotheses_data)
    
    st.markdown("---")
    diagnostic_view.render_diagnostics(st.session_state.diagnostics_data)

# RIGHT COLUMN: Telemetry Signal log, Graphs, & Historical memory database
with col_right:
    # Render unified timeline logs
    timeline_view.render_timeline(st.session_state.timeline)
    
    st.markdown("---")
    st.subheader("System Metrics")
    metrics_csv_path = os.path.join(os.path.dirname(__file__), "data", "metrics.csv")
    if os.path.exists(metrics_csv_path):
        df_metrics = pd.read_csv(metrics_csv_path)
        services = df_metrics['service'].unique().tolist()
        selected_service = st.selectbox("Select Target Service", services, index=services.index("payment-service") if "payment-service" in services else 0)
        df_svc = df_metrics[df_metrics['service'] == selected_service]
        
        st.write(f"CPU Utilization % ({selected_service})")
        st.line_chart(data=df_svc, x='timestamp', y='cpu_utilization_pct', color="#6366f1")
        
        st.write(f"p99 Response Latency ({selected_service})")
        st.line_chart(data=df_svc, x='timestamp', y='p99_latency_ms', color="#f59e0b")
    else:
        st.info("No metrics file found.")

st.markdown("---")
# Clean collapsible history list to keep page minimal
with st.expander("📚 Operational Memory Log History (RAG Reference List)"):
    fresh_history = load_historical_memory()
    for inc in fresh_history:
        st.markdown(f"""
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
        """, unsafe_allow_html=True)
