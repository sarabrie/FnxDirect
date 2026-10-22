import hashlib
import json
import os
import queue
import re
import ssl
import threading
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
from google import genai
from google.genai import types
from chat_history import get_cached_answer, get_chunk_scores, save_cached_answer
from topics import GENERAL_TOPIC, topic_filter
import warmup

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _query_results(results, key):
    values = results.get(key)
    if not isinstance(values, list) or not values:
        return []
    first_result = values[0]
    return first_result if isinstance(first_result, list) else []


def _split_follow_ups(text):
    pattern = r"\[FOLLOW_UP\](.*?)\[/FOLLOW_UP\]"
    follow_ups = [
        " ".join(match.split())
        for match in re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    ]
    answer = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    return answer, list(dict.fromkeys(follow_ups))[:3]


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


def _available_chunks(collection, topic):
    where = topic_filter(topic)
    if where is None or not collection.topic_counts:
        return collection.count()
    if topic == GENERAL_TOPIC:
        return collection.topic_counts.get(GENERAL_TOPIC, 0)
    return collection.topic_counts.get(topic, 0) + collection.topic_counts.get(GENERAL_TOPIC, 0)


def get_collection():
    """The search engine (its own process — see search_worker.py); waits until it is loaded."""
    return warmup.wait_until_ready()


def _load_api_keys():
    """
    Keys from GEMINI_API_KEYS (comma-separated) plus GEMINI_API_KEY, in order, without duplicates.
    Free-tier quota is counted per Google Cloud project, so each key should come from a different project.
    """
    raw = [os.getenv("GEMINI_API_KEY", "")] + os.getenv("GEMINI_API_KEYS", "").split(",")
    keys = list(dict.fromkeys(key.strip() for key in raw if key.strip()))
    # A real key is plain ASCII; anything else (e.g. Hebrew placeholder text) fails every request.
    invalid = [number for number, key in enumerate(keys, 1) if not key.isascii()]
    if invalid:
        print(f"Skipping invalid Gemini key(s) #{', #'.join(map(str, invalid))} in .env (not a real key)", flush=True)
    return [key for key in keys if key.isascii()]


GEMINI_API_KEYS = _load_api_keys()
_gemini_clients = {}
_clients_lock = threading.Lock()


def _get_gemini_client(key_index=0):
    if not GEMINI_API_KEYS:
        raise RuntimeError("חסר GEMINI_API_KEY (או GEMINI_API_KEYS) בקובץ .env.")
    with _clients_lock:
        if key_index not in _gemini_clients:
            _gemini_clients[key_index] = genai.Client(api_key=GEMINI_API_KEYS[key_index])
        return _gemini_clients[key_index]


# (key_index, model) -> time until which that key's quota for that model is used up (429).
_exhausted_until = {}
_DEFAULT_QUOTA_COOLDOWN_SECONDS = 60 * 60


def _is_quota_error(error):
    text = str(error)
    return getattr(error, "code", None) == 429 or "429" in text or "RESOURCE_EXHAUSTED" in text


def _mark_exhausted(key_index, model, error):
    # Google says how long until the quota resets, e.g. 'retryDelay': '51142s'.
    match = re.search(r"retryDelay'?:\s*'?(\d+(?:\.\d+)?)s", str(error))
    cooldown = float(match.group(1)) if match else _DEFAULT_QUOTA_COOLDOWN_SECONDS
    _exhausted_until[(key_index, model)] = time.time() + cooldown
    print(f"Gemini key #{key_index + 1} out of quota for {model}; skipping it for {cooldown / 3600:.1f}h", flush=True)


def _is_exhausted(key_index, model):
    return _exhausted_until.get((key_index, model), 0) > time.time()


_FOLLOW_UP_TAG = "[follow_up]"


def _displayable_prefix(text):
    """Part of the streamed text that is safe to show (before any [FOLLOW_UP] tag)."""
    lowered = text.lower()
    tag_index = lowered.find(_FOLLOW_UP_TAG)
    if tag_index >= 0:
        return text[:tag_index]
    # Hold back a trailing partial tag such as "[FOLL".
    for size in range(min(len(_FOLLOW_UP_TAG) - 1, len(text)), 0, -1):
        if _FOLLOW_UP_TAG.startswith(lowered[-size:]):
            return text[:-size]
    return text


# Tried in order; a slow or overloaded model is hedged by the next one in parallel.
GEMINI_MODELS = [
    name.strip()
    for name in os.getenv(
        "GEMINI_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-3-flash-preview,gemini-3.6-flash"
    ).split(",")
    if name.strip()
]
HEDGE_DELAY_SECONDS = 3
# At most this many requests per question — the free tier allows only ~20 requests/day per model.
MAX_PARALLEL_REQUESTS = 2
# Lowest thinking level each model accepts; less thinking = faster first token.
_LOW_THINKING_ONLY = {"gemini-3.8-flash"}


def _config_for(model):
    level = types.ThinkingLevel.LOW if model in _LOW_THINKING_ONLY else types.ThinkingLevel.MINIMAL
    return types.GenerateContentConfig(
        max_output_tokens=2048,  # includes thinking tokens; 700 cut Hebrew answers mid-sentence
        thinking_config=types.ThinkingConfig(thinking_level=level),
    )


def _open_stream(candidate, prompt, results):
    model, key_index = candidate
    try:
        stream = _get_gemini_client(key_index).models.generate_content_stream(
            model=model, contents=prompt, config=_config_for(model)
        )
        first_chunk = next(stream, None)
        results.put((candidate, first_chunk, stream, None))
    except Exception as e:
        results.put((candidate, None, None, e))


def _start_stream(prompt):
    """
    Opens a Gemini stream and returns (first_chunk, stream) from whichever (model, key) answers first.
    Candidates are each model with each API key in turn. If one errors (503 overload, 429 quota)
    or has not started answering within HEDGE_DELAY_SECONDS, the next candidate is started
    (up to MAX_PARALLEL_REQUESTS at once). A key whose quota ran out for a model is skipped
    until Google's quota reset time.
    """
    if not GEMINI_API_KEYS:
        raise RuntimeError("חסר GEMINI_API_KEY (או GEMINI_API_KEYS) בקובץ .env.")
    results = queue.Queue()
    candidates = [(model, key_index) for model in GEMINI_MODELS for key_index in range(len(GEMINI_API_KEYS))]
    pending = candidates * 2  # second round in case every model is momentarily overloaded
    running = 0
    last_error = None

    def launch_next():
        nonlocal running
        while pending:
            candidate = pending.pop(0)
            if not _is_exhausted(candidate[1], candidate[0]):
                threading.Thread(
                    target=_open_stream, args=(candidate, prompt, results), daemon=True
                ).start()
                running += 1
                return True
        return False

    launch_next()
    while running:
        try:
            (model, key_index), first_chunk, stream, error = results.get(timeout=HEDGE_DELAY_SECONDS)
        except queue.Empty:
            if running < MAX_PARALLEL_REQUESTS:
                launch_next()
            continue
        running -= 1
        if error is None:
            if running:
                # Close the losing streams once they arrive so they stop generating.
                threading.Thread(target=_close_streams, args=(results, running), daemon=True).start()
            return first_chunk, stream
        if _is_quota_error(error):
            _mark_exhausted(key_index, model, error)
        else:
            print(f"Gemini {model} (key #{key_index + 1}) failed: {type(error).__name__}: {str(error)[:200]}", flush=True)
        last_error = error
        launch_next()
    if last_error is None:
        # Every key is out of quota for every model — don't call Google at all.
        raise RuntimeError("המכסה היומית של כל מפתחות Gemini נגמרה. נסו שוב מאוחר יותר.")
    raise last_error


def _close_streams(results, count):
    for _ in range(count):
        _, _, stream, _ = results.get()
        if stream is not None and hasattr(stream, "close"):
            stream.close()


def _stream_answer(first_chunk, stream, follow_up_questions, on_complete=None):
    full_text = ""
    emitted = ""
    chunk = first_chunk
    while chunk is not None:
        full_text += chunk.text or ""
        visible = _displayable_prefix(full_text)
        if len(visible) > len(emitted):
            yield visible[len(emitted):]
            emitted = visible
        chunk = next(stream, None)

    answer, parsed_follow_ups = _split_follow_ups(full_text)
    shown = emitted.lstrip()
    if answer.startswith(shown) and answer[len(shown):].strip():
        yield answer[len(shown):]
    follow_up_questions.extend(parsed_follow_ups)
    if on_complete and answer:
        on_complete(answer, parsed_follow_ups)


_STREAM_END = object()
# Typing pace. While Gemini is still sending, typing slows down as the typed text runs low,
# so it keeps going (instead of pausing) until the rest of the response, incl. follow-ups, arrives.
TYPEWRITER_SECONDS_PER_WORD = 0.06
TYPEWRITER_SLOW_SECONDS_PER_WORD = 0.15
TYPEWRITER_LOW_WATER_WORDS = 12
_WORD_RE = re.compile(r"\s*\S+")


def _read_stream(first_chunk, stream, pieces, follow_up_questions, on_complete):
    """Background reader: pushes visible answer text to `pieces`, fills follow-ups at the end."""
    try:
        for piece in _stream_answer(first_chunk, stream, follow_up_questions, on_complete):
            pieces.put(piece)
        pieces.put(_STREAM_END)
    except Exception as error:
        pieces.put(error)


def _typewriter(pieces):
    """
    Yields the answer word by word so it appears to be typed.
    Slows down when little text is left and Gemini hasn't finished; emits several words per step
    when a lot of text is piling up, so typing never lags far behind.
    """
    buffer = ""
    finished = False
    while buffer or not finished:
        wait_for_more = not buffer
        while not finished:
            try:
                item = pieces.get(timeout=0.5) if wait_for_more else pieces.get_nowait()
            except queue.Empty:
                break
            wait_for_more = False
            if item is _STREAM_END:
                finished = True
            elif isinstance(item, Exception):
                raise item
            else:
                buffer += item
        if not buffer:
            continue
        words = _WORD_RE.findall(buffer)
        if not words:  # whitespace only
            yield buffer
            buffer = ""
            continue
        if not finished and len(words) <= TYPEWRITER_LOW_WATER_WORDS:
            words_per_step, delay = 1, TYPEWRITER_SLOW_SECONDS_PER_WORD
        else:
            words_per_step, delay = 1 + len(words) // 50, TYPEWRITER_SECONDS_PER_WORD
        step = "".join(words[:words_per_step])
        buffer = buffer[len(step):]
        yield step
        time.sleep(delay)


def _answer_cache_key(question, topic, user_prefs):
    normalized = " ".join(question.split()).strip(" ?!.,״\"'").lower()
    prefs = user_prefs or {}
    parts = [
        normalized,
        topic or "",
        prefs.get("preferred_name") or "",
        prefs.get("response_length") or "standard",
        prefs.get("tone") or "simple",
    ]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def generate_rag_response(question, collection, user_prefs=None, topic=None):
    """Returns (answer_text_or_stream, sources, chunk_ids, prompt_text, follow_up_questions)."""
    cache_key = _answer_cache_key(question, topic, user_prefs)
    cached = get_cached_answer(cache_key)
    if cached:
        # Same question asked before — no Gemini call; still "typed" like a live answer.
        pieces = queue.Queue()
        pieces.put(cached["answer"])
        pieces.put(_STREAM_END)
        return (
            _typewriter(pieces), cached["sources"], cached["chunk_ids"],
            cached["prompt_text"], cached["follow_up_questions"],
        )

    # Within one topic fewer chunks are enough — a smaller prompt means a faster answer.
    where = topic_filter(topic)
    result_count = min(6 if where else 10, _available_chunks(collection, topic))
    if result_count == 0:
        return "זה לא כתוב באתר הפניקס.", [], [], "", []

    results = collection.query(query_texts=[question], n_results=result_count, where=where)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if not documents:
        return "זה לא כתוב באתר הפניקס.", [], [], "", []

    context_text = ""
    sources = []
    chunk_ids = []
    scored = []
    for document, metadata, chunk_id in zip(documents, metadatas, ids):
        if not isinstance(document, str) or not document.strip():
            continue
        if not isinstance(metadata, dict):
            metadata = {}
        if _is_generic_homepage_url(metadata.get("url")):
            continue
        scored.append((chunk_id, document, metadata))

    scores = get_chunk_scores([chunk_id for chunk_id, _, _ in scored])
    scored = [(scores.get(chunk_id, 1.0), chunk_id, document, metadata)
              for chunk_id, document, metadata in scored]

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
        return "זה לא כתוב באתר הפניקס.", [], [], "", []

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
בסוף התשובה, הוסף עד 3 הצעות המשך קצרות ומזמינות, בנושאים שונים שאפשר לענות עליהם מתוך הקטעים המצורפים. נסח כל הצעה כהזמנה, למשל: "רוצה לדעת גם איך מגישים תביעה?", ולא כשאלת מידע ישירה. הצע רק נושאים שיש עליהם מידע נוסף בקטעים; אם יש רק נושא אחד רלוונטי, הצע רק אותו. כתוב כל הצעה בנפרד ובפורמט המדויק [FOLLOW_UP]רוצה לדעת גם...?[/FOLLOW_UP], אחרי התשובה.
המקורות יוצגו בנפרד מהתשובה.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""

    def store_in_cache(answer, follow_ups):
        if "זה לא כתוב באתר" not in answer:
            save_cached_answer(cache_key, answer, sources, chunk_ids, prompt, follow_ups)

    first_chunk, stream = _start_stream(prompt)
    # Read the whole response (answer + follow-ups) in the background while the answer is
    # being typed, so the follow-ups are ready by the time the typing finishes.
    follow_up_questions = []
    pieces = queue.Queue()
    threading.Thread(
        target=_read_stream,
        args=(first_chunk, stream, pieces, follow_up_questions, store_in_cache),
        daemon=True,
    ).start()
    return _typewriter(pieces), sources, chunk_ids, prompt, follow_up_questions


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
