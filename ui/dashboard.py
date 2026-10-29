"""
ui/dashboard.py
───────────────
Overview Dashboard for TruthGuard.
Enterprise-grade monitoring for document intelligence, verification activity,
and emerging policy conflicts across the knowledge base.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import func, select
from database import repository
from database.models import QASession
from ui.styles import PALETTE, render_status_pill


def render_dashboard(db_session):
    if not db_session:
        st.error("Database connection unavailable.")
        return

    # Header / Hero Section
    st.markdown(
        """
        <div class="tg-hero">
            <div class="tg-hero-tag">ENTERPRISE VERIFICATION INTELLIGENCE</div>
            <h1 class="tg-hero-title">Trust every answer. Verify every source.</h1>
            <p class="tg-hero-subtitle">
                Monitor document intelligence, real-time adversarial verification activity, and emerging conflicts across your institutional knowledge base.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Hero Action CTAs
    col_cta1, col_cta2, _ = st.columns([2, 2, 6])
    with col_cta1:
        if st.button("💬 Ask TruthGuard", type="primary", use_container_width=True):
            st.session_state["nav_page"] = "💬 Ask TruthGuard"
            st.rerun()
    with col_cta2:
        if st.button("⚔️ Explore Conflicts", use_container_width=True):
            st.session_state["nav_page"] = "⚔️ Conflict Explorer"
            st.rerun()

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    stats = repository.get_dashboard_stats(db_session)

    # Compute Verified Answers count
    verified_count = db_session.scalar(
        select(func.count())
        .select_from(QASession)
        .where(QASession.verification_status.in_(["verified", "verified_with_warnings"]))
    ) or 0

    total_docs = stats.get("total_documents", 0)
    total_conflicts = stats.get("total_conflicts", 0)
    pending_reviews = stats.get("pending_human_reviews", 0)

    # 4 Balanced KPI Cards
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(
            f"""
            <div class="tg-kpi-card">
                <div class="tg-kpi-header">
                    <span class="tg-kpi-label">Indexed Documents</span>
                    <span class="tg-kpi-icon">📄</span>
                </div>
                <div class="tg-kpi-val">{total_docs}</div>
                <div class="tg-kpi-desc">{stats.get('total_chunks', 0)} chunks vectorized</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        st.markdown(
            f"""
            <div class="tg-kpi-card">
                <div class="tg-kpi-header">
                    <span class="tg-kpi-label">Conflicts Detected</span>
                    <span class="tg-kpi-icon" style="color: {PALETTE['status_conflict_text']}; background: {PALETTE['status_conflict_bg']};">⚠️</span>
                </div>
                <div class="tg-kpi-val">{total_conflicts}</div>
                <div class="tg-kpi-desc">{stats.get('pending_conflicts', 0)} pending investigation</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="tg-kpi-card">
                <div class="tg-kpi-header">
                    <span class="tg-kpi-label">Verified Answers</span>
                    <span class="tg-kpi-icon" style="color: {PALETTE['status_verified_text']}; background: {PALETTE['status_verified_bg']};">🛡️</span>
                </div>
                <div class="tg-kpi-val">{verified_count}</div>
                <div class="tg-kpi-desc">Out of {stats.get('total_qa_sessions', 0)} total sessions</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        st.markdown(
            f"""
            <div class="tg-kpi-card">
                <div class="tg-kpi-header">
                    <span class="tg-kpi-label">Pending Reviews</span>
                    <span class="tg-kpi-icon" style="color: {PALETTE['status_warning_text']}; background: {PALETTE['status_warning_bg']};">⚖️</span>
                </div>
                <div class="tg-kpi-val">{pending_reviews}</div>
                <div class="tg-kpi-desc">Awaiting compliance sign-off</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    # Empty Database State Guard
    if total_docs == 0:
        st.markdown(
            """
            <div class="tg-card" style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 2.5rem; margin-bottom: 12px;">📁</div>
                <h3 style="margin: 0 0 8px 0; color: #172033;">Knowledge Base is Empty</h3>
                <p style="color: #697586; max-width: 500px; margin: 0 auto 20px auto; font-size: 0.95rem;">
                    Upload organizational policies, amendments, or run the synthetic initialization script to activate real-time verification and conflict detection.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚀 Go to Document Management", type="primary"):
            st.session_state["nav_page"] = "📄 Documents"
            st.rerun()
        return

    # Main 2-Column Content Layout
    col_left, col_right = st.columns([6, 4])

    with col_left:
        st.markdown(
            """
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;">
                <h3 style="font-size: 1.15rem; font-weight: 700; color: #172033; margin: 0;">
                    Recent Verification Activity
                </h3>
                <span style="font-size: 0.8rem; color: #697586;">Live LangGraph Audits</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        recent_sessions = repository.get_qa_sessions(db_session, limit=5)

        if recent_sessions:
            for s in recent_sessions:
                pill_html = render_status_pill(s.verification_status)
                ans_snippet = (s.final_answer or "No answer recorded.")[:140]
                if len(s.final_answer or "") > 140:
                    ans_snippet += "..."
                created = s.created_at.strftime("%b %d, %H:%M") if s.created_at else "Recently"
                latency = f"{s.latency_ms:.0f}ms" if s.latency_ms else "N/A"

                st.markdown(
                    f"""
                    <div class="tg-card" style="padding: 16px 20px; margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div style="font-weight: 600; font-size: 0.95rem; color: #172033; max-width: 75%;">
                                {s.question}
                            </div>
                            <div>{pill_html}</div>
                        </div>
                        <div style="font-size: 0.86rem; color: #475569; line-height: 1.5; margin-bottom: 10px;">
                            {ans_snippet}
                        </div>
                        <div style="display: flex; align-items: center; gap: 14px; font-size: 0.75rem; color: #94A3B8;">
                            <span>🕒 {created}</span>
                            <span>⚡ {latency}</span>
                            <span>🔍 Hybrid BM25 + Vector</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div class="tg-card" style="padding: 24px; text-align: center; color: #697586;">
                    <p style="margin: 0; font-size: 0.9rem;">No question-answering sessions logged yet.</p>
                    <p style="margin: 4px 0 0 0; font-size: 0.8rem;">Click <b>Ask TruthGuard</b> above to run your first adversarial verification query.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_right:
        # Conflict Distribution Breakdown
        st.markdown(
            """
            <h3 style="font-size: 1.15rem; font-weight: 700; color: #172033; margin: 0 0 14px 0;">
                Conflict Distribution
            </h3>
            """,
            unsafe_allow_html=True,
        )

        conflicts_by_sev = stats.get("conflicts_by_severity", {})
        if conflicts_by_sev:
            st.bar_chart(conflicts_by_sev)
        else:
            st.markdown(
                """
                <div class="tg-card" style="padding: 16px; text-align: center; color: #15803D; background: #F0FDF4; border-color: #BBF7D0;">
                    <span style="font-size: 1.2rem;">✨</span>
                    <div style="font-weight: 600; font-size: 0.9rem; margin-top: 4px;">Corpus Coherent</div>
                    <div style="font-size: 0.78rem; color: #166534;">No active policy discrepancies identified</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Multi-Agent Engine Architecture Status
        st.markdown(
            """
            <div class="tg-card" style="padding: 18px 20px; margin-top: 14px;">
                <div style="font-weight: 700; font-size: 0.92rem; color: #172033; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                    <span>Verification Pipeline Status</span>
                    <span style="font-size: 0.72rem; color: #10B981; font-weight: 600;">HEALTHY</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.83rem;">
                        <span style="color: #475569;">🔍 Retriever Agent (Dense + BM25)</span>
                        <span class="tg-badge tg-badge-verified">Active</span>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.83rem;">
                        <span style="color: #475569;">✍️ Synthesizer Agent (Grounding)</span>
                        <span class="tg-badge tg-badge-verified">Active</span>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.83rem;">
                        <span style="color: #475569;">🧐 Adversarial Critic Agent</span>
                        <span class="tg-badge tg-badge-verified">Active</span>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.83rem;">
                        <span style="color: #475569;">⚖️ Resolution Agent (Authority Rules)</span>
                        <span class="tg-badge tg-badge-verified">Active</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Pending Review Summary Callout
        if pending_reviews > 0:
            st.markdown(
                f"""
                <div class="tg-card" style="border-left: 4px solid {PALETTE['status_warning_text']}; padding: 16px 18px; margin-top: 12px;">
                    <div style="font-weight: 600; font-size: 0.9rem; color: #172033; margin-bottom: 4px;">
                        ⚠️ {pending_reviews} Case(s) Require Compliance Review
                    </div>
                    <div style="font-size: 0.8rem; color: #697586; margin-bottom: 10px;">
                        Contradictory peer policies were escalated by the Resolution Agent.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🛡️ Open Review Queue", use_container_width=True):
                st.session_state["nav_page"] = "🛡️ Review Queue"
                st.rerun()
