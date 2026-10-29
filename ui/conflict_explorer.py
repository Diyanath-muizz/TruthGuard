"""
ui/conflict_explorer.py
───────────────────────
Conflict Explorer — Evidence-focused contradiction investigation workspace.
Displays side-by-side comparative analysis of conflicting policy passages,
authority levels, effective dates, supersession links, and human adjudication tools.
"""

from __future__ import annotations

import streamlit as st
from database import repository
from database.models import Document
from services.conflict_service import ConflictService
from ui.styles import PALETTE, render_status_pill


def render_conflict_explorer(db_session):
    if not db_session:
        st.error("Database connection unavailable.")
        return

    # Hero / Header Banner
    st.markdown(
        """
        <div class="tg-hero">
            <div class="tg-hero-tag">CONFLICT AUDITING & GOVERNANCE</div>
            <h1 class="tg-hero-title">Cross-Document Conflict Explorer</h1>
            <p class="tg-hero-subtitle">
                Investigate, compare side-by-side, and adjudicate contradictions, outdated statements, and supersession links detected across organizational documents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Filter Toolbar
    f_col1, f_col2, f_col3 = st.columns([3, 3, 4])
    with f_col1:
        status_filter = st.selectbox(
            "Resolution Status",
            ["All", "pending", "confirmed", "resolved", "false_positive"],
            index=0,
        )
    with f_col2:
        type_filter = st.selectbox(
            "Conflict Category",
            ["All", "superseded_amendment", "contradictory_faq", "version_mismatch", "numerical", "date", "scope"],
            index=0,
        )

    filters = {}
    if status_filter != "All":
        filters["resolution_status"] = status_filter
    if type_filter != "All":
        filters["conflict_type"] = type_filter

    reports = repository.get_conflict_reports(db_session, filters=filters)
    all_docs: dict[int, Document] = {d.id: d for d in repository.get_all_documents(db_session)}

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if not reports:
        st.markdown(
            """
            <div class="tg-card" style="text-align: center; padding: 36px 20px;">
                <div style="font-size: 2rem; margin-bottom: 8px;">✨</div>
                <h4 style="margin: 0 0 6px 0; color: #172033;">No Conflicts Found</h4>
                <p style="color: #697586; margin: 0; font-size: 0.9rem;">
                    No document discrepancies match the selected filter criteria.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div style="font-size: 0.82rem; font-weight: 600; color: #697586; margin-bottom: 14px;">
            DISPLAYING {len(reports)} IDENTIFIED CONFLICT REPORTS
        </div>
        """,
        unsafe_allow_html=True,
    )

    for r in reports:
        # Determine status pill
        status_label = r.resolution_status.upper()
        if r.resolution_status == "resolved":
            badge_html = '<span class="tg-badge tg-badge-verified">RESOLVED</span>'
        elif r.resolution_status == "confirmed":
            badge_html = '<span class="tg-badge tg-badge-conflict">CONFIRMED CONFLICT</span>'
        elif r.resolution_status == "false_positive":
            badge_html = '<span class="tg-badge tg-badge-neutral">FALSE POSITIVE</span>'
        else:
            badge_html = '<span class="tg-badge tg-badge-warning">PENDING REVIEW</span>'

        # Card container
        st.markdown(
            f"""
            <div class="tg-card" style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                            <span class="tg-badge tg-badge-info">REPORT #{r.id}</span>
                            <span style="font-weight: 700; font-size: 1.05rem; color: #172033;">
                                {r.conflict_type.replace('_', ' ').upper()}
                            </span>
                        </div>
                        <div style="font-size: 0.88rem; color: #475569; margin-top: 4px;">
                            {r.description}
                        </div>
                    </div>
                    <div>{badge_html}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Involved documents and passages
        doc_ids = r.document_ids or []
        involved = [all_docs.get(did) for did in doc_ids if all_docs.get(did)]

        # Side-by-side Comparative Layout
        col_a, col_b = st.columns(2)

        doc_a = involved[0] if len(involved) > 0 else None
        doc_b = involved[1] if len(involved) > 1 else None

        passage_a_text = ""
        passage_b_text = ""
        if r.passages and len(r.passages) > 0:
            passage_a_text = r.passages[0].get("text", r.passages[0].get("evidence", ""))
        if r.passages and len(r.passages) > 1:
            passage_b_text = r.passages[1].get("text", r.passages[1].get("evidence", ""))

        with col_a:
            title_a = doc_a.title if doc_a and doc_a.title else (doc_a.filename if doc_a else "Source Document A")
            type_a = doc_a.doc_type if doc_a else "Document"
            ver_a = doc_a.version if doc_a and doc_a.version else "1.0"
            eff_a = doc_a.effective_date if doc_a and doc_a.effective_date else "N/A"
            auth_a = doc_a.authority_level if doc_a else 2

            st.markdown(
                f"""
                <div class="tg-comparison-box">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #64748B;">SOURCE A</span>
                        <span class="tg-badge tg-badge-neutral">Authority Level {auth_a}</span>
                    </div>
                    <div style="font-weight: 700; font-size: 0.95rem; color: #172033; margin-bottom: 4px;">
                        {title_a}
                    </div>
                    <div style="font-size: 0.78rem; color: #64748B; margin-bottom: 10px;">
                        Type: <b>{type_a}</b> • Version: <b>{ver_a}</b> • Effective: <b>{eff_a}</b>
                    </div>
                    <div class="tg-passage-box">
                        "{passage_a_text or 'Passage excerpt recorded in report payload.'}"
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_b:
            title_b = doc_b.title if doc_b and doc_b.title else (doc_b.filename if doc_b else "Source Document B")
            type_b = doc_b.doc_type if doc_b else "Document"
            ver_b = doc_b.version if doc_b and doc_b.version else "1.0"
            eff_b = doc_b.effective_date if doc_b and doc_b.effective_date else "N/A"
            auth_b = doc_b.authority_level if doc_b else 2

            st.markdown(
                f"""
                <div class="tg-comparison-box">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #64748B;">SOURCE B</span>
                        <span class="tg-badge tg-badge-neutral">Authority Level {auth_b}</span>
                    </div>
                    <div style="font-weight: 700; font-size: 0.95rem; color: #172033; margin-bottom: 4px;">
                        {title_b}
                    </div>
                    <div style="font-size: 0.78rem; color: #64748B; margin-bottom: 10px;">
                        Type: <b>{type_b}</b> • Version: <b>{ver_b}</b> • Effective: <b>{eff_b}</b>
                    </div>
                    <div class="tg-passage-box">
                        "{passage_b_text or 'Passage excerpt recorded in report payload.'}"
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Institutional Precedence Analysis
        precedence_note = ""
        if doc_a and doc_b:
            if doc_b.authority_level > doc_a.authority_level:
                precedence_note = f"Source B ({title_b}, Level {doc_b.authority_level}) holds higher institutional authority over Source A ({title_a}, Level {doc_a.authority_level})."
            elif doc_a.authority_level > doc_b.authority_level:
                precedence_note = f"Source A ({title_a}, Level {doc_a.authority_level}) holds higher institutional authority over Source B ({title_b}, Level {doc_b.authority_level})."
            else:
                precedence_note = f"Equal authority conflict (Level {doc_a.authority_level} vs Level {doc_b.authority_level}). Requires human compliance adjudication."

            if doc_b.supersedes and (title_a in doc_b.supersedes or (doc_a.filename and doc_a.filename in doc_b.supersedes)):
                precedence_note += " Source B explicitly supersedes Source A via document metadata header."

        st.markdown(
            f"""
            <div style="background: #F1F5F9; border-radius: 8px; padding: 12px 16px; margin: 12px 0; font-size: 0.85rem; color: #334155;">
                ⚖️ <b>Precedence Analysis:</b> {precedence_note or 'Automated conflict detection based on semantic discrepancy.'}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Action Buttons
        act_col1, act_col2, act_col3, _ = st.columns([2, 2, 2, 4])
        with act_col1:
            if st.button("✅ Mark Resolved", key=f"btn_res_{r.id}", use_container_width=True):
                ConflictService.update_conflict_status(
                    r.id, "resolved", "Adjudicated and resolved by compliance officer", "human_admin", db_session
                )
                st.success("Conflict marked as Resolved.")
                st.rerun()

        with act_col2:
            if st.button("📌 Confirm Conflict", key=f"btn_conf_{r.id}", use_container_width=True):
                ConflictService.update_conflict_status(
                    r.id, "confirmed", "Confirmed policy contradiction requiring governance update", "human_admin", db_session
                )
                st.info("Conflict marked as Confirmed.")
                st.rerun()

        with act_col3:
            if st.button("❌ False Positive", key=f"btn_fp_{r.id}", use_container_width=True):
                ConflictService.update_conflict_status(
                    r.id, "false_positive", "Dismissed as false positive semantic overlap", "human_admin", db_session
                )
                st.warning("Conflict dismissed as False Positive.")
                st.rerun()

        st.markdown("<hr style='border: 0; border-top: 1px solid #E2E8F0; margin: 18px 0;'>", unsafe_allow_html=True)
