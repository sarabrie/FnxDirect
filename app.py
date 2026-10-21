import logging
from time import perf_counter

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
from assistant_service import create_collection, generate_rag_response
from performance import timed
from chat_history import (
    conversation_exists,
    conversation_is_hidden,
    hide_conversation,
    initialize_history,
    list_conversations,
    load_messages,
    new_conversation_id,
    rename_conversation,
    save_message,
    save_feedback,
)

_PERF_LOGGER.info(
    "performance phase=app.import duration_ms=%.2f",
    (perf_counter() - _APP_STARTED_AT) * 1000,
)

load_dotenv()

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="centered",
)

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
    st.session_state.messages = load_messages(
        conversation_id,
        user_id=conversation_owner_id,
    )


@st.cache_resource
def get_collection():
    return create_collection()


@st.cache_data(ttl=15, show_spinner=False)
def get_cached_conversations(user_id, search_query):
    return list_conversations(user_id=user_id, search_query=search_query)


@st.cache_data(ttl=60, show_spinner=False)
def get_cached_bot_preferences(user_id):
    return get_bot_preferences(user_id)


# ─── Header ──────────────────────────────────────────────────────────────────
app_ui.render_header(user)

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

# ─── Collection load ──────────────────────────────────────────────────────────
try:
    _collection_load_started_at = perf_counter()
    with st.spinner("מכין את עוזר החיפוש. הטעינה הראשונה עשויה להימשך כחצי דקה..."):
        collection = get_collection()
    _PERF_LOGGER.info(
        "performance phase=app.load_collection duration_ms=%.2f",
        (perf_counter() - _collection_load_started_at) * 1000,
    )
    _PERF_LOGGER.info(
        "performance phase=app.startup_to_collection duration_ms=%.2f",
        (perf_counter() - _APP_STARTED_AT) * 1000,
    )
except Exception as error:
    print(f"שגיאה בטעינת מסד המידע: {type(error).__name__}: {error}")
    st.error("לא הצלחתי לטעון את מודל החיפוש. בדקו את חיבור האינטרנט ונסו להפעיל מחדש.")
    st.stop()

# ─── Flush pending feedback ───────────────────────────────────────────────────
for msg in st.session_state.messages:
    mid = msg.get("message_id")
    if not mid:
        continue
    pending_key = f"fb_submit_{mid}"
    if pending_key in st.session_state:
        fb = st.session_state.pop(pending_key)
        save_feedback(
            message_id=mid,
            conversation_id=conversation_id,
            user_id=user["sub"] if user else None,
            rating=fb["rating"],
            reasons=fb["reasons"],
            comment=fb.get("comment", ""),
        )

# ─── Chat ─────────────────────────────────────────────────────────────────────
def _on_feedback(message_id, rating, reasons, comment):
    save_feedback(
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
    app_ui.render_messages(st.session_state.messages, on_feedback=_on_feedback)

typed_question = st.chat_input("כתבו את השאלה שלכם...")
question = typed_question or selected_question

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    save_message(
        conversation_id,
        "user",
        question,
        user_id=conversation_owner_id,
    )
    get_cached_conversations.clear()

    with st.chat_message("assistant"):
        with st.spinner("מחפש מידע באתר הפניקס..."):
            try:
                response, sources, chunk_ids, prompt_text = generate_rag_response(
                    question, collection, user_prefs=user_prefs
                )
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
                answer, sources, chunk_ids, prompt_text = str(error), [], [], ""
                st.markdown(answer)
            except Exception as error:
                print(f"שגיאה ביצירת תשובה: {type(error).__name__}: {error}")
                if getattr(error, "code", None) == 429 or "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    answer = "מכסת השימוש ב-Gemini הסתיימה. נסו שוב לאחר איפוס המכסה."
                else:
                    answer = f"שגיאה: {type(error).__name__}: {error}"
                sources, chunk_ids, prompt_text = [], [], ""
                st.markdown(answer)
            app_ui.render_sources(sources)

    message_id = save_message(
        conversation_id, "assistant", answer, sources,
        chunk_ids=chunk_ids, prompt_text=prompt_text,
        user_id=conversation_owner_id,
    )
    get_cached_conversations.clear()
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "message_id": message_id,
    })
    st.rerun()
