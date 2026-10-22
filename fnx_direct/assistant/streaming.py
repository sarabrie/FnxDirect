"""
Turns a raw Gemini stream into what the chat shows: the answer text without the [FOLLOW_UP] tags,
typed out word by word, with the follow-up suggestions collected separately.
"""
import queue
import re
import time

_FOLLOW_UP_TAG = "[follow_up]"
_FOLLOW_UP_PATTERN = r"\[FOLLOW_UP\](.*?)\[/FOLLOW_UP\]"
MAX_FOLLOW_UPS = 3

STREAM_END = object()
# Typing pace. While Gemini is still sending, typing slows down as the typed text runs low,
# so it keeps going (instead of pausing) until the rest of the response, incl. follow-ups, arrives.
TYPEWRITER_SECONDS_PER_WORD = 0.06
TYPEWRITER_SLOW_SECONDS_PER_WORD = 0.15
TYPEWRITER_LOW_WATER_WORDS = 12
_WORD_RE = re.compile(r"\s*\S+")


def split_follow_ups(text):
    """Returns (answer without follow-up tags, up to MAX_FOLLOW_UPS unique follow-ups)."""
    follow_ups = [
        " ".join(match.split())
        for match in re.findall(_FOLLOW_UP_PATTERN, text, re.IGNORECASE | re.DOTALL)
    ]
    answer = re.sub(_FOLLOW_UP_PATTERN, "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    return answer, list(dict.fromkeys(follow_ups))[:MAX_FOLLOW_UPS]


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

    answer, parsed_follow_ups = split_follow_ups(full_text)
    shown = emitted.lstrip()
    if answer.startswith(shown) and answer[len(shown):].strip():
        yield answer[len(shown):]
    follow_up_questions.extend(parsed_follow_ups)
    if on_complete and answer:
        on_complete(answer, parsed_follow_ups)


def read_stream(first_chunk, stream, pieces, follow_up_questions, on_complete):
    """Background reader: pushes visible answer text to `pieces`, fills follow-ups at the end."""
    try:
        for piece in _stream_answer(first_chunk, stream, follow_up_questions, on_complete):
            pieces.put(piece)
        pieces.put(STREAM_END)
    except Exception as error:
        pieces.put(error)


def typewriter(pieces):
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
            if item is STREAM_END:
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


def type_out(text):
    """A finished text (e.g. from the answer cache) typed out like a live answer."""
    pieces = queue.Queue()
    pieces.put(text)
    pieces.put(STREAM_END)
    return typewriter(pieces)
