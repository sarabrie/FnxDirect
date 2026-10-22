"""
Chat transcript: user bubbles, answer cards (sources, copy, like / dislike) and the follow-up pills.

Feedback is not saved here: a click stores {"rating", "reasons", "comment"} under
pending_feedback_key(message_id) and the chat page saves it on the next run.
"""
import html

import streamlit as st

from fnx_direct.history.feedback import DISLIKE, INACCURATE_REASON, LIKE
from fnx_direct.ui.components.copy_button import render_copy_button
from fnx_direct.ui.components.sources import render_sources

DISLIKE_REASONS = [
    INACCURATE_REASON,
    "התשובה לא ענתה על מה ששאלתי",
    "התשובה לא הייתה מפורטת מספיק",
    "הניסוח לא היה ברור / מבלבל",
    "הטון או אופן הפנייה לא היו נעימים",
]


def pending_feedback_key(message_id):
    return f"fb_submit_{message_id}"


def render_header(user=None):
    hello = f'<div class="hero-hello">שלום, {html.escape(user.get("name", ""))}</div>' if user else ""
    st.markdown(
        f'<div class="hero">{hello}<h1 class="hero-title">איך אפשר לעזור?</h1></div>',
        unsafe_allow_html=True,
    )


def render_user_message(content):
    with st.chat_message("user"):
        st.markdown(content)
        render_copy_button(content, label="העתקת השאלה")


def render_messages(messages, with_feedback=True, animate_follow_ups_for=None, disabled=False):
    """Renders the conversation. Returns the follow-up question the user clicked, or None."""
    selected_question = None
    assistant_indexes = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    last_assistant = assistant_indexes[-1] if assistant_indexes else None
    for idx, message in enumerate(messages):
        if message["role"] != "assistant":
            render_user_message(message["content"])
            continue

        message_id = message.get("message_id") or idx
        with st.chat_message("assistant"):
            st.markdown(message["content"])
            render_sources(message.get("sources"))
            render_message_actions(
                message["content"], message_id, with_feedback=with_feedback and bool(message.get("message_id"))
            )
        # Follow-ups sit under the answer card, only for the latest answer.
        if idx == last_assistant:
            clicked = render_follow_ups(
                message.get("follow_up_questions") or [],
                message_id,
                animate=message_id == animate_follow_ups_for,
                disabled=disabled,
            )
            selected_question = clicked or selected_question
    return selected_question


def render_follow_ups(questions, message_id, animate=False, disabled=False):
    """Follow-up pills under the answer card. Returns the clicked question or None."""
    if not questions:
        return None
    clicked = None
    with st.container(key=f"followups_{message_id}"):
        for option_idx, question in enumerate(questions):
            # Wrapper key only drives the CSS fade-in; the button keeps its own stable key.
            with st.container(key=f"fu_anim{option_idx}_{message_id}") if animate else st.container():
                if st.button(
                    question,
                    icon=":material/arrow_back:",
                    key=f"follow_up_{message_id}_{option_idx}",
                    disabled=disabled,
                ):
                    clicked = question
    return clicked


def render_message_actions(content, message_id, with_feedback=True):
    """Copy / like / dislike row at the bottom of an answer card."""
    state_key = f"fb_{message_id}"
    state = st.session_state.get(state_key, "idle")  # idle | liked | dislike_open | submitted
    with st.container(key=f"actions_{message_id}"):
        copy_col, like_col, dislike_col, note_col = st.columns([1, 1, 1, 9], gap="small", vertical_alignment="center")
        with copy_col:
            render_copy_button(content, label="העתקת התשובה")
        if not with_feedback:
            return
        with like_col:
            if st.button(
                "", icon=":material/thumb_up:", key=f"like_{message_id}", help="תשובה טובה",
                type="primary" if state == "liked" else "secondary", disabled=state in {"liked", "submitted"},
            ):
                st.session_state[state_key] = "liked"
                st.session_state[pending_feedback_key(message_id)] = {"rating": LIKE, "reasons": [], "comment": ""}
                st.rerun()
        with dislike_col:
            if st.button(
                "", icon=":material/thumb_down:", key=f"dislike_{message_id}", help="דיווח על בעיה",
                disabled=state in {"liked", "submitted"},
            ):
                st.session_state[state_key] = "idle" if state == "dislike_open" else "dislike_open"
                st.rerun()
        with note_col:
            if state in {"liked", "submitted"}:
                st.markdown('<span class="fb-thanks">תודה על המשוב</span>', unsafe_allow_html=True)

    if state == "dislike_open":
        _render_dislike_form(message_id, state_key)


def _render_dislike_form(message_id, state_key):
    st.markdown('<div class="fb-card-title">מה לא היה בסדר?</div>', unsafe_allow_html=True)
    selected = [reason for reason in DISLIKE_REASONS if st.checkbox(reason, key=f"reason_{message_id}_{reason}")]
    comment = st.text_area(
        "פרטים נוספים",
        placeholder="פרטים נוספים (לא חובה)",
        key=f"comment_{message_id}",
        label_visibility="collapsed",
        height=80,
    )
    submit_col, cancel_col, _ = st.columns([2, 2, 6])
    with submit_col:
        if st.button("שליחה", key=f"submit_fb_{message_id}", type="primary"):
            st.session_state[pending_feedback_key(message_id)] = {
                "rating": DISLIKE,
                "reasons": selected,
                "comment": comment,
            }
            st.session_state[state_key] = "submitted"
            st.rerun()
    with cancel_col:
        if st.button("ביטול", key=f"cancel_fb_{message_id}"):
            st.session_state[state_key] = "idle"
            st.rerun()


def render_follow_up_reserve():
    """Empty space under the answer card where the follow-ups will appear, so nothing jumps."""
    st.markdown('<div class="fu-reserve" aria-hidden="true"></div>', unsafe_allow_html=True)


def render_actions_reserve():
    """Empty space for the copy / feedback buttons that appear after the answer is saved."""
    st.markdown('<div class="actions-reserve" aria-hidden="true"></div>', unsafe_allow_html=True)
