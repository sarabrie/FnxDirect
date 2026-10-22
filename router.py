from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from auth_db import init_auth_db
from routes import PAGES

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="wide",
)

st.markdown(
    """
    <style>
    *, *::before, *::after { box-sizing: border-box; }
    html, body, [data-testid="stMain"] {
        max-width: 100%;
        overflow-x: hidden;
    }
    [data-testid="stApp"], [data-testid="stAppViewContainer"],
    [data-testid="stMainBlockContainer"], .block-container,
    [data-testid="stColumn"], [data-testid="stHorizontalBlock"],
    [data-testid="stForm"], [data-testid="stDataFrame"],
    [data-testid="stDataEditor"], [data-testid="stTable"] {
        max-width: 100%;
        min-width: 0;
    }
    [data-testid="stDataFrame"], [data-testid="stDataEditor"],
    [data-testid="stTable"] {
        overflow-x: auto;
    }
    img, iframe, video, input, textarea, select, button { max-width: 100%; }
    [data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; }

    @media (max-width: 767px) {
        .block-container { width: 100%; padding-inline: 1rem !important; }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.5rem;
        }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            flex: 1 1 100% !important;
            width: 100% !important;
            max-width: 100% !important;
        }
        [data-testid="stSidebar"] { max-width: min(85vw, 20rem); }
        [data-testid="stChatMessage"], [data-testid="stChatInput"] { max-width: 100%; }
        [data-testid="stForm"] { width: 100%; }
    }

    @media (min-width: 768px) and (max-width: 1023px) {
        .block-container { width: 100%; padding-inline: 1.5rem !important; }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.75rem;
        }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            flex: 1 1 18rem;
            min-width: 0;
            max-width: 100%;
        }
        [data-testid="stChatMessage"], [data-testid="stChatInput"] { max-width: 100%; }
        [data-testid="stForm"] { width: 100%; }
    }

    @media (min-width: 1024px) {
        .block-container { width: 100%; }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 0;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_auth_db()
navigation = st.navigation(PAGES, position="hidden")
navigation.run()