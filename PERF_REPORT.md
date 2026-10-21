# Performance report

Measurements are local, single-run observations from 2026-10-22 using Python 3.14.0, the checked-out Chroma data, the existing application configuration, one synthetic Hebrew question, and the configured Gemini model. The question text, answer, environment-variable values, and database URL are intentionally not recorded. These timings are not a statistically stable production benchmark.

## Before

Cold-process app-module imports took **12.57 s**. Loading the Chroma collection and its sentence-transformer embedding model took **33.50 s**. Together, the measured import and collection initialization path took about **46.07 s**.

One RAG response had the following measured phases:

| Phase | Duration |
|---|---:|
| Chroma retrieval | 0.88 s |
| Reranking, including ten separate `get_chunk_score` database reads | 19.85 s |
| Gemini generation | 51.26 s |
| Retrieval + reranking + model total | 71.99 s |

The ten chunk-score reads each opened a separate PostgreSQL connection; their measured durations ranged from **1.53 s to 3.18 s** in this run. Their latency dominated reranking. Generation latency is a single remote request and can vary with network/provider conditions.

Database history/preferences reads and writes were instrumented, but no account-specific history/preferences or write was exercised for this baseline; no user records were created or modified. Streamlit page-render latency was not measured in a browser. `@st.cache_resource` already protected the collection in the existing app, so the collection measurement above represents a cold process load, not every Streamlit rerun.

Instrumentation records timings through the `fnxdirect.performance` logger. It logs phase names and durations only, not prompts, response content, credentials, or database URLs.
