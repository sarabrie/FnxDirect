"""
Topics the knowledge base is split into. Each chunk gets a "topic" metadata field
(derived from its page URL) so a search can be limited to one topic.
Kept free of heavy imports so the UI can use it without loading chromadb.
"""
from urllib.parse import urlsplit

# Customer-service / claims pages apply to every insurance topic, so they are always searched too.
GENERAL_TOPIC = "service"

TOPICS = {
    "car": {
        "label": "ביטוח רכב",
        "icon": ":material/directions_car:",
        "paths": ["car-insurance", "insurance/car"],
        "suggestions": [
            "מה כולל ביטוח מקיף לרכב?",
            "איך מדווחים על תאונת דרכים?",
            "מה ההבדל בין ביטוח חובה לביטוח צד ג'?",
        ],
    },
    "apartment": {
        "label": "ביטוח דירה",
        "icon": ":material/home:",
        "paths": ["apartment-insurance", "insurance/home"],
        "suggestions": [
            "מה כולל ביטוח דירה?",
            "איך מגישים תביעה על נזקי מים?",
            "האם ביטוח תכולה מכסה גניבה?",
        ],
    },
    "travel": {
        "label": "ביטוח נסיעות",
        "icon": ":material/flight:",
        "paths": ["travel-insurance", "insurance/travel"],
        "suggestions": [
            'מה כולל ביטוח נסיעות לחו"ל?',
            "האם הביטוח מכסה ביטול טיסה?",
            "איך מקבלים עזרה רפואית בחו\"ל?",
        ],
    },
    GENERAL_TOPIC: {
        "label": "שירות ותביעות",
        "icon": ":material/support_agent:",
        "paths": ["customer-service", "claims-customer-service"],
        "suggestions": [
            "איך יוצרים קשר עם הפניקס?",
            "איך בודקים סטטוס של תביעה?",
            "מה שעות הפעילות של מוקד השירות?",
        ],
    },
}

DEFAULT_SUGGESTIONS = [
    "איך מגישים תביעה על נזקי מים?",
    'מה כולל ביטוח נסיעות לחו"ל?',
    "איך יוצרים קשר עם הפניקס?",
]


def topic_for_url(url):
    if not isinstance(url, str):
        return GENERAL_TOPIC
    try:
        path = urlsplit(url).path.strip("/").lower()
    except ValueError:
        return GENERAL_TOPIC
    for topic, info in TOPICS.items():
        if any(path == prefix or path.startswith(prefix + "/") for prefix in info["paths"]):
            return topic
    return GENERAL_TOPIC


def topic_filter(topic):
    """Chroma `where` clause for a topic, or None to search everything."""
    if topic not in TOPICS:
        return None
    if topic == GENERAL_TOPIC:
        return {"topic": GENERAL_TOPIC}
    return {"topic": {"$in": [topic, GENERAL_TOPIC]}}
