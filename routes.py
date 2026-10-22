import streamlit as st

import admin_ui
import auth_ui
import landing_ui
from auth_db import (
    consume_google_oauth_state,
    login_or_register_google,
)
from chat_history import list_conversations


def render_landing_page():
    if auth_ui.get_current_user() or st.session_state.get("guest_mode"):
        st.switch_page(chat_page)
    landing_ui.render_landing()


def render_history_page():
    user = auth_ui.get_current_user()
    if not user:
        st.switch_page(landing_page)

    st.title("היסטוריית שיחות")
    conversations = list_conversations(user_id=user["sub"])
    if not conversations:
        st.info("עדיין אין שיחות בחשבון.")
        return

    for conversation in conversations:
        title = conversation.get("title") or "שיחה חדשה"
        if st.button(title, key=f"history_route_{conversation['id']}", use_container_width=True):
            st.query_params["conversation"] = conversation["id"]
            st.switch_page(chat_page)


def render_google_callback():
    error = st.query_params.get("error")
    code = st.query_params.get("code")
    received_state = st.query_params.get("state", "")

    if error:
        st.error("ההתחברות עם Google בוטלה או נכשלה. נסו שוב.")
    elif not code or not received_state or not consume_google_oauth_state(str(received_state)):
        st.error("לא ניתן לאמת את בקשת ההתחברות. התחילו את התהליך מחדש.")
    else:
        try:
            result = login_or_register_google(str(code))
        except Exception:
            result = "ההתחברות עם Google נכשלה זמנית. נסו שוב בעוד רגע."
        if isinstance(result, str):
            st.error(result)
        else:
            auth_ui._save_session(*result)
            st.query_params.clear()
            st.switch_page(chat_page)
            return

    st.query_params.clear()
    if st.button("חזרה לדף הכניסה"):
        st.switch_page(landing_page)


def render_admin_page():
    if not auth_ui.get_current_user():
        st.switch_page(landing_page)
    admin_ui.render_admin_panel()


landing_page = st.Page(
    render_landing_page,
    title="כניסה",
    default=True,
)
chat_page = st.Page(
    "app.py",
    title="הצ׳אט",
    url_path="chat",
)
history_page = st.Page(
    render_history_page,
    title="היסטוריית שיחות",
    url_path="history",
)
google_callback_page = st.Page(
    render_google_callback,
    title="התחברות עם Google",
    url_path="auth_google_callback",
)
admin_page = st.Page(
    render_admin_page,
    title="ניהול",
    url_path="admin",
)

PAGES = [
    landing_page,
    chat_page,
    history_page,
    google_callback_page,
    admin_page,
]