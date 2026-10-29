"""
ui/admin_review.py
──────────────────
Review Queue & Compliance Governance Interface for TruthGuard.
Enables authorized human reviewers to resolve escalated edge-cases,
audit system decisions, and correct document relationships.
"""

from __future__ import annotations

import streamlit as st
from config.settings import settings
from database import repository
from database.models import HumanReviewCase
from services.audit_service import AuditService
from ui.styles import PALETTE, render_status_pill


def render_admin_review(db_session):
    if not db_session:
        st.error("Database connection unavailable.")
        return

    # Hero / Header Banner
    st.markdown(
        """
        <div class="tg-hero">
            <div class="tg-hero-tag">HUMAN-IN-THE-LOOP COMPLIANCE</div>
            <h1 class="tg-hero-title">Review Queue & Escalation Management</h1>
            <p class="tg-hero-subtitle">
                Resolve policy contradictions escalated by the adversarial resolution engine, review audit records, and maintain human oversight.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_queue, tab_history, tab_audit = st.tabs([
        "🚨 Escalated Cases",
        "⚖️ Resolved Cases",
        "📜 Immutable Audit Trail",
    ])

    with tab_queue:
        pending_cases = repository.get_human_reviews(db_session, status="pending")

        if not pending_cases:
            st.markdown(
                """
                <div class="tg-card" style="text-align: center; padding: 40px 20px;">
                    <div style="font-size: 2.2rem; margin-bottom: 8px;">✨</div>
                    <h3 style="margin: 0 0 6px 0; color: #172033;">Escalation Queue Clear</h3>
                    <p style="color: #697586; margin: 0; font-size: 0.92rem;">
                        No policy questions currently require manual human adjudication.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="font-size: 0.82rem; font-weight: 600; color: #DC2626; margin-bottom: 14px;">
                    ⚠️ {len(pending_cases)} ESCALATED CASE{'S' if len(pending_cases) != 1 else ''} AWAITING HUMAN RESOLUTION
                </div>
                """,
                unsafe_allow_html=True,
            )

            for c in pending_cases:
                st.markdown(
                    f"""
                    <div class="tg-card" style="border-left: 4px solid #DC2626; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div>
                                <span class="tg-badge tg-badge-conflict">CASE #{c.id}</span>
                                <span style="font-weight: 700; font-size: 1.05rem; color: #172033; margin-left: 8px;">
                                    {c.question}
                                </span>
                            </div>
                            <span class="tg-badge tg-badge-warning">PENDING HUMAN REVIEW</span>
                        </div>
                        <div style="font-size: 0.88rem; color: #475569; margin: 8px 0 12px 0;">
                            <b>Escalation Reason:</b> {c.reason}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if c.conflicting_passages:
                    st.markdown("##### Conflicting Source Passages:")
                    cols = st.columns(min(len(c.conflicting_passages), 3))
                    for idx, p in enumerate(c.conflicting_passages):
                        with cols[idx % len(cols)]:
                            doc_label = p.get('filename') or f"Document #{p.get('doc_id')}"
                            st.markdown(
                                f"""
                                <div class="tg-source-card">
                                    <div style="font-weight: 600; font-size: 0.85rem; color: #172033; margin-bottom: 6px;">
                                        📄 {doc_label}
                                    </div>
                                    <div class="tg-passage-box">
                                        "{p.get('text', '')}"
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                res_notes = st.text_area(
                    "Compliance Reviewer Determination & Precedence Ruling:",
                    placeholder="State which document version applies or specify institutional exception...",
                    key=f"notes_{c.id}",
                )

                b_col1, b_col2, _ = st.columns([3, 3, 4])
                with b_col1:
                    if st.button("✅ Approve Policy Ruling & Resolve", key=f"btn_res_{c.id}", type="primary", use_container_width=True):
                        repository.update_human_review(
                            db_session,
                            c.id,
                            {
                                "status": "resolved",
                                "resolution_notes": res_notes or "Resolved by compliance administrator.",
                                "reviewed_by": "human_compliance_officer",
                            },
                        )
                        AuditService.log_human_review_resolved(str(c.id), "human_compliance_officer", db_session)
                        db_session.commit()
                        st.success(f"Case #{c.id} successfully resolved and recorded in audit trail.")
                        st.rerun()

                with b_col2:
                    if st.button("❌ Mark as Inapplicable", key=f"btn_inapp_{c.id}", use_container_width=True):
                        repository.update_human_review(
                            db_session,
                            c.id,
                            {
                                "status": "false_positive",
                                "resolution_notes": res_notes or "Marked inapplicable by compliance administrator.",
                                "reviewed_by": "human_compliance_officer",
                            },
                        )
                        db_session.commit()
                        st.info(f"Case #{c.id} marked as inapplicable.")
                        st.rerun()

                st.markdown("<hr style='border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;'>", unsafe_allow_html=True)

    with tab_history:
        st.subheader("Historical Human Review Decisions")
        resolved_cases = repository.get_human_reviews(db_session, status="resolved")
        if not resolved_cases:
            st.info("No cases have been resolved yet.")
        else:
            for rc in resolved_cases:
                st.markdown(
                    f"""
                    <div class="tg-card" style="padding: 16px 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-weight: 700; font-size: 0.95rem; color: #172033;">Case #{rc.id}: {rc.question}</span>
                            <span class="tg-badge tg-badge-verified">RESOLVED</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #475569; margin-bottom: 6px;">
                            <b>Determination:</b> {rc.resolution_notes or 'Resolved without notes.'}
                        </div>
                        <div style="font-size: 0.76rem; color: #94A3B8;">
                            Reviewed by: <b>{rc.reviewed_by or 'compliance_officer'}</b> • Date: {rc.updated_at.strftime('%Y-%m-%d %H:%M') if rc.updated_at else 'N/A'}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with tab_audit:
        st.subheader("Immutable Audit Log")
        stats = repository.get_dashboard_stats(db_session)
        events = stats.get("recent_audit_events", [])
        if events:
            for e in events:
                st.markdown(
                    f"""
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #FFFFFF; border: 1px solid #E6EAF0; border-radius: 8px; margin-bottom: 8px;">
                        <div>
                            <span class="tg-badge tg-badge-info">{e.get('event_type')}</span>
                            <span style="font-size: 0.88rem; color: #172033; margin-left: 10px;">{e.get('description')}</span>
                        </div>
                        <span style="font-size: 0.78rem; color: #94A3B8;">{e.get('created_at', '')[:19].replace('T', ' ')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No audit events recorded.")
