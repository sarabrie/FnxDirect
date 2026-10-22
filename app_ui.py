import html
import re
from datetime import date, datetime
from urllib.parse import urlsplit
import streamlit as st
from routes import history_page, landing_page, logout_page

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
    --ink: #142c32;
    --muted: #5d7074;
    --teal: #087f79;
    --teal-dark: #08645f;
    --teal-pale: #e5f4f1;
    --gold: #d79a34;
    --line: #d9e3e2;
    --surface: #ffffff;
    --canvas: #f5f8f7;
}

.stApp {
    direction: rtl;
    color: var(--ink);
    background:
      radial-gradient(ellipse at 86% 0%, rgba(8,127,121,.075), transparent 32%),
      var(--canvas);
    font-family: 'Heebo', sans-serif;
}

[data-testid="stSidebar"] {
    background: #eef4f2;
    border-left: 1px solid var(--line);
}

[data-testid="stSidebar"] * { font-family: 'Heebo', sans-serif; }
.block-container { max-width: 980px; padding: 2.5rem 2rem 7rem; }
.stApp, .stApp button, .stApp input, .stApp textarea { font-family: 'Heebo', sans-serif; }

.brand-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; border-radius: 12px;
    color: white; background: var(--teal); font-size: 23px; font-weight: 700;
    box-shadow: 0 4px 10px rgba(8,100,95,.20);
}

.app-heading { padding: 12px 0 22px; border-bottom: 1px solid var(--line); margin-bottom: 26px; }
.app-brand { display:flex; align-items:center; gap:12px; margin-bottom:24px; }
.app-brand-name { color:var(--ink); font-size:16px; font-weight:800; }
.app-brand-sub { color:var(--muted); font-size:12px; margin-top:1px; }
.eyebrow { color: var(--teal-dark); font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.intro-title { color: var(--ink); font-size: 34px; font-weight: 800; line-height: 1.25; margin: 0; }
.intro-copy { color: var(--muted); font-size: 15px; margin-top: 8px; line-height:1.7; }
.trust-line { color: var(--muted); font-size: 12px; padding: 13px 0 0; }

[data-testid="stChatMessage"] {
    direction: rtl;
    text-align: right;
    border-radius: 8px;
    margin-bottom: 16px;
    padding: 18px 20px;
    border: 1px solid var(--line);
    background: var(--surface);
    box-shadow: 0 3px 12px rgba(20,44,50,.035);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.8; }
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"] { background: var(--teal-pale); color: var(--teal-dark); }

[data-testid="stChatInput"] { direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; font-family: 'Heebo', sans-serif; min-height:52px; }
[data-testid="stChatInput"] > div { border-color: #b8cecb; border-radius: 8px; box-shadow: 0 8px 26px rgba(20,44,50,.08); }
[data-testid="stChatInput"] > div:focus-within { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(8,127,121,.12), 0 8px 26px rgba(20,44,50,.08); }

.stButton > button {
    direction: rtl;
    text-align: right;
    border-color: var(--line);
    color: var(--ink);
    border-radius: 7px;
    min-height: 40px;
    transition: color .16s ease, background .16s ease, border-color .16s ease, transform .16s ease;
}

.stButton > button:hover {
    border-color: var(--teal);
    color: var(--teal-dark);
    background: #f2faf8;
    transform: translateY(-1px);
}
.stButton > button:focus-visible { outline: 3px solid rgba(8,127,121,.28); outline-offset: 2px; }
[data-testid="stSidebar"] .stButton > button { width:100%; }
[data-testid="stSidebar"] [data-testid="stTextInput"] input { border-radius:7px; background:#fff; }
.history-group { color:#718285; font-size:11px; font-weight:700; letter-spacing:0; margin:14px 0 5px; }
.history-empty { border:1px dashed #bacbc8; border-radius:7px; padding:12px; color:var(--muted); font-size:12px; line-height:1.6; }
.suggestion-heading { color:var(--ink); font-size:16px; font-weight:800; margin:4px 0 4px; }
.suggestion-copy { color:var(--muted); font-size:13px; margin-bottom:12px; }
.stSpinner > div { border-top-color:var(--teal) !important; }

.src-toggle {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 14px; padding: 6px 13px;
    font-size: 12px; font-weight: 700;
    color: var(--teal-dark); background: var(--teal-pale);
    border: 1px solid #b9dcd5; border-radius: 7px;
    cursor: pointer; list-style: none; user-select: none;
    transition: background 0.15s ease; font-family: 'Heebo', sans-serif;
}
.src-toggle::-webkit-details-marker { display: none; }
.src-toggle:hover { background: #d6eeea; }

.src-popup {
    margin-top: 8px; padding: 12px 14px;
    background: #ffffff; border: 1px solid var(--line);
    border-radius: 7px; box-shadow: 0 6px 24px rgba(20,44,50,.10);
    display: flex; flex-direction: column; gap: 7px;
    direction: rtl; font-family: 'Heebo', sans-serif; max-width: 420px;
}

.src-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }

.src-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 6px;
    background: var(--teal-pale); color: var(--teal-dark);
    font-size: 11px; font-weight: 700; flex-shrink: 0;
}

.src-link {
    color: var(--ink) !important; font-weight: 600;
    text-decoration: none !important; flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    transition: color 0.15s ease;
}
.src-link:hover { color: var(--teal-dark) !important; }
.src-arrow { font-size: 11px; color: var(--teal-dark); flex-shrink: 0; }

.fb-toast {
    font-size: 12px; color: var(--teal-dark); font-weight: 700;
    padding: 4px 10px; background: var(--teal-pale);
    border-radius: 7px; border: 1px solid #b9dcd5;
    font-family: 'Heebo', sans-serif; display: inline-block; margin-top: 8px;
}
.fb-card {
    margin-top: 10px; padding: 14px 16px;
    background: #fff; border: 1px solid var(--line);
    border-radius: 7px; direction: rtl;
    font-family: 'Heebo', sans-serif;
        box-shadow: 0 4px 16px rgba(20,44,50,.08);
    max-width: 480px;
}
.fb-card-title { font-size: 14px; font-weight: 700; color: var(--ink); margin-bottom: 10px; }

@media (max-width: 760px) {
        .block-container { padding: 1.5rem 1rem 6rem; }
        .intro-title { font-size: 28px; }
        [data-testid="stChatMessage"] { padding: 14px; }
}
</style>
"""

_HEADER_HTML = """
<div class="app-heading">
<div class="app-brand">
  <div class="brand-mark">✳</div>
    <div><div class="app-brand-name">FNX Direct</div><div class="app-brand-sub">העוזר החכם של הפניקס</div></div>
</div>
<div class="eyebrow">מידע ברור, במקום אחד</div>
<h1 class="intro-title">איך אפשר לעזור?</h1>
<div class="intro-copy">שאלו על ביטוח, תביעות ושירות. התשובות מבוססות על המידע באתר הפניקס.</div>
<div class="trust-line">✳ &nbsp; תשובות מבוססות מקור &nbsp; · &nbsp; קישורים לעמודי המידע הרלוונטיים</div>
</div>
"""


def render_header(user=None):
    st.markdown(_CSS, unsafe_allow_html=True)
    greeting_html = ""
    if user:
        name = html.escape(user.get("name", "משתמש"))
        greeting_html = f'<div style="font-size:13px;color:#087e70;font-weight:700;margin-bottom:6px">שלום, {name} 👋</div>'
    st.markdown(greeting_html + _HEADER_HTML, unsafe_allow_html=True)


def render_sidebar(conversations, user=None, history_owner_id=None):
    with st.sidebar:
        st.markdown("### FNX Direct")
        st.caption("העוזר החכם של הפניקס")
        _render_sidebar_user(user)
        st.divider()
        action = None
        if st.button("שיחה חדשה", use_container_width=True):
            action = ("new", None)
        if user and st.button("⚙️ הגדרות אישיות", use_container_width=True):
            action = ("preferences", None)
        st.divider()
        search_query = ""
        if user:
            st.markdown("**השיחות שלי**")
            st.page_link(history_page, label="היסטוריה מלאה")
        else:
            st.markdown("**השיחות כאורח**")
            st.caption("התחברו כדי להעביר אותן לחשבון ולשמור אותן שם.")
        search_query = st.text_input(
            "חיפוש שיחה",
            placeholder="חיפוש בכותרת או בתוכן",
            key=f"history_search_{history_owner_id or 'guest'}",
        )
        today = date.today()
        group_labels = {"today": "היום", "week": "7 הימים האחרונים", "older": "קודמות"}
        last_group = None
        for conversation in conversations:
            try:
                updated = datetime.fromisoformat(conversation.get("updated_at", "")).date()
            except (TypeError, ValueError):
                updated = None
            age_days = (today - updated).days if updated else 8
            group = "today" if age_days <= 0 else "week" if age_days <= 7 else "older"
            if group != last_group:
                st.markdown(f'<div class="history-group">{group_labels[group]}</div>', unsafe_allow_html=True)
                last_group = group
            conversation_id = conversation["id"]
            editing_id = st.session_state.get("editing_conversation_id")
            deleting_id = st.session_state.get("deleting_conversation_id")

            if editing_id == conversation_id:
                with st.form(f"rename_history_{conversation_id}"):
                    new_title = st.text_input(
                        "כותרת חדשה",
                        value=conversation["title"],
                        max_chars=48,
                        key=f"rename_title_{conversation_id}",
                    )
                    save_col, cancel_col = st.columns(2)
                    with save_col:
                        save_title = st.form_submit_button(
                            "שמור",
                            disabled=not new_title.strip(),
                        )
                    with cancel_col:
                        cancel_edit = st.form_submit_button("ביטול")
                if save_title:
                    action = ("rename", conversation_id, new_title)
                elif cancel_edit:
                    action = ("cancel_edit", conversation_id)

            row_cols = st.columns([6, 1, 1])
            with row_cols[0]:
                if st.button(
                    conversation["title"],
                    key=f"history_{conversation_id}",
                    use_container_width=True,
                ):
                    action = ("select", conversation_id)
            with row_cols[1]:
                if st.button("✎", key=f"edit_history_{conversation_id}", help="עריכת כותרת"):
                    st.session_state["editing_conversation_id"] = conversation_id
                    st.session_state.pop("deleting_conversation_id", None)
                    st.rerun()
            with row_cols[2]:
                if deleting_id == conversation_id:
                    confirm_delete = st.button(
                        "✓",
                        key=f"confirm_delete_{conversation_id}",
                        help="הסרה מההיסטוריה שלי",
                    )
                    if confirm_delete:
                        action = ("delete", conversation_id)
                elif st.button("×", key=f"delete_history_{conversation_id}", help="הסרה מההיסטוריה שלי"):
                    st.session_state["deleting_conversation_id"] = conversation_id
                    st.session_state.pop("editing_conversation_id", None)
                    st.rerun()
            if deleting_id == conversation_id:
                st.caption("השיחה תוסתר רק מההיסטוריה שלך; הנתונים יישארו במאגר.")
                if st.button("ביטול הסרה", key=f"cancel_delete_{conversation_id}"):
                    action = ("cancel_delete", conversation_id)
        if not conversations:
            empty_message = "לא נמצאו שיחות מתאימות. נסו מילות חיפוש אחרות." if search_query else "השיחות שלכם יופיעו כאן אחרי שתתחילו לשאול."
            st.markdown(f'<div class="history-empty">{empty_message}</div>', unsafe_allow_html=True)
        st.divider()
        st.markdown("**נושאים שאפשר לשאול עליהם**")
        st.caption("תביעות · ביטוח רכב · ביטוח דירה · ביטוח נסיעות")
    return action, False


def _render_sidebar_user(user):
    if user:
        initial = user.get("name", "?")[0].upper()
        name = user.get("name", "משתמש")
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;gap:8px;background:#e8f5f1;'
            f'border:1px solid #c5e0d8;border-radius:999px;padding:5px 14px 5px 10px;'
            f'font-size:13px;font-weight:700;color:#087e70;font-family:Heebo,sans-serif">'
            f'<span style="width:26px;height:26px;border-radius:50%;background:#087e70;color:white;'
            f'display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800">{initial}</span>'
            f'{name}</div>',
            unsafe_allow_html=True,
        )
        st.caption(user.get("email", ""))
        st.page_link(logout_page, label="התנתקות")
    else:
        st.caption("כניסה כאורח")
        if st.button("התחברות / הרשמה", use_container_width=True, type="primary"):
            st.session_state["guest_mode"] = False
            st.switch_page(landing_page)


def render_suggestions():
    st.markdown('<div class="suggestion-heading">אפשר להתחיל מכאן</div><div class="suggestion-copy">בחרו נושא או כתבו שאלה משלכם</div>', unsafe_allow_html=True)
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


def render_followup_chips(questions):
    """Render 2-3 follow-up suggestion chips. Returns the clicked question or None."""
    if not questions:
        return None
    st.markdown('<div class="followup-chips">', unsafe_allow_html=True)
    cols = st.columns(len(questions))
    clicked = None
    for col, q in zip(cols, questions):
        if col.button(f"↩ {q}", key=f"followup_{hash(q)}", use_container_width=True):
            clicked = q
    st.markdown('</div>', unsafe_allow_html=True)
    return clicked


def _sanitize_for_copy(text):
    """Strip Markdown formatting for clean plain-text clipboard content."""
    # Remove code fences
    text = re.sub(r"```[\s\S]*?```", lambda m: re.sub(r"```\w*", "", m.group()).strip(), text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove markdown links, keep label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove headings markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse excess blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_copy_button(content, message_id):
    """Render a self-contained JS copy button — no st.rerun, isolated per message."""
    clean = _sanitize_for_copy(content)
    # Store text in data-attribute (html.escape handles all quotes/special chars safely)
    data_text = html.escape(clean, quote=True)
    uid = f"copy_{message_id}"
    html_snippet = f"""
<button id="{uid}" class="copy-btn"
        title="העתק תוכן ללוח"
        aria-label="העתק תוכן ללוח"
        data-copy="{data_text}"
        onclick="(function(){{
            var btn = document.getElementById('{uid}');
            navigator.clipboard.writeText(btn.dataset.copy).then(function(){{
                btn.textContent = '✓ הועתק!';
                btn.classList.add('copied');
                setTimeout(function(){{ btn.textContent = '⎘ העתק תשובה'; btn.classList.remove('copied'); }}, 2000);
            }}).catch(function(){{
                btn.textContent = '⚠ לא זמין';
                setTimeout(function(){{ btn.textContent = '⎘ העתק תשובה'; }}, 2000);
            }});
        }})()">
  ⎘ העתק תשובה
</button>
"""
    st.markdown(html_snippet, unsafe_allow_html=True)


def render_messages(messages, on_feedback=None):
    selected_question = None
    for idx, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                st.markdown(message["content"])
                follow_up_questions = message.get("follow_up_questions") or []
                if not follow_up_questions and message.get("follow_up_question"):
                    follow_up_questions = [message["follow_up_question"]]
                if follow_up_questions:
                    st.caption("אפשר להמשיך מכאן")
                    message_id = message.get("message_id", idx)
                    for option_idx, follow_up_question in enumerate(follow_up_questions):
                        if st.button(
                            f"💬 {follow_up_question}",
                            key=f"follow_up_{message_id}_{option_idx}",
                            use_container_width=True,
                        ):
                            selected_question = follow_up_question
                render_sources(message.get("sources"))
                render_copy_button(message["content"], message.get("message_id") or idx)
                if on_feedback and message.get("message_id"):
                    render_feedback_buttons(message["message_id"], idx)
            else:
                st.markdown(message["content"])
    return selected_question


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
