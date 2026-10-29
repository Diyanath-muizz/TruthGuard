"""
ui/chat.py
──────────
Ask TruthGuard — Premium Multi-Agent Verification Workspace.
Enables asking natural language questions, executing the 4-agent LangGraph workflow,
auditing adversarial findings, inspecting evidence provenance, and reading
explainable trust rationales.
"""

from __future__ import annotations

import streamlit as st
from agents import VerificationStatus, WorkflowState
from database import repository
from ui.styles import PALETTE, render_status_pill
from workflows.question_answering_graph import run_qa_workflow


def render_chat(db_session):
    if not db_session:
        st.error("Database connection unavailable.")
        return

    # Hero / Header Banner
    st.markdown(
        """
        <div class="tg-hero">
            <div class="tg-hero-tag">ADVERSARIAL VERIFICATION WORKSPACE</div>
            <h1 class="tg-hero-title">Ask. Challenge. Verify.</h1>
            <p class="tg-hero-subtitle">
                Ask questions across your documents and inspect the evidence behind every answer.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    all_docs = repository.get_all_documents(db_session)
    if not all_docs:
        st.markdown(
            """
            <div class="tg-card" style="border-left: 4px solid #D97706; padding: 16px 20px;">
                <div style="font-weight: 600; color: #92400E; margin-bottom: 4px;">⚠️ Document Knowledge Base Empty</div>
                <div style="font-size: 0.88rem; color: #78350F;">
                    Please upload policies, amendments, or run the synthetic initialization script to index documents before asking questions.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("📄 Open Document Management"):
            st.session_state["nav_page"] = "📄 Documents"
            st.rerun()

    # Pre-configured Sample Demonstration Queries
    st.markdown(
        """
        <div style="font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #697586; margin-bottom: 8px;">
            Sample Demonstration Queries
        </div>
        """,
        unsafe_allow_html=True,
    )

    sample_col1, sample_col2, sample_col3 = st.columns(3)
    sample_selected = None

    with sample_col1:
        if st.button("🌴 Leave Entitlement (Supersession)", use_container_width=True):
            sample_selected = "How many days of annual leave are employees entitled to?"
    with sample_col2:
        if st.button("🏢 Remote Work (Equal Conflict)", use_container_width=True):
            sample_selected = "What is the policy for working remotely?"
    with sample_col3:
        if st.button("🦷 Dental Implants (Abstention)", use_container_width=True):
            sample_selected = "Does company insurance cover adult orthodontic dental implants?"

    # Manage input state
    default_text = ""
    if sample_selected:
        st.session_state["qa_input_box"] = sample_selected
        default_text = sample_selected

    # Main Input Area
    question_text = st.text_input(
        "Ask a policy or compliance question:",
        value=st.session_state.get("qa_input_box", default_text),
        placeholder="e.g. How many days of annual leave are employees entitled to?",
        key="qa_input_box",
    )

    col_btn, _ = st.columns([2.5, 7.5])
    with col_btn:
        submit = st.button("🛡️ Verify & Answer", type="primary", use_container_width=True)

    # Execute QA workflow
    if (submit or sample_selected) and question_text.strip():
        with st.status("Executing TruthGuard multi-agent pipeline...", expanded=True) as status_box:
            st.write("🔍 **1. Retriever Agent:** Executing hybrid dense vector search + BM25 reciprocal rank fusion...")
            st.write("✍️ **2. Synthesizer Agent:** Extracting atomic claims grounded strictly in evidence (zero compromise blending)...")
            st.write("🧐 **3. Adversarial Critic Agent:** Cross-checking numeric values, supersession status, and dates...")
            st.write("⚖️ **4. Resolution Agent:** Enforcing institutional authority rules and producing final determination...")

            state: WorkflowState = run_qa_workflow(
                question=question_text.strip(),
                db_session=db_session,
                max_revisions=2,
            )
            status_box.update(label="Verification Pipeline Complete", state="complete", expanded=False)

        st.session_state["latest_qa_state"] = state

    # Render Results Workspace
    latest_state: WorkflowState = st.session_state.get("latest_qa_state")
    if latest_state and latest_state.resolution_output:
        res = latest_state.resolution_output
        critic = latest_state.critic_output

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

        # Status Pill and Heading
        status_pill = render_status_pill(res.status.value)
        source_count = len(res.citations) if res.citations else 0

        st.markdown(
            f"""
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <h2 style="font-size: 1.25rem; font-weight: 700; color: #172033; margin: 0;">Verified Determination</h2>
                    {status_pill}
                </div>
                <span style="font-size: 0.8rem; color: #697586;">
                    {source_count} Supporting Source{'s' if source_count != 1 else ''} Grounded
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Answer Presentation Panel with Status-Specific Left Border
        border_color = PALETTE['primary']
        if res.status == VerificationStatus.VERIFIED:
            border_color = PALETTE['status_verified_text']
        elif res.status in {VerificationStatus.CONFLICT_DETECTED, VerificationStatus.HUMAN_REVIEW_REQUIRED}:
            border_color = PALETTE['status_conflict_text']
        elif res.status == VerificationStatus.VERIFIED_WITH_WARNINGS:
            border_color = PALETTE['status_warning_text']
        elif res.status == VerificationStatus.ABSTAINED:
            border_color = PALETTE['status_neutral_text']

        st.markdown(
            f"""
            <div class="tg-card" style="border-left: 5px solid {border_color}; padding: 22px 24px; background: #FFFFFF;">
                <div style="font-size: 1.05rem; line-height: 1.65; color: #172033; font-weight: 450;">
                    {res.final_answer.replace(chr(10), '<br>')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Specialized Section: Why This Answer Is Trusted
        st.markdown(
            f"""
            <div class="tg-card" style="background: #FAFAFC; border: 1px solid #E2E8F0; padding: 20px 22px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                    <span style="font-size: 1.1rem;">⚖️</span>
                    <span style="font-weight: 700; font-size: 0.98rem; color: #172033;">Why This Answer Is Trusted</span>
                </div>
                <div style="font-size: 0.9rem; color: #334155; line-height: 1.6;">
                    {res.trust_explanation.replace(chr(10), '<br>')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Outdated Sources Callout
        if res.outdated_sources:
            outdated_items = "".join([
                f"<li style='margin-bottom: 4px;'><b>{o.filename}</b> (Type: {o.doc_type}, Version: {o.version or 'N/A'}, Authority Level: {o.authority_level})</li>"
                for o in res.outdated_sources
            ])
            st.markdown(
                f"""
                <div class="tg-card" style="border-left: 4px solid {PALETTE['status_warning_text']}; background: {PALETTE['status_warning_bg']}; padding: 16px 20px;">
                    <div style="font-weight: 600; color: {PALETTE['status_warning_text']}; font-size: 0.9rem; margin-bottom: 6px;">
                        ⚠️ Excluded Outdated / Superseded Sources
                    </div>
                    <div style="font-size: 0.85rem; color: #78350F;">
                        The adversarial critic detected the following historical documents in the retrieved context that have been superseded by newer authoritative policy:
                        <ul style="margin: 8px 0 0 0; padding-left: 20px;">
                            {outdated_items}
                        </ul>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Dedicated Evidence Presentation Section
        st.markdown(
            """
            <h3 style="font-size: 1.15rem; font-weight: 700; color: #172033; margin: 24px 0 12px 0;">
                Evidence & Grounding Provenance
            </h3>
            """,
            unsafe_allow_html=True,
        )

        if res.citations:
            for idx, c in enumerate(res.citations):
                st.markdown(
                    f"""
                    <div class="tg-source-card">
                        <div class="tg-source-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span class="tg-badge tg-badge-info">CITATION [{idx+1}]</span>
                                <span class="tg-source-title">{c.filename}</span>
                            </div>
                            <div style="display: flex; gap: 6px;">
                                <span class="tg-badge tg-badge-neutral">{c.doc_type}</span>
                                <span class="tg-badge tg-badge-neutral">v{c.version or '1.0'}</span>
                                <span class="tg-badge tg-badge-verified">Level {c.authority_level}</span>
                            </div>
                        </div>
                        <div style="display: flex; gap: 16px; font-size: 0.78rem; color: #64748B; margin-bottom: 8px;">
                            <span>📅 Effective: <b>{c.effective_date or 'N/A'}</b></span>
                            <span>📄 Page: <b>{c.page_number or 1}</b></span>
                        </div>
                        <div class="tg-passage-box">
                            "{c.passage_text.strip()}"
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div class="tg-card" style="padding: 16px; color: #697586; font-size: 0.88rem;">
                    No direct grounding citations were attached to this outcome (e.g. abstention or missing policy evidence).
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Adversarial Audit Findings & Execution Trace
        with st.expander("🧐 Adversarial Critic Audit Details", expanded=False):
            if critic:
                pass_label = "✅ Passed All Stress Tests" if critic.passes_verification else "❌ Critic Raised Issues"
                st.write(f"**Verification Outcome:** {pass_label}")
                st.write(f"**Critic Confidence Level:** `{critic.overall_confidence.upper()}`")
                st.write(f"**Audit Summary:** {critic.verification_summary}")

                if critic.all_findings:
                    st.markdown("#### Itemized Audit Findings:")
                    for f in critic.all_findings:
                        sev_badge = "🔴 CRITICAL" if f.severity == "critical" else ("🟡 WARNING" if f.severity == "warning" else "ℹ️ INFO")
                        st.markdown(f"• **[{sev_badge}] `{f.finding_type.upper()}`** — {f.description}")
                        if f.recommendation:
                            st.caption(f"  *Resolution Action: {f.recommendation}*")
                else:
                    st.success("No contradictions, staleness warnings, or unsupported claims detected.")

        with st.expander("📜 Multi-Agent Workflow Execution Trace", expanded=False):
            st.caption("Step-by-step observable state transitions orchestrated by LangGraph:")
            for log_entry in latest_state.workflow_log:
                st.code(log_entry, language="text")
