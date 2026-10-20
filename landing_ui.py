"""
Landing page — shown before entering the chat.
Offers: Login, Register, Continue as Guest, Google OAuth.
"""
import os
import streamlit as st
from auth_db import login_user, register_user, validate_password

_ACCESS_KEY = "_auth_access"
_REFRESH_KEY = "_auth_refresh"

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap');

:root {
    --ink: #172b2a;
    --muted: #687775;
    --green: #087e70;
    --green-light: #e8f5f1;
    --line: #dce5df;
}

.stApp {
    direction: rtl;
    font-family: 'Heebo', sans-serif;
    background: radial-gradient(ellipse at 80% 0%, #d4ede6 0, transparent 45%),
                radial-gradient(ellipse at 20% 100%, #e4f2e9 0, transparent 40%),
                #f4f6f2;
}

.landing-wrap {
    max-width: 460px;
    margin: 0 auto;
    padding: 3rem 1rem 6rem;
    direction: rtl;
    font-family: 'Heebo', sans-serif;
}

.brand-row {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 2.5rem;
}

.brand-mark {
    width: 52px; height: 52px;
    border-radius: 16px;
    background: var(--green);
    color: white;
    font-size: 26px; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 18px rgba(8,126,112,0.28);
    flex-shrink: 0;
}

.brand-name { font-size: 22px; font-weight: 800; color: var(--ink); }
.brand-sub  { font-size: 13px; color: var(--muted); margin-top: 1px; }

.hero-title {
    font-size: 34px; font-weight: 800; color: var(--ink);
    line-height: 1.2; margin-bottom: 10px;
}

.hero-sub {
    font-size: 16px; color: var(--muted);
    margin-bottom: 2.2rem; line-height: 1.6;
}

.card {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 28px 26px 22px;
    box-shadow: 0 8px 32px rgba(8,80,60,0.08);
    margin-bottom: 16px;
}

.card-title {
    font-size: 18px; font-weight: 800; color: var(--ink);
    margin-bottom: 4px;
}

.card-sub {
    font-size: 13px; color: var(--muted);
    margin-bottom: 18px;
}

.divider-text {
    display: flex; align-items: center; gap: 10px;
    color: var(--muted); font-size: 12px; margin: 14px 0;
}
.divider-text::before, .divider-text::after {
    content: ''; flex: 1; height: 1px; background: var(--line);
}

.guest-btn-wrap { text-align: center; margin-top: 8px; }

.trust-row {
    display: flex; gap: 18px; justify-content: center;
    margin-top: 2rem; flex-wrap: wrap;
}
.trust-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--muted); font-weight: 600;
}
.trust-dot { color: var(--green); font-size: 14px; }

/* Override Streamlit inputs */
[data-testid="stTextInput"] input {
    direction: rtl; text-align: right;
    font-family: 'Heebo', sans-serif;
    border-radius: 10px !important;
}

.stButton > button {
    font-family: 'Heebo', sans-serif !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    transition: all 0.2s ease !important;
}

/* Google button */
.google-btn {
    display: flex; align-items: center; justify-content: center; gap: 10px;
    width: 100%; padding: 11px 16px;
    background: #fff; border: 1.5px solid #dadce0;
    border-radius: 12px; cursor: pointer;
    font-size: 14px; font-weight: 700; color: #3c4043;
    font-family: 'Heebo', sans-serif;
    text-decoration: none;
    transition: background 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.google-btn:hover { background: #f8f9fa; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.google-logo { width: 20px; height: 20px; }
</style>
"""

_GOOGLE_LOGO_SVG = """<svg class="google-logo" viewBox="0 0 48 48">
  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
</svg>"""


def _save_session(access: str, refresh: str):
    st.session_state[_ACCESS_KEY] = access
    st.session_state[_REFRESH_KEY] = refresh


def _google_oauth_url() -> str:
    if not _GOOGLE_CLIENT_ID:
        return ""
    import urllib.parse
    params = {
        "client_id": _GOOGLE_CLIENT_ID,
        "redirect_uri": _GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def render_landing():
    """
    Renders the landing page. Returns True when the user should proceed to chat
    (either logged in or chose guest mode).
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # Handle Google OAuth callback
    code = st.query_params.get("code")
    if code:
        _handle_google_callback(code)

    tab_state = st.session_state.get("landing_tab", "login")

    st.markdown('<div class="landing-wrap">', unsafe_allow_html=True)

    # Brand
    st.markdown("""
    <div class="brand-row">
      <div class="brand-mark">✳</div>
      <div>
        <div class="brand-name">FNX Direct</div>
        <div class="brand-sub">העוזר החכם של הפניקס</div>
      </div>
    </div>
    <div class="hero-title">שאלות על ביטוח?<br>אנחנו כאן.</div>
    <div class="hero-sub">קבלו תשובות מיידיות על ביטוח, תביעות ושירות — מבוסס על המידע הרשמי של הפניקס.</div>
    """, unsafe_allow_html=True)

    # Card
    st.markdown('<div class="card">', unsafe_allow_html=True)

    if tab_state == "login":
        st.markdown('<div class="card-title">ברוכים השבים 👋</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">התחברו כדי לשמור את היסטוריית השיחות שלכם</div>', unsafe_allow_html=True)

        # Google button
        google_url = _google_oauth_url()
        if google_url:
            st.markdown(
                f'<a href="{google_url}" class="google-btn">{_GOOGLE_LOGO_SVG} המשך עם Google</a>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("אימייל", placeholder="your@email.com", label_visibility="collapsed")
            password = st.text_input("סיסמה", type="password", placeholder="סיסמה", label_visibility="collapsed")
            submitted = st.form_submit_button("התחברות →", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("יש למלא אימייל וסיסמה.")
            else:
                result = login_user(email, password)
                if isinstance(result, str):
                    st.error(result)
                else:
                    _save_session(*result)
                    st.session_state["landing_done"] = True
                    st.rerun()

        st.markdown('<hr style="border:none;border-top:1px solid #dce5df;margin:16px 0">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("הרשמה חדשה", use_container_width=True):
                st.session_state["landing_tab"] = "register"
                st.rerun()
        with col2:
            if st.button("כניסה כאורח", use_container_width=True):
                st.session_state["landing_done"] = True
                st.rerun()

    else:  # register
        st.markdown('<div class="card-title">יצירת חשבון חדש ✨</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">הרשמה חינמית — שמרו את השיחות שלכם</div>', unsafe_allow_html=True)

        google_url = _google_oauth_url()
        if google_url:
            st.markdown(
                f'<a href="{google_url}" class="google-btn">{_GOOGLE_LOGO_SVG} הרשמה עם Google</a>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)

        with st.form("register_form", clear_on_submit=False):
            display_name = st.text_input("שם תצוגה", placeholder="השם שלך", label_visibility="collapsed")
            email = st.text_input("אימייל", placeholder="your@email.com", label_visibility="collapsed")
            password = st.text_input("סיסמה", type="password", placeholder="סיסמה (8+ תווים, אות גדולה, ספרה, סימן)", label_visibility="collapsed")
            password2 = st.text_input("אימות סיסמה", type="password", placeholder="הזינו שוב את הסיסמה", label_visibility="collapsed")
            submitted = st.form_submit_button("הרשמה →", use_container_width=True, type="primary")

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
                    st.session_state["landing_done"] = True
                    st.rerun()

        st.markdown('<hr style="border:none;border-top:1px solid #dce5df;margin:16px 0">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("יש לי חשבון", use_container_width=True):
                st.session_state["landing_tab"] = "login"
                st.rerun()
        with col2:
            if st.button("כניסה כאורח", use_container_width=True):
                st.session_state["landing_done"] = True
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # card

    # Trust indicators
    st.markdown("""
    <div class="trust-row">
      <div class="trust-item"><span class="trust-dot">✳</span> תשובות מבוססות מקור</div>
      <div class="trust-item"><span class="trust-dot">🔒</span> מאובטח ופרטי</div>
      <div class="trust-item"><span class="trust-dot">⚡</span> מיידי וזמין תמיד</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # landing-wrap

    return st.session_state.get("landing_done", False)


def _handle_google_callback(code: str):
    """Exchange Google auth code for user info and create/login user."""
    if not _GOOGLE_CLIENT_ID or not _GOOGLE_CLIENT_SECRET:
        st.error("Google OAuth לא מוגדר. הגדירו GOOGLE_CLIENT_ID ו-GOOGLE_CLIENT_SECRET ב-.env")
        st.query_params.clear()
        return

    import urllib.request
    import urllib.parse
    import json as _json

    try:
        # Exchange code for tokens
        token_data = urllib.parse.urlencode({
            "code": code,
            "client_id": _GOOGLE_CLIENT_ID,
            "client_secret": _GOOGLE_CLIENT_SECRET,
            "redirect_uri": _GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_data, method="POST")
        with urllib.request.urlopen(req) as resp:
            tokens = _json.loads(resp.read())

        # Get user info
        req2 = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        with urllib.request.urlopen(req2) as resp:
            info = _json.loads(resp.read())

        _upsert_google_user(info)
        st.query_params.clear()
    except Exception as e:
        st.error(f"שגיאה בהתחברות עם Google: {e}")
        st.query_params.clear()


def _upsert_google_user(info: dict):
    """Create or update a Google-authenticated user and start session."""
    import sqlite3
    from contextlib import closing
    from auth_db import _connect, _create_session, init_auth_db
    from uuid import uuid4

    init_auth_db()
    email = info.get("email", "").lower().strip()
    name = info.get("name") or info.get("given_name") or email.split("@")[0]
    provider_id = info.get("sub")

    with closing(_connect()) as conn:
        row = conn.execute("SELECT id FROM users WHERE provider_id=? AND auth_provider='google'", (provider_id,)).fetchone()
        if row:
            uid = row["id"]
        else:
            # Check by email
            row2 = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row2:
                uid = row2["id"]
                with conn:
                    conn.execute("UPDATE users SET auth_provider='google', provider_id=? WHERE id=?", (provider_id, uid))
            else:
                uid = str(uuid4())
                with conn:
                    conn.execute(
                        "INSERT INTO users (id, email, auth_provider, provider_id, display_name) VALUES (?,?,?,?,?)",
                        (uid, email, "google", provider_id, name),
                    )
                    conn.execute("INSERT INTO user_preferences (user_id) VALUES (?)", (uid,))

    access, refresh = _create_session(uid)
    _save_session(access, refresh)
    st.session_state["landing_done"] = True
