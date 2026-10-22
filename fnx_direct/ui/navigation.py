"""
Page registry. Each page module is imported only when its page runs, so the first screen
doesn't wait for the others — and page modules can import this one to switch pages.
"""
import streamlit as st


def render_landing_page():
    from fnx_direct.ui.pages import landing
    landing.render()


def render_chat_page():
    from fnx_direct.ui.pages import chat
    chat.render()


def render_history_page():
    from fnx_direct.ui.pages import history
    history.render()


def render_google_callback_page():
    from fnx_direct.ui.pages import google_callback
    google_callback.render()


def render_admin_page():
    from fnx_direct.ui.pages import admin
    admin.render()


landing_page = st.Page(render_landing_page, title="כניסה", default=True)
chat_page = st.Page(render_chat_page, title="הצ׳אט", url_path="chat")
history_page = st.Page(render_history_page, title="היסטוריית שיחות", url_path="history")
# Must match auth/google_oauth.GOOGLE_CALLBACK_PATH.
google_callback_page = st.Page(render_google_callback_page, title="התחברות עם Google", url_path="auth_google_callback")
admin_page = st.Page(render_admin_page, title="ניהול", url_path="admin")

PAGES = [landing_page, chat_page, history_page, google_callback_page, admin_page]
