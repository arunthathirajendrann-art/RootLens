import streamlit as st

def render_hypotheses(hypotheses_data: dict):
    st.subheader("AI Competing Hypotheses Scorecard")
    st.markdown("Gemini model analysis of timeline events relative to patterns in past operational memory:")
    
    hypotheses = hypotheses_data.get("hypotheses", [])
    
    h_col1, h_col2 = st.columns([1, 1])
    
    for idx, hyp in enumerate(hypotheses):
        col_to_use = h_col1 if idx % 2 == 0 else h_col2
        with col_to_use:
            conf_val = hyp.get("confidence", 0.0)
            conf_percent = int(conf_val * 100)
            
            st.markdown(f"""
            <div class="hypothesis-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <h4 style="margin: 0; color: #f8fafc; font-weight:600;">{hyp.get('title')}</h4>
                    <span style="background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid #3b82f6; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight:700;">
                        Confidence: {conf_percent}%
                    </span>
                </div>
                <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 15px;">{hyp.get('description')}</p>
            </div>
            """, unsafe_allow_html=True)
            
            subcol1, subcol2 = st.columns(2)
            with subcol1:
                st.markdown("**✔️ Evidence FOR:**")
                for ev in hyp.get("evidence_for", []):
                    st.markdown(f"- <span style='font-size:0.85rem; color:#a7f3d0;'>{ev}</span>", unsafe_allow_html=True)
            with subcol2:
                st.markdown("**❌ Evidence AGAINST:**")
                for ev in hyp.get("evidence_against", []):
                    st.markdown(f"- <span style='font-size:0.85rem; color:#fca5a5;'>{ev}</span>", unsafe_allow_html=True)
            st.markdown("<hr style='border-color: rgba(255,255,255,0.05);'/>", unsafe_allow_html=True)
