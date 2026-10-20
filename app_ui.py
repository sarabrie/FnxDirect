import streamlit as st


def render_header():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap');

:root {
    --ink: #172b2a;
    --muted: #687775;
    --green: #087e70;
    --line: #dce5df;
}
.stApp {
    direction: rtl;
    color: var(--ink);
    background: radial-gradient(ellipse at 85% 0%, #e4f2e9 0, transparent 36%), #f7f8f5;
    font-family: 'Heebo', sans-serif;
}
[data-testid="stSidebar"] {
    background: #edf3ee;
    border-left: 1px solid var(--line);
}
[data-testid="stSidebar"] * { font-family: 'Heebo', sans-serif; }
.block-container { max-width: 860px; padding-top: 2.5rem; padding-bottom: 8rem; }
.brand-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; border-radius: 13px;
    color: white; background: var(--green); font-size: 23px; font-weight: 700;
}
.eyebrow { color: var(--green); font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.intro-title { color: var(--ink); font-size: 32px; font-weight: 800; line-height: 1.25; margin: 0; }
.intro-copy { color: var(--muted); font-size: 16px; margin-top: 8px; }
.trust-line { color: var(--muted); font-size: 13px; padding: 12px 0 18px; border-bottom: 1px solid var(--line); }
[data-testid="stChatMessage"] { direction: rtl; text-align: right; }
[data-testid="stChatInput"] { direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; font-family: 'Heebo', sans-serif; }
.stButton > button { direction: rtl; text-align: right; border-color: var(--line); color: var(--ink); }
.stButton > button:hover { border-color: var(--green); color: var(--green); }
a { color: var(--green) !important; }
</style>
<div style="display:flex;align-items:center;gap:13px;margin-bottom:22px">
  <div class="brand-mark">✳</div>
  <div><div class="eyebrow">FNX DIRECT</div><div style="font-size:17px;font-weight:700">העוזר של הפניקס</div></div>
</div>
<div class="eyebrow">מידע ברור, במקום אחד</div>
<h1 class="intro-title">איך אפשר לעזור?</h1>
<div class="intro-copy">שאלו על ביטוח, תביעות ושירות. התשובות מבוססות על המידע באתר הפניקס.</div>
<div class="trust-line">✳ &nbsp; תשובות מבוססות מקור &nbsp; · &nbsp; קישורים לעמודים הרלוונטיים</div>
""", unsafe_allow_html=True)


def render_sidebar(conversations):
    with st.sidebar:
        st.markdown("### הפניקס")
        st.caption("עוזר מידע אישי")
        action = None
        if st.button("שיחה חדשה", use_container_width=True):
            action = ("new", None)
        st.divider()
        st.markdown("**היסטוריית שיחות**")
        for conversation in conversations:
            if st.button(
                conversation["title"],
                key=f"history_{conversation['id']}",
                use_container_width=True,
            ):
                action = ("select", conversation["id"])
        st.divider()
        st.markdown("**נושאים שאפשר לשאול עליהם**")
        st.caption("תביעות · ביטוח רכב · ביטוח דירה · ביטוח נסיעות")
    return action


def render_suggestions():
    st.markdown("**אפשר להתחיל מכאן**")
    suggestions = [
        "איך מגישים תביעה על נזקי מים?",
        "מה כולל ביטוח נסיעות לחו״ל?",
        "איך יוצרים קשר עם הפניקס?",
    ]
    suggestion_columns = st.columns(len(suggestions))
    selected_question = None
    for column, suggestion in zip(suggestion_columns, suggestions):
        if column.button(suggestion, use_container_width=True):
            selected_question = suggestion
    return selected_question


def render_messages(messages):
    for message in messages:
        with st.chat_message(message["role"]):
            render_message_content(message["content"], message.get("sources"))


def render_message_content(content, sources=None):
    st.markdown(content)
    if sources:
        st.markdown("**מקורות**")
        for source in sources:
            st.markdown(f"- [לעמוד המקור]({source})")
