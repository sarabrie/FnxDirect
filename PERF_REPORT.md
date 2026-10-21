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

## After

Measurements used the same Python version, local Chroma data, synthetic question, and configured model. The request was run once; Gemini returned a retryable 503 before the first text chunk, so its one retry is included in end-to-end timing.

| Phase | Before | After |
|---|---:|---:|
| App-module imports | 12.57 s | 5.79 s |
| Chroma retrieval | 0.88 s | 0.73 s |
| Chunk-score reads + reranking | 19.85 s (10 reads) | 3.07 s (1 batched read + 0.39 s reranking) |
| Full RAG response | 71.99 s | 21.87 s |

The one batched chunk-score query took **2.68 s**, down from ten separate reads totaling approximately **19.85 s**. The combined score-read/reranking phase was about **84.5% shorter** in these runs. Chroma retrieval was similar. The measured streamed request took about **21.87 s to its first visible text and full completion** for this short answer; before streaming, the application waited for the full model response, so a comparable first-token measurement was unavailable.

Gemini timing is remote and variable: the baseline model call took 51.26 s; the after run had two attempts (about 1.35 s before its 503 and 14.11 s for the retry, plus the configured 3 s retry delay). Treat the end-to-end comparison as a single-run observation, not a guaranteed 69.6% production speedup.

The after cold resource warm-up (Chroma collection plus Gemini client, initialized concurrently) took **57.84 s** in the local environment. The baseline collection-only load was **33.50 s**; these are not directly comparable because model download/cache and resource scope varied. The important UX change is that the app now schedules both warm-ups in the background and does not wait for them before rendering the authenticated chat. A Streamlit `AppTest` with a simulated 5-second collection load confirmed that the chat UI rendered while that load was still incomplete; this is a behavior check, not a production browser timing.

History/preferences and write timings remain instrumented but were not benchmarked against real account data. The only real database operation in the RAG measurements was the batched chunk-score read. No test writes, DDL, or migration execution were performed. The new index migration is a manual deployment step.

## Comparison and limits

- The measured synchronous import path improved from 12.57 s to 5.79 s. Heavy Chroma and Gemini imports are deferred, and model resources are warmed concurrently in the background.
- Chunk-score N+1 reads were replaced by one pooled query, reducing that measured segment from about 19.85 s to 2.68 s; CPU reranking remained below 0.4 s.
- Exact repeated questions can reuse cached Chroma query results for five minutes, avoiding repeated query embedding and retrieval during that period.
- The app streams Gemini text as it arrives. The response prompt, ten retrieved chunks, output-token limit, and model were not reduced or changed, since one timing sample cannot establish a quality-safe reduction.
- No hosted Streamlit migration, Neon suspend setting changes, prompt-cache setup, or automatic DDL execution was done.
