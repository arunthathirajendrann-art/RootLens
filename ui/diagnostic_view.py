import streamlit as st
from typing import Any, Dict


def render_diagnostics(diagnostics_data: Dict[str, Any]):
    st.subheader("Suggested Diagnostic Verification Procedures")
    st.markdown("Prioritized triage operations to prove or disprove hypotheses:")

    diagnostics = diagnostics_data.get("diagnostic_steps", []) or diagnostics_data.get("diagnostic_sequence", [])
    if not diagnostics:
        st.info("No diagnostic steps generated.")
        return

    for idx, diag in enumerate(diagnostics, start=1):
        step_num = diag.get("priority") or diag.get("step") or idx
        action = diag.get("diagnostic") or diag.get("command_or_action", "")
        tests_hyp = diag.get("tests_hypothesis") or diag.get("purpose", "")
        expected = diag.get("expected_signal", "")

        p_badge = f"<span class='timeline-source bg-warning'>Priority: {step_num}</span>"
        if str(step_num) in ("1", "HIGH"):
            p_badge = f"<span class='timeline-source bg-critical'>Priority: 1</span>"

        st.markdown(
            f"""
        <div style="margin-bottom: 15px;">
            <div style="display:flex; align-items:center; gap: 10px; margin-bottom: 5px;">
                <strong>Diagnostic #{idx}: {tests_hyp}</strong>
                {p_badge}
            </div>
            <div class="terminal-block">$ {action}</div>
            {f'<div style="font-size:0.8rem; color:#475569; margin-top:3px;"><em>Expected Signal:</em> {expected}</div>' if expected else ''}
        </div>
        """,
            unsafe_allow_html=True,
        )
