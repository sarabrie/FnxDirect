import logging
import os
import ssl
from concurrent.futures import ThreadPoolExecutor
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
import streamlit as st
from chat_history import get_chunk_scores
from performance import timed

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
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    return chroma_client.get_collection(
        name="fnx_website_chunks_multilingual",
        embedding_function=SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )


def _create_gemini_resources():
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("חסר GEMINI_API_KEY בקובץ .env.")
    with timed("model.client_init"):
        from google import genai
        from google.genai import types

        return genai.Client(api_key=gemini_api_key), types


def _log_gemini_resources_failure(future):
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logging.getLogger("fnxdirect.performance").error(
            "model.client_init_failed error_type=%s",
            type(error).__name__,
        )


@st.cache_resource(show_spinner=False)
def _get_gemini_resources_loader():
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fnxdirect-gemini")
    future = executor.submit(_create_gemini_resources)
    future.add_done_callback(_log_gemini_resources_failure)
    return executor, future


def warm_gemini_client():
    _get_gemini_resources_loader()


def _get_gemini_resources():
    _, future = _get_gemini_resources_loader()
    try:
        return future.result()
    except Exception:
        _get_gemini_resources_loader.clear()
        raise


@st.cache_data(ttl=300, show_spinner=False)
def _query_collection_cached(_collection, question, n_results, collection_path):
    return _collection.query(query_texts=[question], n_results=n_results)


def _stream_model_response(prompt):
    with timed("rag.model_setup"):
        client, types = _get_gemini_resources()
        config = types.GenerateContentConfig(
            max_output_tokens=512,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        )
    last_error = None
    stream_started_at = time.perf_counter()
    for attempt in range(3):
        emitted_text = False
        try:
            with timed("rag.model"):
                for chunk in client.models.generate_content_stream(
                    model="gemini-3.8-flash",
                    contents=prompt,
                    config=config,
                ):
                    text = chunk.text
                    if not text:
                        continue
                    if not emitted_text:
                        emitted_text = True
                        logging.getLogger("fnxdirect.performance").info(
                            "performance phase=rag.model_first_token duration_ms=%.2f",
                            (time.perf_counter() - stream_started_at) * 1000,
                        )
                    yield text
            if not emitted_text:
                yield "לא הצלחתי לנסח תשובה כרגע. נסו שוב בעוד רגע."
            return
        except Exception as error:
            last_error = error
            retryable = "503" in str(error) or "UNAVAILABLE" in str(error)
            if retryable and not emitted_text and attempt < 2:
                with timed("rag.model_retry_wait"):
                    time.sleep(3)
                continue
            logging.getLogger("fnxdirect.performance").error(
                "rag.stream_failed error_type=%s",
                type(error).__name__,
            )
            raise
    raise last_error


def generate_rag_response(question, collection, user_prefs=None):
    """Returns (answer_text, sources, chunk_ids, prompt_text)."""
    with timed("rag.retrieval"):
        result_count = min(10, collection.count())
        if result_count == 0:
            return "זה לא כתוב באתר הפניקס.", [], [], ""

        results = _query_collection_cached(
            collection,
            question,
            result_count,
            DB_PATH,
        )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", [], [], ""

    context_text = ""
    sources = []
    chunk_ids = []
    scored = []
    valid_results = []
    for document, metadata, chunk_id in zip(documents, metadatas, ids):
        if not isinstance(document, str) or not document.strip():
            continue
        if not isinstance(metadata, dict):
            metadata = {}
        if _is_generic_homepage_url(metadata.get("url")):
            continue
        valid_results.append((chunk_id, document, metadata))

    chunk_scores = get_chunk_scores(chunk_id for chunk_id, _, _ in valid_results)
    with timed("rag.rerank"):
        for chunk_id, document, metadata in valid_results:
            scored.append((chunk_scores.get(chunk_id, 1.0), chunk_id, document, metadata))

        # Re-rank: penalised chunks sink to the bottom, still included for transparency
        scored.sort(key=lambda x: x[0], reverse=True)

        for _, chunk_id, document, metadata in scored:
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

    prompt_started_at = time.perf_counter()
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

    logging.getLogger("fnxdirect.performance").info(
        "performance phase=rag.prompt_assembly duration_ms=%.2f",
        (time.perf_counter() - prompt_started_at) * 1000,
    )
    return _stream_model_response(prompt), sources, chunk_ids, prompt


def generate_conversation_title(question):
    client, _ = _get_gemini_resources()
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
