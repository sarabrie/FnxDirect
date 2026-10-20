import os

import chromadb
from google import genai
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


def create_collection():
    chroma_client = chromadb.PersistentClient(path="./fnx_db")
    return chroma_client.get_collection(
        name="fnx_website_chunks_multilingual",
        embedding_function=SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )


def _get_gemini_client():
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("חסר GEMINI_API_KEY בקובץ .env.")
    return genai.Client(api_key=gemini_api_key)


def generate_rag_response(question, collection):
    results = collection.query(query_texts=[question], n_results=5)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", []

    context_text = ""
    sources = []
    for document, metadata in zip(documents, metadatas):
        context_text += f"- {document}\n"
        url = metadata.get("url")
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

    client = _get_gemini_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    answer = response.text or "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
    if "זה לא כתוב באתר" in answer:
        sources = []
    return answer, sources


def generate_conversation_title(question):
    client = _get_gemini_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=(
            "צור כותרת קצרה ומסכמת לשיחה על סמך השאלה הראשונה בלבד. "
            "כתוב בעברית, עד 6 מילים, והחזר את הכותרת בלבד ללא מרכאות או הסבר.\n\n"
            f"שאלה: {question}"
        ),
    )

    title = " ".join((response.text or "").split()).strip(" \"'״׳")
    if not title:
        raise RuntimeError("מודל Gemini לא החזיר כותרת לשיחה.")
    return title[:48]
