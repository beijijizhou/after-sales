import streamlit as st


BRAND_ORANGE = "#F68A0A"
BRAND_TEAL = "#43A8AB"
BRAND_YELLOW = "#FFDB32"


def configure_page():
    st.set_page_config(
        page_title="生产管理系统",
        page_icon="🧵",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        f"""
        <style>
        :root {{
            --brand-orange: {BRAND_ORANGE};
            --brand-orange-dark: #D96F00;
            --brand-teal: {BRAND_TEAL};
            --brand-teal-dark: #237E84;
            --brand-yellow: {BRAND_YELLOW};
            --ink-strong: #162536;
            --ink: #344556;
            --ink-muted: #6C7C8C;
            --surface: rgba(255, 255, 255, 0.94);
            --line: rgba(32, 66, 82, 0.12);
            --shadow-sm: 0 8px 24px rgba(27, 60, 75, 0.07);
            --radius-sm: 12px;
            --radius-md: 18px;
            --radius-lg: 24px;
        }}

        html, body, [class*="css"] {{
            font-family: Inter, "SF Pro Text", "PingFang SC", "Microsoft YaHei",
                system-ui, sans-serif;
        }}
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {{
            color: var(--ink);
            background:
                linear-gradient(rgba(32, 92, 104, 0.028) 1px, transparent 1px),
                linear-gradient(90deg, rgba(32, 92, 104, 0.028) 1px, transparent 1px),
                radial-gradient(circle at 88% 5%, rgba(67, 168, 171, 0.22), transparent 30rem),
                radial-gradient(circle at 10% 94%, rgba(246, 138, 10, 0.17), transparent 32rem),
                linear-gradient(135deg, #EAF3F4 0%, #F2F6F2 48%, #F7EFE3 100%) !important;
            background-size: 28px 28px, 28px 28px, auto, auto, auto !important;
            background-attachment: fixed !important;
        }}
        [data-testid="stHeader"] {{
            background: rgba(241, 247, 246, 0.76);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid rgba(32, 66, 82, 0.08);
        }}
        [data-testid="stMainBlockContainer"], .block-container {{
            width: min(92%, 1700px);
            max-width: 1700px;
            padding: 2.4rem 2.2rem 4rem;
        }}
        h1, h2, h3 {{
            color: var(--ink-strong);
            letter-spacing: -0.025em;
        }}
        h1 {{
            font-size: clamp(1.85rem, 2.6vw, 2.5rem) !important;
            font-weight: 760 !important;
            line-height: 1.18 !important;
            margin-bottom: 1.45rem !important;
        }}
        h1::after {{
            content: "";
            display: block;
            width: 3.25rem;
            height: 0.3rem;
            margin-top: 0.7rem;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--brand-orange), var(--brand-yellow));
        }}
        h2 {{ font-weight: 720 !important; }}
        h3 {{ font-weight: 690 !important; }}
        p, label, [data-testid="stCaptionContainer"] {{ color: var(--ink); }}
        [data-testid="stCaptionContainer"] {{ color: var(--ink-muted); }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(165deg, rgba(255,255,255,0.98) 0%, rgba(239,248,248,0.98) 68%, rgba(255,247,235,0.98) 100%);
            border-right: 1px solid var(--line);
            box-shadow: 10px 0 34px rgba(27, 60, 75, 0.055);
        }}
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
            padding-top: 0.65rem;
        }}
        [data-testid="stSidebar"] hr {{
            border-color: var(--line);
            margin: 0.95rem 0;
        }}
        .app-brand {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            padding: 0.7rem 0.55rem 1rem;
        }}
        .app-brand__mark {{
            position: relative;
            width: 58px;
            height: 58px;
            flex: 0 0 58px;
            overflow: hidden;
            border-radius: 17px;
            background: #fff;
            border: 1px solid rgba(246, 138, 10, 0.18);
            box-shadow: 0 9px 22px rgba(246, 138, 10, 0.15);
        }}
        .app-brand__mark img {{
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            transform: scale(1.72);
        }}
        .app-brand__name {{
            color: var(--ink-strong);
            font-size: 1rem;
            font-weight: 780;
            line-height: 1.2;
        }}
        .app-brand__sub {{
            margin-top: 0.23rem;
            color: var(--brand-teal-dark);
            font-size: 0.68rem;
            font-weight: 720;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {{
            min-height: 2.55rem;
            border-radius: 11px;
            padding: 0.48rem 0.7rem;
            color: var(--ink);
            font-weight: 580;
            transition: background 160ms ease, color 160ms ease, transform 160ms ease;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{
            color: var(--brand-teal-dark);
            background: rgba(67, 168, 171, 0.10);
            transform: translateX(2px);
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {{
            color: #9A4B00;
            background: linear-gradient(90deg, rgba(246, 138, 10, 0.16), rgba(255, 219, 50, 0.10));
            box-shadow: inset 3px 0 0 var(--brand-orange);
        }}
        [data-testid="stSidebar"] details {{
            border: 1px solid transparent;
            border-radius: 13px;
            background: rgba(255, 255, 255, 0.48);
        }}
        [data-testid="stSidebar"] details[open] {{
            border-color: var(--line);
            background: rgba(255, 255, 255, 0.75);
        }}
        [data-testid="stSidebar"] details summary {{
            font-weight: 680;
            color: var(--ink-strong);
        }}

        [data-testid="stMetric"] {{
            min-height: 7rem;
            padding: 1.05rem 1.15rem;
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            background: var(--surface);
            box-shadow: var(--shadow-sm);
        }}
        [data-testid="stMetricLabel"] {{
            color: var(--ink-muted);
            font-weight: 620;
        }}
        [data-testid="stMetricValue"] {{
            color: var(--ink-strong);
            font-weight: 760;
            letter-spacing: -0.035em;
        }}
        [data-testid="stForm"] {{
            padding: 1.35rem;
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            background: var(--surface);
            box-shadow: var(--shadow-sm);
        }}
        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] > div,
        [data-baseweb="select"] > div {{
            border-color: rgba(32, 66, 82, 0.17) !important;
            border-radius: var(--radius-sm) !important;
            background: rgba(255,255,255,0.96) !important;
            transition: border-color 150ms ease, box-shadow 150ms ease;
        }}
        [data-baseweb="input"] > div:focus-within,
        [data-baseweb="textarea"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within {{
            border-color: var(--brand-teal) !important;
            box-shadow: 0 0 0 3px rgba(67, 168, 171, 0.14) !important;
        }}
        [data-testid="stButton"] button,
        [data-testid="stFormSubmitButton"] button,
        [data-testid="stDownloadButton"] button {{
            min-height: 2.55rem;
            border-radius: var(--radius-sm);
            border-color: rgba(32, 66, 82, 0.16);
            font-weight: 680;
            box-shadow: 0 5px 14px rgba(27, 60, 75, 0.06);
            transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease;
        }}
        [data-testid="stButton"] button:hover,
        [data-testid="stFormSubmitButton"] button:hover,
        [data-testid="stDownloadButton"] button:hover {{
            border-color: var(--brand-teal);
            color: var(--brand-teal-dark);
            transform: translateY(-1px);
            box-shadow: 0 9px 20px rgba(27, 60, 75, 0.10);
        }}
        button[kind="primary"] {{
            border: 0 !important;
            color: #fff !important;
            background: linear-gradient(135deg, var(--brand-orange), #F7A31A) !important;
            box-shadow: 0 9px 22px rgba(246, 138, 10, 0.24) !important;
        }}
        button[kind="primary"]:hover {{
            color: #fff !important;
            box-shadow: 0 12px 26px rgba(246, 138, 10, 0.30) !important;
        }}
        button:disabled {{
            transform: none !important;
            box-shadow: none !important;
        }}
        [data-baseweb="tab-list"] {{
            gap: 0.3rem;
            padding: 0.32rem;
            border-radius: 14px;
            background: rgba(223, 234, 237, 0.64);
        }}
        [data-baseweb="tab"] {{
            min-height: 2.55rem;
            border-radius: 10px;
            padding-inline: 1rem;
            color: var(--ink-muted);
            font-weight: 650;
        }}
        [data-baseweb="tab"][aria-selected="true"] {{
            color: var(--ink-strong);
            background: #fff;
            box-shadow: 0 5px 14px rgba(27, 60, 75, 0.09);
        }}
        [data-testid="stSegmentedControl"] {{
            padding: 0.22rem;
            border: 1px solid var(--line);
            border-radius: 13px;
            background: rgba(255,255,255,0.82);
        }}
        [data-testid="stSegmentedControl"] label {{
            border-radius: 9px !important;
            font-weight: 630;
        }}
        [data-testid="stExpander"] {{
            border-color: var(--line);
            border-radius: var(--radius-md);
            background: rgba(255,255,255,0.78);
        }}
        [data-testid="stAlert"] {{
            border-radius: var(--radius-md);
            border-width: 1px;
            box-shadow: 0 6px 18px rgba(27, 60, 75, 0.05);
        }}
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            background: #fff;
            box-shadow: var(--shadow-sm);
        }}
        hr {{ border-color: var(--line) !important; }}

        @media (max-width: 768px) {{
            [data-testid="stMainBlockContainer"], .block-container {{
                width: 100%;
                padding: 1.35rem 1rem 3rem;
            }}
            [data-testid="stMetric"] {{
                min-height: 5.7rem;
                padding: 0.85rem;
            }}
            h1 {{ font-size: 1.75rem !important; }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                scroll-behavior: auto !important;
                transition-duration: 0.01ms !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
