"""
Streamlit entry point (launched by start.py): page config, the loading screen, global layout CSS
and page navigation. The pages themselves live in fnx_direct/ui/pages.
"""
import streamlit as st

from fnx_direct import config
from fnx_direct.search import engine
from fnx_direct.ui.components import loading
from fnx_direct.ui.styles import inject_css

st.set_page_config(page_title=config.PAGE_TITLE, page_icon=config.PAGE_ICON, layout="wide")

# Begin loading the search model (no-op if start.py already did). Until it is half loaded,
# show the loading screen — decided before importing the app pages, so it appears immediately.
engine.start()
if not loading.splash_done():
    loading.render_splash()
    st.stop()

from fnx_direct.auth.database import init_auth_db  # noqa: E402 — after the loading screen on purpose
from fnx_direct.ui.navigation import PAGES  # noqa: E402

inject_css("layout.css")
init_auth_db()
st.navigation(PAGES, position="hidden").run()
