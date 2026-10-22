"""
Search engine process: owns ChromaDB and the embedding model.

Loading them is CPU-heavy and, inside the website's own process, it starved every page render
(Python runs one thread at a time). Here it runs on its own core. Started by warmup.start();
reports its loading stages, then answers queries over a local socket.

The question embedding runs on ONNX Runtime (the model's official ONNX export) instead of
torch / sentence-transformers: identical vectors, but ~4s to load instead of ~25s.

Messages to the website:   ("stage", name) · ("ready", info) · ("error", text)
Requests from the website: ("query", kwargs for collection.query) -> ("ok", result) | ("error", text)
"""
import os
import sys
from multiprocessing.connection import Client
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_PATH = str(APP_DIR / "fnx_db")
COLLECTION_NAME = "fnx_website_chunks_multilingual"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ONNX_FILE = "onnx/model.onnx"
MAX_TOKENS = 128  # the model's max_seq_length
AUTHKEY_ENV = "FNX_SEARCH_AUTHKEY"


def _model_snapshot():
    hf_cache = Path(
        os.getenv("HF_HUB_CACHE")
        or Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    )
    snapshots = sorted((hf_cache / ("models--" + EMBEDDING_MODEL.replace("/", "--")) / "snapshots").glob("*"))
    return snapshots[-1] if snapshots else None


class OnnxEmbedder:
    """Mean-pooled sentence embeddings, same as SentenceTransformer(EMBEDDING_MODEL).encode()."""

    def __init__(self, snapshot):
        import numpy as np
        import onnxruntime
        from tokenizers import Tokenizer

        self._np = np
        self._tokenizer = Tokenizer.from_file(str(snapshot / "tokenizer.json"))
        self._tokenizer.enable_truncation(MAX_TOKENS)
        pad_id = self._tokenizer.token_to_id("<pad>")
        self._tokenizer.enable_padding(pad_id=pad_id if pad_id is not None else 0, pad_token="<pad>")
        self._session = onnxruntime.InferenceSession(str(snapshot / ONNX_FILE), providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self._session.get_inputs()}

    def __call__(self, texts):
        np = self._np
        encoded = self._tokenizer.encode_batch(list(texts))
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feed)[0]
        weights = mask[..., None].astype(hidden.dtype)
        return ((hidden * weights).sum(1) / np.clip(weights.sum(1), 1e-9, None)).tolist()


def _load_embedder():
    snapshot = _model_snapshot()
    if snapshot is None or not (snapshot / ONNX_FILE).is_file():
        try:  # one-time download of the official ONNX export (same HuggingFace repo as the model)
            from huggingface_hub import hf_hub_download

            hf_hub_download(EMBEDDING_MODEL, ONNX_FILE)
            snapshot = _model_snapshot()
        except Exception as error:
            print(f"ONNX model unavailable ({type(error).__name__}); using sentence-transformers", flush=True)
    if snapshot is not None and (snapshot / ONNX_FILE).is_file():
        return OnnxEmbedder(snapshot)

    # Fallback: the original (slower to load) torch model.
    if snapshot is not None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # cached — skip ~30s of Hub checks
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL)
    return lambda texts: model.encode(list(texts)).tolist()


def _ensure_topics(collection):
    """Tags every chunk with a "topic" (from its URL) so searches can be limited to one topic."""
    from topics import topic_for_url

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
    embed = _load_embedder()
    # Opened without an embedding function: we pass query vectors ourselves (see _query).
    collection = chromadb.PersistentClient(path=DB_PATH).get_collection(name=COLLECTION_NAME)
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


def main(port, authkey):
    sys.path.insert(0, str(APP_DIR))
    conn = Client(("127.0.0.1", port), authkey=authkey)
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
    main(int(sys.argv[1]), bytes.fromhex(os.environ[AUTHKEY_ENV]))
