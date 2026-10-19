import os
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
import chromadb
from google import genai
import streamlit as st
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
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
    chroma_client = chromadb.PersistentClient(path="./fnx_db")
    return chroma_client.get_collection(
        name="fnx_website_chunks_multilingual",
        embedding_function=SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )


def generate_rag_response(question, collection):
    results = collection.query(
        query_texts=[question],
        n_results=5
    )

    documents = results.get('documents', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", []

    context_text = ""
    sources = []
    for doc, meta in zip(documents, metadatas):
        context_text += f"- {doc}\n"
        url = meta.get('url')
        if url and url not in sources:
            sources.append(url)

    prompt = f"""
אתה עוזר וירטואלי של חברת הפניקס.
    ענה בעברית ובצורה ברורה, ורק על סמך הקטעים המצורפים.
    חפש מידע רלוונטי בכל הקטעים, כולל כותרות, רשימות וניסוחים שקולים לשאלה.
    אם קטע עונה על חלק מהשאלה, מסור את המידע הנתמך וציין אילו פרטים אינם מופיעים.
    אל תוסיף עובדות שאינן מופיעות בקטעים. אם אף קטע אינו מכיל מידע רלוונטי, ענה בדיוק: "זה לא כתוב באתר הפניקס."
    דוגמה: אם הקטע אומר "מעקב פשוט ונוח אחר ההשקעה שלך" והשאלה היא מה האפליקציה מאפשרת, ענה: "האפליקציה מאפשרת מעקב פשוט ונוח אחר ההשקעה שלך."
    המקורות יוצגו בנפרד מהתשובה.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("חסר GEMINI_API_KEY בקובץ .env.")

    client = genai.Client(api_key=gemini_api_key)
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
    )

    answer = response.text or "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
    if "זה לא כתוב באתר" in answer:
        sources = []
    return answer, sources


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap');

:root {
    --ink: #172b2a;
    --muted: #687775;
    --green: #087e70;
    --line: #dce5df;
}
.stApp {
    direction: rtl;
    color: var(--ink);
    background: radial-gradient(ellipse at 85% 0%, #e4f2e9 0, transparent 36%), #f7f8f5;
    font-family: 'Heebo', sans-serif;
}
[data-testid="stSidebar"] {
    background: #edf3ee;
    border-left: 1px solid var(--line);
}
[data-testid="stSidebar"] * { font-family: 'Heebo', sans-serif; }
.block-container { max-width: 860px; padding-top: 2.5rem; padding-bottom: 8rem; }
.brand-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; border-radius: 13px;
    color: white; background: var(--green); font-size: 23px; font-weight: 700;
}
.eyebrow { color: var(--green); font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.intro-title { color: var(--ink); font-size: 32px; font-weight: 800; line-height: 1.25; margin: 0; }
.intro-copy { color: var(--muted); font-size: 16px; margin-top: 8px; }
.trust-line { color: var(--muted); font-size: 13px; padding: 12px 0 18px; border-bottom: 1px solid var(--line); }
[data-testid="stChatMessage"] { direction: rtl; text-align: right; }
[data-testid="stChatInput"] { direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; font-family: 'Heebo', sans-serif; }
.stButton > button { direction: rtl; text-align: right; border-color: var(--line); color: var(--ink); }
.stButton > button:hover { border-color: var(--green); color: var(--green); }
a { color: var(--green) !important; }
</style>
<div style="display:flex;align-items:center;gap:13px;margin-bottom:22px">
  <div class="brand-mark">✳</div>
  <div><div class="eyebrow">FNX DIRECT</div><div style="font-size:17px;font-weight:700">העוזר של הפניקס</div></div>
</div>
<div class="eyebrow">מידע ברור, במקום אחד</div>
<h1 class="intro-title">איך אפשר לעזור?</h1>
<div class="intro-copy">שאלו על ביטוח, תביעות ושירות. התשובות מבוססות על המידע באתר הפניקס.</div>
<div class="trust-line">✳ &nbsp; תשובות מבוססות מקור &nbsp; · &nbsp; קישורים לעמודים הרלוונטיים</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### הפניקס")
    st.caption("עוזר מידע אישי")
    if st.button("שיחה חדשה", use_container_width=True):
        conversation_id = new_conversation_id()
        st.session_state.conversation_id = conversation_id
        st.session_state.messages = []
        st.query_params["conversation"] = conversation_id
        st.rerun()
    st.divider()
    st.markdown("**היסטוריית שיחות**")
    for conversation in list_conversations():
        if st.button(
            conversation["title"],
            key=f"history_{conversation['id']}",
            use_container_width=True,
        ):
            st.query_params["conversation"] = conversation["id"]
            st.rerun()
    st.divider()
    st.markdown("**נושאים שאפשר לשאול עליהם**")
    st.caption("תביעות · ביטוח רכב · ביטוח דירה · ביטוח נסיעות")

try:
    collection = get_collection()
except Exception:
    st.error("לא הצלחתי להתחבר למסד המידע. ודאו שתיקיית fnx_db קיימת ונסו להפעיל מחדש.")
    st.stop()

if not st.session_state.messages:
    st.markdown("**אפשר להתחיל מכאן**")
    suggestions = [
        "איך מגישים תביעה על נזקי מים?",
        "מה כולל ביטוח נסיעות לחו״ל?",
        "איך יוצרים קשר עם הפניקס?",
    ]
    suggestion_columns = st.columns(len(suggestions))
    selected_question = None
    for column, suggestion in zip(suggestion_columns, suggestions):
        if column.button(suggestion, use_container_width=True):
            selected_question = suggestion
else:
    selected_question = None
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                st.markdown("**מקורות**")
                for source in message["sources"]:
                    st.markdown(f"- [לעמוד המקור]({source})")

typed_question = st.chat_input("כתבו את השאלה שלכם...")
question = typed_question or selected_question

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    save_message(conversation_id, "user", question)
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("מחפש מידע באתר הפניקס..."):
            try:
                answer, sources = generate_rag_response(question, collection)
            except RuntimeError as error:
                answer, sources = str(error), []
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
        if sources:
            st.markdown("**מקורות**")
            for source in sources:
                st.markdown(f"- [לעמוד המקור]({source})")

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
    })
    save_message(conversation_id, "assistant", answer, sources)
    st.rerun()
