"""Personal settings form: how the assistant addresses the user, answer length and tone."""
import streamlit as st

from fnx_direct.auth.preferences import RESPONSE_LENGTHS, TONES, get_bot_preferences, save_bot_preferences

_LENGTH_LABELS = {
    "short": "קצר ותמציתי (עד 3 משפטים)",
    "standard": "סטנדרטי (1-2 פסקאות)",
    "detailed": "מפורט ומעמיק (עם נקודות)",
}
_TONE_LABELS = {"simple": "פשוט ובגובה העיניים", "formal": "מקצועי ורשמי"}


def render_preferences_panel(user, on_save):
    prefs = get_bot_preferences(user["sub"])

    # No chat input on this screen, so no need for the bottom space reserved for it.
    st.markdown('<style>.block-container { padding-bottom: 2rem; }</style>', unsafe_allow_html=True)
    st.markdown("### הגדרות אישיות")
    preferred_name = st.text_input(
        "שם / פנייה מועדפת",
        value=prefs.get("preferred_name") or "",
        placeholder="לדוגמא: רינה",
    )
    response_length = st.radio(
        "אורך תשובה",
        options=RESPONSE_LENGTHS,
        format_func=_LENGTH_LABELS.get,
        index=RESPONSE_LENGTHS.index(prefs.get("response_length", "standard")),
        horizontal=True,
    )
    tone = st.radio(
        "סגנון וטון",
        options=TONES,
        format_func=_TONE_LABELS.get,
        index=TONES.index(prefs.get("tone", "simple")),
        horizontal=True,
    )
    if st.button("שמור הגדרות", type="primary"):
        save_bot_preferences(user["sub"], preferred_name or None, response_length, tone)
        st.success("ההגדרות נשמרו בהצלחה!")
        if on_save:
            on_save({"preferred_name": preferred_name or None, "response_length": response_length, "tone": tone})
