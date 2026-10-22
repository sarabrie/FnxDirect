import os
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import app_ui
import admin_ui
import auth_ui
from routes import landing_page
from auth_db import init_auth_db, get_bot_preferences
from chat_history import (
    conversation_exists,
    conversation_is_hidden,
    hide_conversation,
    initialize_history,
    list_conversations,
    load_messages,
    migrate_guest_conversations,
    new_conversation_id,
    rename_conversation,
    save_message,
    save_feedback,
)

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="wide",
)

init_auth_db()
initialize_history()

# ─── Auth state ───────────────────────────────────────────────────────────────
user = auth_ui.get_current_user()
guest_mode = st.session_state.get("guest_mode", False)
if not user and not guest_mode:
    st.switch_page(landing_page)
    st.stop()

if user and st.session_state.get("guest_id"):
    migrate_guest_conversations(st.session_state["guest_id"], user["sub"])
    st.session_state.pop("guest_id", None)
    st.session_state.pop("guest_mode", None)

# Keep the legacy query route working, now behind authentication.
if st.query_params.get("admin") == "1":
    admin_ui.render_admin_panel()
    st.stop()

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
    from assistant_service import create_collection

    return create_collection()


# ─── Header ──────────────────────────────────────────────────────────────────
app_ui.render_header(user)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
search_key = f"history_search_{conversation_owner_id}"
conversations = list_conversations(
    user_id=conversation_owner_id,
    search_query=st.session_state.get(search_key, ""),
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
            st.session_state.pop("editing_conversation_id", None)
        else:
            st.error("לא ניתן לערוך את הכותרת של השיחה הזו.")
    elif action == "delete":
        if hide_conversation(
            selected_conversation_id,
            user_id=conversation_owner_id,
        ):
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

    app_ui.render_preferences_panel(user, on_save=_on_prefs_save)
    st.stop()

# ─── Load user prefs (cached in session) ─────────────────────────────────────
if user and "user_prefs" not in st.session_state:
    st.session_state["user_prefs"] = get_bot_preferences(user["sub"])

user_prefs = st.session_state.get("user_prefs") if user else None

# ─── Collection load ──────────────────────────────────────────────────────────
try:
    with st.spinner("מכין את עוזר החיפוש. הטעינה הראשונה עשויה להימשך כחצי דקה..."):
        collection = get_collection()
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
    selected_question = app_ui.render_messages(
        st.session_state.messages,
        on_feedback=_on_feedback,
    )

pending_error = st.session_state.get("pending_assistant_error")
if pending_error and pending_error.get("conversation_id") == conversation_id:
    st.error(pending_error["message"])
    if st.button("נסה שוב", key=f"retry_{conversation_id}", type="primary"):
        st.session_state["retry_question"] = pending_error["question"]
        st.session_state.pop("pending_assistant_error", None)
        st.rerun()

typed_question = st.chat_input("כתבו את השאלה שלכם...")
retry_question = st.session_state.get("retry_question")
question = typed_question or selected_question or retry_question
is_retry = retry_question is not None and question == retry_question and not typed_question and not selected_question

if question:
    if is_retry:
        st.session_state.pop("retry_question", None)
    else:
        st.session_state.pop("retry_question", None)
        st.session_state.pop("pending_assistant_error", None)
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        save_message(
            conversation_id,
            "user",
            question,
            user_id=conversation_owner_id,
        )

    request_error = None
    with st.chat_message("assistant"):
        with st.spinner("מחפש מידע באתר הפניקס..."):
            follow_up_questions = []
            try:
                from assistant_service import generate_rag_response

                response, sources, chunk_ids, prompt_text, follow_up_questions = generate_rag_response(
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
                    suggested_questions = []
            except RuntimeError as error:
                answer, sources, chunk_ids, prompt_text = str(error), [], [], ""
                follow_up_questions = []
                st.markdown(answer)
                request_error = answer
            except Exception as error:
                print(f"שגיאה ביצירת תשובה: {type(error).__name__}: {error}")
                if getattr(error, "code", None) == 429 or "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    answer = "השירות עמוס כרגע. אפשר להמתין מעט ולנסות שוב."
                else:
                    answer = "לא הצלחנו לקבל תשובה כרגע. בדקו את החיבור ונסו שוב."
                sources, chunk_ids, prompt_text = [], [], ""
                follow_up_questions = []
                st.markdown(answer)
                request_error = answer
            app_ui.render_sources(sources)

    if request_error:
        st.session_state["pending_assistant_error"] = {
            "conversation_id": conversation_id,
            "question": question,
            "message": request_error,
        }
    else:
        st.session_state.pop("pending_assistant_error", None)
        message_id = save_message(
            conversation_id, "assistant", answer, sources,
            chunk_ids=chunk_ids, prompt_text=prompt_text,
            follow_up_questions=follow_up_questions,
            user_id=conversation_owner_id,
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "follow_up_questions": follow_up_questions,
            "message_id": message_id,
        })
    st.rerun()
