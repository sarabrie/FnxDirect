# FNX Direct

## Run with Docker

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.
2. Start the app:

   ```sh
   docker compose up --build
   ```

3. Open <http://localhost:8501>.

The first image build downloads the multilingual embedding model (about 480 MB)
into the image. The app page appears without waiting for the model; it loads the
already-downloaded model when the first question is submitted.

The ChromaDB index is mounted from `fnx_db` and the conversation history is stored
in the `chat_history_data` Docker volume. Both persist when the container restarts.
Users can search their conversation history, rename conversations, and hide them
from their personal history. Hiding a conversation does not remove its records
from the conversation database.

To refresh the website index, set `FIRE_CRAWL_API_KEY` in `.env`, then run:

```sh
docker compose run --rm app python fnx_rag_pipeline.py
```

To stop the app, run `docker compose down`. To also remove saved conversation
history, run `docker compose down --volumes`.

## Deploy to Vercel

The repository includes a Vercel Services configuration for the FastAPI auth
API and the Streamlit app. Before deploying:

1. Create a managed PostgreSQL database (for example, a Neon project) and copy
   its connection string. The auth API requires PostgreSQL; MySQL is not
   supported by its current driver and schema.
2. Apply the auth schema to that database from the repository root:

   ```sh
   psql "<DATABASE_URL>" -f auth/migrations/001_initial.sql
   ```

3. Import this repository into Vercel and add these environment variables in
   the project settings:
   - `DATABASE_URL` — the managed PostgreSQL connection string.
   - `JWT_SECRET` and `CSRF_SECRET` — generate separate random values, for
     example with `python -c "import secrets; print(secrets.token_hex(48))"`.
   - `GEMINI_API_KEY` — required by the Streamlit app's assistant.
   - `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` — required only if enabling
     Google sign-in; set the OAuth redirect URI to the deployed app URL and
     configure `GOOGLE_REDIRECT_URI` to the same URL.
   - `FIRE_CRAWL_API_KEY` — only needed when refreshing the website index.
4. Deploy with the Vercel project using Services. Verify `/health` returns
   `{"status":"ok"}` and the root URL loads the Streamlit app.

Do not commit production credentials or put them in `vercel.json`.
