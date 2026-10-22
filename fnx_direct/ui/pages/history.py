"""/history — the signed-in user's conversations as a full page."""
import streamlit as st

from fnx_direct.auth import session
from fnx_direct.history.conversations import list_conversations
from fnx_direct.history.database import DEFAULT_TITLE, initialize_history
from fnx_direct.ui import navigation


def render():
    user = session.get_current_user()
    if not user:
        st.switch_page(navigation.landing_page)

    initialize_history()
    st.title("היסטוריית שיחות")
    conversations = list_conversations(user_id=user["sub"])
    if not conversations:
        st.info("עדיין אין שיחות בחשבון.")
        return

    for conversation in conversations:
        title = conversation.get("title") or DEFAULT_TITLE
        if st.button(title, key=f"history_route_{conversation['id']}", use_container_width=True):
            st.query_params["conversation"] = conversation["id"]
            st.switch_page(navigation.chat_page)
