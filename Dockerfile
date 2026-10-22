FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# The full model is used by the crawler/indexer (python -m fnx_direct.knowledge.ingest).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Memory-lean copy of the model for the search worker (~270 MB in RAM instead of ~1.2 GB),
# so the app fits a 512 MB server. Only the files it needs are copied, to keep this layer cached.
ENV FNX_EMBEDDER_DIR=/opt/fnx_embedder
COPY fnx_direct/__init__.py fnx_direct/config.py fnx_direct/
COPY fnx_direct/search/ fnx_direct/search/
RUN python -m fnx_direct.search.embedder

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .

EXPOSE 8501

CMD ["python", "start.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
