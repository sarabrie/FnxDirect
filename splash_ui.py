"""
Loading UI for the search engine.
- render_splash(): full-screen page until loading reaches SPLASH_UNTIL_PERCENT (50%): a progress
  ring next to a looping demo chat (question typed → "thinking" → answer typed → follow-up).
- render_progress_pill(): small ring with the percentage, shown in the app until loading hits 100%.
"""
import json

import streamlit as st

import warmup

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

_SPLASH_HTML = """<!doctype html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --ink: #142c32; --muted: #5d7074; --teal: #087f79; --teal-dark: #08645f;
    --teal-pale: #e5f4f1; --gold: #d79a34; --line: #d9e3e2; --surface: #ffffff;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: transparent; font-family: 'Heebo', 'Segoe UI', sans-serif; color: var(--ink); }
  .wrap {
    height: 100%; display: grid; grid-template-columns: 1fr 1fr; gap: 48px;
    align-items: center; max-width: 1080px; margin: 0 auto; padding: 0 24px;
  }
  /* ── Loading side ── */
  .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 34px; }
  .mark {
    width: 52px; height: 52px; border-radius: 15px; background: var(--teal); color: #fff;
    display: flex; align-items: center; justify-content: center; font-size: 27px; font-weight: 800;
    box-shadow: 0 8px 22px rgba(8,100,95,.25); animation: pulse 2.2s ease-in-out infinite;
  }
  @keyframes pulse { 50% { transform: scale(1.07); box-shadow: 0 10px 30px rgba(8,100,95,.35); } }
  .brand-name { font-size: 21px; font-weight: 800; }
  .brand-sub { font-size: 13px; color: var(--muted); }
  h1 { font-size: 38px; line-height: 1.2; font-weight: 800; margin: 0 0 30px; }
  .ring { position: relative; width: 132px; height: 132px; }
  .ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  .ring circle { fill: none; stroke-width: 9; }
  .ring .track { stroke: #dbe8e5; }
  .ring .fill { stroke: url(#ringGradient); stroke-linecap: round; transition: stroke-dashoffset .3s linear; }
  .ring .pct {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    font-size: 30px; font-weight: 800; color: var(--teal-dark); font-variant-numeric: tabular-nums;
    direction: ltr;  /* "49%", not "%49" */
  }
  .ring .pct small { font-size: 16px; font-weight: 700; margin-inline-start: 1px; }

  /* ── Demo chat side ── */
  .demo {
    position: relative; background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
    box-shadow: 0 24px 60px rgba(20,44,50,.12), 0 2px 8px rgba(20,44,50,.04);
    padding: 18px 18px 20px; height: 400px; overflow: hidden;
  }
  .demo-head { display: flex; align-items: center; gap: 9px; padding-bottom: 12px; border-bottom: 1px solid var(--line); margin-bottom: 14px; }
  .demo-avatar { width: 30px; height: 30px; border-radius: 9px; background: var(--teal); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; }
  .demo-title { font-size: 14px; font-weight: 700; }
  .demo-online { font-size: 12px; color: var(--teal); display: flex; align-items: center; gap: 5px; }
  .demo-online::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: #22b07d; animation: blink 1.6s infinite; }
  @keyframes blink { 50% { opacity: .3; } }
  .demo-tag { margin-inline-start: auto; font-size: 11px; color: var(--muted); background: #f1f5f4; border-radius: 99px; padding: 3px 10px; }
  .chat { display: flex; flex-direction: column; gap: 12px; transition: opacity .4s; }
  .bubble {
    max-width: 86%; padding: 11px 15px; border-radius: 15px; font-size: 14.5px; line-height: 1.65;
    animation: pop .35s ease both;
  }
  @keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.98); } }
  .user { align-self: flex-start; background: var(--teal); color: #fff; border-bottom-right-radius: 4px; }
  .bot { align-self: flex-end; background: #f2f6f5; border: 1px solid var(--line); border-bottom-left-radius: 4px; }
  .caret { display: inline-block; width: 2px; height: 1em; background: currentColor; margin-inline-start: 2px; vertical-align: -2px; animation: blink 0.8s steps(1) infinite; }
  .dots { display: inline-flex; gap: 5px; padding: 4px 2px; }
  .dots span { width: 8px; height: 8px; border-radius: 50%; background: #93aaa6; animation: bounce 1.1s infinite; }
  .dots span:nth-child(2) { animation-delay: .15s; } .dots span:nth-child(3) { animation-delay: .3s; }
  @keyframes bounce { 0%, 60%, 100% { transform: none; opacity: .5; } 30% { transform: translateY(-6px); opacity: 1; } }
  .chip {
    align-self: flex-end; font-size: 13px; color: var(--teal-dark); background: var(--teal-pale);
    border: 1px solid #b9dcd5; border-radius: 99px; padding: 6px 13px;
    animation: chip-in .7s ease both;
  }
  @keyframes chip-in { from { opacity: 0; transform: translateY(6px); color: #b5c6c3; } }
  .glow {
    position: absolute; inset: auto -60px -80px auto; width: 220px; height: 220px; border-radius: 50%;
    background: radial-gradient(circle, rgba(8,127,121,.12), transparent 70%); pointer-events: none;
  }
  @media (max-width: 820px) {
    .wrap { grid-template-columns: 1fr; gap: 22px; align-content: center; }
    h1 { font-size: 28px; } .lead { margin-bottom: 18px; } .brand { margin-bottom: 18px; }
    .demo { height: 330px; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01s !important; animation-iteration-count: 1 !important; }
  }
</style></head>
<body>
<div class="wrap">
  <section>
    <div class="brand">
      <div class="mark">✳</div>
      <div><div class="brand-name">FNX Direct</div><div class="brand-sub">העוזר החכם של הפניקס</div></div>
    </div>
    <h1>טוענים את האתר,<br>אנא המתינו…</h1>
    <div class="ring" role="progressbar" aria-label="התקדמות הטעינה" aria-valuemin="0" aria-valuemax="100">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <defs><linearGradient id="ringGradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#20a69d"/><stop offset="1" stop-color="#08645f"/></linearGradient></defs>
        <circle class="track" cx="60" cy="60" r="52"/>
        <circle class="fill" id="fill" cx="60" cy="60" r="52"/>
      </svg>
      <div class="pct"><span id="pct">0</span><small>%</small></div>
    </div>
  </section>
  <section class="demo" aria-hidden="true">
    <div class="demo-head">
      <div class="demo-avatar">✳</div>
      <div><div class="demo-title">העוזר החכם</div><div class="demo-online">זמין עכשיו</div></div>
      <span class="demo-tag">הדגמה</span>
    </div>
    <div class="chat" id="chat"></div>
    <div class="glow"></div>
  </section>
</div>
<script>
  const scenes = __SCENES__;
  const state = __STATE__;
  const loadedAt = performance.now();

  // ── Progress ring: same stage-based estimate as the server (warmup.progress), animated here;
  //    the server switches to the app at SPLASH_UNTIL_PERCENT, so the ring stops just below it.
  const fill = document.getElementById("fill"), pct = document.getElementById("pct");
  const ring = document.querySelector(".ring");
  const circumference = 2 * Math.PI * 52;
  fill.style.strokeDasharray = circumference;
  function estimate() {
    let stage = state.stage, elapsed = state.stageElapsed + (performance.now() - loadedAt) / 1000;
    while (stage < state.durations.length - 1 && elapsed > state.durations[stage]) {
      elapsed -= state.durations[stage]; stage += 1;
    }
    const start = stage ? state.milestones[stage - 1] : 0, end = state.milestones[stage];
    return Math.min(start + (end - start) * Math.min(1, elapsed / state.durations[stage]), state.cap);
  }
  function tick() {
    const p = estimate();
    fill.style.strokeDashoffset = circumference * (1 - p / 100);
    pct.textContent = Math.round(p);
    ring.setAttribute("aria-valuenow", Math.round(p));
  }
  tick(); setInterval(tick, 200);

  // ── Demo chat loop
  const chat = document.getElementById("chat");
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function bubble(cls) { const el = document.createElement("div"); el.className = "bubble " + cls; chat.appendChild(el); return el; }
  async function typeChars(el, text, ms) {
    const caret = document.createElement("span"); caret.className = "caret";
    for (let i = 1; i <= text.length; i++) { el.textContent = text.slice(0, i); el.appendChild(caret); await sleep(ms); }
    caret.remove();
  }
  async function typeWords(el, text, ms) {
    const words = text.split(" ");
    for (let i = 1; i <= words.length; i++) { el.textContent = words.slice(0, i).join(" "); await sleep(ms); }
  }
  async function play() {
    for (;;) {
      for (const s of scenes) {
        chat.style.opacity = 1; chat.innerHTML = "";
        await sleep(350);
        await typeChars(bubble("user"), s.question, 55);
        await sleep(350);
        const bot = bubble("bot");
        bot.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
        await sleep(1300);
        await typeWords(bot, s.answer, 90);
        await sleep(450);
        const chip = document.createElement("div"); chip.className = "chip"; chip.textContent = "💬 " + s.follow_up;
        chat.appendChild(chip);
        await sleep(2800);
        chat.style.opacity = 0;
        await sleep(450);
      }
    }
  }
  play();
</script></body></html>"""


def render_splash():
    """Shows the loading page; reruns the app by itself once the search engine is ready."""
    st.markdown(
        """
<style>
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.stApp {
    background:
      radial-gradient(ellipse at 14% 84%, rgba(215,154,52,.10), transparent 27%),
      radial-gradient(ellipse at 88% 12%, rgba(8,127,121,.11), transparent 34%),
      #f3f7f5;
}
.block-container { max-width: 100%; padding: 0 !important; }
.st-key-splash iframe { height: 100vh !important; display: block; }
</style>
""",
        unsafe_allow_html=True,
    )
    page = (
        _SPLASH_HTML.replace("__SCENES__", json.dumps(DEMO_SCENES, ensure_ascii=False).replace("<", "\\u003c"))
        .replace("__STATE__", json.dumps(warmup.snapshot()))
    )
    with st.container(key="splash"):
        st.iframe(page, height=640)
    _wait_until_ready()


def splash_done():
    return warmup.failed.is_set() or warmup.progress() >= warmup.SPLASH_UNTIL_PERCENT


@st.fragment(run_every=1)
def _wait_until_ready():
    # Only this fragment reruns each second, so the demo animation keeps playing undisturbed.
    if splash_done():
        st.rerun()


_PILL_CSS = """
<style>
.load-pill {
    position: fixed; bottom: 18px; left: 18px; z-index: 1000;
    display: flex; align-items: center; justify-content: center;
    width: 54px; height: 54px; border-radius: 50%;
    background: #fff; box-shadow: 0 8px 24px rgba(20,44,50,.16);
    animation: load-pill-in .4s ease both;
}
.load-pill svg { position: absolute; inset: 5px; transform: rotate(-90deg); }
.load-pill circle { fill: none; stroke-width: 4; }
.load-pill .track { stroke: #dbe8e5; }
.load-pill .fill { stroke: #087f79; stroke-linecap: round; }
.load-pill span { font: 800 12px 'Heebo', sans-serif; color: #08645f; font-variant-numeric: tabular-nums; direction: ltr; }
@keyframes load-pill-in { from { opacity: 0; transform: scale(.8); } }
</style>
"""


def render_progress_pill(rerun_when_ready=False):
    """Small progress ring (bottom corner) while the rest of the search engine loads."""
    if warmup.is_ready() or warmup.failed.is_set():
        return
    _progress_pill(rerun_when_ready)


@st.fragment(run_every=1)
def _progress_pill(rerun_when_ready):
    if warmup.is_ready() or warmup.failed.is_set():
        if rerun_when_ready:
            st.rerun()  # e.g. the chat page enables its input
        return
    percent = warmup.progress()
    circumference = 2 * 3.14159 * 20
    st.markdown(
        _PILL_CSS
        + f'<div class="load-pill" role="progressbar" aria-label="טעינת מנוע החיפוש" aria-valuenow="{percent}" '
        f'aria-valuemin="0" aria-valuemax="100"><svg viewBox="0 0 44 44" aria-hidden="true">'
        f'<circle class="track" cx="22" cy="22" r="20"/><circle class="fill" cx="22" cy="22" r="20" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{circumference * (1 - percent / 100):.1f}"/>'
        f"</svg><span>{percent}%</span></div>",
        unsafe_allow_html=True,
    )
