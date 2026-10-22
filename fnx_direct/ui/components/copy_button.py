"""Copy-to-clipboard icon button (an iframe, because st.markdown strips onclick / JS)."""
import html
import re

import streamlit as st

from fnx_direct.ui.styles import js_literal, read_asset


def _plain_text(text):
    """Strip Markdown formatting for clean plain-text clipboard content."""
    # Code fences → their content
    text = re.sub(r"```[\s\S]*?```", lambda m: re.sub(r"```\w*", "", m.group()).strip(), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)  # bold / italic
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links → label
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # heading markers
    text = re.sub(r"<[^>]+>", "", text)  # HTML tags
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_copy_button(content, label="העתקה"):
    """Copy icon button; `label` is its tooltip."""
    page = (
        read_asset("copy_button.html")
        .replace("__TITLE__", html.escape(label, quote=True))
        .replace("__LABEL__", js_literal(label))
        .replace("__TEXT__", js_literal(_plain_text(content)))
    )
    st.iframe(page, height=34)
