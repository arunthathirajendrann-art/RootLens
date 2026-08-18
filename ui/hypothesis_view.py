import streamlit as st
from typing import Any, Dict


def render_hypotheses(hypotheses_data: Dict[str, Any]):
    st.subheader("AI Competing Hypotheses Scorecard")
    st.markdown("Gemini model analysis of correlated UnifiedTimeline events:")

    hypotheses = hypotheses_data.get("hypotheses", [])
    if not hypotheses:
        st.info("No hypotheses available.")
        return

    h_col1, h_col2 = st.columns([1, 1])

    for idx, hyp in enumerate(hypotheses):
        col_to_use = h_col1 if idx % 2 == 0 else h_col2
        with col_to_use:
            title = hyp.get("root_cause") or hyp.get("title", f"Hypothesis {idx+1}")
            rank = hyp.get("rank", idx + 1)
            conf_val = hyp.get("confidence", 0.0)
            conf_percent = int(conf_val * 100) if isinstance(conf_val, (int, float)) else 0
            reasoning = hyp.get("reasoning_summary") or hyp.get("description", "")

            st.markdown(
                f"""
            <div class="hypothesis-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <h4 style="margin: 0; color: #0f172a; font-weight:600;">Rank {rank}: {title}</h4>
                    <span style="background: rgba(59, 130, 246, 0.15); color: #2563eb; border: 1px solid #93c5fd; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight:700;">
                        Confidence: {conf_percent}%
                    </span>
                </div>
                {f'<p style="color: #475569; font-size: 0.85rem; line-height: 1.4; margin-bottom: 10px;"><strong>Summary:</strong> {reasoning}</p>' if reasoning else ''}
            </div>
            """,
                unsafe_allow_html=True,
            )

            subcol1, subcol2 = st.columns(2)

            # Supporting evidence
            with subcol1:
                st.markdown("**✔️ Evidence FOR:**")
                supp_list = hyp.get("supporting_evidence") or hyp.get("evidence_for", [])
                if not supp_list:
                    st.markdown(
                        "- <span style='font-size:0.8rem; color:#64748b;'>None cited</span>",
                        unsafe_allow_html=True,
                    )
                for item in supp_list:
                    if isinstance(item, dict):
                        ev_id = item.get("event_id") or item.get("id", "")
                        reason = item.get("reason", "")
                        text = f"<strong>[{ev_id}]</strong> {reason}" if ev_id else reason
                    else:
                        text = str(item)
                    st.markdown(
                        f"- <span style='font-size:0.82rem; color:#065f46;'>{text}</span>",
                        unsafe_allow_html=True,
                    )

            # Contradicting evidence
            with subcol2:
                st.markdown("**❌ Evidence AGAINST:**")
                contra_list = hyp.get("contradicting_evidence") or hyp.get("evidence_against", [])
                if not contra_list:
                    st.markdown(
                        "- <span style='font-size:0.8rem; color:#64748b;'>None cited</span>",
                        unsafe_allow_html=True,
                    )
                for item in contra_list:
                    if isinstance(item, dict):
                        ev_id = item.get("event_id") or item.get("id", "")
                        reason = item.get("reason", "")
                        text = f"<strong>[{ev_id}]</strong> {reason}" if ev_id else reason
                    else:
                        text = str(item)
                    st.markdown(
                        f"- <span style='font-size:0.82rem; color:#991b1b;'>{text}</span>",
                        unsafe_allow_html=True,
                    )

            st.markdown("<hr style='border-color: #e2e8f0; margin: 12px 0;'/>", unsafe_allow_html=True)
