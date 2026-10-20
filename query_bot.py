import os
from pathlib import Path
os.environ["PYTHONIOENCODING"] = "utf-8"

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

DB_PATH = str(Path(__file__).resolve().parent / "fnx_db")
_collection = None


def get_collection():
    global _collection
    if _collection is None:
        print("טוען את מסד הנתונים הווקטורי...")
        chroma_client = chromadb.PersistentClient(path=DB_PATH)
        _collection = chroma_client.get_collection(
            name="fnx_website_chunks_multilingual",
            embedding_function=SentenceTransformerEmbeddingFunction(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            ),
        )
    return _collection


def ask_phoenix_bot(question):
    """
    מקבלת שאלה, מחפשת את הקטעים הרלוונטיים ביותר במסד הנתונים,
    ומציגה את התשובה יחד עם קישור למקור (URL).
    """
    collection = get_collection()
    print(f"\n--- מחפש תשובה לשאלה: '{question}' ---")
    # חיפוש 5 הקטעים הקרובים ביותר לשאלה במסד הנתונים הווקטורי
    results = collection.query(
        query_texts=[question],
        n_results=5
    )

    documents = results.get('documents', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]

    if not documents:
        print("לא נמצא מידע רלוונטי באתר.")
        return

    # הצגת התוצאות והמקורות שנשלפו
    print("\nהנה הקטעים שנמצאו באתר הפניקס:")
    for i, (doc, meta) in enumerate(zip(documents, metadatas), 1):
        print(f"\n[קטע {i}]")
        print(f"תוכן: {doc}")
        print(f"מקור (URL): {meta.get('url', 'לא ידוע')}")


# דוגמה להרצת שאלה לדוגמה
if __name__ == "__main__":
    # אפשר לשנות את השאלה הזו לכל שאלה אחרת
    ask_phoenix_bot("איך מגישים תביעה על נזקי מים?")