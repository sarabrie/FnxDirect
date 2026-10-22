"""
Search engine process: owns ChromaDB and the embedding model.

Loading them is CPU-heavy and, inside the website's own process, it starved every page render
(Python runs one thread at a time). Here it runs on its own core. Started by engine.start();
reports its loading stages, then answers queries over a local channel — a Unix socket file
(Linux) or a named pipe (Windows), never a TCP port, so port scans can't reach it.

Messages to the website:   ("stage", name) · ("ready", info) · ("error", text)
Requests from the website: ("query", kwargs for collection.query) -> ("ok", result) | ("error", text)

Run as a module (python -m fnx_direct.search.worker <listener address>) from the project root.
"""
import os
import sys
import time
from multiprocessing.connection import Client

from fnx_direct.config import COLLECTION_NAME, VECTOR_DB_PATH
from fnx_direct.knowledge.topics import topic_for_url
from fnx_direct.search.embedder import load_embedder

AUTHKEY_ENV = "FNX_SEARCH_AUTHKEY"


def _ensure_topics(collection):
    """Tags every chunk with a "topic" (from its URL) so searches can be limited to one topic."""
    existing = collection.get(include=["metadatas"])
    update_ids, update_metadatas = [], []
    counts = {}
    for chunk_id, metadata in zip(existing["ids"], existing["metadatas"]):
        metadata = dict(metadata or {})
        topic = topic_for_url(metadata.get("url"))
        counts[topic] = counts.get(topic, 0) + 1
        if metadata.get("topic") != topic:
            metadata["topic"] = topic
            update_ids.append(chunk_id)
            update_metadatas.append(metadata)
    if update_ids:
        collection.update(ids=update_ids, metadatas=update_metadatas)  # metadata only, no re-embedding
    return counts


def _load(conn):
    import chromadb

    conn.send(("stage", "imported"))
    embed = load_embedder()
    # Opened without an embedding function: we pass query vectors ourselves (see _query).
    collection = chromadb.PersistentClient(path=str(VECTOR_DB_PATH)).get_collection(name=COLLECTION_NAME)
    conn.send(("stage", "model"))
    topic_counts = _ensure_topics(collection)
    total = collection.count()
    if total:
        # First query pays for index warm-up — do it now, not on the user's question.
        collection.query(query_embeddings=embed(["ביטוח"]), n_results=1)
    conn.send(("ready", {"count": total, "topic_counts": topic_counts}))
    return collection, embed


def _query(collection, embed, kwargs):
    texts = kwargs.pop("query_texts", None)
    if texts is not None:
        kwargs["query_embeddings"] = embed(texts)
    return collection.query(**kwargs)


def _connect(address, authkey, attempts=40, delay=0.25):
    """The listener exists before this process starts; retry briefly anyway (e.g. a slow disk)."""
    for attempt in range(attempts):
        try:
            return Client(address, authkey=authkey)
        except OSError as error:  # socket file / pipe not available yet, or busy
            if attempt == attempts - 1:
                raise
            print(f"[search worker] channel not ready ({type(error).__name__}), retrying", flush=True)
            time.sleep(delay)


def main(address, authkey):
    conn = _connect(address, authkey)
    print(f"[search worker] connected to {address}, loading the model", flush=True)
    try:
        collection, embed = _load(conn)
    except Exception as error:
        conn.send(("error", f"{type(error).__name__}: {error}"))
        return
    while True:
        try:
            kind, kwargs = conn.recv()
        except (EOFError, OSError):
            return  # the website process is gone
        try:
            if kind != "query":
                raise ValueError(f"unknown request {kind!r}")
            conn.send(("ok", _query(collection, embed, kwargs)))
        except Exception as error:
            conn.send(("error", f"{type(error).__name__}: {error}"))


if __name__ == "__main__":
    # argv[1]: the listener's address (Unix socket path / Windows pipe name); the key comes via env.
    main(sys.argv[1], bytes.fromhex(os.environ[AUTHKEY_ENV]))
