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
