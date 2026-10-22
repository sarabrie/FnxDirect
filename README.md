# FNX Direct

A Hebrew RAG assistant that answers insurance questions from the Phoenix (הפניקס) website.
Streamlit UI, ChromaDB + a multilingual embedding model for retrieval, Gemini for answers.

## Project structure

```text
start.py                  Launcher: starts the search engine early, then runs Streamlit on app.py
app.py                    Streamlit entry: page config, loading screen, navigation
fnx_direct/
  config.py               Paths and settings (.env is loaded here, once)
  db.py                   Shared SQLite helpers
  ssl_compat.py           Opt-in dev workaround for HTTPS-intercepting networks
  knowledge/              Website topics; crawling + indexing (ingest), index inspection
  search/                 Search-engine process (worker), its client/launcher (engine), embedder
  assistant/              Retrieval, prompt, Gemini client (hedged streaming), answer streaming, service
  history/                Conversations, messages, feedback, answer cache (chat_history.sqlite3)
  auth/                   Accounts, tokens, Google OAuth, preferences, Streamlit session (auth.sqlite3)
  ui/
    navigation.py         Page registry (/, /chat, /history, /auth_google_callback, /admin)
    pages/                One module per page
    components/           Reusable UI pieces (sidebar, messages, sources, loading, ...)
    assets/               CSS and HTML templates
    styles.py             Asset loading / CSS injection
data/
  fnx_db/                 ChromaDB index of the website (tracked in Git)
  *.sqlite3               Runtime databases (ignored by Git)
services/auth_api/        Standalone FastAPI + PostgreSQL auth service (not used by the app)
docs/                     Hackathon brief and materials
```

Dependencies point one way: `ui` → `assistant` / `history` / `auth` / `search` → `knowledge` → `config`.

## Run locally

```sh
pip install -r requirements.txt
cp .env.example .env   # then fill in GEMINI_API_KEY and JWT_SECRET
python start.py        # or run_app.bat on Windows
```

Open <http://localhost:8501>. Streamlit's file watcher is off (see `.streamlit/config.toml`),
so restart the server after code changes.

## Run with Docker

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`, `JWT_SECRET`, and `BASE_URL`.
   For Google sign-in, also set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
2. Start the app:

   ```sh
   docker compose up --build
   ```

3. Open <http://localhost:8501>.

The app routes are `/` (sign-in or guest entry), `/chat`, `/history`, `/admin` and
`/auth_google_callback`. Guests can start chatting without an account; their conversations
remain available in that browser session and are transferred to their account
when they sign in or register. Set `ADMIN_SECRET` to enable the admin panel.

Set `BASE_URL` to the public HTTPS origin in production (for example,
`https://assistant.example.com`); the full authorized redirect URI is
`BASE_URL/auth_google_callback`. Streamlit supports single-segment page paths only, so the
callback uses an underscore instead of nested `/auth/google/callback`. If
`GOOGLE_REDIRECT_URI` is set, it overrides the derived URI and must match exactly
in Google Cloud Console. Do not commit `.env`; configure the same values as secret
environment variables in the cloud deployment.

The first image build downloads the multilingual embedding model (about 480 MB)
into the image and builds a memory-lean copy of it for the search engine
(`python -m fnx_direct.search.embedder`), so the whole app fits in 512 MB of RAM.
Run the same command once locally too; without it the search engine uses the full
model (~1.2 GB at load). The search engine loads in its own process while the user signs in.

### Google sign-in for local development

In Google Cloud Console, configure the OAuth client with this authorized
JavaScript origin:

```text
http://localhost:8501
```

Add this exact authorized redirect URI:

```text
http://localhost:8501/auth_google_callback
```

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BASE_URL=http://localhost:8501`,
and `GOOGLE_REDIRECT_URI=http://localhost:8501/auth_google_callback` in the
local `.env` file, then restart the app. Use the public HTTPS origin and matching
callback URI for a deployed environment.

## Data

The ChromaDB index is mounted from `data/fnx_db` and the conversation history is stored
in the `chat_history_data` Docker volume. Both persist when the container restarts.
Users can search their conversation history, rename conversations, and hide them
from their personal history. Hiding a conversation does not remove its records
from the conversation database.

To refresh the website index, set `FIRE_CRAWL_API_KEY` in `.env`, then run:

```sh
python -m fnx_direct.knowledge.ingest
# or: docker compose run --rm app python -m fnx_direct.knowledge.ingest
```

To inspect the index: `python -m fnx_direct.knowledge.inspect_index ["question"]`.

To stop the app, run `docker compose down`. To also remove saved conversation
history, run `docker compose down --volumes`.
