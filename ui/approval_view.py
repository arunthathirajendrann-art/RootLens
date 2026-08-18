import streamlit as st
import json
from approval.approval_gate import record_approval_gate_decision
from learning.incident_memory import append_to_incident_memory

def render_approval_portal(recovery_data: dict, hypotheses_data: dict):
    st.subheader("Human-In-The-Loop Remediation")
    st.markdown("Select a recovery playbook recommended by the AI. Review and execute only with explicit operational authorization.")
    
    recoveries = recovery_data.get("recovery_actions", [])
    if not recoveries:
        st.info("No recovery recommendations generated.")
        return
        
    options = [f"{r.get('action')} (Risk: {r.get('risk')})" for r in recoveries]
    selected_option = st.selectbox("Select Recovery Plan Option", options)
    
    selected_recovery = next(r for r in recoveries if f"{r.get('action')} (Risk: {r.get('risk')})" == selected_option)
    
    st.markdown("### Playbook Verification & Instructions")
    st.markdown(f"**Target Objective:** {selected_recovery.get('action')}")
    st.markdown(f"**AI Reasoning:** {selected_recovery.get('reason')}")
    
    risk_label = selected_recovery.get("risk")
    risk_color = "red" if risk_label == "HIGH" else "orange" if risk_label == "MEDIUM" else "green"
    
    st.markdown(f"**Risk Profile:** <span style='color:{risk_color}; font-weight:700;'>{risk_label}</span>", unsafe_allow_html=True)
    st.markdown("#### Execution Steps (Dry-run preview):")
    st.markdown(f"<div class='terminal-block'>{selected_recovery.get('instructions')}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🔒 Sign-off Credentials")
    
    col_op, col_com = st.columns([1, 2])
    with col_op:
        operator_name = st.text_input("Operator Username / Email", "site-reliability-lead@tcs.com")
    with col_com:
        operator_comments = st.text_input("Post-action comments / approvals justification")
        
    gate_col1, gate_col2, gate_col3 = st.columns(3)
    
    if 'action_status' not in st.session_state:
        st.session_state.action_status = None
        
    with gate_col1:
        if st.button("✅ APPROVE & EXECUTE", type="primary"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action"), 
                "APPROVED", 
                operator_name, 
                operator_comments
            )
            leading_hypothesis = hypotheses_data.get("hypotheses", [{}])[0].get("title", "Unknown")
            
            # Save to learning history log
            append_to_incident_memory(
                component="payment-api",
                symptoms="Checkout Failure, DB pool exhaustion",
                root_cause=leading_hypothesis,
                recovery_action=selected_recovery.get("action"),
                status="SUCCESSFUL",
                operator_notes=f"Approved by {operator_name}. Notes: {operator_comments}."
            )
            st.rerun()
            
    with gate_col2:
        if st.button("❌ REJECT & TERMINATE"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action"), 
                "REJECTED", 
                operator_name, 
                operator_comments
            )
            
    with gate_col3:
        if st.button("🔍 REQUEST MORE EVIDENCE"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action"), 
                "MORE_DIAGNOSTICS", 
                operator_name, 
                operator_comments
            )
            
    if st.session_state.action_status:
        st.markdown("### Action Status Logs")
        status = st.session_state.action_status.get("status")
        if status == "APPROVED":
            st.success(f"**Execution Log:** [SUCCESS] Action `{st.session_state.action_status.get('action')}` has been dispatched. Log updated.")
        elif status == "REJECTED":
            st.error(f"**Execution Log:** [ABORTED] Action `{st.session_state.action_status.get('action')}` was rejected by {st.session_state.action_status.get('operator')}.")
        elif status == "MORE_DIAGNOSTICS":
            st.warning(f"**Execution Log:** [HOLD] Requesting more diagnostic evidence.")
