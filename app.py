import os
import json
import zipfile
import tempfile
import pandas as pd
import streamlit as st
from datetime import datetime

from ingestion.normalizer import normalize_initial_incident_signals
from correlation.correlation_engine import correlate_events
from correlation.timeline_builder import build_timeline
from reasoning.hypothesis_engine import analyze_unified_timeline, timeline_to_reasoning_dicts, _generate_mock_analysis
from utils.config import PAST_INCIDENTS_PATH

import ui.timeline_view as timeline_view
import ui.hypothesis_view as hypothesis_view
import ui.diagnostic_view as diagnostic_view
import ui.approval_view as approval_view

# Page configurations for a clean interface
st.set_page_config(
    page_title="RootLens Incident Copilot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #1e293b; background-color: #ffffff; }
    .metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px 0 rgba(0,0,0,0.05); }
    .terminal-block { font-family: 'JetBrains Mono', monospace; background: #f1f5f9; padding: 12px; border-radius: 6px; font-size: 0.85rem; }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 20px;">
    <h2 style="margin:0; font-weight:700; color: #0f172a;">RootLens Incident Copilot</h2>
</div>
""", unsafe_allow_html=True)

# State initialization
if "current_screen" not in st.session_state:
    st.session_state.current_screen = 1

if "uploaded_data" not in st.session_state:
    st.session_state.uploaded_data = {}

if "source_repo_path" not in st.session_state:
    st.session_state.source_repo_path = None

if "unified_timeline" not in st.session_state:
    st.session_state.unified_timeline = None

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

def change_screen(screen_num):
    st.session_state.current_screen = screen_num

# Screen 1: Upload
def render_upload_screen():
    st.subheader("Screen 1: Upload Incident Data & Source Code")
    st.write("Upload telemetry signals and the service source repository to begin analysis.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Telemetry Signals (JSON/CSV)**")
        alerts_file = st.file_uploader("Alerts (alerts.json)", type=['json'])
        logs_file = st.file_uploader("Logs (logs.json)", type=['json'])
        metrics_file = st.file_uploader("Metrics (metrics.csv)", type=['csv'])
        deploys_file = st.file_uploader("Deployments (deploys.json)", type=['json'])
        complaints_file = st.file_uploader("Complaints (complaints.json)", type=['json'])
        
    with col2:
        st.markdown("**Source Code Repository**")
        source_zip = st.file_uploader("Source Code (.zip)", type=['zip'])
    
    if st.button("Analyze Incident", type="primary"):
        if source_zip is not None:
            # Extract ZIP to temp directory
            temp_dir = tempfile.mkdtemp(prefix="rootlens_repo_")
            with zipfile.ZipFile(source_zip, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            st.session_state.source_repo_path = temp_dir
        
        # Read uploaded files into dicts
        try:
            alerts_data = json.load(alerts_file) if alerts_file else []
            logs_data = json.load(logs_file) if logs_file else []
            metrics_data = pd.read_csv(metrics_file).to_dict(orient="records") if metrics_file else []
            deploys_data = json.load(deploys_file) if deploys_file else []
            complaints_data = json.load(complaints_file) if complaints_file else []
            
            st.session_state.uploaded_data = {
                "alerts": alerts_data,
                "logs": logs_data,
                "metrics": metrics_data,
                "deploys": deploys_data,
                "complaints": complaints_data
            }
            change_screen(2)
            st.rerun()
        except Exception as e:
            st.error(f"Error parsing uploaded files: {e}")

# Screen 2: Timeline
def render_timeline_screen():
    st.subheader("Screen 2: Correlated Timeline")
    st.write("Unified chronological view of all uploaded signals.")
    
    if not st.session_state.unified_timeline:
        with st.spinner("Building timeline from uploaded data..."):
            raw_data = st.session_state.uploaded_data
            raw_events = normalize_initial_incident_signals(raw_signals=raw_data)
            clusters = correlate_events(raw_events)
            st.session_state.unified_timeline = build_timeline(clusters)
            
    timeline_view.render_timeline(st.session_state.unified_timeline)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back to Upload"):
            change_screen(1)
            st.rerun()
    with col2:
        if st.button("Generate Hypotheses", type="primary"):
            change_screen(3)
            st.rerun()

# Screen 3: Hypotheses
def render_hypotheses_screen():
    st.subheader("Screen 3: Hypotheses & Code Evidence")
    
    if not st.session_state.analysis_result:
        with st.spinner("AI is analyzing timeline against source code..."):
            st.session_state.analysis_result = analyze_unified_timeline(
                st.session_state.unified_timeline,
                source_repo_path=st.session_state.source_repo_path
            )
            
    analysis = st.session_state.analysis_result
    
    for hyp in analysis.get("hypotheses", []):
        st.markdown(f"### Rank {hyp.get('rank')}: {hyp.get('root_cause')}")
        st.write(f"**Confidence**: {hyp.get('confidence')}")
        st.write(f"**Summary**: {hyp.get('reasoning_summary')}")
        
        file_path = hyp.get("implicated_file")
        if file_path:
            st.markdown(f"**Implicated File**: `{file_path}` (Line {hyp.get('implicated_line')})")
            st.code(hyp.get("source_snippet", ""), language="python")
        st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back to Timeline"):
            change_screen(2)
            st.rerun()
    with col2:
        if st.button("View Recommended Fix", type="primary"):
            change_screen(4)
            st.rerun()

# Screen 4: Fix
def render_fix_screen():
    st.subheader("Screen 4: Recommended Fix")
    
    analysis = st.session_state.analysis_result
    fix = analysis.get("recommended_fix", {})
    
    if fix:
        st.markdown(f"**Target File**: `{fix.get('file')}`")
        st.markdown(f"**Explanation**: {fix.get('explanation')}")
        st.markdown(f"**Risk Profile**: {fix.get('risk')}")
        
        col_diff1, col_diff2 = st.columns(2)
        with col_diff1:
            st.markdown("🔴 **Before**")
            st.code(fix.get("diff_before", ""), language="python")
        with col_diff2:
            st.markdown("🟢 **After**")
            st.code(fix.get("diff_after", ""), language="python")
    else:
        st.info("No automated fix recommended by AI.")
        
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Back to Hypotheses"):
            change_screen(3)
            st.rerun()
    with col2:
        if st.button("Reject / Alternative"):
            st.warning("Fix rejected. In a real system, this would prompt the AI for an alternative.")
    with col3:
        if st.button("Approve & Apply Fix", type="primary") and fix:
            # Apply fix logic
            repo_path = st.session_state.source_repo_path
            if repo_path and fix.get("file"):
                target_file = os.path.join(repo_path, fix.get("file"))
                if os.path.exists(target_file):
                    try:
                        with open(target_file, "r") as f:
                            content = f.read()
                        new_content = content.replace(fix.get("diff_before", ""), fix.get("diff_after", ""))
                        with open(target_file, "w") as f:
                            f.write(new_content)
                        st.session_state.fix_applied = True
                    except Exception as e:
                        st.session_state.fix_error = str(e)
            change_screen(5)
            st.rerun()

# Screen 5: Result
def render_result_screen():
    st.subheader("Screen 5: Result")
    
    if getattr(st.session_state, "fix_error", None):
        st.error(f"Failed to apply fix: {st.session_state.fix_error}")
    elif getattr(st.session_state, "fix_applied", False):
        st.success("Fix successfully applied to source code.")
        analysis = st.session_state.analysis_result
        fix = analysis.get("recommended_fix", {})
        
        msg = f"Auto-remediation: Fixed issue in {fix.get('file')}\n\nReason: {fix.get('explanation')}"
        st.code(f"git commit -m '{msg}'", language="bash")
    else:
        st.warning("No fix applied.")
    
    if st.button("Start New Analysis"):
        st.session_state.clear()
        st.rerun()

# State Router
if st.session_state.current_screen == 1:
    render_upload_screen()
elif st.session_state.current_screen == 2:
    render_timeline_screen()
elif st.session_state.current_screen == 3:
    render_hypotheses_screen()
elif st.session_state.current_screen == 4:
    render_fix_screen()
elif st.session_state.current_screen == 5:
    render_result_screen()
