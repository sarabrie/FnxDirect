import importlib
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
import streamlit as st
import chat_history
import app_ui
from assistant_service import (
    create_collection,
    generate_rag_response,
)

importlib.reload(chat_history)

from chat_history import (
    conversation_exists,
    initialize_history,
    list_conversations,
    load_messages,
    new_conversation_id,
    save_message,
)

load_dotenv()

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="centered",
)

initialize_history()

requested_conversation_id = st.query_params.get("conversation")
if (
    requested_conversation_id
    and (
        conversation_exists(requested_conversation_id)
        or st.session_state.get("conversation_id") == requested_conversation_id
    )
):
    conversation_id = requested_conversation_id
else:
    conversation_id = new_conversation_id()
    st.query_params["conversation"] = conversation_id

if st.session_state.get("conversation_id") != conversation_id:
    st.session_state.conversation_id = conversation_id
    st.session_state.messages = load_messages(conversation_id)


@st.cache_resource
def get_collection():
    return create_collection()


app_ui.render_header()
try:
    with st.spinner("מכין את עוזר החיפוש. הטעינה הראשונה עשויה להימשך כחצי דקה..."):
        collection = get_collection()
except Exception as error:
    print(f"שגיאה בטעינת מסד המידע: {type(error).__name__}: {error}")
    st.error("לא הצלחתי לטעון את מודל החיפוש. בדקו את חיבור האינטרנט ונסו להפעיל מחדש.")
    st.stop()

sidebar_action = app_ui.render_sidebar(list_conversations())
if sidebar_action:
    action, selected_conversation_id = sidebar_action
    if action == "new":
        conversation_id = new_conversation_id()
        st.session_state.conversation_id = conversation_id
        st.session_state.messages = []
        st.query_params["conversation"] = conversation_id
    else:
        st.query_params["conversation"] = selected_conversation_id
    st.rerun()

if not st.session_state.messages:
    selected_question = app_ui.render_suggestions()
else:
    selected_question = None
    app_ui.render_messages(st.session_state.messages)

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
    )

    with st.chat_message("assistant"):
        with st.spinner("מחפש מידע באתר הפניקס..."):
            try:
                response, sources = generate_rag_response(question, collection)
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
            except RuntimeError as error:
                answer, sources = str(error), []
                st.markdown(answer)
            except Exception as error:
                print(f"שגיאה ביצירת תשובה: {type(error).__name__}: {error}")
                if (
                    getattr(error, "code", None) == 429
                    or "RESOURCE_EXHAUSTED" in str(error)
                ):
                    answer = "מכסת השימוש ב-Gemini הסתיימה. נסו שוב לאחר איפוס המכסה, או בדקו את מגבלות התוכנית והחיוב בחשבון Google AI."
                else:
                    answer = "לא הצלחתי לקבל תשובה כרגע. בדקו את החיבור ונסו שוב."
                sources = []
                st.markdown(answer)
            app_ui.render_sources(sources)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
    })
    save_message(conversation_id, "assistant", answer, sources)
    st.rerun()
