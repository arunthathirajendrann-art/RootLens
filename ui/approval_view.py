import streamlit as st
from approval.approval_gate import record_approval_gate_decision
from learning.incident_memory import append_to_incident_memory


def render_approval_portal(recovery_data: dict, hypotheses_data: dict):
    st.subheader("Human-In-The-Loop Remediation Gate")
    st.markdown(
        "Review AI recovery proposal. No production action will be executed automatically without explicit operator authorization."
    )

    recoveries = recovery_data.get("recovery_actions", []) or recovery_data.get("recovery_proposal", [])
    if isinstance(recoveries, dict):
        recoveries = [recoveries]

    valid_recoveries = [r for r in recoveries if isinstance(r, dict) and bool(r.get("action"))]
    if not valid_recoveries:
        st.info("No recovery recommendations generated.")
        return

    options = [f"{r.get('action')} (Risk: {r.get('risk', 'MEDIUM')})" for r in valid_recoveries]
    selected_option = st.selectbox("Select Recovery Proposal", options)

    selected_recovery = next(
        (r for r in valid_recoveries if f"{r.get('action')} (Risk: {r.get('risk', 'MEDIUM')})" == selected_option),
        valid_recoveries[0],
    )

    st.markdown("### Proposal Details & Safety Constraints")
    st.markdown(f"**Proposed Objective:** {selected_recovery.get('action')}")
    st.markdown(f"**AI Rationale:** {selected_recovery.get('reason')}")

    risk_label = str(selected_recovery.get("risk", "MEDIUM")).upper()
    risk_color = "red" if risk_label == "HIGH" else "orange" if risk_label == "MEDIUM" else "green"

    st.markdown(
        f"**Risk Profile:** <span style='color:{risk_color}; font-weight:700;'>{risk_label}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("**Human Approval Required:** `True` (Operator Gate Active)")
    st.markdown("#### Verification Procedure (Simulated Preview Only - Zero Infrastructure Execution):")
    st.markdown(
        f"<div class='terminal-block'># PROPOSAL SIMULATION ONLY\n# Action: {selected_recovery.get('action')}\n# Reason: {selected_recovery.get('reason')}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 🔒 Operator Sign-off")

    col_op, col_com = st.columns([1, 2])
    with col_op:
        operator_name = st.text_input("Operator Username / Email", "site-reliability-lead@tcs.com")
    with col_com:
        operator_comments = st.text_input("Post-action comments / approval justification")

    gate_col1, gate_col2, gate_col3 = st.columns(3)

    if "action_status" not in st.session_state:
        st.session_state.action_status = None

    with gate_col1:
        if st.button("✅ APPROVE PROPOSAL (Simulated)", type="primary"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action", "Recovery Action"),
                "APPROVED",
                operator_name,
                operator_comments,
            )
            hypotheses = hypotheses_data.get("hypotheses", [])
            leading_hypothesis = (
                hypotheses[0].get("root_cause") or hypotheses[0].get("title", "Unknown") if hypotheses else "Unknown"
            )

            append_to_incident_memory(
                component="payment-service",
                symptoms="Operational anomaly & telemetry alert spike",
                root_cause=leading_hypothesis,
                recovery_action=selected_recovery.get("action", ""),
                status="APPROVED_PROPOSAL",
                operator_notes=f"Approved proposal by {operator_name}. Notes: {operator_comments}.",
            )
            st.rerun()

    with gate_col2:
        if st.button("❌ REJECT PROPOSAL"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action", "Recovery Action"),
                "REJECTED",
                operator_name,
                operator_comments,
            )

    with gate_col3:
        if st.button("🔍 REQUEST MORE EVIDENCE"):
            st.session_state.action_status = record_approval_gate_decision(
                selected_recovery.get("action", "Recovery Action"),
                "MORE_DIAGNOSTICS",
                operator_name,
                operator_comments,
            )

    if st.session_state.action_status:
        st.markdown("### Decision Status Log")
        status = st.session_state.action_status.get("status")
        if status == "APPROVED":
            st.success(
                f"**Decision Log:** [APPROVED] Proposal `{st.session_state.action_status.get('action')}` was approved by {st.session_state.action_status.get('operator')}. Saved to learning memory (Zero infrastructure execution)."
            )
        elif status == "REJECTED":
            st.error(
                f"**Decision Log:** [REJECTED] Proposal `{st.session_state.action_status.get('action')}` was rejected by {st.session_state.action_status.get('operator')}."
            )
        elif status == "MORE_DIAGNOSTICS":
            st.warning(
                "**Decision Log:** [HOLD] Operator requested additional diagnostic evidence before sign-off."
            )
