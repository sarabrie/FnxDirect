"""/auth_google_callback — where Google redirects after sign-in."""
import streamlit as st

from fnx_direct.auth import session
from fnx_direct.auth.google_oauth import consume_google_oauth_state, login_or_register_google
from fnx_direct.ui import navigation


def render():
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
            session.save_session(*result)
            st.query_params.clear()
            st.switch_page(navigation.chat_page)

    st.query_params.clear()
    if st.button("חזרה לדף הכניסה"):
        st.switch_page(navigation.landing_page)
