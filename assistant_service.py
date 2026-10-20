import os
import ssl
from pathlib import Path
import time
from urllib.parse import urlsplit

# ── SSL fix for Windows corporate/dev environments ────────────────────────────
ssl._create_default_https_context = ssl._create_unverified_context
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""

import httpx
_original_init = httpx.Client.__init__
def _patched_init(self, *args, **kwargs):
    kwargs["verify"] = False
    _original_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_init

_original_async_init = httpx.AsyncClient.__init__
def _patched_async_init(self, *args, **kwargs):
    kwargs["verify"] = False
    _original_async_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _patched_async_init
# ─────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
import chromadb
from google import genai
from google.genai import types
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


def generate_rag_response(question, collection, user_prefs=None):
    """Returns (answer_text, sources, chunk_ids, prompt_text)."""
    result_count = min(10, collection.count())
    if result_count == 0:
        return "זה לא כתוב באתר הפניקס.", [], [], ""

    results = collection.query(query_texts=[question], n_results=result_count)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", [], [], ""

    context_text = ""
    sources = []
    chunk_ids = []
    for document, metadata, chunk_id in zip(documents, metadatas, ids):
        if not isinstance(document, str) or not document.strip():
            continue
        if not isinstance(metadata, dict):
            metadata = {}
        if _is_generic_homepage_url(metadata.get("url")):
            continue

        title = metadata.get("title")
        if title:
            context_text += f"- עמוד: {title}\n  קטע: {document}\n"
        else:
            context_text += f"- {document}\n"

        sources.append({
            "snippet": document,
            "url": _source_url(metadata),
            "title": title if isinstance(title, str) else None,
        })
        chunk_ids.append(chunk_id)

    if not context_text:
        return "זה לא כתוב באתר הפניקס.", [], [], ""

    prefs = user_prefs or {}
    preferred_name = prefs.get("preferred_name")
    response_length = prefs.get("response_length", "standard")
    tone = prefs.get("tone", "simple")

    length_instruction = {
        "short": "ענה בקצרה ובתמציתיות, עד 3 משפטים.",
        "standard": "ענה בפסקה-שתיים סטנדרטיות.",
        "detailed": "ענה באופן מפורט ומעמיק, כולל נקודות ודוגמאות במידת הצורך.",
    }.get(response_length, "ענה בפסקה-שתיים סטנדרטיות.")

    tone_instruction = (
        "השתמש בשפה פשוטה ובגובה העיניים, ללא טרמינולוגיה משפטית."
        if tone == "simple"
        else "השתמש בשפה מקצועית ורשמית עם טרמינולוגיה ביטוחית."
    )

    salutation = f"פנה למשתמש בשם '{preferred_name}'." if preferred_name else ""

    prompt = f"""אתה עוזר וירטואלי של חברת הפניקס.
ענה בעברית ובצורה ברורה, ורק על סמך הקטעים המצורפים.
{salutation}
{length_instruction}
{tone_instruction}
בדוק את כל הקטעים לפני המענה. מידע עשוי להופיע תחת כותרת אחרת או בניסוח שונה מהשאלה.
אם קטע עונה על חלק מהשאלה, מסור את המידע הנתמך וציין אילו פרטים אינם מופיעים.
אל תוסיף עובדות שאינן מופיעות בקטעים. אם אף קטע אינו מכיל מידע רלוונטי, ענה בדיוק: "זה לא כתוב באתר הפניקס."
המקורות יוצגו בנפרד מהתשובה.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""

    config = types.GenerateContentConfig(
        max_output_tokens=512,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )

    last_error = None
    for attempt in range(3):
        client = _get_gemini_client()
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash", contents=prompt, config=config
            )
            client.close()
            answer = response.text or "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
            return answer, sources, chunk_ids, prompt
        except Exception as e:
            client.close()
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                time.sleep(3)
                continue
            raise
    raise last_error


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
