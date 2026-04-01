from __future__ import annotations

APP_TITLE = "SmartCrypto Dashboard"
APP_SUBTITLE = "Versão consolidada com foco em estabilidade e operação"


def base_css() -> str:
    return """
        <style>
        .stApp, [data-testid="stAppViewContainer"], .main {background: #eef2f7;}
        [data-testid="stHeader"] {
            background: transparent !important;
            border-bottom: 0 !important;
            box-shadow: none !important;
            min-height: 0 !important;
            height: 0 !important;
        }
        [data-testid="stHeader"] * {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        [data-testid="stToolbar"] {display:none !important;}
        [data-testid="stDecoration"] {display:none !important;}
        [data-testid="collapsedControl"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
        }
        button[kind="header"] {
            display: none !important;
        }
        [data-testid="stSidebar"] {
            background: #f8fafc !important;
            border-right: 1px solid rgba(148, 163, 184, 0.25) !important;
        }

        section[data-testid="stSidebar"] {
            min-width: 22rem !important;
            max-width: 22rem !important;
            left: 0 !important;
            margin-left: 0 !important;
            transform: translateX(0) !important;
        }
        [data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 22rem !important;
            max-width: 22rem !important;
            left: 0 !important;
            margin-left: 0 !important;
            transform: translateX(0) !important;
        }
        [data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebar"] > div {
            left: 0 !important;
            margin-left: 0 !important;
            transform: none !important;
        }
        [data-testid="stSidebarContent"] {
            margin-left: 0 !important;
            padding-left: 0 !important;
            overflow-x: visible !important;
        }
        [data-testid="stSidebar"] * {
            box-sizing: border-box !important;
        }
        [data-testid="stSidebar"] .block-container {
            padding-top: 0.9rem !important;
            padding-left: 0.9rem !important;
            padding-right: 0.9rem !important;
        }
        .sc-sidebar-card {
            background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
            border: 1px solid rgba(100, 116, 139, 0.35);
            border-radius: 14px;
            padding: 0.75rem 0.85rem;
            margin: 0.45rem 0 0.85rem 0;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
        }
        .sc-sidebar-kv {
            display:flex;
            justify-content:space-between;
            gap:0.7rem;
            font-size:0.95rem;
            padding:0.18rem 0;
            color:#0f172a;
        }
        .sc-sidebar-kv span {
            color:#334155;
            font-weight:700;
        }
        .sc-sidebar-kv strong {
            color:#0f172a;
            font-weight:900;
            text-align:right;
        }
        .sc-operational-banner {
            border-radius: 16px;
            padding: 0.9rem 1rem;
            margin: 0.75rem 0 0.9rem 0;
            border: 1px solid rgba(148, 163, 184, 0.35);
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.10);
        }
        .sc-operational-banner.info {
            background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
            border-color: rgba(96, 165, 250, 0.45);
        }
        .sc-operational-banner.warn {
            background: linear-gradient(180deg, #fffbeb 0%, #fef3c7 100%);
            border-color: rgba(245, 158, 11, 0.45);
        }
        .sc-operational-banner.bad {
            background: linear-gradient(180deg, #fef2f2 0%, #fee2e2 100%);
            border-color: rgba(239, 68, 68, 0.45);
        }
        .sc-operational-banner-title {
            font-size: 1rem;
            font-weight: 900;
            color: #111827;
            margin-bottom: 0.35rem;
        }
        .sc-operational-banner-list {
            margin: 0;
            padding-left: 1.1rem;
            color: #334155;
            font-size: 0.93rem;
        }
        .sc-operational-banner-list li {
            margin: 0.18rem 0;
        }
                [data-testid="stMainBlockContainer"],
        [data-testid="stAppViewBlockContainer"],
        .main .block-container,
        .block-container {
            max-width: none !important;
            width: 100% !important;
            padding-top: 0.75rem !important;
            padding-bottom: 1.2rem !important;
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            margin: 0 !important;
        }
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

        .sc-top-nav-title {
            margin: 0.25rem 0 0.55rem 0;
            font-size: 0.9rem;
            font-weight: 900;
            color: #374151;
            letter-spacing: 0.01em;
        }
        .sc-top-nav-help {
            margin: 0 0 0.9rem 0;
            color: #475569;
            font-size: 0.88rem;
        }
        .sc-console-panel {
            background: #05070a;
            color: #f8fafc;
            border: 1px solid #f3f4f6;
            border-radius: 0;
            padding: 0.45rem 0.55rem;
            overflow-x: auto;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
        }
        .sc-console-grid {
            width: max-content;
            min-width: 100%;
            border-collapse: collapse;
            table-layout: auto;
            font-family: Consolas, "Cascadia Mono", "Fira Code", "Courier New", monospace;
            font-size: 0.92rem;
            line-height: 1.32;
            color: #f8fafc;
            background: transparent;
        }
        .sc-console-grid thead tr,
        .sc-console-grid tbody tr {
            background: transparent;
        }
        .sc-console-th,
        .sc-console-td {
            border: 1px solid rgba(255,255,255,0.92);
            padding: 0.42rem 0.65rem;
            white-space: nowrap;
            text-align: center;
        }
        .sc-console-th {
            color: #f8fafc;
            font-weight: 700;
        }
        .sc-console-td {
            font-weight: 700;
        }
        .sc-console-pos { color: #22c55e !important; font-weight: 900; }
        .sc-console-neg { color: #ef4444 !important; font-weight: 900; }
        .sc-console-neutral { color: #f8fafc !important; font-weight: 700; }
        .sc-console-meta {
            font-size: 0.86rem;
            color: #475569;
            margin-top: 0.35rem;
        }

        </style>
        """


def inject_styles() -> None:
    import streamlit as st

    st.markdown(base_css(), unsafe_allow_html=True)
