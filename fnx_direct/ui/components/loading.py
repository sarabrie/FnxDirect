"""
Loading UI for the search engine.
- render_splash(): full-screen page until loading reaches SPLASH_UNTIL_PERCENT (50%): a progress
  ring next to a looping demo chat (question typed → "thinking" → answer typed → follow-up).
- render_progress_pill(): small ring with the percentage, shown in the app until loading hits 100%.
- render_demo_chat(): the same looping demo chat on its own (the sign-in page shows it).
"""
import streamlit as st

from fnx_direct.search import engine
from fnx_direct.ui.styles import inject_css, js_literal, read_asset, style_tag

DEMO_SCENES = [
    {
        "question": 'מה כולל ביטוח נסיעות לחו"ל?',
        "answer": 'ביטוח הנסיעות של הפניקס כולל כיסוי להוצאות רפואיות בחו"ל, לכבודה ולביטול טיסה, '
                  "ואפשר להוסיף הרחבות לפי הצורך — למשל לספורט אתגרי.",
        "follow_up": "רוצה לדעת גם איך מוסיפים הרחבה?",
    },
    {
        "question": "איך מדווחים על תאונת דרכים?",
        "answer": "אפשר לדווח בקלות דרך האפליקציה או האתר של הפניקס, ישירות מזירת האירוע. "
                  "מומלץ לצלם את הנזק ולהחליף פרטים עם הנהג השני.",
        "follow_up": "רוצה לדעת גם מה קורה אחרי הדיווח?",
    },
    {
        "question": "האם ביטוח דירה מכסה נזקי מים?",
        "answer": "ביטוח המבנה מכסה נזקים לדירה עצמה, כולל נזקי צנרת ומים, "
                  "וביטוח התכולה מגן על הרכוש שבתוכה.",
        "follow_up": "רוצה לדעת גם איך מגישים תביעה?",
    },
]


def splash_done():
    return engine.has_failed() or engine.progress() >= engine.SPLASH_UNTIL_PERCENT


def _demo_chat_html():
    return read_asset("demo_chat.html").replace("__SCENES__", js_literal(DEMO_SCENES))


def render_demo_chat(height=440):
    """The looping demo chat card, in its own frame so its animation runs undisturbed by reruns."""
    with st.container(key="demo_chat"):
        st.iframe(read_asset("demo_page.html").replace("__DEMO_CHAT__", _demo_chat_html()), height=height)


def render_splash():
    """Shows the loading page; reruns the app by itself once enough of the search engine is loaded."""
    inject_css("splash_page.css")
    page = (
        read_asset("splash.html")
        .replace("__STATE__", js_literal(engine.snapshot()))
        .replace("__DEMO_CHAT__", _demo_chat_html())
    )
    with st.container(key="splash"):
        st.iframe(page, height=640)
    _rerun_when_splash_done()


@st.fragment(run_every=1)
def _rerun_when_splash_done():
    # Only this fragment reruns each second, so the demo animation keeps playing undisturbed.
    if splash_done():
        st.rerun()


def _search_engine_settled():
    return engine.is_ready() or engine.has_failed()


def render_progress_pill(rerun_when_ready=False):
    """Small progress ring (bottom corner) while the rest of the search engine loads."""
    if _search_engine_settled():
        return
    _progress_pill(rerun_when_ready)


@st.fragment(run_every=1)
def _progress_pill(rerun_when_ready):
    if _search_engine_settled():
        if rerun_when_ready:
            st.rerun()  # e.g. the chat page enables its input
        return
    percent = engine.progress()
    circumference = 2 * 3.14159 * 20
    st.markdown(
        style_tag("progress_pill.css")
        + f'<div class="load-pill" role="progressbar" aria-label="טעינת מנוע החיפוש" aria-valuenow="{percent}" '
        f'aria-valuemin="0" aria-valuemax="100"><svg viewBox="0 0 44 44" aria-hidden="true">'
        f'<circle class="track" cx="22" cy="22" r="20"/><circle class="fill" cx="22" cy="22" r="20" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{circumference * (1 - percent / 100):.1f}"/>'
        f"</svg><span>{percent}%</span></div>",
        unsafe_allow_html=True,
    )
