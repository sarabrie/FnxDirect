"""The instructions sent to Gemini, built from the retrieved context and the user's preferences."""

NOT_FOUND_ANSWER = "זה לא כתוב באתר הפניקס."

_LENGTH_INSTRUCTIONS = {
    "short": "ענה בקצרה ובתמציתיות, עד 3 משפטים.",
    "standard": "ענה בפסקה-שתיים סטנדרטיות.",
    "detailed": "ענה באופן מפורט ומעמיק, כולל נקודות ודוגמאות במידת הצורך.",
}
_TONE_INSTRUCTIONS = {
    "simple": "השתמש בשפה פשוטה ובגובה העיניים, ללא טרמינולוגיה משפטית.",
    "formal": "השתמש בשפה מקצועית ורשמית עם טרמינולוגיה ביטוחית.",
}


def is_not_found(answer):
    """True when the model said the website doesn't cover the question."""
    return "זה לא כתוב באתר" in answer


def build_prompt(question, context_text, user_prefs=None):
    prefs = user_prefs or {}
    preferred_name = prefs.get("preferred_name")
    length_instruction = _LENGTH_INSTRUCTIONS.get(prefs.get("response_length"), _LENGTH_INSTRUCTIONS["standard"])
    tone_instruction = _TONE_INSTRUCTIONS["simple" if prefs.get("tone", "simple") == "simple" else "formal"]
    salutation = f"פנה למשתמש בשם '{preferred_name}'." if preferred_name else ""

    return f"""אתה עוזר וירטואלי של חברת הפניקס.
ענה בעברית ובצורה ברורה, ורק על סמך הקטעים המצורפים.
{salutation}
{length_instruction}
{tone_instruction}
בדוק את כל הקטעים לפני המענה. מידע עשוי להופיע תחת כותרת אחרת או בניסוח שונה מהשאלה.
אם קטע עונה על חלק מהשאלה, מסור את המידע הנתמך וציין אילו פרטים אינם מופיעים.
אל תוסיף עובדות שאינן מופיעות בקטעים. אם אף קטע אינו מכיל מידע רלוונטי, ענה בדיוק: "{NOT_FOUND_ANSWER}"
בסוף התשובה, הוסף עד 3 הצעות המשך קצרות ומזמינות, בנושאים שונים שאפשר לענות עליהם מתוך הקטעים המצורפים. נסח כל הצעה כהזמנה, למשל: "רוצה לדעת גם איך מגישים תביעה?", ולא כשאלת מידע ישירה. הצע רק נושאים שיש עליהם מידע נוסף בקטעים; אם יש רק נושא אחד רלוונטי, הצע רק אותו. כתוב כל הצעה בנפרד ובפורמט המדויק [FOLLOW_UP]רוצה לדעת גם...?[/FOLLOW_UP], אחרי התשובה.
המקורות יוצגו בנפרד מהתשובה.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""
