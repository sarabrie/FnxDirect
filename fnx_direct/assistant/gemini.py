"""
Gemini access: API keys, per-key quota tracking and a hedged streaming request that races
several (model, key) candidates and keeps whichever starts answering first.
"""
import os
import queue
import re
import threading
import time

from fnx_direct import config, ssl_compat  # noqa: F401 — config fills os.environ from .env if present

ssl_compat.apply_if_enabled()

import httpx  # noqa: E402
from google import genai  # noqa: E402 — after the optional SSL workaround
from google.genai import types  # noqa: E402

from fnx_direct.assistant.errors import is_quota_error  # noqa: E402

MISSING_KEY_MESSAGE = "חסר משתנה סביבה GEMINI_API_KEY (או GEMINI_API_KEYS)."

# Starting order; after that models are tried fastest-first by their measured time to first token
# (see _ranked_models). A slow or overloaded model is hedged by the next one in parallel.
# Measured: 3.6 / 3-preview / 3.5 answer in ~1-1.5s, 3.8 took ~90s.
GEMINI_MODELS = [
    name.strip()
    for name in os.getenv(
        "GEMINI_MODELS", "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash,gemini-3.8-flash"
    ).split(",")
    if name.strip()
]
# A healthy model starts answering in ~1-1.5s; past this, a second model is started alongside it.
HEDGE_DELAY_SECONDS = 2
# At most this many requests per question — the free tier allows only ~20 requests/day per model.
MAX_PARALLEL_REQUESTS = 2
# Lowest thinking level each model accepts; less thinking = faster first token.
_LOW_THINKING_ONLY = {"gemini-3.8-flash"}
_DEFAULT_QUOTA_COOLDOWN_SECONDS = 60 * 60
# httpx drops an idle connection after 5s by default, so every question paid ~1s for a new TLS
# handshake. Keep it open longer; warm_up() opens it while the user is still typing.
_KEEPALIVE_SECONDS = 120
_WARM_UP_INTERVAL_SECONDS = 60


def _clean_key(value):
    # Dashboards and .env files often keep surrounding spaces or quotes: ' "AIza..." '.
    return value.strip().strip("\"'").strip()


def _load_api_keys():
    """
    Keys from the GEMINI_API_KEY and GEMINI_API_KEYS (comma-separated) environment variables,
    in order, without duplicates. Never logs the keys themselves — only how many were found.
    Free-tier quota is counted per Google Cloud project, so each key should come from a different project.
    """
    raw = ",".join(os.environ.get(name, "") for name in ("GEMINI_API_KEY", "GEMINI_API_KEYS"))
    keys = list(dict.fromkeys(key for key in map(_clean_key, raw.split(",")) if key))
    # A real key is plain ASCII; anything else (e.g. Hebrew placeholder text) fails every request.
    invalid = [number for number, key in enumerate(keys, 1) if not key.isascii()]
    if invalid:
        print(f"Skipping invalid Gemini key(s) #{', #'.join(map(str, invalid))} (not a real key)", flush=True)
    keys = [key for key in keys if key.isascii()]
    print(f"Gemini: {len(keys)} API key(s) loaded from the environment", flush=True)
    return keys


GEMINI_API_KEYS = _load_api_keys()
_clients = {}
_clients_lock = threading.Lock()


def _get_client(key_index=0):
    if not GEMINI_API_KEYS:
        raise RuntimeError(MISSING_KEY_MESSAGE)
    with _clients_lock:
        if key_index not in _clients:
            _clients[key_index] = genai.Client(
                api_key=GEMINI_API_KEYS[key_index],
                http_options=types.HttpOptions(
                    client_args={"limits": httpx.Limits(keepalive_expiry=_KEEPALIVE_SECONDS)}
                ),
            )
        return _clients[key_index]


_last_warm_up = 0.0


def warm_up():
    """
    Opens the connection to Google for the key the next question will use (no quota is spent:
    it only reads the model's details), so the question doesn't pay for the TLS handshake.
    Cheap to call often — runs at most once per _WARM_UP_INTERVAL_SECONDS.
    """
    global _last_warm_up
    if not GEMINI_API_KEYS or time.time() - _last_warm_up < _WARM_UP_INTERVAL_SECONDS:
        return
    _last_warm_up = time.time()
    model, key_index = next(iter(_candidates()), (GEMINI_MODELS[0], 0))
    try:
        _get_client(key_index).models.get(model=model)
    except Exception as error:
        print(f"Gemini warm-up failed: {type(error).__name__}: {str(error)[:200]}", flush=True)


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


# ── Speed tracking ───────────────────────────────────────────────────────────
# model -> recent time to first token (seconds, moving average). Unmeasured models keep their
# GEMINI_MODELS position behind the measured ones that are faster than the hedge delay.
_first_token_seconds = {}


def _record_first_token(model, seconds):
    previous = _first_token_seconds.get(model)
    _first_token_seconds[model] = seconds if previous is None else 0.6 * previous + 0.4 * seconds


def _ranked_models():
    def speed(item):
        position, model = item
        # Unmeasured: assume it just about makes the hedge delay, keep the configured order.
        return _first_token_seconds.get(model, HEDGE_DELAY_SECONDS), position
    return [model for _, model in sorted(enumerate(GEMINI_MODELS), key=speed)]


def _candidates():
    """(model, key_index) pairs to try, fastest model first, skipping keys out of quota."""
    return [
        (model, key_index)
        for model in _ranked_models()
        for key_index in range(len(GEMINI_API_KEYS))
        if not _is_exhausted(key_index, model)
    ]


# ── Hedged streaming ─────────────────────────────────────────────────────────

def _config_for(model):
    level = types.ThinkingLevel.LOW if model in _LOW_THINKING_ONLY else types.ThinkingLevel.MINIMAL
    return types.GenerateContentConfig(
        max_output_tokens=2048,  # includes thinking tokens; 700 cut Hebrew answers mid-sentence
        thinking_config=types.ThinkingConfig(thinking_level=level),
    )


def _open_stream(candidate, prompt, results):
    model, key_index = candidate
    started = time.time()
    try:
        stream = _get_client(key_index).models.generate_content_stream(
            model=model, contents=prompt, config=_config_for(model)
        )
        first_chunk = next(stream, None)
        # Recorded for the losers of a race too, so a slow model drops down the ranking.
        _record_first_token(model, time.time() - started)
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
    Candidates are each model (fastest first, see _ranked_models) with each API key in turn. If one errors (503 overload, 429 quota),
    the next candidate is started. If one has not started answering within HEDGE_DELAY_SECONDS,
    a candidate of a *different* model is started alongside it (up to MAX_PARALLEL_REQUESTS at
    once): a slow model is usually slow for every key. A key whose quota ran out for a model is
    skipped until Google's quota reset time.
    """
    if not GEMINI_API_KEYS:
        raise RuntimeError(MISSING_KEY_MESSAGE)
    results = queue.Queue()
    pending = _candidates() * 2  # second round in case every model is momentarily overloaded
    running_models = []  # model of each request in flight
    last_error = None

    def launch_next(same_model=None):
        """Starts the first pending candidate of `same_model` if any, else of a model not already in flight."""
        pending[:] = [(model, key_index) for model, key_index in pending if not _is_exhausted(key_index, model)]
        if not pending:
            return False
        candidate = next(
            (c for c in pending if c[0] == same_model),
            next((c for c in pending if c[0] not in running_models), pending[0]),
        )
        pending.remove(candidate)
        threading.Thread(target=_open_stream, args=(candidate, prompt, results), daemon=True).start()
        running_models.append(candidate[0])
        return True

    launch_next()
    while running_models:
        try:
            (model, key_index), first_chunk, stream, error = results.get(timeout=HEDGE_DELAY_SECONDS)
        except queue.Empty:
            if len(running_models) < MAX_PARALLEL_REQUESTS:
                launch_next()
            continue
        running_models.remove(model)
        if error is None:
            if running_models:
                # Close the losing streams once they arrive so they stop generating.
                threading.Thread(
                    target=_close_streams, args=(results, len(running_models)), daemon=True
                ).start()
            return first_chunk, stream
        last_error = error
        if is_quota_error(error):
            _mark_exhausted(key_index, model, error)
            launch_next(same_model=model)  # this key's quota is used up; the next key's may not be
        else:
            # e.g. 503 overloaded: that's the model, not the key — try another model.
            print(f"Gemini {model} (key #{key_index + 1}) failed: {type(error).__name__}: {str(error)[:200]}", flush=True)
            launch_next()
    if last_error is None:
        # Every key is out of quota for every model — don't call Google at all.
        raise RuntimeError("המכסה היומית של כל מפתחות Gemini נגמרה. נסו שוב מאוחר יותר.")
    raise last_error
