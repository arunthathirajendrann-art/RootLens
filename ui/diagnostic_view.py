import streamlit as st

def render_diagnostics(diagnostics_data: dict):
    st.subheader("Suggested Diagnostic Verification Procedures")
    st.markdown("Prioritized triage operations to prove or disprove the hypotheses:")
    
    diagnostics = diagnostics_data.get("diagnostic_steps", [])
    for diag in diagnostics:
        p_badge = f"<span class='timeline-source bg-warning'>Priority: {diag.get('priority')}</span>"
        if diag.get('priority') == 'HIGH':
            p_badge = f"<span class='timeline-source bg-critical'>Priority: HIGH</span>"
            
        st.markdown(f"""
        <div style="margin-bottom: 15px;">
            <div style="display:flex; align-items:center; gap: 10px; margin-bottom: 5px;">
                <strong>Step {diag.get('step')}: {diag.get('purpose')}</strong>
                {p_badge}
            </div>
            <div class="terminal-block">$ {diag.get('command_or_action')}</div>
        </div>
        """, unsafe_allow_html=True)
