"""
app.py
──────
TruthGuard — Adversarial Verification for Multi-Agent Document Q&A.
Main Streamlit application entry point featuring enterprise styling,
deep-navy navigation, and real-time agent telemetry.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from config.settings import settings
from database import repository
from database.initialization import get_db, initialize_database
from ui.admin_review import render_admin_review
from ui.chat import render_chat
from ui.conflict_explorer import render_conflict_explorer
from ui.dashboard import render_dashboard
from ui.document_management import render_document_management
from ui.evaluation import render_evaluation
from ui.styles import get_custom_css, render_brand_header

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("truthguard")

# Configure Streamlit page
st.set_page_config(
    page_title="TruthGuard — AI Verification Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    # Inject Global Enterprise Design Stylesheet
    st.markdown(get_custom_css(), unsafe_allow_html=True)

    # Initialize DB on first run
    initialize_database()

    nav_options = [
        "📊 Overview",
        "💬 Ask TruthGuard",
        "📄 Documents",
        "⚔️ Conflict Explorer",
        "🛡️ Review Queue",
        "📈 Evaluation",
    ]

    # Initialize active nav state
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = nav_options[0]

    with get_db() as db_session:
        # Sidebar Navigation
        with st.sidebar:
            st.markdown(render_brand_header(compact=True), unsafe_allow_html=True)

            st.markdown(
                """
                <div style="font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; 
                            text-transform: uppercase; color: #9CA3AF; margin: 12px 0 6px 4px;">
                    WORKSPACE
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Determine selected index safely
            current_nav = st.session_state.get("nav_page", nav_options[0])
            nav_index = nav_options.index(current_nav) if current_nav in nav_options else 0

            selected_page = st.radio(
                "Navigation",
                nav_options,
                index=nav_index,
                label_visibility="collapsed",
                key="sidebar_nav_radio",
            )
            # Sync state if changed by user
            if selected_page != st.session_state["nav_page"]:
                st.session_state["nav_page"] = selected_page

            st.markdown(
                """
                <div style="font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; 
                            text-transform: uppercase; color: #9CA3AF; margin: 18px 0 6px 4px;">
                    SYSTEM TELEMETRY
                </div>
                """,
                unsafe_allow_html=True,
            )

            stats = repository.get_dashboard_stats(db_session)
            provider_label = settings.llm_provider.upper()
            provider_mode = "Deterministic" if settings.llm_provider == "mock" else "Live Cloud"

            st.markdown(
                f"""
                <div class="tg-telemetry-pill">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                        <span style="font-size: 0.75rem; color: #9CA3AF; font-weight: 500;">Multi-Agent Pipeline</span>
                        <span style="font-size: 0.72rem; color: #10B981; font-weight: 600;"><span class="tg-status-dot"></span>ONLINE</span>
                    </div>
                    <div style="font-size: 0.76rem; color: #D1D5DB; margin-bottom: 3px;">
                        • <b>Engine:</b> LangGraph 4-Agent
                    </div>
                    <div style="font-size: 0.76rem; color: #D1D5DB; margin-bottom: 3px;">
                        • <b>Retrieval:</b> Dense + BM25 RRF
                    </div>
                    <div style="font-size: 0.76rem; color: #D1D5DB; margin-bottom: 3px;">
                        • <b>LLM:</b> {provider_label} ({provider_mode})
                    </div>
                    <div style="font-size: 0.76rem; color: #D1D5DB; margin-bottom: 3px;">
                        • <b>Corpus:</b> {stats['total_documents']} docs ({stats['total_chunks']} chunks)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                """
                <div style="padding: 10px 4px 0 4px; font-size: 0.7rem; color: #6B7280; text-align: center;">
                    TruthGuard Enterprise v2.4 • SOC2 Ready
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Route to selected page
        page_name = st.session_state["nav_page"]
        if page_name == "📊 Overview":
            render_dashboard(db_session)
        elif page_name == "💬 Ask TruthGuard":
            render_chat(db_session)
        elif page_name == "📄 Documents":
            render_document_management(db_session)
        elif page_name == "⚔️ Conflict Explorer":
            render_conflict_explorer(db_session)
        elif page_name == "🛡️ Review Queue":
            render_admin_review(db_session)
        elif page_name == "📈 Evaluation":
            render_evaluation(db_session)


if __name__ == "__main__":
    main()
