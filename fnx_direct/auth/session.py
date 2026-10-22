"""
The signed-in user of the current Streamlit session.
Tokens live in st.session_state only (never in cookies); an expired access token is refreshed silently.
"""
import streamlit as st

from fnx_direct.auth.tokens import refresh_session, revoke_refresh_token, verify_access_token

_ACCESS_KEY = "_auth_access"
_REFRESH_KEY = "_auth_refresh"


def save_session(access, refresh):
    st.session_state[_ACCESS_KEY] = access
    st.session_state[_REFRESH_KEY] = refresh


def _clear_session():
    st.session_state.pop(_ACCESS_KEY, None)
    st.session_state.pop(_REFRESH_KEY, None)


def get_current_user():
    """The JWT claims ({"sub", "email", "name"}) of the signed-in user, or None."""
    access = st.session_state.get(_ACCESS_KEY)
    if access:
        claims = verify_access_token(access)
        if claims:
            return claims

    raw_refresh = st.session_state.get(_REFRESH_KEY)
    if raw_refresh:
        result = refresh_session(raw_refresh)
        if isinstance(result, tuple):
            save_session(*result)
            return verify_access_token(result[0])
        _clear_session()
    return None


def logout():
    raw_refresh = st.session_state.get(_REFRESH_KEY)
    if raw_refresh:
        revoke_refresh_token(raw_refresh)
    _clear_session()
