"""
Starts the app: begins loading the search engine right away (in its own process), preloads the
slow-to-import modules in the background, then runs the Streamlit server on app.py.

Usage: python start.py [extra streamlit options, e.g. --server.port=8501]
"""
import importlib
import os
import sys
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
os.environ["PYTHONIOENCODING"] = "utf-8"  # inherited by the search worker process

# google.genai alone takes ~5s to import; do it in the background (not before the server starts)
# so neither the first page nor the first question has to wait for it.
_PRELOAD_MODULES = (
    "fnx_direct.assistant.service",
    "fnx_direct.auth.accounts",
    "fnx_direct.auth.google_oauth",
    "fnx_direct.history.conversations",
    "fnx_direct.ui.components.loading",
)


def _preload_app_modules():
    for name in _PRELOAD_MODULES:
        importlib.import_module(name)


if __name__ == "__main__":
    from streamlit.web import cli

    from fnx_direct.search import engine

    engine.start()
    threading.Thread(target=_preload_app_modules, name="preload-app-modules", daemon=True).start()
    sys.argv = ["streamlit", "run", str(ROOT_DIR / "app.py"), *sys.argv[1:]]
    sys.exit(cli.main())
