"""Finds the website chunks relevant to a question and turns them into prompt context and sources."""
from urllib.parse import urlsplit

from fnx_direct.history.feedback import get_chunk_scores
from fnx_direct.knowledge.topics import GENERAL_TOPIC, topic_filter

# Within one topic fewer chunks are enough — a smaller prompt means a faster answer.
RESULTS_PER_TOPIC = 6
RESULTS_ALL_TOPICS = 10


def public_page_url(url):
    """The URL if it points to a specific http(s) page (not a bare homepage), else None."""
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
    except ValueError:
        return None
    if parsed_url.scheme.lower() not in {"http", "https"} or not hostname or parsed_url.path in {"", "/"}:
        return None
    return url


def _is_homepage_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return False
    return parsed_url.scheme.lower() in {"http", "https"} and bool(parsed_url.netloc) and parsed_url.path in {"", "/"}


def _available_chunks(collection, topic):
    where = topic_filter(topic)
    if where is None or not collection.topic_counts:
        return collection.count()
    if topic == GENERAL_TOPIC:
        return collection.topic_counts.get(GENERAL_TOPIC, 0)
    return collection.topic_counts.get(topic, 0) + collection.topic_counts.get(GENERAL_TOPIC, 0)


def retrieve(question, collection, topic=None):
    """
    Returns (context_text, sources, chunk_ids) for the chunks closest to the question,
    ordered so chunks that users reported as inaccurate come last.
    """
    where = topic_filter(topic)
    result_count = min(RESULTS_PER_TOPIC if where else RESULTS_ALL_TOPICS, _available_chunks(collection, topic))
    if result_count == 0:
        return "", [], []

    results = collection.query(query_texts=[question], n_results=result_count, where=where)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    candidates = []
    for document, metadata, chunk_id in zip(documents, metadatas, ids):
        if not isinstance(document, str) or not document.strip():
            continue
        if not isinstance(metadata, dict):
            metadata = {}
        if _is_homepage_url(metadata.get("url")):
            continue
        candidates.append((chunk_id, document, metadata))

    # Re-rank: penalised chunks sink to the bottom, still included for transparency.
    scores = get_chunk_scores([chunk_id for chunk_id, _, _ in candidates])
    candidates.sort(key=lambda candidate: scores.get(candidate[0], 1.0), reverse=True)

    context_text = ""
    sources = []
    chunk_ids = []
    for chunk_id, document, metadata in candidates:
        title = metadata.get("title")
        if title:
            context_text += f"- עמוד: {title}\n  קטע: {document}\n"
        else:
            context_text += f"- {document}\n"
        sources.append({
            "snippet": document,
            "url": public_page_url(metadata.get("url")),
            "title": title if isinstance(title, str) else None,
        })
        chunk_ids.append(chunk_id)
    return context_text, sources, chunk_ids
