import os
os.environ["PYTHONIOENCODING"] = "utf-8"

import chromadb

# 1. טעינת מסד הנתונים הקיים
print("טוען את מסד הנתונים הווקטורי...")
chroma_client = chromadb.PersistentClient(path="./fnx_db")
collection = chroma_client.get_collection(name="fnx_website_chunks")

def ask_phoenix_bot(question):
    """
    מקבלת שאלה, מחפשת את הקטעים הרלוונטיים ביותר במסד הנתונים,
    ומציגה את התשובה יחד עם קישור למקור (URL).
    """
    print(f"\n--- מחפש תשובה לשאלה: '{question}' ---")    
    # חיפוש 3 הקטעים הקרובים ביותר לשאלה במסד הנתונים הווקטורי
    results = collection.query(
        query_texts=[question],
        n_results=3
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