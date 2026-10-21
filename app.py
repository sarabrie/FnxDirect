import logging
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from uuid import uuid4

_APP_STARTED_AT = perf_counter()
_PERF_LOGGER = logging.getLogger("fnxdirect.performance")

import os
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
import streamlit as st
import app_ui
import admin_ui
import auth_ui
import landing_ui
from auth_db import init_auth_db, get_bot_preferences
from assistant_service import create_collection, generate_rag_response, warm_gemini_client
from performance import timed
from chat_history import (
    conversation_exists,
    conversation_is_hidden,
    hide_conversation,
    initialize_history,
    list_conversations,
    load_messages_page,
    new_conversation_id,
    rename_conversation,
    save_message,
    save_feedback,
)

MESSAGE_PAGE_SIZE = 50

_PERF_LOGGER.info(
    "performance phase=app.import duration_ms=%.2f",
    (perf_counter() - _APP_STARTED_AT) * 1000,
)

@st.cache_resource
def get_collection_loader():
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fnxdirect-rag")
    started_at = perf_counter()
    future = executor.submit(_load_collection, started_at)
    return executor, future


def _load_collection(started_at):
    try:
        return create_collection()
    except Exception as error:
        _PERF_LOGGER.error(
            "collection_load_failed error_type=%s",
            type(error).__name__,
        )
        raise
    finally:
        _PERF_LOGGER.info(
            "performance phase=app.load_collection duration_ms=%.2f",
            (perf_counter() - started_at) * 1000,
        )
        _PERF_LOGGER.info(
            "performance phase=app.startup_to_collection duration_ms=%.2f",
            (perf_counter() - _APP_STARTED_AT) * 1000,
        )


def get_collection():
    _, future = get_collection_loader()
    try:
        return future.result()
    except Exception:
        get_collection_loader.clear()
        raise


@st.cache_data(ttl=15, show_spinner=False)
def get_cached_conversations(user_id, search_query):
    return list_conversations(user_id=user_id, search_query=search_query)


@st.cache_data(ttl=60, show_spinner=False)
def get_cached_bot_preferences(user_id):
    return get_bot_preferences(user_id)


@st.cache_resource(show_spinner=False)
def get_db_write_executor():
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="fnxdirect-db")


def queue_db_write(operation, function, *args, message_write_id=None, **kwargs):
    future = get_db_write_executor().submit(function, *args, **kwargs)
    pending_writes = st.session_state.setdefault("_pending_db_writes", {})
    pending_writes[uuid4().hex] = {
        "future": future,
        "operation": operation,
        "message_write_id": message_write_id,
    }


def resolve_pending_db_writes():
    pending_writes = st.session_state.get("_pending_db_writes", {})
    remaining_writes = {}
    errors = []
    for write_id, pending in pending_writes.items():
        future = pending["future"]
        if not future.done():
            remaining_writes[write_id] = pending
            continue

        message_write_id = pending["message_write_id"]
        try:
            result = future.result()
        except Exception as error:
            _PERF_LOGGER.error(
                "background_db_write_failed operation=%s error_type=%s",
                pending["operation"],
                type(error).__name__,
            )
            errors.append("שמירת מידע נכשלה. אפשר לנסות שוב בעוד רגע.")
            if message_write_id:
                for message in st.session_state.get("messages", []):
                    if message.get("_write_id") == message_write_id:
                        message.pop("_write_id", None)
                        message["_write_error"] = True
                        break
        else:
            if message_write_id:
                for message in st.session_state.get("messages", []):
                    if message.get("_write_id") == message_write_id:
                        message.pop("_write_id", None)
                        message["message_id"] = result
                        break
            if pending["operation"] == "assistant_message":
                get_cached_conversations.clear()

    st.session_state["_pending_db_writes"] = remaining_writes
    return errors


load_dotenv()

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="centered",
)

_background_write_errors = resolve_pending_db_writes()

with timed("app.initialize_auth_db"):
    init_auth_db()
with timed("app.initialize_history"):
    initialize_history()

# ─── Admin panel ──────────────────────────────────────────────────────────────
if st.query_params.get("admin") == "1":
    admin_ui.render_admin_panel()
    st.stop()

# ─── Google OAuth callback ───────────────────────────────────────────────────
if "code" in st.query_params and "state" not in st.query_params:
    from auth_db import login_or_register_google
    _code = st.query_params["code"]
    st.query_params.clear()
    _result = login_or_register_google(_code)
    if isinstance(_result, str):
        st.error(_result)
    else:
        auth_ui._save_session(*_result)
        st.session_state.pop("show_auth", None)
        st.rerun()

# ─── Landing page ─────────────────────────────────────────────────────────────
if not st.session_state.get("landing_done"):
    # If already authenticated from a previous session, skip landing
    _existing_user = auth_ui.get_current_user()
    if _existing_user:
        st.session_state["landing_done"] = True
    else:
        entered = landing_ui.render_landing()
        if not entered:
            st.stop()

# ─── Auth state ───────────────────────────────────────────────────────────────
user = auth_ui.get_current_user()
user_id = user["sub"] if user else None
conversation_owner_id = user_id
if conversation_owner_id is None:
    guest_id = st.session_state.setdefault("guest_id", new_conversation_id())
    conversation_owner_id = f"guest:{guest_id}"

# ─── Conversation routing ─────────────────────────────────────────────────────
requested_conversation_id = st.query_params.get("conversation")
get_collection_loader()
warm_gemini_client()

if (
    requested_conversation_id
    and (
        conversation_exists(
            requested_conversation_id,
            user_id=conversation_owner_id,
        )
        or (
            st.session_state.get("conversation_id") == requested_conversation_id
            and st.session_state.get("conversation_owner_id") == conversation_owner_id
            and not conversation_is_hidden(
                requested_conversation_id,
                user_id=conversation_owner_id,
            )
        )
    )
):
    conversation_id = requested_conversation_id
else:
    conversation_id = new_conversation_id()
    st.query_params["conversation"] = conversation_id

if (
    st.session_state.get("conversation_id") != conversation_id
    or st.session_state.get("conversation_owner_id") != conversation_owner_id
):
    st.session_state.conversation_id = conversation_id
    st.session_state.conversation_owner_id = conversation_owner_id
    st.session_state.messages, has_older_messages = load_messages_page(
        conversation_id,
        user_id=conversation_owner_id,
        limit=MESSAGE_PAGE_SIZE,
    )
    st.session_state["has_older_messages"] = has_older_messages
# ─── Header ──────────────────────────────────────────────────────────────────
app_ui.render_header(user)
for _write_error in _background_write_errors:
    st.error(_write_error)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
search_key = f"history_search_{conversation_owner_id}"
conversations = get_cached_conversations(
    conversation_owner_id,
    st.session_state.get(search_key, ""),
)
sidebar_result = app_ui.render_sidebar(conversations, user, conversation_owner_id)
sidebar_action, _ = sidebar_result

if sidebar_action:
    action = sidebar_action[0]
    selected_conversation_id = sidebar_action[1]
    if action == "new":
        conversation_id = new_conversation_id()
        st.session_state.conversation_id = conversation_id
        st.session_state.conversation_owner_id = conversation_owner_id
        st.session_state.messages = []
        st.session_state["has_older_messages"] = False
        st.query_params["conversation"] = conversation_id
    elif action == "preferences":
        st.session_state["show_preferences"] = not st.session_state.get("show_preferences", False)
    elif action == "select":
        st.query_params["conversation"] = selected_conversation_id
    elif action == "rename":
        title = sidebar_action[2]
        if rename_conversation(
            selected_conversation_id,
            title,
            user_id=conversation_owner_id,
        ):
            get_cached_conversations.clear()
            st.session_state.pop("editing_conversation_id", None)
        else:
            st.error("לא ניתן לערוך את הכותרת של השיחה הזו.")
    elif action == "delete":
        if hide_conversation(
            selected_conversation_id,
            user_id=conversation_owner_id,
        ):
            get_cached_conversations.clear()
            st.session_state.pop("deleting_conversation_id", None)
            if selected_conversation_id == conversation_id:
                conversation_id = new_conversation_id()
                st.session_state.conversation_id = conversation_id
                st.session_state.messages = []
                st.session_state["has_older_messages"] = False
                st.query_params["conversation"] = conversation_id
        else:
            st.error("לא ניתן להסיר את השיחה הזו מההיסטוריה.")
    elif action == "cancel_edit":
        st.session_state.pop("editing_conversation_id", None)
    elif action == "cancel_delete":
        st.session_state.pop("deleting_conversation_id", None)
    st.rerun()

# ─── Preferences panel ────────────────────────────────────────────────────────
if st.session_state.get("show_preferences") and user:
    def _on_prefs_save(new_prefs):
        st.session_state["user_prefs"] = new_prefs
        st.session_state["show_preferences"] = False
        get_cached_bot_preferences.clear()

    app_ui.render_preferences_panel(user, on_save=_on_prefs_save)
    st.stop()

# ─── Load user prefs (cached in session) ─────────────────────────────────────
if user and "user_prefs" not in st.session_state:
    with timed("app.load_preferences"):
        st.session_state["user_prefs"] = get_cached_bot_preferences(user["sub"])

user_prefs = st.session_state.get("user_prefs") if user else None

# ─── Flush pending feedback ───────────────────────────────────────────────────
for msg in st.session_state.messages:
    mid = msg.get("message_id")
    if not mid:
        continue
    pending_key = f"fb_submit_{mid}"
    if pending_key in st.session_state:
        fb = st.session_state.pop(pending_key)
        queue_db_write(
            "feedback",
            save_feedback,
            message_id=mid,
            conversation_id=conversation_id,
            user_id=user["sub"] if user else None,
            rating=fb["rating"],
            reasons=fb["reasons"],
            comment=fb.get("comment", ""),
        )

# ─── Chat ─────────────────────────────────────────────────────────────────────
def _on_feedback(message_id, rating, reasons, comment):
    queue_db_write(
        "feedback",
        save_feedback,
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=user["sub"] if user else None,
        rating=rating,
        reasons=reasons,
        comment=comment,
    )

if not st.session_state.messages:
    selected_question = app_ui.render_suggestions()
else:
    selected_question = None
    if st.session_state.get("has_older_messages") and st.button(
        "טען הודעות קודמות"
    ):
        older_messages, has_older_messages = load_messages_page(
            conversation_id,
            user_id=conversation_owner_id,
            limit=MESSAGE_PAGE_SIZE,
            before_id=st.session_state.messages[0]["_db_id"],
        )
        st.session_state.messages = older_messages + st.session_state.messages
        st.session_state["has_older_messages"] = has_older_messages
        st.rerun()
    app_ui.render_messages(st.session_state.messages, on_feedback=_on_feedback)

typed_question = st.chat_input("כתבו את השאלה שלכם...")
question = typed_question or selected_question

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    user_message_future = get_db_write_executor().submit(
        save_message,
        conversation_id,
        "user",
        question,
        user_id=conversation_owner_id,
    )
    user_message_saved = False

    with st.chat_message("assistant"):
        with st.spinner("מחפש מידע באתר הפניקס..."):
            try:
                with st.spinner("מכין את עוזר החיפוש..."):
                    with timed("app.wait_for_collection"):
                        collection = get_collection()
                response, sources, chunk_ids, prompt_text = generate_rag_response(
                    question, collection, user_prefs=user_prefs
                )
                user_message_future.result()
                user_message_saved = True
                if isinstance(response, str):
                    answer = response
                    st.markdown(answer)
                else:
                    answer = st.write_stream(response)
                if not answer:
                    answer = "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
                    st.markdown(answer)
                if "זה לא כתוב באתר" in answer:
                    sources = []
                    chunk_ids = []
            except RuntimeError as error:
                _PERF_LOGGER.error(
                    "rag.answer_failed error_type=%s",
                    type(error).__name__,
                )
                if "GEMINI_API_KEY" in str(error):
                    answer = "שירות יצירת התשובות אינו מוגדר כרגע."
                else:
                    answer = "לא הצלחתי להשלים את התשובה. נסו שוב בעוד רגע."
                sources, chunk_ids, prompt_text = [], [], ""
                st.markdown(answer)
            except Exception as error:
                _PERF_LOGGER.error(
                    "rag.answer_failed error_type=%s",
                    type(error).__name__,
                )
                if getattr(error, "code", None) == 429 or "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    answer = "מכסת השימוש ב-Gemini הסתיימה. נסו שוב לאחר איפוס המכסה."
                else:
                    answer = "לא הצלחתי להשלים את התשובה. נסו שוב בעוד רגע."
                sources, chunk_ids, prompt_text = [], [], ""
                st.markdown(answer)
            finally:
                if not user_message_saved:
                    try:
                        user_message_future.result()
                        user_message_saved = True
                    except Exception as error:
                        _PERF_LOGGER.error(
                            "background_db_write_failed operation=user_message error_type=%s",
                            type(error).__name__,
                        )
                        answer = "לא הצלחתי לשמור את השאלה. נסו לשלוח אותה שוב."
                        sources, chunk_ids, prompt_text = [], [], ""
                        st.error(answer)
                if user_message_saved:
                    get_cached_conversations.clear()
            app_ui.render_sources(sources)

    client_write_id = uuid4().hex if user_message_saved else None
    if user_message_saved:
        queue_db_write(
            "assistant_message",
            save_message,
            conversation_id,
            "assistant",
            answer,
            sources,
            chunk_ids=chunk_ids,
            prompt_text=prompt_text,
            user_id=conversation_owner_id,
            message_write_id=client_write_id,
        )
    get_cached_conversations.clear()
    assistant_message = {
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "message_id": None,
    }
    if client_write_id:
        assistant_message["_write_id"] = client_write_id
    st.session_state.messages.append(assistant_message)
    st.rerun()
