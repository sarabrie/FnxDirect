"""
/admin — review of negative feedback (answer, reasons, comment).
Requires a signed-in user plus the ADMIN_SECRET password from .env.
"""
import json
import os

import streamlit as st

from fnx_direct.auth import session
from fnx_direct.history.database import initialize_history
from fnx_direct.history.feedback import get_negative_feedback
from fnx_direct.ui import navigation


def render():
    if not session.get_current_user():
        st.switch_page(navigation.landing_page)

    secret = os.getenv("ADMIN_SECRET", "")
    if not secret:
        st.error("לוח הניהול אינו זמין עד להגדרת ADMIN_SECRET.")
        return

    entered = st.text_input("סיסמת מנהל", type="password", key="admin_secret_input")
    if not entered:
        st.info("הזינו סיסמת מנהל כדי לצפות במשובים.")
        return
    if entered != secret:
        st.error("סיסמה שגויה.")
        return

    st.markdown("### סקירת משובים שליליים")
    initialize_history()
    rows = get_negative_feedback(limit=100)
    if not rows:
        st.success("אין משובים שליליים כרגע.")
        return

    st.caption(f"{len(rows)} משובים שליליים אחרונים")
    for row in rows:
        reasons = json.loads(row.get("reasons_json") or "[]")
        comment = row.get("comment") or ""
        with st.expander(f"📩 הודעה #{row['message_id']} — {row['created_at'][:16]}"):
            st.markdown(f"**תוכן ההודעה:**\n\n{row['message_content']}")
            if reasons:
                st.markdown("**סיבות:**")
                for reason in reasons:
                    st.markdown(f"- {reason}")
            if comment:
                st.markdown(f"**הערה חופשית:** {comment}")
            st.caption(f"משתמש: {row['user_id'] or 'אנונימי'} | שיחה: {row['conversation_id']}")
