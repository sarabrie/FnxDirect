from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

DB_PATH = str(Path(__file__).resolve().parent / "fnx_db")


def main():
    # 1. טעינת מסד הנתונים הקיים
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    collection = chroma_client.get_collection(
        name="fnx_website_chunks_multilingual",
        embedding_function=SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )

    # 2. בדיקת מספר הנתונים הכולל שנשמרו
    count = collection.count()
    print(f"סך הכל קטעים שנשמרו במסד הנתונים: {count}")

    # 3. שליפת הצצה לכמה קטעים ראשונים כדי לוודא את תוכנם והמקור שלהם
    sample_data = collection.peek(limit=3)

    print("\nהצצה לנתונים הראשונים במסד:")
    for i in range(len(sample_data["documents"])):
        print(f"\n[פריט {i+1}]")
        print(f"מקור (URL): {sample_data['metadatas'][i].get('url')}")
        print(f"כותרת: {sample_data['metadatas'][i].get('title')}")
        print(f"תוכן חלקי: {sample_data['documents'][i][:150]}...")


if __name__ == "__main__":
    main()