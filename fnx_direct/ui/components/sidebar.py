"""
Chat sidebar: brand, the user chip (or sign-in button for guests), "new chat", settings and the
conversation history (search, rename, hide). Rendering returns the action the user chose, if any:
    ("new", None) · ("preferences", None) · ("select", id) · ("rename", id, title) ·
    ("delete", id) · ("cancel_edit", id) · ("cancel_delete", id)
"""
import html
from datetime import date, datetime

import streamlit as st

from fnx_direct.auth import session
from fnx_direct.history.database import TITLE_MAX_LENGTH
from fnx_direct.ui import navigation

EDITING_KEY = "editing_conversation_id"
DELETING_KEY = "deleting_conversation_id"
# Chat-page state dropped on logout.
_CHAT_STATE_KEYS = ("messages", "conversation_id", "conversation_owner_id", "user_prefs", "show_preferences", "topic")
_HISTORY_GROUPS = {"today": "היום", "week": "7 הימים האחרונים", "older": "קודמות"}


def history_search_key(owner_id):
    return f"history_search_{owner_id or 'guest'}"


def render_sidebar(conversations, user=None, history_owner_id=None):
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="side-mark">✳</div><div class="side-name">FNX Direct</div></div>',
            unsafe_allow_html=True,
        )
        _render_user(user)
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
    return action


def _render_user(user):
    if not user:
        if st.button("התחברות / הרשמה", use_container_width=True, type="primary"):
            _go_to_login()
        st.markdown('<div class="guest-login-hint">התחברו כדי לשמור את השיחות שלכם.</div>', unsafe_allow_html=True)
        return

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


def _go_to_login():
    # After logging in, reopen the conversation the guest was in (it moves into the account).
    st.session_state["resume_conversation_id"] = st.session_state.get("conversation_id")
    st.session_state["guest_mode"] = False
    st.switch_page(navigation.landing_page)


def _logout():
    session.logout()
    for key in _CHAT_STATE_KEYS:
        st.session_state.pop(key, None)
    st.query_params.clear()
    st.switch_page(navigation.landing_page)


def _history_group(conversation, today):
    try:
        updated = datetime.fromisoformat(conversation.get("updated_at", "")).date()
    except (TypeError, ValueError):
        updated = None
    age_days = (today - updated).days if updated else 8
    return "today" if age_days <= 0 else "week" if age_days <= 7 else "older"


def _render_history(conversations, history_owner_id):
    """Logged-in user's conversation list (search, rename, hide). Returns a sidebar action or None."""
    action = None
    st.markdown('<div class="side-label">השיחות שלי</div>', unsafe_allow_html=True)
    search_query = st.text_input(
        "חיפוש שיחה",
        placeholder="חיפוש בשיחות",
        key=history_search_key(history_owner_id),
        label_visibility="collapsed",
        live=True,  # filter while typing, no Enter needed
    )
    today = date.today()
    last_group = None
    with st.container(key="history_list"):
        for conversation in conversations:
            group = _history_group(conversation, today)
            if group != last_group:
                st.markdown(f'<div class="history-group">{_HISTORY_GROUPS[group]}</div>', unsafe_allow_html=True)
                last_group = group
            if st.session_state.get(EDITING_KEY) == conversation["id"]:
                action = _render_rename_form(conversation) or action
            else:
                action = _render_history_row(conversation) or action
        if not conversations:
            empty_message = "לא נמצאו שיחות." if search_query else "עדיין אין שיחות."
            st.markdown(f'<div class="history-empty">{empty_message}</div>', unsafe_allow_html=True)
    return action


def _render_rename_form(conversation):
    conversation_id = conversation["id"]
    with st.form(f"rename_history_{conversation_id}", border=False):
        new_title = st.text_input(
            "כותרת חדשה",
            value=conversation["title"],
            max_chars=TITLE_MAX_LENGTH,
            key=f"rename_title_{conversation_id}",
            label_visibility="collapsed",
        )
        save_col, cancel_col = st.columns(2)
        with save_col:
            save_title = st.form_submit_button("שמירה", disabled=not new_title.strip())
        with cancel_col:
            cancel_edit = st.form_submit_button("ביטול")
    if save_title:
        return ("rename", conversation_id, new_title)
    if cancel_edit:
        return ("cancel_edit", conversation_id)
    return None


def _render_history_row(conversation):
    conversation_id = conversation["id"]
    action = None
    row_cols = st.columns([7, 1, 1], gap="small", vertical_alignment="center")
    with row_cols[0]:
        if st.button(conversation["title"], key=f"history_{conversation_id}", use_container_width=True):
            action = ("select", conversation_id)

    if st.session_state.get(DELETING_KEY) == conversation_id:
        # Confirm in place: ✕ keeps it, ✓ hides it from this user's history (data stays in the DB).
        with row_cols[1]:
            if st.button("", icon=":material/close:", key=f"cancel_delete_{conversation_id}", help="ביטול"):
                action = ("cancel_delete", conversation_id)
        with row_cols[2]:
            if st.button("", icon=":material/check:", key=f"confirm_delete_{conversation_id}", help="אישור הסרה"):
                action = ("delete", conversation_id)
        return action

    with row_cols[1]:
        if st.button("", icon=":material/edit:", key=f"edit_history_{conversation_id}", help="עריכת כותרת"):
            st.session_state[EDITING_KEY] = conversation_id
            st.session_state.pop(DELETING_KEY, None)
            st.rerun()
    with row_cols[2]:
        if st.button("", icon=":material/delete:", key=f"delete_history_{conversation_id}", help="הסרה מההיסטוריה"):
            st.session_state[DELETING_KEY] = conversation_id
            st.session_state.pop(EDITING_KEY, None)
            st.rerun()
    return action
