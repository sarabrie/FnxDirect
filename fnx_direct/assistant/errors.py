"""Error classification shared by the Gemini client and the chat page (kept import-light)."""


def is_quota_error(error):
    """True for Gemini 429 / RESOURCE_EXHAUSTED (rate limit or daily quota)."""
    text = str(error)
    return getattr(error, "code", None) == 429 or "429" in text or "RESOURCE_EXHAUSTED" in text
