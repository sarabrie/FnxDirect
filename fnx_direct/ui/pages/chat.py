"""
/chat — the assistant. Each run: resolve who owns the conversation (user or guest), open the
requested conversation, handle sidebar actions, render the transcript and answer a new question.
"""
import threading

import streamlit as st

from fnx_direct.assistant.errors import is_quota_error
from fnx_direct.assistant.prompt import is_not_found
from fnx_direct.auth import session
from fnx_direct.auth.preferences import get_bot_preferences
from fnx_direct.history.conversations import (
    conversation_exists,
    conversation_is_hidden,
    guest_owner_id,
    hide_conversation,
    list_conversations,
    migrate_guest_conversations,
    new_conversation_id,
    rename_conversation,
)
from fnx_direct.history.database import initialize_history
from fnx_direct.history.feedback import save_feedback
from fnx_direct.history.messages import load_messages, save_message
from fnx_direct.search import engine
from fnx_direct.ui import navigation
from fnx_direct.ui.components import messages as transcript
from fnx_direct.ui.components.loading import render_progress_pill
from fnx_direct.ui.components.preferences import render_preferences_panel
from fnx_direct.ui.components.search_status import render_search_status
from fnx_direct.ui.components.sidebar import DELETING_KEY, EDITING_KEY, history_search_key, render_sidebar
from fnx_direct.ui.components.sources import render_sources
from fnx_direct.ui.components.topic_picker import render_suggestions, render_topic_picker
from fnx_direct.ui.styles import inject_css

EMPTY_ANSWER = "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
BUSY_ANSWER = "השירות עמוס כרגע. אפשר להמתין מעט ולנסות שוב."
FAILED_ANSWER = "לא הצלחנו לקבל תשובה כרגע. בדקו את החיבור ונסו שוב."


def render():
    initialize_history()
    user = session.get_current_user()
    if not user and not st.session_state.get("guest_mode", False):
        st.switch_page(navigation.landing_page)

    _adopt_guest_session(user)
    # Legacy admin route (?admin=1).
    if st.query_params.get("admin") == "1":
        st.switch_page(navigation.admin_page)

    owner_id = _conversation_owner(user)
    conversation_id = _open_conversation(owner_id)

    inject_css("chat.css")
    transcript.render_header(user)
    _render_sidebar(user, owner_id, conversation_id)

    if st.session_state.get("show_preferences") and user:
        render_preferences_panel(user, on_save=_on_preferences_saved)
        st.stop()
    user_prefs = _user_preferences(user)

    # The search engine loads in the background; asking waits until it's ready.
    engine.start()
    model_ready = engine.is_ready()
    if engine.has_failed():
        st.error("לא הצלחתי לטעון את מודל החיפוש. בדקו את חיבור האינטרנט ונסו להפעיל מחדש.")
    # Progress ring until the rest of the search engine is loaded; then a rerun enables the input.
    render_progress_pill(rerun_when_ready=True)

    # Open the connection to Gemini now, while the user reads / types, not when they ask.
    threading.Thread(target=_warm_up_gemini, name="gemini-warm-up", daemon=True).start()

    feedback_user_id = user["sub"] if user else None
    _save_pending_feedback(conversation_id, feedback_user_id)

    topic = render_topic_picker()
    suggestions_slot = st.empty()
    if not st.session_state.messages:
        with suggestions_slot.container():
            selected_question = render_suggestions(topic, disabled=not model_ready)
    else:
        selected_question = transcript.render_messages(
            st.session_state.messages,
            animate_follow_ups_for=st.session_state.pop("animate_follow_ups", None),
            disabled=not model_ready,
        )

    _render_pending_error(conversation_id)

    typed_question = st.chat_input(
        "כתבו את השאלה שלכם..." if model_ready else "עוד רגע אפשר לשאול…",
        disabled=not model_ready,
    )
    retry_question = st.session_state.pop("retry_question", None)
    question = typed_question or selected_question or retry_question
    if not question:
        return

    # The conversation starts now: drop the starter suggestions right away (not on the rerun
    # after the answer), so the page doesn't jump when the answer is done.
    suggestions_slot.empty()
    is_retry = question == retry_question and not typed_question and not selected_question
    if not is_retry:
        st.session_state.pop("pending_assistant_error", None)
        st.session_state.messages.append({"role": "user", "content": question})
        transcript.render_user_message(question)
        save_message(conversation_id, "user", question, user_id=owner_id)

    _answer(question, conversation_id, owner_id, user_prefs, topic)
    st.rerun()


# ── Owner & conversation ─────────────────────────────────────────────────────

def _adopt_guest_session(user):
    """After a guest signs in: move their conversations into the account and reopen the current one."""
    if user and st.session_state.get("guest_id"):
        migrate_guest_conversations(st.session_state["guest_id"], user["sub"])
        st.session_state.pop("guest_id", None)
        st.session_state.pop("guest_mode", None)
    if user and st.session_state.get("resume_conversation_id"):
        st.query_params["conversation"] = st.session_state.pop("resume_conversation_id")


def _conversation_owner(user):
    if user:
        return user["sub"]
    return guest_owner_id(st.session_state.setdefault("guest_id", new_conversation_id()))


def _is_open_in_session(conversation_id, owner_id):
    """A new conversation has no rows until its first message, but is already open in this session."""
    return (
        st.session_state.get("conversation_id") == conversation_id
        and st.session_state.get("conversation_owner_id") == owner_id
        and not conversation_is_hidden(conversation_id, user_id=owner_id)
    )


def _start_new_conversation(owner_id):
    conversation_id = new_conversation_id()
    st.session_state.conversation_id = conversation_id
    st.session_state.conversation_owner_id = owner_id
    st.session_state.messages = []
    st.query_params["conversation"] = conversation_id
    return conversation_id


def _open_conversation(owner_id):
    """The conversation in ?conversation= if the owner may see it, otherwise a new one."""
    requested = st.query_params.get("conversation")
    if requested and (
        conversation_exists(requested, user_id=owner_id) or _is_open_in_session(requested, owner_id)
    ):
        conversation_id = requested
    else:
        conversation_id = new_conversation_id()
        st.query_params["conversation"] = conversation_id

    if (
        st.session_state.get("conversation_id") != conversation_id
        or st.session_state.get("conversation_owner_id") != owner_id
    ):
        st.session_state.conversation_id = conversation_id
        st.session_state.conversation_owner_id = owner_id
        st.session_state.messages = load_messages(conversation_id, user_id=owner_id)
    return conversation_id


# ── Sidebar ──────────────────────────────────────────────────────────────────

def _render_sidebar(user, owner_id, conversation_id):
    # Guests don't see a history list in the sidebar.
    conversations = list_conversations(
        user_id=owner_id,
        search_query=st.session_state.get(history_search_key(owner_id), ""),
    ) if user else []
    action = render_sidebar(conversations, user, owner_id)
    if action:
        _handle_sidebar_action(action, owner_id, conversation_id)
        st.rerun()


def _handle_sidebar_action(action, owner_id, conversation_id):
    kind, target_id = action[0], action[1]
    if kind == "new":
        _start_new_conversation(owner_id)
    elif kind == "preferences":
        st.session_state["show_preferences"] = not st.session_state.get("show_preferences", False)
    elif kind == "select":
        st.query_params["conversation"] = target_id
    elif kind == "rename":
        if rename_conversation(target_id, action[2], user_id=owner_id):
            st.session_state.pop(EDITING_KEY, None)
        else:
            st.error("לא ניתן לערוך את הכותרת של השיחה הזו.")
    elif kind == "delete":
        if hide_conversation(target_id, user_id=owner_id):
            st.session_state.pop(DELETING_KEY, None)
            if target_id == conversation_id:
                _start_new_conversation(owner_id)
        else:
            st.error("לא ניתן להסיר את השיחה הזו מההיסטוריה.")
    elif kind == "cancel_edit":
        st.session_state.pop(EDITING_KEY, None)
    elif kind == "cancel_delete":
        st.session_state.pop(DELETING_KEY, None)


# ── Preferences & feedback ───────────────────────────────────────────────────

def _on_preferences_saved(new_prefs):
    st.session_state["user_prefs"] = new_prefs
    st.session_state["show_preferences"] = False


def _user_preferences(user):
    if not user:
        return None
    if "user_prefs" not in st.session_state:
        st.session_state["user_prefs"] = get_bot_preferences(user["sub"])
    return st.session_state["user_prefs"]


def _save_pending_feedback(conversation_id, user_id):
    for message in st.session_state.messages:
        message_id = message.get("message_id")
        if not message_id:
            continue
        feedback = st.session_state.pop(transcript.pending_feedback_key(message_id), None)
        if feedback:
            save_feedback(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                rating=feedback["rating"],
                reasons=feedback["reasons"],
                comment=feedback.get("comment", ""),
            )


# ── Answering ────────────────────────────────────────────────────────────────

def _warm_up_gemini():
    # Imported here: google.genai is slow to import (start.py preloads it in the background).
    from fnx_direct.assistant import gemini

    gemini.warm_up()


def _render_pending_error(conversation_id):
    pending_error = st.session_state.get("pending_assistant_error")
    if not pending_error or pending_error.get("conversation_id") != conversation_id:
        return
    st.error(pending_error["message"])
    if st.button("נסה שוב", key=f"retry_{conversation_id}", type="primary"):
        st.session_state["retry_question"] = pending_error["question"]
        st.session_state.pop("pending_assistant_error", None)
        st.rerun()


def _answer(question, conversation_id, owner_id, user_prefs, topic):
    """Streams the answer into an assistant card, then saves it (or remembers the error for a retry)."""
    request_error = None
    follow_up_questions = []
    sources, chunk_ids, prompt_text = [], [], ""
    assistant_box = st.chat_message("assistant")
    # Room for the follow-ups under the card from the start, so nothing jumps when they appear.
    transcript.render_follow_up_reserve()
    with assistant_box:
        sources_slot = None
        try:
            # Imported here: google.genai is slow to import, and only needed once a question is asked.
            from fnx_direct.assistant.service import generate_rag_response, get_collection

            if not engine.is_ready():
                # Asked before the background load finished — wait for it only now.
                with st.spinner("מסיים להכין את עוזר החיפוש, עוד כמה שניות..."):
                    get_collection()
            # Rotating status only until the first token arrives; the answer then streams in.
            status_placeholder = st.empty()
            render_search_status(status_placeholder)
            answer_slot = st.container()
            sources_slot = st.container()
            transcript.render_actions_reserve()  # room for the copy / like row inside the card
            try:
                response, sources, chunk_ids, prompt_text, follow_up_questions = generate_rag_response(
                    question, get_collection(), user_prefs=user_prefs, topic=topic
                )
            finally:
                status_placeholder.empty()
            with answer_slot:
                if isinstance(response, str):
                    answer = response
                    st.markdown(answer)
                else:
                    answer = st.write_stream(response)
                if not answer:
                    answer = EMPTY_ANSWER
                    st.markdown(answer)
            if is_not_found(answer):
                sources, chunk_ids = [], []
        except Exception as error:
            if isinstance(error, RuntimeError):
                answer = str(error)  # already a user-facing message
            else:
                print(f"שגיאה ביצירת תשובה: {type(error).__name__}: {error}")
                answer = BUSY_ANSWER if is_quota_error(error) else FAILED_ANSWER
            sources, chunk_ids, prompt_text, follow_up_questions = [], [], "", []
            st.markdown(answer)
            request_error = answer
        with sources_slot or st.container():
            render_sources(sources)

    if request_error:
        st.session_state["pending_assistant_error"] = {
            "conversation_id": conversation_id,
            "question": question,
            "message": request_error,
        }
        return

    st.session_state.pop("pending_assistant_error", None)
    message_id = save_message(
        conversation_id, "assistant", answer, sources,
        chunk_ids=chunk_ids, prompt_text=prompt_text,
        follow_up_questions=follow_up_questions,
        user_id=owner_id,
    )
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "follow_up_questions": follow_up_questions,
        "message_id": message_id,
    })
    st.session_state["animate_follow_ups"] = message_id
