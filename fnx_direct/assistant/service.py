"""
Answers a question: answer cache → retrieval → prompt → Gemini stream, typed out live.
This is the only module the chat page calls for answers (imported lazily — google.genai is slow to load).
"""
import hashlib
import json
import queue
import threading

from fnx_direct.assistant import gemini, streaming
from fnx_direct.assistant.prompt import NOT_FOUND_ANSWER, build_prompt, is_not_found
from fnx_direct.assistant.retrieval import retrieve
from fnx_direct.history.answer_cache import get_cached_answer, save_cached_answer
from fnx_direct.search import engine


def get_collection():
    """The search engine (its own process — see search/worker.py); waits until it is loaded."""
    return engine.wait_until_ready()


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
        return (
            streaming.type_out(cached["answer"]), cached["sources"], cached["chunk_ids"],
            cached["prompt_text"], cached["follow_up_questions"],
        )

    context_text, sources, chunk_ids = retrieve(question, collection, topic)
    if not context_text:
        return NOT_FOUND_ANSWER, [], [], "", []

    prompt = build_prompt(question, context_text, user_prefs)

    def store_in_cache(answer, follow_ups):
        if not is_not_found(answer):
            save_cached_answer(cache_key, answer, sources, chunk_ids, prompt, follow_ups)

    first_chunk, stream = gemini.start_stream(prompt)
    # Read the whole response (answer + follow-ups) in the background while the answer is
    # being typed, so the follow-ups are ready by the time the typing finishes.
    follow_up_questions = []
    pieces = queue.Queue()
    threading.Thread(
        target=streaming.read_stream,
        args=(first_chunk, stream, pieces, follow_up_questions, store_in_cache),
        daemon=True,
    ).start()
    return streaming.typewriter(pieces), sources, chunk_ids, prompt, follow_up_questions
