import html
import json
import re
from datetime import date, datetime
from urllib.parse import urlsplit
import streamlit as st
from routes import landing_page
from topics import DEFAULT_SUGGESTIONS, TOPICS

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
    --teal-light: #20a69d;
    --teal-pale: #e5f4f1;
    --line: #d9e3e2;
    --hairline: #e8efed;
    --surface: #ffffff;
    --canvas: #f5f8f7;
}

.stApp {
    direction: rtl;
    color: var(--ink);
    background:
      radial-gradient(ellipse at 86% 0%, rgba(8,127,121,.08), transparent 32%),
      radial-gradient(ellipse at 10% 100%, rgba(32,166,157,.06), transparent 30%),
      var(--canvas);
    font-family: 'Heebo', sans-serif;
}
.stApp, .stApp button, .stApp input, .stApp textarea { font-family: 'Heebo', sans-serif; }
/* Streamlit sets text-align:left on each element container; Hebrew content starts on the right. */
.stApp [data-testid="stElementContainer"], .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"] { text-align: right; }
.block-container { max-width: 940px; padding: 1.6rem 2rem 7rem; }
.stSpinner > div { border-top-color: var(--teal) !important; }

/* ── Buttons (base) ── */
.stButton > button {
    direction: rtl; border-color: var(--line); color: var(--ink); border-radius: 10px; min-height: 40px;
    transition: color .16s ease, background .16s ease, border-color .16s ease, transform .16s ease, box-shadow .16s ease;
}
.stButton > button:hover { border-color: var(--teal); color: var(--teal-dark); background: #f2faf8; }
.stButton > button:focus-visible { outline: 3px solid rgba(8,127,121,.28); outline-offset: 2px; }

/* ── Sidebar: fits one screen; only the conversation list scrolls ── */
[data-testid="stSidebar"] { background: #eef4f2; border-left: 1px solid var(--line); }
/* Material icons need their own font — overriding it printed names like "keyboard_double_arrow_left". */
[data-testid="stSidebar"] *:not([data-testid="stIconMaterial"]) { font-family: 'Heebo', sans-serif; }
[data-testid="stSidebarContent"] { direction: rtl; text-align: right; overflow: hidden; }
[data-testid="stSidebarHeader"] { height: 2.6rem; min-height: 0; padding-top: .6rem; }
[data-testid="stSidebarUserContent"] { padding: 0 1.25rem 0; }
@media (min-width: 768px) {
    section[data-testid="stSidebar"] { width: 340px !important; min-width: 340px !important; }
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .55rem; }
/* Streamlit pulls markdown blocks up by -16px (to offset <p> margins); our HTML blocks have no <p>. */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stSidebar"] .stButton > button { width: 100%; }
[data-testid="stSidebar"] [data-testid="stTextInput"] input { border-radius: 10px; background: #fff; min-height: 38px; }
.side-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.side-mark {
    width: 34px; height: 34px; border-radius: 10px; flex: none;
    display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; font-weight: 800;
    background: linear-gradient(135deg, var(--teal-light), var(--teal-dark)); box-shadow: 0 4px 12px rgba(8,100,95,.25);
}
.side-name { font-size: 16px; font-weight: 800; color: var(--ink); }
.user-chip { display: flex; align-items: center; gap: 10px; min-width: 0; }
.user-avatar {
    width: 34px; height: 34px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center;
    background: var(--teal-pale); color: var(--teal-dark); font-weight: 800; font-size: 14px; border: 1px solid #b9dcd5;
}
.user-name { font-size: 14px; font-weight: 700; color: var(--ink); line-height: 1.2; }
.user-email { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.guest-login-hint { color: var(--muted); font-size: 12.5px; margin-top: -2px; }
.side-label { color: #718285; font-size: 12px; font-weight: 700; margin-top: 6px; }
.st-key-history_list { max-height: calc(100vh - 372px); overflow-y: auto; overflow-x: hidden; padding-inline-end: 2px; }
.st-key-history_list [data-testid="stVerticalBlock"] { gap: .3rem; }
.history-group { color: #8a9a9c; font-size: 11px; font-weight: 700; margin: 8px 0 2px; }
.history-empty { color: var(--muted); font-size: 12.5px; padding: 6px 2px; }
[class*="st-key-history_"] button { min-height: 36px; background: transparent; border-color: transparent; }
[class*="st-key-history_"] button:hover { background: #fff; border-color: var(--line); }
[class*="st-key-history_"] button, [class*="st-key-history_"] button > div { justify-content: flex-start; }
[class*="st-key-history_"] button p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13.5px; }
/* Small icon buttons: rename / delete / settings / logout */
[class*="st-key-edit_history_"] button, [class*="st-key-delete_history_"] button,
[class*="st-key-confirm_delete_"] button, [class*="st-key-cancel_delete_"] button,
.st-key-logout button, .st-key-open_settings button {
    min-height: 34px; padding: 0 8px; color: var(--muted); border-color: transparent; background: transparent;
}
[class*="st-key-edit_history_"] button:hover, .st-key-open_settings button:hover,
[class*="st-key-cancel_delete_"] button:hover { color: var(--teal-dark); background: var(--teal-pale); border-color: transparent; }
[class*="st-key-delete_history_"] button:hover, [class*="st-key-confirm_delete_"] button,
.st-key-logout button:hover { color: #b42318; background: #fdecea; border-color: transparent; }
.st-key-new_chat button { font-weight: 700; }
.side-footer {
    display: flex; align-items: center; gap: 6px; padding: 10px 0 12px; margin-top: 4px;
    border-top: 1px solid var(--line); color: #7a8b8d; font-size: 11.5px;
}
.side-footer .copy-mark {
    flex: none; font-size: 15px; font-weight: 700; line-height: 1; color: #6b7d7f;
}

/* ── Header + empty state ── */
.hero { margin: 4px 0 18px; }
.hero-hello { color: var(--teal-dark); font-size: 14px; font-weight: 700; margin-bottom: 2px; }
.hero-title {
    font-size: 34px; font-weight: 800; line-height: 1.2; margin: 0;
    background: linear-gradient(90deg, var(--ink), var(--teal-dark)); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.section-label { color: #718285; font-size: 12.5px; font-weight: 700; margin: 2px 0 6px; }

/* Topic tiles: equal squares, icon above label */
.st-key-topic_grid [data-testid="stHorizontalBlock"] { gap: 10px; }
.st-key-topic_grid .stButton > button {
    min-height: 88px; border-radius: 14px; background: #fff; border: 1px solid var(--line); color: var(--ink);
    box-shadow: 0 2px 10px rgba(20,44,50,.04);
}
.st-key-topic_grid .stButton > button > div,
.st-key-topic_grid .stButton > button > div > span { flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.st-key-topic_grid .stButton > button p { font-size: 14px; font-weight: 700; text-align: center; }
.st-key-topic_grid .stButton > button [data-testid="stIconMaterial"] { font-size: 26px; color: var(--teal); margin: 0; }
.st-key-topic_grid .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(20,44,50,.08); }
.st-key-topic_grid .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--teal-light), var(--teal-dark)); border-color: transparent; color: #fff;
    box-shadow: 0 10px 24px rgba(8,127,121,.28);
}
.st-key-topic_grid .stButton > button[kind="primary"] [data-testid="stIconMaterial"] { color: #fff; }

/* Suggested questions */
.st-key-suggestions .stButton > button {
    min-height: 64px; border-radius: 14px; background: #fff; border-color: var(--line); text-align: right;
    box-shadow: 0 2px 10px rgba(20,44,50,.04);
}
.st-key-suggestions .stButton > button > div, .st-key-suggestions .stButton > button > div > span {
    justify-content: space-between; width: 100%; flex-direction: row-reverse; gap: 8px;
}
.st-key-suggestions .stButton > button [data-testid="stIconMaterial"] { color: var(--teal); }
.st-key-suggestions .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(20,44,50,.08); }

/* ── Chat messages ── */
@keyframes msg-in { from { opacity: 0; transform: translateY(10px); } }
[data-testid="stChatMessage"] {
    direction: rtl; text-align: right; background: transparent; border: none; box-shadow: none;
    padding: 0; margin-bottom: 18px; gap: 12px; animation: msg-in .45s ease both;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.85; font-size: 15.5px; }
/* User: gradient bubble on the right, no avatar */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"] { display: none; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    flex: 0 1 auto; max-width: 78%; padding: 11px 18px; color: #fff; position: relative;
    margin-left: auto !important; margin-right: 0 !important;  /* Streamlit centers it; pin it to the right */
    background: linear-gradient(135deg, #0b9189, var(--teal-dark));
    border-radius: 20px 20px 6px 20px; box-shadow: 0 10px 24px rgba(8,100,95,.22);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] { color: #fff; }
/* The question's copy icon sits just outside the bubble (left) and shows on hover, like common chat apps */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stElementContainer"]:has(iframe) {
    position: absolute; left: -42px; bottom: 4px; width: 34px; opacity: 0; transition: opacity .2s ease;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]):hover [data-testid="stElementContainer"]:has(iframe),
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stElementContainer"]:has(iframe):focus-within { opacity: 1; }
/* Streamlit pulls markdown up by -16px to offset <p> margins; in the bubble we want plain padding */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] p { margin: 0; }
/* Assistant: white card with a gradient avatar */
[data-testid="stChatMessageAvatarAssistant"] {
    width: 38px; height: 38px; border-radius: 12px; color: #fff;
    background: linear-gradient(135deg, var(--teal-light), var(--teal-dark)); box-shadow: 0 6px 16px rgba(8,100,95,.28);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
    background: var(--surface); border: 1px solid var(--hairline); border-radius: 6px 20px 20px 20px;
    padding: 16px 22px 8px; box-shadow: 0 1px 2px rgba(20,44,50,.04), 0 14px 34px rgba(20,44,50,.07);
}
/* Answer actions: copy / like / dislike, under a hairline */
[class*="st-key-actions_"] { border-top: 1px solid var(--hairline); padding-top: 6px; margin-top: 2px; }
[class*="st-key-actions_"] [data-testid="stHorizontalBlock"] { gap: 2px; align-items: center; }
[class*="st-key-like_"] button, [class*="st-key-dislike_"] button {
    min-height: 32px; width: 32px; padding: 0; border-color: transparent; background: transparent; color: #7a8b8d;
}
[class*="st-key-like_"] button:hover, [class*="st-key-dislike_"] button:hover { background: var(--teal-pale); color: var(--teal-dark); border-color: transparent; }
[class*="st-key-like_"] button[kind="primary"] { background: var(--teal-pale); color: var(--teal-dark); }
.fb-thanks { color: var(--teal-dark); font-size: 12.5px; font-weight: 600; }

/* Follow-ups: pills under the answer card; the newest set fades in one after another (light → dark) */
[class*="st-key-followups_"] {
    flex-direction: row !important; flex-wrap: wrap; gap: 8px !important; margin: -6px 50px 18px 0;
}
[class*="st-key-followups_"] > div { width: auto !important; flex: 0 1 auto; }
[class*="st-key-follow_up_"] button {
    min-height: 0; padding: 7px 16px; border-radius: 999px; font-size: 13.5px; font-weight: 600;
    color: var(--teal-dark); background: #fff; border: 1px solid #b9dcd5; box-shadow: 0 3px 10px rgba(8,100,95,.07);
}
[class*="st-key-follow_up_"] button > div, [class*="st-key-follow_up_"] button > div > span { flex-direction: row-reverse; gap: 6px; }
[class*="st-key-follow_up_"] button:hover {
    background: var(--teal-pale); border-color: var(--teal); transform: translateY(-1px); box-shadow: 0 8px 18px rgba(8,100,95,.12);
}
@keyframes fnx-follow-up-in { from { opacity: 0; transform: translateY(8px); color: #b5c6c3; } to { opacity: 1; transform: none; } }
[class*="st-key-fu_anim"] { animation: fnx-follow-up-in .7s ease both; }
[class*="st-key-fu_anim0_"] { animation-delay: .05s; }
[class*="st-key-fu_anim1_"] { animation-delay: .4s; }
[class*="st-key-fu_anim2_"] { animation-delay: .75s; }
[class*="st-key-fu_anim3_"] { animation-delay: 1.1s; }
/* Space kept while the answer is written, so nothing jumps when the actions / follow-ups appear */
.actions-reserve { min-height: 59px; }
.fu-reserve { min-height: 66px; }
@media (prefers-reduced-motion: reduce) {
    [class*="st-key-fu_anim"], [data-testid="stChatMessage"] { animation-duration: .01s; animation-delay: 0s !important; }
}

/* ── Chat input ── */
[data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background: transparent; }
[data-testid="stChatInput"] { direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; font-family: 'Heebo', sans-serif; min-height: 52px; font-size: 15px; }
[data-testid="stChatInput"] > div {
    border-color: #c7d9d6; border-radius: 16px; background: #fff; box-shadow: 0 12px 34px rgba(20,44,50,.10);
}
[data-testid="stChatInput"] > div:focus-within { border-color: var(--teal); box-shadow: 0 0 0 4px rgba(8,127,121,.12), 0 12px 34px rgba(20,44,50,.10); }

/* ── Sources ── */
.src-toggle {
    display: inline-flex; align-items: center; gap: 6px; margin-top: 10px; padding: 5px 12px;
    font-size: 12px; font-weight: 700; color: var(--teal-dark); background: var(--teal-pale);
    border: 1px solid #b9dcd5; border-radius: 999px; cursor: pointer; list-style: none; user-select: none;
    transition: background 0.15s ease; font-family: 'Heebo', sans-serif;
}
.src-toggle::-webkit-details-marker { display: none; }
.src-toggle:hover { background: #d6eeea; }
.src-popup {
    margin-top: 8px; padding: 12px 14px; background: #ffffff; border: 1px solid var(--line);
    border-radius: 12px; box-shadow: 0 6px 24px rgba(20,44,50,.10);
    display: flex; flex-direction: column; gap: 7px; direction: rtl; font-family: 'Heebo', sans-serif; max-width: 420px;
}
.src-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.src-num {
    display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 6px;
    background: var(--teal-pale); color: var(--teal-dark); font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.src-link {
    color: var(--ink) !important; font-weight: 600; text-decoration: none !important; flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: color 0.15s ease;
}
.src-link:hover { color: var(--teal-dark) !important; }
.src-arrow { font-size: 11px; color: var(--teal-dark); flex-shrink: 0; }

/* ── Dislike feedback form ── */
.fb-card-title { font-size: 14px; font-weight: 700; color: var(--ink); margin: 6px 0 2px; }

@media (max-width: 760px) {
    .block-container { padding: 1.2rem 1rem 6rem; }
    .hero-title { font-size: 27px; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] { max-width: 92%; }
    [class*="st-key-followups_"] { margin-right: 0; }
}
</style>
"""


def render_header(user=None):
    st.markdown(_CSS, unsafe_allow_html=True)
    hello = f'<div class="hero-hello">שלום, {html.escape(user.get("name", ""))}</div>' if user else ""
    st.markdown(
        f'<div class="hero">{hello}<h1 class="hero-title">איך אפשר לעזור?</h1></div>',
        unsafe_allow_html=True,
    )


def render_sidebar(conversations, user=None, history_owner_id=None):
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="side-mark">✳</div><div class="side-name">FNX Direct</div></div>',
            unsafe_allow_html=True,
        )
        _render_sidebar_user(user)
        action = None
        if user:
            new_col, settings_col = st.columns([6, 1], gap="small", vertical_alignment="center")
            with new_col:
                if st.button("שיחה חדשה", icon=":material/add:", key="new_chat", use_container_width=True):
                    action = ("new", None)
            with settings_col:
                # No tooltip: Streamlit keeps it open while the button has focus, covering the logout icon.
                if st.button("", icon=":material/settings:", key="open_settings"):
                    action = ("preferences", None)
            action = _render_history(conversations, history_owner_id) or action
        elif st.button("שיחה חדשה", icon=":material/add:", key="new_chat", use_container_width=True):
            action = ("new", None)
        st.markdown(
            '<div class="side-footer"><span class="copy-mark" aria-hidden="true">©</span>'
            "כל הזכויות שמורות לרינה קימל ושרה ברייש</div>",
            unsafe_allow_html=True,
        )
    return action, False


def _render_history(conversations, history_owner_id):
    """Logged-in user's conversation list (search, rename, hide). Returns a sidebar action or None."""
    action = None
    st.markdown('<div class="side-label">השיחות שלי</div>', unsafe_allow_html=True)
    search_query = st.text_input(
        "חיפוש שיחה",
        placeholder="חיפוש בשיחות",
        key=f"history_search_{history_owner_id or 'guest'}",
        label_visibility="collapsed",
    )
    today = date.today()
    group_labels = {"today": "היום", "week": "7 הימים האחרונים", "older": "קודמות"}
    last_group = None
    with st.container(key="history_list"):
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
                with st.form(f"rename_history_{conversation_id}", border=False):
                    new_title = st.text_input(
                        "כותרת חדשה",
                        value=conversation["title"],
                        max_chars=48,
                        key=f"rename_title_{conversation_id}",
                        label_visibility="collapsed",
                    )
                    save_col, cancel_col = st.columns(2)
                    with save_col:
                        save_title = st.form_submit_button("שמירה", disabled=not new_title.strip())
                    with cancel_col:
                        cancel_edit = st.form_submit_button("ביטול")
                if save_title:
                    action = ("rename", conversation_id, new_title)
                elif cancel_edit:
                    action = ("cancel_edit", conversation_id)
                continue

            row_cols = st.columns([7, 1, 1], gap="small", vertical_alignment="center")
            with row_cols[0]:
                if st.button(conversation["title"], key=f"history_{conversation_id}", use_container_width=True):
                    action = ("select", conversation_id)
            if deleting_id == conversation_id:
                # Confirm in place: ✕ keeps it, ✓ hides it from this user's history (data stays in the DB).
                with row_cols[1]:
                    if st.button("", icon=":material/close:", key=f"cancel_delete_{conversation_id}", help="ביטול"):
                        action = ("cancel_delete", conversation_id)
                with row_cols[2]:
                    if st.button("", icon=":material/check:", key=f"confirm_delete_{conversation_id}", help="אישור הסרה"):
                        action = ("delete", conversation_id)
                continue
            with row_cols[1]:
                if st.button("", icon=":material/edit:", key=f"edit_history_{conversation_id}", help="עריכת כותרת"):
                    st.session_state["editing_conversation_id"] = conversation_id
                    st.session_state.pop("deleting_conversation_id", None)
                    st.rerun()
            with row_cols[2]:
                if st.button("", icon=":material/delete:", key=f"delete_history_{conversation_id}", help="הסרה מההיסטוריה"):
                    st.session_state["deleting_conversation_id"] = conversation_id
                    st.session_state.pop("editing_conversation_id", None)
                    st.rerun()
        if not conversations:
            empty_message = "לא נמצאו שיחות." if search_query else "עדיין אין שיחות."
            st.markdown(f'<div class="history-empty">{empty_message}</div>', unsafe_allow_html=True)
    return action


def _go_to_login():
    # After logging in, reopen the conversation the guest was in (it moves into the account).
    st.session_state["resume_conversation_id"] = st.session_state.get("conversation_id")
    st.session_state["guest_mode"] = False
    st.switch_page(landing_page)


def _logout():
    import auth_ui

    auth_ui.logout()
    for key in ("messages", "conversation_id", "conversation_owner_id", "user_prefs", "show_preferences", "topic"):
        st.session_state.pop(key, None)
    st.query_params.clear()
    st.switch_page(landing_page)


def _render_sidebar_user(user):
    if user:
        name = user.get("name") or "משתמש"
        chip_col, logout_col = st.columns([6, 1], gap="small", vertical_alignment="center")
        with chip_col:
            st.markdown(
                f'<div class="user-chip"><span class="user-avatar">{html.escape(name[0].upper())}</span>'
                f'<div style="min-width:0"><div class="user-name">{html.escape(name)}</div>'
                f'<div class="user-email">{html.escape(user.get("email", ""))}</div></div></div>',
                unsafe_allow_html=True,
            )
        with logout_col:
            if st.button("", icon=":material/logout:", key="logout"):
                _logout()
    else:
        if st.button("התחברות / הרשמה", use_container_width=True, type="primary"):
            _go_to_login()
        st.markdown('<div class="guest-login-hint">התחברו כדי לשמור את השיחות שלכם.</div>', unsafe_allow_html=True)


def _toggle_topic(topic):
    st.session_state["topic"] = None if st.session_state.get("topic") == topic else topic


def render_topic_picker():
    """
    Four equal square tiles (icon above label). Clicking a tile limits the search to that topic;
    clicking it again clears the choice. Returns the topic key, or None for all topics.
    """
    selected = st.session_state.get("topic")
    with st.container(key="topic_grid"):
        for column, (topic, info) in zip(st.columns(len(TOPICS), gap="small"), TOPICS.items()):
            with column:
                st.button(
                    info["label"],
                    icon=info["icon"],
                    key=f"topic_{topic}",
                    type="primary" if topic == selected else "secondary",
                    use_container_width=True,
                    on_click=_toggle_topic,
                    args=(topic,),
                )
    return selected


def render_suggestions(topic=None, disabled=False):
    suggestions = TOPICS[topic]["suggestions"] if topic in TOPICS else DEFAULT_SUGGESTIONS
    st.markdown('<div class="section-label">שאלות נפוצות</div>', unsafe_allow_html=True)
    selected_question = None
    with st.container(key="suggestions"):
        for column, suggestion in zip(st.columns(len(suggestions), gap="small"), suggestions):
            if column.button(
                suggestion, icon=":material/arrow_back:", use_container_width=True, disabled=disabled,
                key=f"suggestion_{suggestion}",
            ):
                selected_question = suggestion
    return selected_question


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


_COPY_BUTTON_HTML = """<!doctype html>
<html dir="rtl"><head><meta charset="utf-8">
<style>
  html, body { margin: 0; background: transparent; }
  button {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; padding: 0; color: #7a8b8d;
    background: transparent; border: 1px solid transparent; border-radius: 7px;
    cursor: pointer; transition: background .15s, color .15s, border-color .15s;
  }
  button:hover { background: #e5f4f1; color: #08645f; }
  button:focus-visible { outline: 3px solid rgba(8,127,121,.28); outline-offset: 2px; }
  svg { width: 18px; height: 18px; }
  .done, button.copied .copy, button.failed .copy { display: none; }
  button.copied .done { display: block; }
  button.copied { color: #087f79; background: #e5f4f1; }
  button.failed { color: #b42318; }
</style></head>
<body><button type="button" title="__TITLE__" aria-label="__TITLE__">
  <svg class="copy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="9" y="9" width="11" height="11" rx="2"></rect>
    <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"></path>
  </svg>
  <svg class="done" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7.5"></path>
  </svg>
</button>
<script>
  const text = __TEXT__;
  const title = __LABEL__;
  const btn = document.querySelector("button");
  function fallbackCopy() {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok ? Promise.resolve() : Promise.reject();
  }
  function flash(state, message) {
    btn.classList.add(state);
    btn.title = message;
    btn.setAttribute("aria-label", message);
    setTimeout(() => {
      btn.classList.remove(state);
      btn.title = title;
      btn.setAttribute("aria-label", title);
    }, 2000);
  }
  btn.addEventListener("click", () => {
    const copy = navigator.clipboard ? navigator.clipboard.writeText(text).catch(fallbackCopy) : fallbackCopy();
    copy.then(() => flash("copied", "הועתק!"), () => flash("failed", "ההעתקה לא זמינה"));
  });
</script></body></html>"""


def _js_string(value):
    # json.dumps gives a valid JS string literal; escaping every "<" means LLM text can never
    # close the <script> or open markup inside the iframe.
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def render_copy_button(content, label="העתקה"):
    """Copy icon button (label is its tooltip). Runs in an iframe because st.markdown strips onclick/JS."""
    page = (
        _COPY_BUTTON_HTML.replace("__TITLE__", html.escape(label, quote=True))
        .replace("__LABEL__", _js_string(label))
        .replace("__TEXT__", _js_string(_sanitize_for_copy(content)))
    )
    st.iframe(page, height=34)


def render_follow_up_reserve():
    """Empty space under the answer card where the follow-ups will appear, so nothing jumps."""
    st.markdown('<div class="fu-reserve" aria-hidden="true"></div>', unsafe_allow_html=True)


def render_actions_reserve():
    """Empty space for the copy / feedback buttons that appear after the answer is saved."""
    st.markdown('<div class="actions-reserve" aria-hidden="true"></div>', unsafe_allow_html=True)


_SEARCH_STEPS = ["מחפש מידע באתר הפניקס…", "מנתח את המקורות הרלוונטיים…", "מנסח תשובה…"]
_SEARCH_STEP_SECONDS = 2.4


def render_search_status(placeholder):
    """Rotating status text (search → analyze → compose); the last step stays until the answer starts."""
    spans = []
    for index, step in enumerate(_SEARCH_STEPS):
        is_last = index == len(_SEARCH_STEPS) - 1
        animation = "fnx-step-last" if is_last else "fnx-step"
        spans.append(
            f'<span class="fnx-status-step" style="animation: {animation} {_SEARCH_STEP_SECONDS}s ease '
            f'{index * _SEARCH_STEP_SECONDS}s both">{html.escape(step)}</span>'
        )
    placeholder.markdown(
        """
<style>
.fnx-status { display:flex; align-items:center; gap:10px; min-height:28px; color:var(--teal-dark, #08645f);
    font-size:14px; font-weight:600; }
.fnx-status-dot { width:14px; height:14px; border-radius:50%; flex:none;
    border:2px solid #b9dcd5; border-top-color:#087f79; animation: fnx-spin .8s linear infinite; }
.fnx-status-text { position:relative; flex:1; height:22px; }
.fnx-status-step { position:absolute; inset-inline-start:0; top:0; white-space:nowrap; opacity:0; }
@keyframes fnx-spin { to { transform: rotate(360deg); } }
@keyframes fnx-step { 0% { opacity:0; transform:translateY(4px); } 12%, 85% { opacity:1; transform:none; }
    100% { opacity:0; transform:translateY(-4px); } }
@keyframes fnx-step-last { 0% { opacity:0; transform:translateY(4px); } 12%, 100% { opacity:1; transform:none; } }
@media (prefers-reduced-motion: reduce) {
    .fnx-status-dot { animation-duration: 2s; }
    .fnx-status-step { animation-duration: .01s !important; }
}
</style>
<div class="fnx-status" role="status" aria-live="polite">
  <span class="fnx-status-dot"></span>
  <span class="fnx-status-text">"""
        + "".join(spans)
        + "</span></div>",
        unsafe_allow_html=True,
    )


def render_messages(messages, on_feedback=None, animate_follow_ups_for=None, disabled=False):
    selected_question = None
    assistant_indexes = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    last_assistant = assistant_indexes[-1] if assistant_indexes else None
    for idx, message in enumerate(messages):
        if message["role"] != "assistant":
            with st.chat_message("user"):
                st.markdown(message["content"])
                render_copy_button(message["content"], label="העתקת השאלה")
            continue

        message_id = message.get("message_id") or idx
        with st.chat_message("assistant"):
            st.markdown(message["content"])
            render_sources(message.get("sources"))
            render_message_actions(message["content"], message_id, with_feedback=bool(on_feedback and message.get("message_id")))
        # Follow-ups sit under the answer card, only for the latest answer.
        if idx == last_assistant:
            follow_up_questions = message.get("follow_up_questions") or []
            if not follow_up_questions and message.get("follow_up_question"):
                follow_up_questions = [message["follow_up_question"]]
            clicked = render_follow_ups(
                follow_up_questions, message_id, animate=message_id == animate_follow_ups_for, disabled=disabled
            )
            selected_question = clicked or selected_question
    return selected_question


def render_follow_ups(questions, message_id, animate=False, disabled=False):
    """Follow-up pills under the answer card. Returns the clicked question or None."""
    if not questions:
        return None
    clicked = None
    with st.container(key=f"followups_{message_id}"):
        for option_idx, question in enumerate(questions):
            # Wrapper key only drives the CSS fade-in; the button keeps its own stable key.
            with st.container(key=f"fu_anim{option_idx}_{message_id}") if animate else st.container():
                if st.button(
                    question,
                    icon=":material/arrow_back:",
                    key=f"follow_up_{message_id}_{option_idx}",
                    disabled=disabled,
                ):
                    clicked = question
    return clicked


def render_message_actions(content, message_id, with_feedback=True):
    """Copy / like / dislike row at the bottom of an answer card."""
    fb_key = f"fb_{message_id}"
    state = st.session_state.get(fb_key, "idle")  # idle | liked | dislike_open | submitted
    with st.container(key=f"actions_{message_id}"):
        copy_col, like_col, dislike_col, note_col = st.columns([1, 1, 1, 9], gap="small", vertical_alignment="center")
        with copy_col:
            render_copy_button(content, label="העתקת התשובה")
        if not with_feedback:
            return
        with like_col:
            if st.button(
                "", icon=":material/thumb_up:", key=f"like_{message_id}", help="תשובה טובה",
                type="primary" if state == "liked" else "secondary", disabled=state in {"liked", "submitted"},
            ):
                st.session_state[fb_key] = "liked"
                st.session_state[f"fb_submit_{message_id}"] = {"rating": "LIKE", "reasons": [], "comment": ""}
                st.rerun()
        with dislike_col:
            if st.button(
                "", icon=":material/thumb_down:", key=f"dislike_{message_id}", help="דיווח על בעיה",
                disabled=state in {"liked", "submitted"},
            ):
                st.session_state[fb_key] = "idle" if state == "dislike_open" else "dislike_open"
                st.rerun()
        with note_col:
            if state in {"liked", "submitted"}:
                st.markdown('<span class="fb-thanks">תודה על המשוב</span>', unsafe_allow_html=True)

    if state == "dislike_open":
        st.markdown('<div class="fb-card-title">מה לא היה בסדר?</div>', unsafe_allow_html=True)
        selected = [reason for reason in DISLIKE_REASONS if st.checkbox(reason, key=f"reason_{message_id}_{reason}")]
        comment = st.text_area(
            "פרטים נוספים",
            placeholder="פרטים נוספים (לא חובה)",
            key=f"comment_{message_id}",
            label_visibility="collapsed",
            height=80,
        )
        c1, c2, _ = st.columns([2, 2, 6])
        with c1:
            if st.button("שליחה", key=f"submit_fb_{message_id}", type="primary"):
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

    # No chat input on this screen, so no need for the bottom space reserved for it.
    st.markdown('<style>.block-container { padding-bottom: 2rem; }</style>', unsafe_allow_html=True)
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
