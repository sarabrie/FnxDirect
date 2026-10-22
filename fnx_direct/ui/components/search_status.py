"""Rotating status text shown while an answer is being prepared."""
import html

from fnx_direct.ui.styles import style_tag

_STEPS = ["מחפש מידע באתר הפניקס…", "מנתח את המקורות הרלוונטיים…", "מנסח תשובה…"]
_STEP_SECONDS = 2.4


def render_search_status(placeholder):
    """Search → analyze → compose; the last step stays until the answer starts."""
    spans = []
    for index, step in enumerate(_STEPS):
        animation = "fnx-step-last" if index == len(_STEPS) - 1 else "fnx-step"
        spans.append(
            f'<span class="fnx-status-step" style="animation: {animation} {_STEP_SECONDS}s ease '
            f'{index * _STEP_SECONDS}s both">{html.escape(step)}</span>'
        )
    placeholder.markdown(
        style_tag("search_status.css")
        + '<div class="fnx-status" role="status" aria-live="polite">\n'
        + '  <span class="fnx-status-dot"></span>\n'
        + '  <span class="fnx-status-text">'
        + "".join(spans)
        + "</span></div>",
        unsafe_allow_html=True,
    )
