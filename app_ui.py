import html
import re
from urllib.parse import urlsplit
import streamlit as st
import auth_ui

DISLIKE_REASONS = [
    "המידע אינו מדויק או שגוי",
    "התשובה לא ענתה על מה ששאלתי",
    "התשובה לא הייתה מפורטת מספיק",
    "הניסוח לא היה ברור / מבלבל",
    "הטון או אופן הפנייה לא היו נעימים",
]

# Plain string — no f-string, so CSS braces are safe
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap');

:root {
    --ink: #172b2a;
    --muted: #687775;
    --green: #087e70;
    --green-light: #e8f5f1;
    --green-hover: #06665b;
    --line: #dce5df;
    --card-bg: #ffffff;
}

.stApp {
    direction: rtl;
    color: var(--ink);
    background: radial-gradient(ellipse at 85% 0%, #e4f2e9 0, transparent 36%), #f7f8f5;
    font-family: 'Heebo', sans-serif;
}

[data-testid="stSidebar"] {
    background: #edf3ee;
    border-left: 1px solid var(--line);
}

[data-testid="stSidebar"] * { font-family: 'Heebo', sans-serif; }
.block-container { max-width: 860px; padding-top: 2.5rem; padding-bottom: 8rem; }

.brand-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; border-radius: 13px;
    color: white; background: var(--green); font-size: 23px; font-weight: 700;
    box-shadow: 0 4px 10px rgba(8, 126, 112, 0.25);
}

.eyebrow { color: var(--green); font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.intro-title { color: var(--ink); font-size: 32px; font-weight: 800; line-height: 1.25; margin: 0; }
.intro-copy { color: var(--muted); font-size: 16px; margin-top: 8px; }
.trust-line { color: var(--muted); font-size: 13px; padding: 12px 0 18px; border-bottom: 1px solid var(--line); }

[data-testid="stChatMessage"] {
    direction: rtl;
    text-align: right;
    border-radius: 14px;
    margin-bottom: 14px;
}

[data-testid="stChatInput"] { direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; font-family: 'Heebo', sans-serif; }

.stButton > button {
    direction: rtl;
    text-align: right;
    border-color: var(--line);
    color: var(--ink);
    border-radius: 10px;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    border-color: var(--green);
    color: var(--green);
    background: #f0f7f4;
}

.src-toggle {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 14px; padding: 6px 13px;
    font-size: 12px; font-weight: 700;
    color: var(--green); background: var(--green-light);
    border: 1px solid #c5e0d8; border-radius: 999px;
    cursor: pointer; list-style: none; user-select: none;
    transition: background 0.15s ease; font-family: 'Heebo', sans-serif;
}
.src-toggle::-webkit-details-marker { display: none; }
.src-toggle:hover { background: #d5ede6; }

.src-popup {
    margin-top: 8px; padding: 12px 14px;
    background: #ffffff; border: 1px solid #daeae3;
    border-radius: 14px; box-shadow: 0 6px 24px rgba(8,80,60,0.10);
    display: flex; flex-direction: column; gap: 7px;
    direction: rtl; font-family: 'Heebo', sans-serif; max-width: 420px;
}

.src-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }

.src-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 6px;
    background: var(--green-light); color: var(--green);
    font-size: 11px; font-weight: 700; flex-shrink: 0;
}

.src-link {
    color: var(--ink) !important; font-weight: 600;
    text-decoration: none !important; flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    transition: color 0.15s ease;
}
.src-link:hover { color: var(--green) !important; }
.src-arrow { font-size: 11px; color: var(--green); flex-shrink: 0; }

.fb-toast {
    font-size: 12px; color: var(--green); font-weight: 700;
    padding: 4px 10px; background: var(--green-light);
    border-radius: 8px; border: 1px solid #c5e0d8;
    font-family: 'Heebo', sans-serif; display: inline-block; margin-top: 8px;
}
.fb-card {
    margin-top: 10px; padding: 14px 16px;
    background: #fff; border: 1px solid #daeae3;
    border-radius: 14px; direction: rtl;
    font-family: 'Heebo', sans-serif;
    box-shadow: 0 4px 16px rgba(8,80,60,0.08);
    max-width: 480px;
}
.fb-card-title { font-size: 14px; font-weight: 700; color: var(--ink); margin-bottom: 10px; }
</style>
"""

_HEADER_HTML = """
<div style="display:flex;align-items:center;gap:13px;margin-bottom:22px">
  <div class="brand-mark">✳</div>
  <div><div class="eyebrow">FNX DIRECT</div><div style="font-size:17px;font-weight:700">העוזר של הפניקס</div></div>
</div>
<div class="eyebrow">מידע ברור, במקום אחד</div>
<h1 class="intro-title">איך אפשר לעזור?</h1>
<div class="intro-copy">שאלו על ביטוח, תביעות ושירות. התשובות מבוססות על המידע באתר הפניקס.</div>
<div class="trust-line">✳ &nbsp; תשובות מבוססות מקור &nbsp; · &nbsp; קישורים מאומתים לעמודי הפניקס</div>
"""


def render_header(user=None):
    st.markdown(_CSS, unsafe_allow_html=True)
    greeting_html = ""
    if user:
        name = html.escape(user.get("name", "משתמש"))
        greeting_html = f'<div style="font-size:13px;color:#087e70;font-weight:700;margin-bottom:6px">שלום, {name} 👋</div>'
    st.markdown(greeting_html + _HEADER_HTML, unsafe_allow_html=True)


def render_sidebar(conversations, user=None):
    with st.sidebar:
        st.markdown("### הפניקס")
        st.caption("עוזר מידע אישי")
        show_auth = auth_ui.render_sidebar_auth(user)
        st.divider()
        action = None
        if st.button("שיחה חדשה", use_container_width=True):
            action = ("new", None)
        if user and st.button("⚙️ הגדרות אישיות", use_container_width=True):
            action = ("preferences", None)
        st.divider()
        st.markdown("**היסטוריית שיחות**")
        for conversation in conversations:
            if st.button(
                conversation["title"],
                key=f"history_{conversation['id']}",
                use_container_width=True,
            ):
                action = ("select", conversation["id"])
        st.divider()
        st.markdown("**נושאים שאפשר לשאול עליהם**")
        st.caption("תביעות · ביטוח רכב · ביטוח דירה · ביטוח נסיעות")
    return action, show_auth


def render_suggestions():
    st.markdown("**אפשר להתחיל מכאן**")
    suggestions = [
        "איך מגישים תביעה על נזקי מים?",
        'מה כולל ביטוח נסיעות לחו"ל?',
        "איך יוצרים קשר עם הפניקס?",
    ]
    suggestion_columns = st.columns(len(suggestions))
    selected_question = None
    for column, suggestion in zip(suggestion_columns, suggestions):
        if column.button(suggestion, use_container_width=True):
            selected_question = suggestion
    return selected_question


def render_messages(messages, on_feedback=None):
    for idx, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                st.markdown(message["content"])
                render_sources(message.get("sources"))
                if on_feedback and message.get("message_id"):
                    render_feedback_buttons(message["message_id"], idx)
            else:
                st.markdown(message["content"])


def render_feedback_buttons(message_id, idx):
    fb_key = f"fb_{message_id}"
    state = st.session_state.get(fb_key, "idle")  # idle | liked | dislike_open | submitted

    if state == "liked":
        st.markdown('<div class="fb-toast">תודה על המשוב שלך! 👍</div>', unsafe_allow_html=True)
        return
    if state == "submitted":
        st.markdown('<div class="fb-toast">המשוב התקבל, תודה שעזרת לנו להשתפר! ❤️</div>', unsafe_allow_html=True)
        return

    col_like, col_dislike, _ = st.columns([1, 1, 8])
    with col_like:
        if st.button("👍", key=f"like_{message_id}", help="תשובה טובה", disabled=(state != "idle")):
            st.session_state[fb_key] = "liked"
            st.session_state[f"fb_submit_{message_id}"] = {"rating": "LIKE", "reasons": [], "comment": ""}
            st.rerun()
    with col_dislike:
        if st.button("👎", key=f"dislike_{message_id}", help="דווח על בעיה", disabled=(state not in {"idle", "dislike_open"})):
            st.session_state[fb_key] = "idle" if state == "dislike_open" else "dislike_open"
            st.rerun()

    if state == "dislike_open":
        st.markdown('<div class="fb-card"><div class="fb-card-title">מה לא היה בסדר?</div></div>', unsafe_allow_html=True)
        selected = []
        for reason in DISLIKE_REASONS:
            if st.checkbox(reason, key=f"reason_{message_id}_{reason}"):
                selected.append(reason)
        comment = st.text_area(
            "פרטים נוספים",
            placeholder="נשמח לפרטים נוספים שיעזרו לנו להשתפר...",
            key=f"comment_{message_id}",
            label_visibility="collapsed",
            height=80,
        )
        c1, c2, _ = st.columns([2, 2, 6])
        with c1:
            if st.button("שלח משוב", key=f"submit_fb_{message_id}", type="primary"):
                st.session_state[f"fb_submit_{message_id}"] = {
                    "rating": "DISLIKE",
                    "reasons": selected,
                    "comment": comment,
                }
                st.session_state[fb_key] = "submitted"
                st.rerun()
        with c2:
            if st.button("ביטול", key=f"cancel_fb_{message_id}"):
                st.session_state[fb_key] = "idle"
                st.rerun()


def render_preferences_panel(user, on_save):
    from auth_db import get_bot_preferences, save_bot_preferences
    prefs = get_bot_preferences(user["sub"])

    st.markdown("### הגדרות אישיות")
    preferred_name = st.text_input(
        "שם / פנייה מועדפת",
        value=prefs.get("preferred_name") or "",
        placeholder="לדוגמא: רינה",
    )
    response_length = st.radio(
        "אורך תשובה",
        options=["short", "standard", "detailed"],
        format_func=lambda x: {
            "short": "קצר ותמציתי (עד 3 משפטים)",
            "standard": "סטנדרטי (1-2 פסקאות)",
            "detailed": "מפורט ומעמיק (עם נקודות)",
        }[x],
        index=["short", "standard", "detailed"].index(prefs.get("response_length", "standard")),
        horizontal=True,
    )
    tone = st.radio(
        "סגנון וטון",
        options=["simple", "formal"],
        format_func=lambda x: "פשוט ובגובה העיניים" if x == "simple" else "מקצועי ורשמי",
        index=["simple", "formal"].index(prefs.get("tone", "simple")),
        horizontal=True,
    )
    if st.button("שמור הגדרות", type="primary"):
        save_bot_preferences(user["sub"], preferred_name or None, response_length, tone)
        st.success("ההגדרות נשמרו בהצלחה!")
        if on_save:
            on_save({"preferred_name": preferred_name or None, "response_length": response_length, "tone": tone})


def _clean_source_title(title, url=None):
    if not isinstance(title, str) or not title.strip():
        if url:
            parts = [p for p in urlsplit(url).path.split("/") if p]
            if parts:
                return parts[-1].replace("-", " ").title()
        return "עמוד מידע באתר הפניקס"

    clean = title.strip()
    for phrase in [
        "| הפניקס חברה לביטוח",
        "| הפניקס",
        "- הפניקס חברה לביטוח",
        "- הפניקס",
        "הפניקס -",
        "הפניקס |",
        "הפניקס",
    ]:
        if clean.endswith(phrase):
            clean = clean[:-len(phrase)].strip(" -|·")
        if clean.startswith(phrase):
            clean = clean[len(phrase):].strip(" -|·")
    return clean or "עמוד מידע באתר הפניקס"


def _group_sources(cited_sources):
    grouped = []
    seen = {}
    for source in cited_sources:
        url = _source_link(source.get("url"))
        raw_title = source.get("title")
        snippet = source.get("snippet", "").strip()
        if not snippet:
            continue
        key = url if url else (raw_title or snippet[:30])
        if key in seen:
            seen[key]["snippets"].append(snippet)
        else:
            entry = {
                "url": url,
                "title": _clean_source_title(raw_title, url),
                "snippets": [snippet],
            }
            seen[key] = entry
            grouped.append(entry)
    return grouped


def _strip_html_tags(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def render_sources(sources):
    if not isinstance(sources, list):
        return

    cited_sources = [
        s for s in sources
        if isinstance(s, dict) and isinstance(s.get("snippet"), str)
    ]
    if not cited_sources:
        return

    grouped = _group_sources(cited_sources)
    if not grouped:
        return

    rows_html = []
    for idx, item in enumerate(grouped, 1):
        url = item["url"]
        title = html.escape(_strip_html_tags(item["title"]))
        if url:
            safe_url = html.escape(url, quote=True)
            rows_html.append(
                f'<div class="src-row">'
                f'<span class="src-num">{idx}</span>'
                f'<a class="src-link" href="{safe_url}" target="_blank" rel="noopener noreferrer" title="{title}">{title}</a>'
                f'<span class="src-arrow">↗</span>'
                f'</div>'
            )
        else:
            rows_html.append(
                f'<div class="src-row">'
                f'<span class="src-num">{idx}</span>'
                f'<span class="src-link">{title}</span>'
                f'</div>'
            )

    count = len(grouped)
    label = f"מקורות ({count})" if count > 1 else "מקור"
    full_html = (
        f'<details>'
        f'<summary class="src-toggle">✳ {label} ▾</summary>'
        f'<div class="src-popup">{"".join(rows_html)}</div>'
        f'</details>'
    )
    st.markdown(full_html, unsafe_allow_html=True)


def render_message_content(content, sources=None):
    st.markdown(content)
    render_sources(sources)


def _source_link(url):
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
    except ValueError:
        return None
    if (
        parsed_url.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed_url.path in {"", "/"}
    ):
        return None
    return url
