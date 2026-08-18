import streamlit as st
from typing import List
from utils.schemas import NormalizedSignal

def render_timeline(timeline: List[NormalizedSignal]):
    st.subheader("Unified Incident Timeline")
    st.markdown("Correlated events across alerts, system logs, user tickets, and deployments:")
    
    for event in timeline:
        src = event.signal_type
        sev = event.severity
        ts = event.parsed_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = event.message
        comp = event.component
        
        badge_class = "bg-info"
        if src == "alert":
            badge_class = "bg-critical" if sev == "CRITICAL" else "bg-warning"
        elif src == "deploy":
            badge_class = "bg-deploy"
        elif src == "complaint":
            badge_class = "bg-complaint"
        elif sev in ["ERROR", "CRITICAL"]:
            badge_class = "bg-critical"
        elif sev == "WARNING":
            badge_class = "bg-warning"
            
        st.markdown(f"""
        <div class="timeline-item {sev.lower()}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <div>
                    <span class="timeline-source {badge_class}">{src}</span>
                    <span style="font-weight: 600; color: #1e293b;">{comp}</span>
                </div>
                <span class="timeline-time">{ts}</span>
            </div>
            <div style="color: #334155; font-size: 0.95rem;">{msg}</div>
        </div>
        """, unsafe_allow_html=True)
