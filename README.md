# FNX Direct

## Run with Docker

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`, `JWT_SECRET`, and `BASE_URL`.
   For Google sign-in, also set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
2. Start the app:

   ```sh
   docker compose up --build
   ```

3. Open <http://localhost:8501>.

The app routes are `/` (sign-in or guest entry), `/chat`, `/history`, and
`/logout`. Guests can start chatting without an account; their conversations
remain available in that browser session and are transferred to their account
when they sign in or register. Google OAuth returns to `/auth_google_callback`.
Set `BASE_URL` to the
public HTTPS origin in production (for example, `https://assistant.example.com`);
the full authorized redirect URI is `BASE_URL/auth_google_callback`. Streamlit
supports single-segment page paths only, so the callback uses an underscore
instead of nested `/auth/google/callback`. If
`GOOGLE_REDIRECT_URI` is set, it overrides the derived URI and must match exactly
in Google Cloud Console. Do not commit `.env`; configure the same values as secret
environment variables in the cloud deployment. Set `ADMIN_SECRET` to enable the
admin panel.

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
