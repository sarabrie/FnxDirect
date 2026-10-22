"""Loads the static CSS / HTML files in ui/assets and injects stylesheets into the page."""
import json
from functools import lru_cache
from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).with_name("assets")


@lru_cache(maxsize=None)
def read_asset(name):
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def style_tag(name):
    return f"\n<style>\n{read_asset(name)}</style>\n"


def inject_css(name):
    st.markdown(style_tag(name), unsafe_allow_html=True)


def js_literal(value):
    """
    A value as a JavaScript literal that is safe inside an inline <script>: escaping every "<"
    means text (e.g. from the LLM) can never close the script or open markup.
    """
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
