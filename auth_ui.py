"""
Auth UI — login / register panel rendered inside the Streamlit sidebar and main area.
Tokens are stored in st.session_state only (never in cookies via Streamlit).
"""
import streamlit as st
from auth_db import (
    init_auth_db,
    login_user,
    logout_user,
    refresh_session,
    register_user,
    verify_access_token,
    build_google_auth_url,
)

_ACCESS_KEY = "_auth_access"
_REFRESH_KEY = "_auth_refresh"


# ─── CSS injected once ───────────────────────────────────────────────────────

_AUTH_CSS = """
<style>
.auth-card {
    background: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 18px;
    padding: 28px 28px 22px;
    margin: 0 auto 24px;
    max-width: 420px;
    box-shadow: 0 6px 28px rgba(8,80,60,0.09);
    direction: rtl;
    font-family: 'Heebo', sans-serif;
}
.auth-title {
    font-size: 22px;
    font-weight: 800;
    color: #172b2a;
    margin-bottom: 4px;
}
.auth-sub {
    font-size: 14px;
    color: #687775;
    margin-bottom: 20px;
}
.auth-divider {
    border: none;
    border-top: 1px solid #dce5df;
    margin: 18px 0;
}
.user-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #e8f5f1;
    border: 1px solid #c5e0d8;
    border-radius: 999px;
    padding: 5px 14px 5px 10px;
    font-size: 13px;
    font-weight: 700;
    color: #087e70;
    font-family: 'Heebo', sans-serif;
}
.user-avatar {
    width: 26px; height: 26px;
    border-radius: 50%;
    background: #087e70;
    color: white;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 800;
}
.google-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    padding: 10px 16px;
    background: #fff;
    border: 1px solid #dce5df;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 700;
    color: #172b2a;
    text-decoration: none;
    font-family: 'Heebo', sans-serif;
    transition: background 0.15s, border-color 0.15s;
    cursor: pointer;
    margin-bottom: 4px;
}
.google-btn:hover { background: #f5f5f5; border-color: #aaa; }
</style>
"""


def _inject_css():
    st.markdown(_AUTH_CSS, unsafe_allow_html=True)


def _render_google_button():
    url = build_google_auth_url()
    if url:
        import html as _html
        safe_url = _html.escape(url, quote=True)
        st.markdown(
            f'<a class="google-btn" href="{safe_url}" target="_self">'
            f'<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="20"/>'
            f'התחברות עם Google'
            f'</a>',
            unsafe_allow_html=True,
        )


# ─── Session helpers ─────────────────────────────────────────────────────────

def _save_session(access: str, refresh: str):
    st.session_state[_ACCESS_KEY] = access
    st.session_state[_REFRESH_KEY] = refresh


def _clear_session():
    st.session_state.pop(_ACCESS_KEY, None)
    st.session_state.pop(_REFRESH_KEY, None)


def get_current_user() -> dict | None:
    """
    Returns decoded JWT payload if logged in and token valid.
    Attempts silent refresh if access token expired.
    """
    access = st.session_state.get(_ACCESS_KEY)
    if access:
        claims = verify_access_token(access)
        if claims:
            return claims

    # Try silent refresh
    raw_refresh = st.session_state.get(_REFRESH_KEY)
    if raw_refresh:
        result = refresh_session(raw_refresh)
        if isinstance(result, tuple):
            new_access, new_refresh = result
            _save_session(new_access, new_refresh)
            return verify_access_token(new_access)
        # Refresh failed — clear session
        _clear_session()
    return None


def logout():
    raw_refresh = st.session_state.get(_REFRESH_KEY)
    if raw_refresh:
        logout_user(raw_refresh)
    _clear_session()
    st.session_state["auth_panel"] = "login"


# ─── Main auth panel (rendered in main area) ─────────────────────────────────

def render_auth_page():
    """Full-page auth panel shown when user is not logged in and clicks התחברות."""
    _inject_css()
    init_auth_db()

    panel = st.session_state.get("auth_panel", "login")

    st.markdown('<div class="auth-card">', unsafe_allow_html=True)

    if panel == "login":
        st.markdown('<div class="auth-title">ברוכים השבים 👋</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-sub">התחברו כדי לשמור את היסטוריית השיחות שלכם</div>', unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("אימייל", placeholder="your@email.com", label_visibility="collapsed")
            password = st.text_input("סיסמה", type="password", placeholder="סיסמה", label_visibility="collapsed")
            submitted = st.form_submit_button("התחברות", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("יש למלא אימייל וסיסמה.")
            else:
                result = login_user(email, password)
                if isinstance(result, str):
                    st.error(result)
                else:
                    _save_session(*result)
                    st.session_state.pop("show_auth", None)
                    st.rerun()

        st.markdown('<hr class="auth-divider">', unsafe_allow_html=True)
        _render_google_button()
        st.markdown('<hr class="auth-divider">', unsafe_allow_html=True)
        if st.button("אין לי חשבון — הרשמה", use_container_width=True):
            st.session_state["auth_panel"] = "register"
            st.rerun()

    else:  # register
        st.markdown('<div class="auth-title">יצירת חשבון חדש</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-sub">הרשמה חינמית — שמרו את השיחות שלכם</div>', unsafe_allow_html=True)

        with st.form("register_form", clear_on_submit=False):
            display_name = st.text_input("שם תצוגה", placeholder="השם שלך", label_visibility="collapsed")
            email = st.text_input("אימייל", placeholder="your@email.com", label_visibility="collapsed")
            password = st.text_input("סיסמה", type="password", placeholder="סיסמה (8+ תווים, אות גדולה, ספרה, סימן)", label_visibility="collapsed")
            password2 = st.text_input("אימות סיסמה", type="password", placeholder="הזינו שוב את הסיסמה", label_visibility="collapsed")
            submitted = st.form_submit_button("הרשמה", use_container_width=True, type="primary")

        if submitted:
            if not all([display_name, email, password, password2]):
                st.error("יש למלא את כל השדות.")
            elif password != password2:
                st.error("הסיסמאות אינן תואמות.")
            else:
                result = register_user(email, password, display_name)
                if isinstance(result, str):
                    st.error(result)
                else:
                    _save_session(*result)
                    st.session_state.pop("show_auth", None)
                    st.rerun()

        st.markdown('<hr class="auth-divider">', unsafe_allow_html=True)
        _render_google_button()
        st.markdown('<hr class="auth-divider">', unsafe_allow_html=True)
        if st.button("יש לי חשבון — התחברות", use_container_width=True):
            st.session_state["auth_panel"] = "login"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ─── Sidebar auth widget ──────────────────────────────────────────────────────

def render_sidebar_auth(user: dict | None):
    """
    Renders auth controls inside the sidebar.
    Returns True if the main area should show the auth page instead of chat.
    """
    _inject_css()
    init_auth_db()

    if user:
        initial = user.get("name", "?")[0].upper()
        name = user.get("name", "משתמש")
        st.markdown(
            f'<div class="user-chip">'
            f'<span class="user-avatar">{initial}</span>'
            f'{name}'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.caption(user.get("email", ""))
        if st.button("התנתקות", use_container_width=True):
            logout()
            st.rerun()
        return False

    # Guest
    show = st.session_state.get("show_auth", False)
    btn_label = "סגירה ✕" if show else "התחברות / הרשמה"
    if st.button(btn_label, use_container_width=True, type="primary" if not show else "secondary"):
        st.session_state["show_auth"] = not show
        st.rerun()
    return show
