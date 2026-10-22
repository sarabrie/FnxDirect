"""The collapsible "sources" list under an answer: one row per website page, linking to it."""
import html
import re
from urllib.parse import urlsplit

import streamlit as st

from fnx_direct.assistant.retrieval import public_page_url

_FALLBACK_TITLE = "עמוד מידע באתר הפניקס"
# Brand suffixes / prefixes removed from page titles.
_BRAND_AFFIXES = [
    "| הפניקס חברה לביטוח",
    "| הפניקס",
    "- הפניקס חברה לביטוח",
    "- הפניקס",
    "הפניקס -",
    "הפניקס |",
    "הפניקס",
]


def _clean_title(title, url=None):
    if not isinstance(title, str) or not title.strip():
        if url:
            parts = [p for p in urlsplit(url).path.split("/") if p]
            if parts:
                return parts[-1].replace("-", " ").title()
        return _FALLBACK_TITLE

    clean = title.strip()
    for phrase in _BRAND_AFFIXES:
        if clean.endswith(phrase):
            clean = clean[:-len(phrase)].strip(" -|·")
        if clean.startswith(phrase):
            clean = clean[len(phrase):].strip(" -|·")
    return clean or _FALLBACK_TITLE


def _group_by_page(sources):
    grouped = []
    seen = {}
    for source in sources:
        url = public_page_url(source.get("url"))
        raw_title = source.get("title")
        snippet = source.get("snippet", "").strip()
        if not snippet:
            continue
        key = url if url else (raw_title or snippet[:30])
        if key in seen:
            seen[key]["snippets"].append(snippet)
        else:
            entry = {"url": url, "title": _clean_title(raw_title, url), "snippets": [snippet]}
            seen[key] = entry
            grouped.append(entry)
    return grouped


def _row_html(number, item):
    title = html.escape(re.sub(r"<[^>]+>", "", item["title"]).strip())
    if not item["url"]:
        return f'<div class="src-row"><span class="src-num">{number}</span><span class="src-link">{title}</span></div>'
    safe_url = html.escape(item["url"], quote=True)
    return (
        f'<div class="src-row">'
        f'<span class="src-num">{number}</span>'
        f'<a class="src-link" href="{safe_url}" target="_blank" rel="noopener noreferrer" title="{title}">{title}</a>'
        f'<span class="src-arrow">↗</span>'
        f'</div>'
    )


def render_sources(sources):
    if not isinstance(sources, list):
        return
    cited = [s for s in sources if isinstance(s, dict) and isinstance(s.get("snippet"), str)]
    grouped = _group_by_page(cited)
    if not grouped:
        return

    rows_html = "".join(_row_html(number, item) for number, item in enumerate(grouped, 1))
    label = f"מקורות ({len(grouped)})" if len(grouped) > 1 else "מקור"
    st.markdown(
        f'<details>'
        f'<summary class="src-toggle">✳ {label} ▾</summary>'
        f'<div class="src-popup">{rows_html}</div>'
        f'</details>',
        unsafe_allow_html=True,
    )
