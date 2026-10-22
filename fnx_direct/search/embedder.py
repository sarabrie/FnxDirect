"""
Question embeddings for the search worker, sized to fit a 512 MB server.

The model is run in a memory-lean form that gives exactly the same vectors as
SentenceTransformer(EMBEDDING_MODEL).encode():
  - tokenizer: SentencePiece (~45 MB) instead of tokenizer.json via `tokenizers` (~250 MB)
  - the 366 MB word-embedding table is a memory-mapped .npy file: only the rows of the
    question's tokens are read into RAM
  - the rest of the network (82 MB) runs on ONNX Runtime
prepare() builds these files once from the official ONNX export; the Dockerfile runs it at build
time (python -m fnx_direct.search.embedder). Without them the full ONNX model is used (~800 MB),
and without that, sentence-transformers.
"""
import os
from pathlib import Path

from fnx_direct.config import EMBEDDER_DIR, EMBEDDING_MODEL

ONNX_FILE = "onnx/model.onnx"
SPM_FILE = "sentencepiece.bpe.model"
ENCODER_FILE = "encoder.onnx"
TABLE_FILE = "word_embeddings.npy"
MAX_TOKENS = 128  # the model's max_seq_length
_WORD_EMBEDDINGS = "embeddings.word_embeddings.weight"
# XLM-R token ids: SentencePiece pieces shifted by one, plus these specials.
_BOS, _PAD, _EOS, _UNK = 0, 1, 2, 3
_STANDARD_INPUTS = {"input_ids", "attention_mask", "token_type_ids"}


def _mean_pool(np, hidden, mask):
    weights = mask[..., None].astype(hidden.dtype)
    return ((hidden * weights).sum(1) / np.clip(weights.sum(1), 1e-9, None)).tolist()


class LeanEmbedder:
    """The memory-lean model built by prepare()."""

    def __init__(self, model_dir):
        import numpy as np
        import onnxruntime
        import sentencepiece

        self._np = np
        self._spm = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / SPM_FILE))
        self._table = np.load(model_dir / TABLE_FILE, mmap_mode="r")
        options = onnxruntime.SessionOptions()
        options.enable_cpu_mem_arena = False
        self._session = onnxruntime.InferenceSession(
            str(model_dir / ENCODER_FILE), options, providers=["CPUExecutionProvider"]
        )
        input_names = {i.name for i in self._session.get_inputs()}
        (self._vectors_input,) = input_names - _STANDARD_INPUTS
        self._has_token_types = "token_type_ids" in input_names

    def _token_ids(self, text):
        pieces = [piece_id + 1 if piece_id else _UNK for piece_id in self._spm.encode(text)]
        return [_BOS, *pieces[:MAX_TOKENS - 2], _EOS]

    def __call__(self, texts):
        np = self._np
        rows = [self._token_ids(text) for text in texts]
        ids = np.full((len(rows), max(map(len, rows))), _PAD, dtype=np.int64)
        mask = np.zeros_like(ids)
        for i, row in enumerate(rows):
            ids[i, :len(row)] = row
            mask[i, :len(row)] = 1
        feed = {"input_ids": ids, "attention_mask": mask, self._vectors_input: np.asarray(self._table[ids])}
        if self._has_token_types:
            feed["token_type_ids"] = np.zeros_like(ids)
        return _mean_pool(np, self._session.run(None, feed)[0], mask)


class OnnxEmbedder:
    """The full official ONNX export with the `tokenizers` tokenizer (~800 MB in RAM)."""

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
        return _mean_pool(np, self._session.run(None, feed)[0], mask)


def _model_snapshot():
    hf_cache = Path(
        os.getenv("HF_HUB_CACHE")
        or Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    )
    snapshots = sorted((hf_cache / ("models--" + EMBEDDING_MODEL.replace("/", "--")) / "snapshots").glob("*"))
    return snapshots[-1] if snapshots else None


def _lean_model_ready():
    # The encoder is written last, so its presence means the other files are complete.
    return all((EMBEDDER_DIR / name).is_file() for name in (SPM_FILE, TABLE_FILE, ENCODER_FILE))


def prepare():
    """Builds the lean model files in EMBEDDER_DIR (needs the `onnx` package and ~1.5 GB RAM)."""
    import shutil

    import numpy as np
    import onnx
    from huggingface_hub import hf_hub_download
    from onnx import TensorProto, helper, numpy_helper

    EMBEDDER_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(hf_hub_download(EMBEDDING_MODEL, SPM_FILE), EMBEDDER_DIR / SPM_FILE)
    model = onnx.load(hf_hub_download(EMBEDDING_MODEL, ONNX_FILE))

    # Cut the word-embedding lookup out of the graph: its output becomes a model input.
    gather = next(n for n in model.graph.node if n.op_type == "Gather" and n.input[0] == _WORD_EMBEDDINGS)
    table = next(i for i in model.graph.initializer if i.name == _WORD_EMBEDDINGS)
    np.save(EMBEDDER_DIR / TABLE_FILE, numpy_helper.to_array(table))
    model.graph.node.remove(gather)
    model.graph.initializer.remove(table)
    model.graph.input.append(
        helper.make_tensor_value_info(gather.output[0], TensorProto.FLOAT, ["batch", "sequence", table.dims[1]])
    )
    onnx.checker.check_model(model)
    onnx.save(model, EMBEDDER_DIR / ENCODER_FILE)


def load_embedder():
    """Returns a callable: list of texts -> list of vectors."""
    if _lean_model_ready():
        return LeanEmbedder(EMBEDDER_DIR)
    print(f"Lean embedding model not found in {EMBEDDER_DIR} (run: python -m fnx_direct.search.embedder); "
          "using the full model, which needs ~800 MB of RAM", flush=True)

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


if __name__ == "__main__":
    prepare()
    print(f"Lean embedding model written to {EMBEDDER_DIR}")
