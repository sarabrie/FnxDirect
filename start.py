"""
Starts the Streamlit app and, in the same process, begins loading the search model
right away — so it is ready by the time the user finishes logging in.

Usage: python start.py [extra streamlit options, e.g. --server.port=8501]
"""
import os
import sys
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))


if __name__ == "__main__":
    from streamlit.web import cli

    import threading

    import warmup

    # The search engine loads in its own process (search_worker.py) right away.
    warmup.start()

    def _preload_app_modules():
        # google.genai alone takes ~5s to import; do it in the background (not before the server
        # starts) so neither the first page nor the first question has to wait for it.
        import assistant_service, auth_db, chat_history, landing_ui, splash_ui, topics  # noqa: E401,F401

    threading.Thread(target=_preload_app_modules, name="preload-app-modules", daemon=True).start()
    sys.argv = ["streamlit", "run", str(APP_DIR / "router.py"), *sys.argv[1:]]
    sys.exit(cli.main())
