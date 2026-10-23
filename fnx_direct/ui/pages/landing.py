"""Landing page: sign in, register, Google sign-in or continue as a guest."""
import html

import streamlit as st

from fnx_direct.auth import session
from fnx_direct.auth.accounts import login_user, register_user
from fnx_direct.auth.google_oauth import build_google_auth_url
from fnx_direct.ui import navigation
from fnx_direct.ui.components.loading import render_demo_chat, render_progress_pill
from fnx_direct.ui.styles import inject_css, read_asset

_TAB_KEY = "landing_tab"


def render():
    if session.get_current_user() or st.session_state.get("guest_mode"):
        st.switch_page(navigation.chat_page)

    inject_css("landing.css")
    st.markdown("""
    <div class="brand-row">
      <div class="brand-mark">✳</div>
      <div>
        <div class="brand-name">FNX Direct</div>
        <div class="brand-sub">העוזר החכם של הפניקס</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    auth_col, hero_col = st.columns([0.85, 1.15], gap="large", vertical_alignment="center")
    with auth_col, st.container(border=True, key="auth_card"):
        if st.session_state.get(_TAB_KEY, "login") == "login":
            _render_login()
        else:
            _render_register()
        _render_switch_and_guest()

    with hero_col:
        st.html(
            '<div class="hero-block">'
            '<div class="hero-title">ביטוח, קצת<br>יותר פשוט.</div>'
            '<div class="hero-sub">כל התשובות על הביטוח שלכם, במקום אחד.</div>'
            "</div>"
        )
        render_demo_chat()

    # The rest of the search engine keeps loading while the user logs in.
    render_progress_pill()


def _render_google_button(label):
    google_url = build_google_auth_url()
    if not google_url:
        return
    st.markdown(
        f'<a href="{html.escape(google_url, quote=True)}" class="google-btn">{read_asset("google_logo.svg")} {label}</a>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)


def _signed_in(tokens):
    session.save_session(*tokens)
    # Straight to the chat page — skips an extra rerun of the landing page that only redirects.
    st.switch_page(navigation.chat_page)


def _render_login():
    st.markdown('<div class="card-title">ברוכים השבים</div>', unsafe_allow_html=True)
    _render_google_button("המשך עם Google")

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("אימייל", placeholder="כתובת אימייל", label_visibility="collapsed")
        password = st.text_input("סיסמה", type="password", placeholder="סיסמה", label_visibility="collapsed")
        submitted = st.form_submit_button("התחברות", use_container_width=True, type="primary")

    if not submitted:
        return
    if not email or not password:
        st.error("כדי להתחבר, מלאו אימייל וסיסמה.")
        return
    with st.spinner("מתחבר…"):
        result = login_user(email, password)
    if isinstance(result, str):
        st.error(result)
    else:
        _signed_in(result)


def _render_register():
    st.markdown('<div class="card-title">יצירת חשבון</div>', unsafe_allow_html=True)
    _render_google_button("הרשמה עם Google")

    with st.form("register_form", clear_on_submit=False):
        display_name = st.text_input("שם תצוגה", placeholder="השם שלכם", label_visibility="collapsed")
        email = st.text_input("אימייל", placeholder="כתובת אימייל", label_visibility="collapsed")
        password = st.text_input(
            "סיסמה", type="password", placeholder="סיסמה: לפחות 8 תווים, אות וספרה", label_visibility="collapsed"
        )
        password2 = st.text_input(
            "אימות סיסמה", type="password", placeholder="הזינו שוב את הסיסמה", label_visibility="collapsed"
        )
        submitted = st.form_submit_button("יצירת חשבון", use_container_width=True, type="primary")

    if not submitted:
        return
    if not all([display_name, email, password, password2]):
        st.error("כדי ליצור חשבון, מלאו את כל השדות.")
        return
    if password != password2:
        st.error("הסיסמאות לא תואמות. בדקו את ההקלדה ונסו שוב.")
        return
    with st.spinner("יוצר חשבון…"):
        result = register_user(email, password, display_name)
    if isinstance(result, str):
        st.error(result)
    else:
        _signed_in(result)


def _render_switch_and_guest():
    st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)
    switch_col, guest_col = st.columns(2, gap="small")
    with switch_col:
        on_login = st.session_state.get(_TAB_KEY, "login") == "login"
        switch_label, switch_to = ("פתיחת חשבון", "register") if on_login else ("יש לי חשבון", "login")
        if st.button(switch_label, use_container_width=True):
            st.session_state[_TAB_KEY] = switch_to
            st.rerun()
    with guest_col:
        if st.button("המשך כאורח", use_container_width=True):
            st.session_state["guest_mode"] = True
            st.rerun()
