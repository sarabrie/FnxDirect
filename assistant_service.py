import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from dotenv import load_dotenv
import chromadb
from google import genai
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DB_PATH = str(Path(__file__).resolve().parent / "fnx_db")


def _query_results(results, key):
    values = results.get(key)
    if not isinstance(values, list) or not values:
        return []
    first_result = values[0]
    return first_result if isinstance(first_result, list) else []


def _source_url(metadata):
    if not isinstance(metadata, dict):
        return None
    url = metadata.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return None
    if (
        parsed_url.scheme.lower() not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.path in {"", "/"}
    ):
        return None
    return url


def _is_generic_homepage_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return False
    return (
        parsed_url.scheme.lower() in {"http", "https"}
        and bool(parsed_url.netloc)
        and parsed_url.path in {"", "/"}
    )


def _generate_with_retry(client, model, contents, retries=3, delay=5):
    for attempt in range(retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception as e:
            if attempt < retries - 1 and ("503" in str(e) or "UNAVAILABLE" in str(e)):
                time.sleep(delay)
            else:
                raise


def create_collection():
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
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
    documents = _query_results(results, "documents")
    metadatas = _query_results(results, "metadatas")

    if not documents:
        return "זה לא כתוב באתר הפניקס.", []

    context_chunks = []
    sources = []
    for index, document in enumerate(documents):
        if not isinstance(document, str) or not document.strip():
            continue
        metadata = metadatas[index] if index < len(metadatas) else None
        metadata = metadata if isinstance(metadata, dict) else {}
        if _is_generic_homepage_url(metadata.get("url")):
            continue

        context_chunks.append(document)
        title = metadata.get("title")
        sources.append({
            "snippet": document,
            "url": _source_url(metadata),
            "title": title if isinstance(title, str) else None,
        })

    if not context_chunks:
        return "זה לא כתוב באתר הפניקס.", []

    context_text = "\n".join(f"- {chunk}" for chunk in context_chunks)

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

    preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    models_to_try = [preferred_model]
    for alt in ["gemini-3.5-flash", "gemini-3.7-flash", "gemini-flash-latest", "gemini-3.8-flash"]:
        if alt not in models_to_try:
            models_to_try.append(alt)

    response = None
    last_error = None
    with _get_gemini_client() as client:
        for model_name in models_to_try:
            try:
                response = _generate_with_retry(client, model_name, prompt)
                break
            except Exception as error:
                last_error = error
                err_text = str(error)
                if (
                    "429" in err_text
                    or "RESOURCE_EXHAUSTED" in err_text
                    or "NOT_FOUND" in err_text
                    or "404" in err_text
                ):
                    continue
                raise error

        if response is None:
            raise last_error

    answer = response.text or "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
    if "זה לא כתוב באתר" in answer:
        sources = []
    return answer, sources


def generate_conversation_title(question):
    """
    מחלץ כותרת קצרה ומסכמת מהשאלה הראשונה ללא צריכת מכסת API
    """
    clean = " ".join((question or "שיחה חדשה").split()[:6])
    return clean[:48] if clean else "שיחה חדשה"
