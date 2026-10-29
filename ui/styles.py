"""
ui/styles.py
────────────
Enterprise Design System for TruthGuard.
Defines cohesive styling, color variables, typography, and reusable UI components.
Inspired by modern enterprise SaaS products (Linear, Stripe, Vercel).
"""

from __future__ import annotations

# Enterprise Color Palette
PALETTE = {
    "bg_main": "#F7F8FC",
    "bg_sidebar": "#111827",
    "bg_sidebar_hover": "#1F2937",
    "bg_card": "#FFFFFF",
    "primary": "#5B5BD6",
    "primary_hover": "#4F46E5",
    "secondary": "#818CF8",
    "text_main": "#172033",
    "text_muted": "#697586",
    "text_light": "#9CA3AF",
    "border": "#E6EAF0",
    "border_subtle": "#EDF2F7",
    "status_verified_bg": "#ECFDF5",
    "status_verified_text": "#15803D",
    "status_verified_border": "#A7F3D0",
    "status_conflict_bg": "#FEF2F2",
    "status_conflict_text": "#DC2626",
    "status_conflict_border": "#FECACA",
    "status_warning_bg": "#FFFBEB",
    "status_warning_text": "#D97706",
    "status_warning_border": "#FDE68A",
    "status_info_bg": "#EFF6FF",
    "status_info_text": "#2563EB",
    "status_info_border": "#BFDBFE",
    "status_neutral_bg": "#F8FAFC",
    "status_neutral_text": "#475569",
    "status_neutral_border": "#E2E8F0",
}


def get_custom_css() -> str:
    """Return the global enterprise CSS stylesheet for TruthGuard."""
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global Typography & Font Family */
    html, body, [class*="css"], .stMarkdown, .stText, p, span, label, div {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }}

    /* Main Container Background */
    [data-testid="stAppViewContainer"] {{
        background-color: {PALETTE['bg_main']} !important;
        color: {PALETTE['text_main']};
    }}

    /* Remove Streamlit default header decoration */
    [data-testid="stHeader"] {{
        background-color: transparent !important;
        height: 2.5rem;
    }}

    .block-container {{
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1280px;
    }}

    /* Sidebar Styling — Deep Navy Enterprise */
    [data-testid="stSidebar"] {{
        background-color: {PALETTE['bg_sidebar']} !important;
        border-right: 1px solid #1F2937 !important;
    }}

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
    [data-testid="stSidebar"] label {{
        color: #E5E7EB !important;
    }}

    [data-testid="stSidebar"] hr {{
        border-color: #1F2937 !important;
        margin: 1rem 0 !important;
    }}

    /* Sidebar Radio Navigation */
    [data-testid="stSidebar"] [data-testid="stRadio"] > div {{
        gap: 4px;
    }}

    [data-testid="stSidebar"] [data-testid="stRadio"] label {{
        background-color: transparent;
        padding: 8px 12px;
        border-radius: 8px;
        transition: all 0.15s ease-in-out;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.92rem;
        border: 1px solid transparent;
        display: flex;
        align-items: center;
    }}

    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
        background-color: {PALETTE['bg_sidebar_hover']};
        color: #FFFFFF !important;
    }}

    [data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
    [data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] {{
        background-color: rgba(91, 91, 214, 0.18) !important;
        border: 1px solid rgba(91, 91, 214, 0.4) !important;
        color: #FFFFFF !important;
    }}

    /* Enterprise Cards */
    .tg-card {{
        background: {PALETTE['bg_card']};
        border: 1px solid {PALETTE['border']};
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03), 0 1px 2px rgba(0, 0, 0, 0.02);
        transition: border-color 0.15s ease;
    }}

    .tg-card:hover {{
        border-color: #CBD5E1;
    }}

    /* KPI Metric Cards */
    .tg-kpi-card {{
        background: #FFFFFF;
        border: 1px solid {PALETTE['border']};
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }}

    .tg-kpi-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
    }}

    .tg-kpi-label {{
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {PALETTE['text_muted']};
    }}

    .tg-kpi-icon {{
        font-size: 1.1rem;
        padding: 6px;
        border-radius: 8px;
        background: #F1F5F9;
        color: {PALETTE['primary']};
    }}

    .tg-kpi-val {{
        font-size: 1.85rem;
        font-weight: 700;
        color: {PALETTE['text_main']};
        line-height: 1.2;
    }}

    .tg-kpi-desc {{
        font-size: 0.8rem;
        color: {PALETTE['text_muted']};
        margin-top: 4px;
    }}

    /* Hero / Page Header Banner */
    .tg-hero {{
        background: #FFFFFF;
        border: 1px solid {PALETTE['border']};
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }}

    .tg-hero-tag {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        background: rgba(91, 91, 214, 0.08);
        color: {PALETTE['primary']};
        margin-bottom: 12px;
        border: 1px solid rgba(91, 91, 214, 0.2);
    }}

    .tg-hero-title {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {PALETTE['text_main']};
        margin: 0 0 6px 0;
        letter-spacing: -0.02em;
    }}

    .tg-hero-subtitle {{
        font-size: 0.95rem;
        color: {PALETTE['text_muted']};
        margin: 0;
        line-height: 1.5;
    }}

    /* Status Badges */
    .tg-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }}

    .tg-badge-verified {{
        background: {PALETTE['status_verified_bg']};
        color: {PALETTE['status_verified_text']};
        border: 1px solid {PALETTE['status_verified_border']};
    }}

    .tg-badge-conflict {{
        background: {PALETTE['status_conflict_bg']};
        color: {PALETTE['status_conflict_text']};
        border: 1px solid {PALETTE['status_conflict_border']};
    }}

    .tg-badge-warning {{
        background: {PALETTE['status_warning_bg']};
        color: {PALETTE['status_warning_text']};
        border: 1px solid {PALETTE['status_warning_border']};
    }}

    .tg-badge-info {{
        background: {PALETTE['status_info_bg']};
        color: {PALETTE['status_info_text']};
        border: 1px solid {PALETTE['status_info_border']};
    }}

    .tg-badge-neutral {{
        background: {PALETTE['status_neutral_bg']};
        color: {PALETTE['status_neutral_text']};
        border: 1px solid {PALETTE['status_neutral_border']};
    }}

    /* Evidence / Source Cards */
    .tg-source-card {{
        background: #FFFFFF;
        border: 1px solid {PALETTE['border']};
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 12px;
        transition: transform 0.1s ease, border-color 0.1s ease;
    }}

    .tg-source-card:hover {{
        border-color: {PALETTE['secondary']};
    }}

    .tg-source-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }}

    .tg-source-title {{
        font-weight: 600;
        font-size: 0.95rem;
        color: {PALETTE['text_main']};
    }}

    .tg-passage-box {{
        background: #F8FAFC;
        border-left: 3px solid {PALETTE['primary']};
        border-radius: 0 6px 6px 0;
        padding: 12px 14px;
        font-size: 0.88rem;
        color: #334155;
        line-height: 1.55;
        margin-top: 8px;
    }}

    /* Workflow Agent Timeline */
    .tg-pipeline-step {{
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 10px 14px;
        background: #FFFFFF;
        border: 1px solid {PALETTE['border']};
        border-radius: 8px;
        margin-bottom: 8px;
    }}

    .tg-step-icon {{
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #EEF2FF;
        color: {PALETTE['primary']};
        font-size: 0.85rem;
        font-weight: 700;
    }}

    /* Side-by-side comparison box */
    .tg-comparison-box {{
        background: #FFFFFF;
        border: 1px solid {PALETTE['border']};
        border-radius: 10px;
        padding: 16px 20px;
        height: 100%;
    }}

    /* Button Customization */
    button[kind="primary"] {{
        background-color: {PALETTE['primary']} !important;
        border-color: {PALETTE['primary']} !important;
        border-radius: 8px !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.25rem !important;
        box-shadow: 0 1px 2px rgba(91, 91, 214, 0.2) !important;
    }}

    button[kind="primary"]:hover {{
        background-color: {PALETTE['primary_hover']} !important;
        border-color: {PALETTE['primary_hover']} !important;
    }}

    button[kind="secondary"] {{
        background-color: #FFFFFF !important;
        border: 1px solid {PALETTE['border']} !important;
        border-radius: 8px !important;
        color: {PALETTE['text_main']} !important;
        font-weight: 500 !important;
    }}

    /* Custom Input Fields */
    .stTextInput > div > div > input {{
        border-radius: 8px !important;
        border: 1px solid {PALETTE['border']} !important;
        padding: 10px 14px !important;
        font-size: 0.92rem !important;
    }}

    .stTextInput > div > div > input:focus {{
        border-color: {PALETTE['primary']} !important;
        box-shadow: 0 0 0 2px rgba(91, 91, 214, 0.15) !important;
    }}

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        border-bottom: 1px solid {PALETTE['border']} !important;
        padding-bottom: 2px;
    }}

    .stTabs [data-baseweb="tab"] {{
        border-radius: 6px 6px 0 0;
        padding: 8px 16px;
        font-weight: 500;
        font-size: 0.9rem;
        color: {PALETTE['text_muted']};
    }}

    .stTabs [aria-selected="true"] {{
        color: {PALETTE['primary']} !important;
        border-bottom: 2px solid {PALETTE['primary']} !important;
        font-weight: 600;
    }}

    /* Sidebar Telemetry Pill */
    .tg-telemetry-pill {{
        background: #1F2937;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 10px 12px;
        margin-top: 8px;
    }}

    .tg-status-dot {{
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #10B981;
        margin-right: 6px;
    }}
    </style>
    """


def render_brand_header(compact: bool = False) -> str:
    """Return HTML for TruthGuard brand identity."""
    if compact:
        return """
        <div style="display: flex; align-items: center; gap: 10px; padding: 4px 0 12px 0;">
            <div style="background: linear-gradient(135deg, #5B5BD6, #818CF8); width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 4px rgba(91,91,214,0.3);">
                <span style="color: white; font-size: 18px; font-weight: bold;">🛡️</span>
            </div>
            <div>
                <div style="color: #FFFFFF; font-weight: 700; font-size: 1.05rem; letter-spacing: -0.01em;">TRUTHGUARD</div>
                <div style="color: #9CA3AF; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;">AI Verification Platform</div>
            </div>
        </div>
        """
    return """
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 8px;">
        <div style="background: linear-gradient(135deg, #5B5BD6, #818CF8); width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 3px 6px rgba(91,91,214,0.25);">
            <span style="color: white; font-size: 22px; font-weight: bold;">🛡️</span>
        </div>
        <div>
            <div style="color: #172033; font-weight: 700; font-size: 1.45rem; letter-spacing: -0.02em;">TruthGuard</div>
            <div style="color: #697586; font-size: 0.85rem; font-weight: 500;">Adversarial Verification for Multi-Agent Document Q&A</div>
        </div>
    </div>
    """


def render_status_pill(status_str: str) -> str:
    """Return an enterprise status badge HTML matching TruthGuard standards."""
    s = (status_str or "").lower().strip()
    if "verified" in s and "warning" not in s:
        return f'<span class="tg-badge tg-badge-verified"><span style="font-size:10px;">●</span> VERIFIED</span>'
    elif "warning" in s:
        return f'<span class="tg-badge tg-badge-warning"><span style="font-size:10px;">▲</span> VERIFIED WITH WARNINGS</span>'
    elif "conflict" in s:
        return f'<span class="tg-badge tg-badge-conflict"><span style="font-size:10px;">✕</span> CONFLICT DETECTED</span>'
    elif "human" in s or "escalat" in s:
        return f'<span class="tg-badge tg-badge-conflict"><span style="font-size:10px;">⚠</span> HUMAN REVIEW REQUIRED</span>'
    elif "abstain" in s:
        return f'<span class="tg-badge tg-badge-neutral"><span style="font-size:10px;">○</span> ABSTAINED</span>'
    else:
        return f'<span class="tg-badge tg-badge-info"><span style="font-size:10px;">ℹ</span> {status_str.upper()}</span>'


def apply_custom_theme():
    """Inject the global enterprise stylesheet into Streamlit."""
    import streamlit as st
    st.markdown(get_custom_css(), unsafe_allow_html=True)


def render_top_nav(active_page: str = "") -> str:
    """Legacy helper for top nav compatibility."""
    return ""

