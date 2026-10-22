"""
Gemini access: API keys, per-key quota tracking and a hedged streaming request that races
several (model, key) candidates and keeps whichever starts answering first.
"""
import os
import queue
import re
import threading
import time

from fnx_direct import ssl_compat

ssl_compat.apply_if_enabled()

from google import genai  # noqa: E402 — after the optional SSL workaround
from google.genai import types  # noqa: E402

from fnx_direct.assistant.errors import is_quota_error  # noqa: E402

MISSING_KEY_MESSAGE = "חסר GEMINI_API_KEY (או GEMINI_API_KEYS) בקובץ .env."

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
_DEFAULT_QUOTA_COOLDOWN_SECONDS = 60 * 60


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
_clients = {}
_clients_lock = threading.Lock()


def _get_client(key_index=0):
    if not GEMINI_API_KEYS:
        raise RuntimeError(MISSING_KEY_MESSAGE)
    with _clients_lock:
        if key_index not in _clients:
            _clients[key_index] = genai.Client(api_key=GEMINI_API_KEYS[key_index])
        return _clients[key_index]


# ── Quota tracking ───────────────────────────────────────────────────────────
# (key_index, model) -> time until which that key's quota for that model is used up (429).
_exhausted_until = {}


def _mark_exhausted(key_index, model, error):
    # Google says how long until the quota resets, e.g. 'retryDelay': '51142s'.
    match = re.search(r"retryDelay'?:\s*'?(\d+(?:\.\d+)?)s", str(error))
    cooldown = float(match.group(1)) if match else _DEFAULT_QUOTA_COOLDOWN_SECONDS
    _exhausted_until[(key_index, model)] = time.time() + cooldown
    print(f"Gemini key #{key_index + 1} out of quota for {model}; skipping it for {cooldown / 3600:.1f}h", flush=True)


def _is_exhausted(key_index, model):
    return _exhausted_until.get((key_index, model), 0) > time.time()


# ── Hedged streaming ─────────────────────────────────────────────────────────

def _config_for(model):
    level = types.ThinkingLevel.LOW if model in _LOW_THINKING_ONLY else types.ThinkingLevel.MINIMAL
    return types.GenerateContentConfig(
        max_output_tokens=2048,  # includes thinking tokens; 700 cut Hebrew answers mid-sentence
        thinking_config=types.ThinkingConfig(thinking_level=level),
    )


def _open_stream(candidate, prompt, results):
    model, key_index = candidate
    try:
        stream = _get_client(key_index).models.generate_content_stream(
            model=model, contents=prompt, config=_config_for(model)
        )
        first_chunk = next(stream, None)
        results.put((candidate, first_chunk, stream, None))
    except Exception as e:
        results.put((candidate, None, None, e))


def _close_streams(results, count):
    for _ in range(count):
        _, _, stream, _ = results.get()
        if stream is not None and hasattr(stream, "close"):
            stream.close()


def start_stream(prompt):
    """
    Opens a Gemini stream and returns (first_chunk, stream) from whichever (model, key) answers first.
    Candidates are each model with each API key in turn. If one errors (503 overload, 429 quota)
    or has not started answering within HEDGE_DELAY_SECONDS, the next candidate is started
    (up to MAX_PARALLEL_REQUESTS at once). A key whose quota ran out for a model is skipped
    until Google's quota reset time.
    """
    if not GEMINI_API_KEYS:
        raise RuntimeError(MISSING_KEY_MESSAGE)
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
        if is_quota_error(error):
            _mark_exhausted(key_index, model, error)
        else:
            print(f"Gemini {model} (key #{key_index + 1}) failed: {type(error).__name__}: {str(error)[:200]}", flush=True)
        last_error = error
        launch_next()
    if last_error is None:
        # Every key is out of quota for every model — don't call Google at all.
        raise RuntimeError("המכסה היומית של כל מפתחות Gemini נגמרה. נסו שוב מאוחר יותר.")
    raise last_error
