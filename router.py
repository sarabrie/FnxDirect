from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from auth_db import init_auth_db
from routes import PAGES

st.set_page_config(
    page_title="הפניקס | עוזר אישי",
    page_icon="✳",
    layout="wide",
)

init_auth_db()
navigation = st.navigation(PAGES, position="hidden")
navigation.run()