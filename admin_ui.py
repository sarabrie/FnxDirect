"""
Admin panel — accessible at /?admin=1
Shows negative feedback with message content, reasons, and comments.
No auth beyond a simple secret token check (set ADMIN_SECRET in .env).
"""
import json
import os
import streamlit as st
from chat_history import get_negative_feedback


def render_admin_panel():
    secret = os.getenv("ADMIN_SECRET", "")
    entered = st.text_input("סיסמת מנהל", type="password", key="admin_secret_input")
    if not entered:
        st.info("הזינו סיסמת מנהל כדי לצפות במשובים.")
        return
    if secret and entered != secret:
        st.error("סיסמה שגויה.")
        return

    st.markdown("### סקירת משובים שליליים")

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
                for r in reasons:
                    st.markdown(f"- {r}")
            if comment:
                st.markdown(f"**הערה חופשית:** {comment}")
            st.caption(f"משתמש: {row['user_id'] or 'אנונימי'} | שיחה: {row['conversation_id']}")
