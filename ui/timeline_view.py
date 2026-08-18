import streamlit as st
from typing import Any
from datetime import datetime


def render_timeline(timeline: Any):
    st.subheader("Unified Incident Timeline")
    st.markdown("Correlated events across alerts, system logs, user tickets, deployments, and late evidence:")

    if hasattr(timeline, "entries"):
        entries = timeline.entries
    elif isinstance(timeline, dict) and "entries" in timeline:
        entries = timeline["entries"]
    elif isinstance(timeline, list):
        entries = timeline
    else:
        entries = [timeline]

    if not entries:
        st.info("No timeline events to display.")
        return

    for event in entries:
        src = getattr(event, "source", event.get("source") if isinstance(event, dict) else "unknown")
        sev = getattr(event, "severity", event.get("severity") if isinstance(event, dict) else "INFO")
        ts_raw = getattr(
            event,
            "timestamp",
            getattr(event, "parsed_timestamp", event.get("timestamp") if isinstance(event, dict) else ""),
        )
        if isinstance(ts_raw, datetime):
            ts = ts_raw.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            ts = str(ts_raw)

        msg = getattr(
            event,
            "description",
            getattr(event, "message", event.get("description") if isinstance(event, dict) else ""),
        )
        comp = getattr(
            event,
            "component",
            getattr(event, "service", event.get("component") if isinstance(event, dict) else "unknown"),
        )
        ev_id = getattr(
            event,
            "event_id",
            getattr(event, "signal_id", event.get("event_id") if isinstance(event, dict) else ""),
        )

        badge_class = "bg-info"
        if src in ["alerts", "alert"]:
            badge_class = "bg-critical" if sev in ["CRITICAL", "HIGH"] else "bg-warning"
        elif src in ["deploys", "deploy"]:
            badge_class = "bg-deploy"
        elif src in ["complaints", "complaint"]:
            badge_class = "bg-complaint"
        elif src in ["config"]:
            badge_class = "bg-warning"
        elif src in ["gc_profiler"]:
            badge_class = "bg-critical" if sev == "CRITICAL" else "bg-warning"
        elif sev in ["ERROR", "CRITICAL"]:
            badge_class = "bg-critical"
        elif sev == "WARNING":
            badge_class = "bg-warning"

        st.markdown(
            f"""
        <div class="timeline-item {sev.lower()}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <div>
                    <span class="timeline-source {badge_class}">{src}</span>
                    <span style="font-weight: 600; color: #0f172a;">{comp}</span>
                    <span style="font-size: 0.75rem; color: #64748b; margin-left: 6px;">[{ev_id}]</span>
                </div>
                <span class="timeline-time">{ts}</span>
            </div>
            <div style="color: #334155; font-size: 0.9rem;">{msg}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
