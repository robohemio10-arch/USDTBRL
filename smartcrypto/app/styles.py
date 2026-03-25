from __future__ import annotations

APP_TITLE = "SmartCrypto Dashboard"
APP_SUBTITLE = "Versão consolidada com foco em estabilidade e operação"


def base_css() -> str:
    return """
        <style>
        .stApp, [data-testid="stAppViewContainer"], .main {background: #eef2f7;}
        [data-testid="stHeader"] {display:none !important; height:0 !important; visibility:hidden !important;}
        [data-testid="stToolbar"] {display:none !important;}
        [data-testid="stDecoration"] {display:none !important;}
        .block-container {padding-top: 0.25rem; padding-bottom: 1.2rem;}
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #d7dbe0 0%, #c7ccd4 100%);
            border: 1px solid #b0b7c3;
            border-radius: 14px;
            padding: 0.65rem 0.85rem;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.10);
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.98rem;
            font-weight: 900;
            color: #374151;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem;
            font-weight: 800;
            color: #111827;
        }
        .stButton button, .stFormSubmitButton button, .stDownloadButton button,
        div[data-testid="stNumberInputStepUp"] button, div[data-testid="stNumberInputStepDown"] button {
            background: linear-gradient(180deg, #6b7280 0%, #4b5563 100%) !important;
            border: 1px solid #374151 !important;
            color: #f9fafb !important;
            font-weight: 900 !important;
            font-size: 1.02rem !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
        }
        .stButton button:hover, .stFormSubmitButton button:hover, .stDownloadButton button:hover,
        div[data-testid="stNumberInputStepUp"] button:hover, div[data-testid="stNumberInputStepDown"] button:hover {
            background: linear-gradient(180deg, #5b6472 0%, #434c59 100%) !important;
            border-color: #56606f !important;
            color: #ffffff !important;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-testid="stTextInputRootElement"] > div,
        div[data-testid="stNumberInputContainer"] > div,
        div[data-testid="stTextArea"] textarea,
        textarea, input {
            background: #d9dee6 !important;
            color: #111827 !important;
            border-color: #aeb7c4 !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] div,
        div[data-testid="stTextInputRootElement"] input,
        div[data-testid="stNumberInputContainer"] input,
        textarea {
            background: #eef2f7 !important;
            color: #111827 !important;
            caret-color: #111827 !important;
        }
        label, .stSelectbox label, .stTextInput label, .stNumberInput label, .stTextArea label {
            color: #374151 !important;
            font-weight: 800 !important;
        }
        .sc-card {
            background: linear-gradient(180deg, #d7dbe0 0%, #c7ccd4 100%);
            border: 1px solid #b0b7c3;
            border-radius: 14px;
            padding: 1rem 1rem 0.9rem 1rem;
            margin-bottom: 0.85rem;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.10);
            color: #111827;
        }
        .sc-chip-wrap {display:flex; flex-wrap:wrap; gap:0.45rem; margin-top:0.3rem; margin-bottom:0.2rem;}
        .sc-chip {
            display:inline-flex; align-items:center; gap:0.35rem;
            padding:0.35rem 0.65rem; border-radius:999px;
            font-size:0.82rem; font-weight:700;
            border:1px solid rgba(17,24,39,0.10);
            background:rgba(255,255,255,0.70);
            color:#111827;
        }
        .sc-chip.good {border-color: rgba(14,203,129,0.35); color:#065f46;}
        .sc-chip.warn {border-color: rgba(240,185,11,0.35); color:#92400e;}
        .sc-chip.bad {border-color: rgba(246,70,93,0.35); color:#991b1b;}
        .sc-chip.neutral {border-color: rgba(148,163,184,0.35); color:#334155;}
        .sc-section-title {font-size:1.08rem; font-weight:900; margin:0 0 0.55rem 0; color:#111827;}
        .sc-muted {color:#475569; font-size:0.88rem;}
        .sc-kv {display:grid; grid-template-columns: 1fr auto; gap:0.35rem; font-size:0.92rem; color:#111827;}
        .sc-kv span:last-child {font-weight:700;}
        .sc-time-card {
            background: linear-gradient(180deg, #d7dbe0 0%, #c7ccd4 100%);
            border: 1px solid #b0b7c3;
            border-radius: 14px;
            padding: 0.95rem 1rem;
            min-height: 96px;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.10);
        }
        .sc-time-label {
            font-size: 0.9rem;
            font-weight: 900;
            color: #374151;
            margin-bottom: 0.25rem;
        }
        .sc-time-value {
            font-size: 1.15rem;
            font-weight: 900;
            color: #111827;
            line-height: 1.2;
        }
        .sc-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
            border: 1px solid #d1d5db;
            border-radius: 12px;
            overflow: hidden;
        }
        .sc-table th, .sc-table td {
            border-bottom: 1px solid #e5e7eb;
            padding: 0.55rem 0.75rem;
            text-align: left;
            color: #111827;
        }
        .sc-table th {
            background: #eef2f7;
            font-weight: 800;
        }
        .sc-table tr:nth-child(even) td {
            background: #f8fafc;
        }
        </style>
        """


def inject_styles() -> None:
    import streamlit as st

    st.markdown(base_css(), unsafe_allow_html=True)
