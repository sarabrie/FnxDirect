import os
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
import chromadb
from google import genai

load_dotenv()

# 1. טעינת מסד הנתונים הווקטורי
chroma_client = chromadb.PersistentClient(path="./fnx_db")
collection = chroma_client.get_collection(name="fnx_website_chunks")

# 2. אתחול לקוח ה-AI
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise RuntimeError("חסר GEMINI_API_KEY. הגדירי אותו בקובץ .env.")
client = genai.Client(api_key=gemini_api_key)
def generate_rag_response(question):
    print(f"\n--- מעבד שאלה: '{question}' ---")
    
    # שליפת 3 הקטעים הרלוונטיים ביותר
    results = collection.query(
        query_texts=[question],
        n_results=3
    )
    
    documents = results.get('documents', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]
    
    if not documents:
        print("תשובה: זה לא כתוב באתר הפניקס.")
        return

    # בניית ההקשר (Context) מתוך ה-Chunks שנשלפו
    context_text = ""
    sources = set()
    for doc, meta in zip(documents, metadatas):
        context_text += f"- {doc}\n"
        if meta.get('url'):
            sources.add(meta.get('url'))

    # פרומפט קשיח למניעת הזיות וחיוב ציטוט מקור
    prompt = f"""
אתה עוזר וירטואלי של חברת הפניקס.
ענה על השאלה הבאה **אך ורק** על סמך המידע המצורף בהקשר להלן.
אם המידע אינו מופיע במפורש בהקשר, ענה בדיוק: "זה לא כתוב באתר הפניקס."
אל תמציא מידע מחוץ להקשר המסופק.
אם ענית על בסיס המידע, צרף בסוף התשובה את כתובת המקור.

הקשר מתוך האתר:
{context_text}

שאלה: {question}
"""

    # קריאה למודל השפה
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
    )

    print("\n--- תשובת הבוט ---")
    print(response.text)
    if sources and "זה לא כתוב באתר" not in response.text:
        print("\nמקורות:")
        for url in sources:
            print(f"- {url}")

if __name__ == "__main__":
    # שאלה ראשונה
    generate_rag_response("איך מגישים תביעה על נזקי מים?")
    
    # שאלה שנייה
    generate_rag_response("אילו חדשות יש באפליקציית הפניקס לגבי השקעות?")