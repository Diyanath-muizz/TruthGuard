"""
ui/document_management.py
─────────────────────────
Document Ingestion & Management Interface for TruthGuard.
Enables uploading PDF, DOCX, and TXT policy files, editing metadata,
inspecting vector embeddings and chunk lineage, and synchronizing indexes.
"""

from __future__ import annotations

import streamlit as st
from config.settings import AUTHORITY_HIERARCHY
from database import repository
from database.models import Document
from services.document_service import DocumentService
from ui.styles import PALETTE


def render_document_management(db_session):
    if not db_session:
        st.error("Database connection unavailable.")
        return

    # Hero / Header Banner
    st.markdown(
        """
        <div class="tg-hero">
            <div class="tg-hero-tag">KNOWLEDGE BASE REPOSITORY</div>
            <h1 class="tg-hero-title">Institutional Document Management</h1>
            <p class="tg-hero-subtitle">
                Centralized library for organizational policies, amendments, and FAQs with automated version tracking, authority level indexing, and proactive conflict analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    doc_service = DocumentService()

    tab_library, tab_upload, tab_ops = st.tabs([
        "📚 Document Library",
        "📤 Ingest New Document",
        "⚙️ Index Maintenance",
    ])

    with tab_library:
        all_docs = repository.get_all_documents(db_session)

        if not all_docs:
            st.markdown(
                """
                <div class="tg-card" style="text-align: center; padding: 40px 20px;">
                    <div style="font-size: 2.2rem; margin-bottom: 8px;">📄</div>
                    <h3 style="margin: 0 0 6px 0; color: #172033;">No Documents Indexed</h3>
                    <p style="color: #697586; margin: 0 0 16px 0; font-size: 0.92rem;">
                        The repository is currently empty. Upload your first policy or amendment in the tab above.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            # Search & Filter Toolbar
            s_col1, s_col2, s_col3 = st.columns([5, 3, 2])
            with s_col1:
                search_query = st.text_input("🔍 Search documents by title or filename", "", label_visibility="collapsed", placeholder="Search documents...")
            with s_col2:
                type_filter = st.selectbox("Filter Type", ["All Types", "Policy", "Amendment", "FAQ", "Other"], label_visibility="collapsed")
            with s_col3:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.82rem; color: #64748B; text-align: right;'>Total: <b>{len(all_docs)}</b> docs</div>", unsafe_allow_html=True)

            filtered_docs = [
                d for d in all_docs
                if (not search_query or search_query.lower() in d.filename.lower() or search_query.lower() in (d.title or "").lower())
                and (type_filter == "All Types" or d.doc_type == type_filter)
            ]

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

            for d in filtered_docs:
                auth_badge = f'<span class="tg-badge tg-badge-verified">Level {d.authority_level}</span>'
                type_badge = f'<span class="tg-badge tg-badge-info">{d.doc_type.upper()}</span>'
                ver_text = f"v{d.version}" if d.version else "v1.0"
                eff_text = f"Effective: {d.effective_date}" if d.effective_date else "No effective date"
                supersedes_badge = f'<span class="tg-badge tg-badge-warning">Supersedes: {d.supersedes}</span>' if d.supersedes else ''

                st.markdown(
                    f"""
                    <div class="tg-card" style="margin-bottom: 12px; padding: 16px 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div>
                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                    <span style="font-weight: 700; font-size: 1rem; color: #172033;">
                                        {d.title or d.filename}
                                    </span>
                                    {type_badge}
                                    {auth_badge}
                                    {supersedes_badge}
                                </div>
                                <div style="font-size: 0.8rem; color: #64748B;">
                                    <code>{d.filename}</code> • Version: <b>{ver_text}</b> • {eff_text} • Scope: <b>{d.department or 'All'}</b> • <b>{d.total_chunks}</b> chunks
                                </div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Expandable details & sample chunks
                with st.expander(f"Inspect Chunks & Actions — {d.filename}", expanded=False):
                    chunks = repository.get_chunks_for_document(db_session, d.id)
                    if chunks:
                        st.caption(f"Showing sample chunk (1 of {len(chunks)}):")
                        st.markdown(
                            f"""
                            <div class="tg-passage-box">
                                {chunks[0].text[:350]}...
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    c_del, _ = st.columns([2, 8])
                    with c_del:
                        if st.button(f"🗑️ Delete Document", key=f"del_{d.id}"):
                            if doc_service.delete_document(d.id, db_session):
                                st.success(f"Deleted {d.filename}.")
                                st.rerun()

    with tab_upload:
        st.subheader("Upload Document for Verification")
        st.caption("Supported formats: PDF, DOCX, TXT. Documents are processed as untrusted text evidence.")

        uploaded_file = st.file_uploader(
            "Choose a document file",
            type=["pdf", "docx", "txt"],
            help="Files are strictly parsed as untrusted text evidence.",
        )

        with st.expander("📝 Document Metadata (Auto-extracted from headers if left blank)", expanded=True):
            col_a, col_b = st.columns(2)
            with col_a:
                meta_title = st.text_input("Document Title", placeholder="e.g. Annual Leave Policy 2025")
                meta_type = st.selectbox("Document Type", ["Policy", "Amendment", "FAQ", "Other"])
                meta_version = st.text_input("Version Identifier", placeholder="e.g. 2025 or v2.0")
                meta_dept = st.text_input("Department / Scope", value="All")

            with col_b:
                meta_pub = st.text_input("Publication Date (YYYY-MM-DD)", placeholder="2025-01-01")
                meta_eff = st.text_input("Effective Date (YYYY-MM-DD)", placeholder="2025-01-01")
                meta_exp = st.text_input("Expiration Date (YYYY-MM-DD, optional)", placeholder="")
                meta_supersedes = st.text_input("Explicitly Supersedes", placeholder="e.g. Annual Leave Policy 2024")

            auth_default = AUTHORITY_HIERARCHY.get(meta_type, 2)
            meta_auth = st.slider("Institutional Authority Level (1 = Lowest, 4 = Highest)", 1, 4, value=auth_default)

        if st.button("🚀 Process & Ingest Document", type="primary", disabled=(uploaded_file is None)):
            if uploaded_file:
                with st.status("Ingesting document...", expanded=True) as status_box:
                    st.write("1. Verifying file signature & SHA-256 integrity...")
                    file_bytes = uploaded_file.read()

                    st.write("2. Parsing text & extracting metadata headers...")
                    user_meta = {
                        "title": meta_title.strip() if meta_title else None,
                        "doc_type": meta_type,
                        "version": meta_version.strip() if meta_version else None,
                        "department": meta_dept.strip() if meta_dept else "All",
                        "publication_date": meta_pub.strip() if meta_pub else None,
                        "effective_date": meta_eff.strip() if meta_eff else None,
                        "expiration_date": meta_exp.strip() if meta_exp else None,
                        "supersedes": meta_supersedes.strip() if meta_supersedes else None,
                        "authority_level": meta_auth,
                    }

                    st.write("3. Generating embeddings & vectorizing into ChromaDB + BM25...")
                    st.write("4. Running proactive contradiction scan against existing knowledge base...")
                    res = doc_service.process_upload(
                        file_bytes=file_bytes,
                        filename=uploaded_file.name,
                        user_metadata=user_meta,
                        db_session=db_session,
                    )

                    if res.success:
                        status_box.update(label=f"Ingestion Succeeded! Created {res.chunk_count} chunks.", state="complete", expanded=False)
                        st.success(f"Document **{res.filename}** ingested successfully.")
                        if res.conflict_count > 0:
                            st.warning(f"⚠️ Proactive conflict scan detected **{res.conflict_count}** potential conflict(s). Check Conflict Explorer.")
                        st.rerun()
                    else:
                        status_box.update(label="Ingestion Failed", state="error", expanded=True)
                        for err in res.errors:
                            st.error(f"Error: {err}")

    with tab_ops:
        st.subheader("Index Maintenance & Health")
        st.caption("Rebuild persistent ChromaDB vector store and BM25 sparse index from source documents in SQLite.")

        st.markdown(
            """
            <div class="tg-card" style="padding: 18px 20px;">
                <div style="font-weight: 600; font-size: 0.95rem; color: #172033; margin-bottom: 6px;">
                    Index Synchronization
                </div>
                <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 14px;">
                    Use this operation if you have modified SQLite records or want to rebuild vector embeddings and lexical sparse postings from scratch.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🔄 Rebuild All Retrieval Indexes"):
            with st.spinner("Rebuilding indexes from SQLite documents..."):
                res = doc_service.rebuild_index(db_session)
                st.success(f"Indexes synchronized successfully: {res['total_documents']} documents, {res['total_chunks']} chunks.")
