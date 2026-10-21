"""
Landing page — shown before entering the chat.
Offers: Login, Register, Continue as Guest, Google OAuth.
"""
import streamlit as st
from auth_db import (
    build_google_auth_url,
    consume_google_oauth_state,
    login_or_register_google,
    login_user,
    register_user,
    validate_password,
)

_ACCESS_KEY = "_auth_access"
_REFRESH_KEY = "_auth_refresh"

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
    --canvas: #f3f7f5;
}

.stApp {
    direction: rtl;
    font-family: 'Heebo', sans-serif;
    color: var(--ink);
    background:
      radial-gradient(ellipse at 14% 84%, rgba(215,154,52,.10), transparent 27%),
      radial-gradient(ellipse at 88% 12%, rgba(8,127,121,.11), transparent 34%),
      var(--canvas);
}

.block-container { max-width: 1180px; padding: 4.5rem 2rem 3rem; }
.stApp, .stApp button, .stApp input { font-family: 'Heebo', sans-serif; }

.landing-wrap {
    margin: 0 auto;
    direction: rtl;
}

.brand-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0 0 3.5rem;
}

.brand-mark {
    width: 46px; height: 46px;
    border-radius: 14px;
    background: var(--teal);
    color: white;
    font-size: 24px; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 7px 18px rgba(8,100,95,.20);
    flex-shrink: 0;
}

.brand-name { font-size: 20px; font-weight: 800; color: var(--ink); }
.brand-sub  { font-size: 13px; color: var(--muted); margin-top: 1px; }

.hero-title {
    font-size: 48px; font-weight: 800; color: var(--ink);
    line-height: 1.18; margin: 0 0 16px; max-width: 560px;
}

.hero-sub {
    font-size: 17px; color: var(--muted);
    margin: 0 0 28px; line-height: 1.8; max-width: 480px;
}

.hero-kicker {
    display: inline-flex; align-items: center; gap: 8px;
    color: var(--teal-dark); font-size: 13px; font-weight: 700;
    margin-bottom: 14px;
}
.hero-kicker::before { content: ''; width: 22px; height: 2px; background: var(--gold); }
.hero-points { display: flex; flex-direction: column; gap: 14px; margin-top: 34px; }
.hero-point { display: flex; align-items: center; gap: 11px; color: var(--ink); font-size: 14px; font-weight: 600; }
.hero-point-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 9px;
    background: var(--teal-pale); color: var(--teal-dark); font-size: 14px; flex-shrink: 0;
}

.card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 32px 30px 26px;
    box-shadow: 0 16px 44px rgba(20,44,50,.08), 0 2px 6px rgba(20,44,50,.03);
    margin: 0 auto;
    max-width: 440px;
}

.card-title {
    font-size: 23px; font-weight: 800; color: var(--ink);
    margin-bottom: 6px;
}

.card-sub {
    font-size: 14px; color: var(--muted);
    margin-bottom: 22px;
}

.divider-text {
    display: flex; align-items: center; gap: 10px;
    color: var(--muted); font-size: 12px; margin: 18px 0;
}
.divider-text::before, .divider-text::after {
    content: ''; flex: 1; height: 1px; background: var(--line);
}

.trust-row {
    display: flex; gap: 28px; justify-content: center;
    margin: 3rem auto 0; padding-top: 20px; border-top: 1px solid var(--line); flex-wrap: wrap;
}
.trust-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--muted); font-weight: 600;
}
.trust-dot { color: var(--teal); font-size: 14px; }

[data-testid="stTextInput"] input {
    direction: rtl; text-align: right;
    font-family: 'Heebo', sans-serif; min-height: 46px;
    border-radius: 7px !important; border-color: var(--line) !important;
    background: #fbfdfc !important; transition: border-color .16s ease, box-shadow .16s ease;
}
[data-testid="stTextInput"] input:hover { border-color: #9bb9b5 !important; }
[data-testid="stTextInput"] input:focus { border-color: var(--teal) !important; box-shadow: 0 0 0 3px rgba(8,127,121,.14) !important; }

.stButton > button, [data-testid="stFormSubmitButton"] > button {
    font-family: 'Heebo', sans-serif !important; min-height: 44px;
    border-radius: 7px !important; font-weight: 700 !important;
    transition: background .16s ease, border-color .16s ease, transform .16s ease !important;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    border-color: var(--teal) !important; transform: translateY(-1px);
}
.stButton > button:focus-visible, [data-testid="stFormSubmitButton"] > button:focus-visible {
    outline: 3px solid rgba(8,127,121,.32) !important; outline-offset: 2px;
}
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background: var(--teal) !important; border-color: var(--teal) !important;
}
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    background: var(--teal-dark) !important;
}

.google-btn {
    display: flex; align-items: center; justify-content: center; gap: 10px;
    width: 100%; min-height: 44px; padding: 10px 16px;
    background: #fff; border: 1px solid var(--line);
    border-radius: 7px; cursor: pointer;
    font-size: 14px; font-weight: 700; color: #3c4043;
    font-family: 'Heebo', sans-serif;
    text-decoration: none;
    transition: background .16s ease, border-color .16s ease, box-shadow .16s ease;
}
.google-btn:hover { background: #f7faf9; border-color: #9bb9b5; box-shadow: 0 3px 10px rgba(20,44,50,.07); }
.google-btn:focus-visible { outline: 3px solid rgba(8,127,121,.32); outline-offset: 2px; }
.google-logo { width: 20px; height: 20px; }

@media (max-width: 760px) {
    .block-container { padding: 2rem 1rem 2rem; }
    .brand-row { margin-bottom: 2.25rem; }
    .hero-title { font-size: 36px; }
    .hero-sub { font-size: 15px; }
    .hero-points { margin: 22px 0 30px; }
    .card { padding: 25px 20px 20px; }
    .trust-row { gap: 12px 20px; margin-top: 2rem; }
    main [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child { order: -1; }
}
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
    return build_google_auth_url() or ""


def _handle_google_callback(code: str):
    state = st.query_params.get("state", "")
    if not state or not consume_google_oauth_state(str(state)):
        st.error("לא ניתן לאמת את בקשת ההתחברות. התחילו את התהליך מחדש.")
        return

    result = login_or_register_google(code)
    if isinstance(result, str):
        st.error(result)
        return
    _save_session(*result)


def render_landing():
    """
    Renders the landing page. Returns True when the user should proceed to chat
    (either logged in or chose guest mode).
    """
    st.markdown(_CSS, unsafe_allow_html=True)

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
    """, unsafe_allow_html=True)

    auth_col, hero_col = st.columns([0.85, 1.15], gap="large", vertical_alignment="center")
    with auth_col:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        if tab_state == "login":
            st.markdown('<div class="card-title">ברוכים השבים</div>', unsafe_allow_html=True)
            st.markdown('<div class="card-sub">התחברו כדי לשמור ולחזור לשיחות שלכם</div>', unsafe_allow_html=True)

            google_url = _google_oauth_url()
            if google_url:
                st.markdown(
                    f'<a href="{google_url}" class="google-btn">{_GOOGLE_LOGO_SVG} המשך עם Google</a>',
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)

            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("אימייל", placeholder="כתובת אימייל", label_visibility="collapsed")
                password = st.text_input("סיסמה", type="password", placeholder="סיסמה", label_visibility="collapsed")
                submitted = st.form_submit_button("התחברות", use_container_width=True, type="primary")

            if submitted:
                if not email or not password:
                    st.error("כדי להתחבר, מלאו אימייל וסיסמה.")
                else:
                    result = login_user(email, password)
                    if isinstance(result, str):
                        st.error(result)
                    else:
                        _save_session(*result)
                        st.session_state["landing_done"] = True
                        st.rerun()

            st.markdown('<hr style="border:none;border-top:1px solid #d9e3e2;margin:20px 0">', unsafe_allow_html=True)
            if st.button("פתיחת חשבון", use_container_width=True):
                st.session_state["landing_tab"] = "register"
                st.rerun()

        else:  # register
            st.markdown('<div class="card-title">יצירת חשבון</div>', unsafe_allow_html=True)
            st.markdown('<div class="card-sub">שמרו את השיחות שלכם וחזרו אליהן בכל עת</div>', unsafe_allow_html=True)

            google_url = _google_oauth_url()
            if google_url:
                st.markdown(
                    f'<a href="{google_url}" class="google-btn">{_GOOGLE_LOGO_SVG} הרשמה עם Google</a>',
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="divider-text">או</div>', unsafe_allow_html=True)

            with st.form("register_form", clear_on_submit=False):
                display_name = st.text_input("שם תצוגה", placeholder="השם שלכם", label_visibility="collapsed")
                email = st.text_input("אימייל", placeholder="כתובת אימייל", label_visibility="collapsed")
                password = st.text_input("סיסמה", type="password", placeholder="סיסמה: 8+ תווים, אות גדולה, ספרה וסימן", label_visibility="collapsed")
                password2 = st.text_input("אימות סיסמה", type="password", placeholder="הזינו שוב את הסיסמה", label_visibility="collapsed")
                submitted = st.form_submit_button("יצירת חשבון", use_container_width=True, type="primary")

            if submitted:
                if not all([display_name, email, password, password2]):
                    st.error("כדי ליצור חשבון, מלאו את כל השדות.")
                elif password != password2:
                    st.error("הסיסמאות לא תואמות. בדקו את ההקלדה ונסו שוב.")
                else:
                    result = register_user(email, password, display_name)
                    if isinstance(result, str):
                        st.error(result)
                    else:
                        _save_session(*result)
                        st.session_state["landing_done"] = True
                        st.rerun()

            st.markdown('<hr style="border:none;border-top:1px solid #d9e3e2;margin:20px 0">', unsafe_allow_html=True)
            if st.button("יש לי חשבון", use_container_width=True):
                st.session_state["landing_tab"] = "login"
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)  # card

        with hero_col:
                st.markdown("""
                <div class="hero-kicker">מידע ברור, במקום אחד</div>
                <div class="hero-title">ביטוח, קצת<br>יותר פשוט.</div>
                <div class="hero-sub">שאלו על הכיסויים, התביעות והשירות שלכם. העוזר של הפניקס יכוון אתכם למידע הרלוונטי באתר, בשפה ברורה ובכל שעה.</div>
                <div class="hero-points">
                    <div class="hero-point"><span class="hero-point-mark">✓</span>תשובות שמבוססות על מידע רשמי</div>
                    <div class="hero-point"><span class="hero-point-mark">↗</span>קישורים לעמודים הרלוונטיים באתר</div>
                    <div class="hero-point"><span class="hero-point-mark">⌕</span>השיחות נשמרות בחשבון שלכם</div>
                </div>
                """, unsafe_allow_html=True)

    # Trust indicators
    st.markdown("""
        <div class="trust-row">
            <div class="trust-item"><span class="trust-dot">✳</span> תשובות מבוססות מקור</div>
            <div class="trust-item"><span class="trust-dot">⌑</span> היסטוריה נשמרת בחשבון</div>
            <div class="trust-item"><span class="trust-dot">◷</span> קישורים למידע הרלוונטי</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # landing-wrap

    return st.session_state.get("landing_done", False)


def _upsert_google_user(info: dict):
    from contextlib import closing
    from uuid import uuid4

    from auth_db import _connect, _create_session, init_auth_db

    init_auth_db()
    email = info.get("email", "").lower().strip()
    name = info.get("name") or info.get("given_name") or email.split("@")[0]
    provider_id = info.get("sub")

    if not provider_id or not email or not info.get("email_verified"):
        return None

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE provider_id=? AND auth_provider='google'",
            (provider_id,),
        ).fetchone()
        if row:
            user_id = row["id"]
        else:
            row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row:
                user_id = row["id"]
                with conn:
                    conn.execute(
                        "UPDATE users SET auth_provider='google', provider_id=? WHERE id=?",
                        (provider_id, user_id),
                    )
            else:
                user_id = str(uuid4())
                with conn:
                    conn.execute(
                        "INSERT INTO users (id, email, auth_provider, provider_id, display_name) "
                        "VALUES (?,?,?,?,?)",
                        (user_id, email, "google", provider_id, name),
                    )
                    conn.execute(
                        "INSERT INTO user_preferences (user_id) VALUES (?)",
                        (user_id,),
                    )

    access, refresh = _create_session(user_id)
    _save_session(access, refresh)


    st.session_state["landing_done"] = True
