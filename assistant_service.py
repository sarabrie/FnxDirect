import os

import chromadb
from google import genai
from google.genai import types
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


def _response_text_chunks(response_stream, client):
    try:
        for chunk in response_stream:
            text = chunk.text
            if text:
                yield text
    finally:
        client.close()


def generate_rag_response(question, collection):
    result_count = min(10, collection.count())
    if result_count == 0:
        return "זה לא כתוב באתר הפניקס.", []

    results = collection.query(query_texts=[question], n_results=result_count)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", []

    context_text = ""
    sources = []
    for document, metadata in zip(documents, metadatas):
        title = metadata.get("title")
        if title:
            context_text += f"- עמוד: {title}\n  קטע: {document}\n"
        else:
            context_text += f"- {document}\n"
        url = metadata.get("url")
        if url and url not in sources:
            sources.append(url)

    prompt = f"""
אתה עוזר וירטואלי של חברת הפניקס.
ענה בעברית ובצורה ברורה, ורק על סמך הקטעים המצורפים.
בדוק את כל הקטעים לפני המענה. מידע עשוי להופיע תחת כותרת אחרת או בניסוח שונה מהשאלה.
אם קטע עונה על חלק מהשאלה, מסור את המידע הנתמך וציין אילו פרטים אינם מופיעים.
אל תענה "זה לא כתוב באתר הפניקס" אם אחד הקטעים מכיל מידע רלוונטי, גם אם אינו עונה על כל השאלה.
אל תוסיף עובדות שאינן מופיעות בקטעים. אם אף קטע אינו מכיל מידע רלוונטי, ענה בדיוק: "זה לא כתוב באתר הפניקס."
דוגמה: אם הקטע אומר "מעקב פשוט ונוח אחר ההשקעה שלך" והשאלה היא מה האפליקציה מאפשרת, ענה: "האפליקציה מאפשרת מעקב פשוט ונוח אחר ההשקעה שלך."
המקורות יוצגו בנפרד מהתשובה.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""

    client = _get_gemini_client()
    try:
        response_stream = client.models.generate_content_stream(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW,
                ),
            ),
        )
    except Exception:
        client.close()
        raise

    return _response_text_chunks(response_stream, client), sources


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
