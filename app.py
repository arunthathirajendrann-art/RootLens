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

# Page configurations
st.set_page_config(
    page_title="Incident Commander AI",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling using glassmorphism and modern colors
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .metric-card {
        background: rgba(30, 41, 59, 0.45);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.15);
    }
    
    .timeline-item {
        border-left: 3px solid #3b82f6;
        padding-left: 20px;
        margin-bottom: 20px;
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
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 600;
    }
    
    .timeline-source {
        font-size: 0.75rem;
        text-transform: uppercase;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 4px;
        margin-right: 8px;
    }
    
    .bg-critical { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .bg-warning { background-color: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
    .bg-info { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .bg-deploy { background-color: rgba(168, 85, 247, 0.2); color: #a855f7; border: 1px solid #a855f7; }
    .bg-complaint { background-color: rgba(236, 72, 153, 0.2); color: #ec7299; border: 1px solid #ec7299; }
    
    .terminal-block {
        font-family: 'JetBrains Mono', monospace;
        background: #0f172a;
        color: #38bdf8;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #0ea5e9;
        margin: 10px 0;
        font-size: 0.9rem;
        overflow-x: auto;
    }
    
    .hypothesis-card {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        transition: transform 0.2s ease;
    }
    
    .hypothesis-card:hover {
        transform: translateY(-2px);
        border-color: rgba(59, 130, 246, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# Main Title & Subheader
st.markdown("""
<div style="display: flex; align-items: center; gap: 15px; margin-bottom: 25px;">
    <h1 style="margin:0; font-weight:800; background: linear-gradient(135deg, #6366f1, #3b82f6, #ec4899); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        🚨 Incident Commander AI
    </h1>
    <span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: 700; text-transform: uppercase;">
        Active Outage Triage
    </span>
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

# Sidebar settings
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    if is_gemini_active():
        st.success("Gemini API Status: Connected")
    else:
        st.warning("No API Key detected. Using local deterministic models.")
        
    st.markdown("---")
    st.markdown("### 💡 Active Scenario details")
    st.info("**Incident ID:** ACT-0921\n\n**Impact:** Checkout Failure / 500 Server Errors on Payment gateway.")
    st.markdown("---")
    st.markdown("Built for TCS Hackathon 2026")

# Load current historical incidents
past_incidents = load_historical_memory()

# Setup reasoning data once
timeline_str = format_timeline_for_prompt(st.session_state.timeline)
past_incidents_str = json.dumps(past_incidents, indent=2)

if 'hypotheses_data' not in st.session_state:
    with st.spinner("AI is generating competing root-cause hypotheses..."):
        st.session_state.hypotheses_data = analyze_hypotheses(timeline_str, past_incidents_str)
        st.session_state.diagnostics_data = plan_diagnostics(timeline_str, json.dumps(st.session_state.hypotheses_data))
        st.session_state.recovery_data = plan_recovery(timeline_str, json.dumps(st.session_state.hypotheses_data))

tab_dash, tab_reason, tab_recovery, tab_history = st.tabs([
    "📊 Telemetry & Timeline", 
    "🧠 AI Reasoning Hub", 
    "🛡️ Human Approval & Action Gate", 
    "📚 Operational Memory"
])

# Tab 1: Timeline
with tab_dash:
    col1, col2 = st.columns([2, 1])
    with col1:
        timeline_view.render_timeline(st.session_state.timeline)
    with col2:
        st.subheader("Metric Anomalies")
        metrics_csv_path = os.path.join(os.path.dirname(__file__), "data", "metrics.csv")
        if os.path.exists(metrics_csv_path):
            df_metrics = pd.read_csv(metrics_csv_path)
            
            st.write("Database Connection Pool Utilization")
            df_conn = df_metrics[df_metrics['metric_name'] == 'db_connections']
            st.line_chart(data=df_conn, x='timestamp', y='value', color="#ef4444")
            
            st.write("Upstream Service Latency (ms)")
            df_lat = df_metrics[df_metrics['metric_name'] == 'latency_ms']
            st.line_chart(data=df_lat, x='timestamp', y='value', color="#f59e0b")
        else:
            st.info("No metrics file found.")

# Tab 2: AI Reasoning
with tab_reason:
    hypothesis_view.render_hypotheses(st.session_state.hypotheses_data)
    st.markdown("---")
    diagnostic_view.render_diagnostics(st.session_state.diagnostics_data)

# Tab 3: Action Gate
with tab_recovery:
    approval_view.render_approval_portal(st.session_state.recovery_data, st.session_state.hypotheses_data)

# Tab 4: History list
with tab_history:
    st.subheader("Operational Memory (past_incidents.json)")
    st.markdown("These past incident profiles are dynamically read and injected into Gemini reasoning contexts:")
    
    # Reload fresh list
    fresh_history = load_historical_memory()
    for inc in fresh_history:
        st.markdown(f"""
        <div class="metric-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <strong>Incident {inc.get('incident_id')} ({inc.get('component')})</strong>
                <span class="timeline-source bg-info">{inc.get('status')}</span>
            </div>
            <div style="font-size:0.9rem; color:#cbd5e1;">
                <p><strong>Symptoms:</strong> {inc.get('symptoms')}</p>
                <p><strong>Root Cause:</strong> {inc.get('root_cause')}</p>
                <p><strong>Remediation:</strong> {inc.get('recovery_action')}</p>
                <p style="color:#94a3b8; font-style:italic;"><strong>Operator Notes:</strong> {inc.get('operator_notes')}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
