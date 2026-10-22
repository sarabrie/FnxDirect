"""
Question embeddings for the search worker.

Runs on ONNX Runtime (the model's official ONNX export) instead of torch / sentence-transformers:
identical vectors, but ~4s to load instead of ~25s. Falls back to sentence-transformers if the
ONNX file can't be found or downloaded.
"""
import os
from pathlib import Path

from fnx_direct.config import EMBEDDING_MODEL

ONNX_FILE = "onnx/model.onnx"
MAX_TOKENS = 128  # the model's max_seq_length


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


def load_embedder():
    """Returns a callable: list of texts -> list of vectors."""
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
