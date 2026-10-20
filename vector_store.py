from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

DB_PATH = str(Path(__file__).resolve().parent / "fnx_db")
_collection = None


def get_collection():
    """
    אתחול עצל (Lazy) של מסד הנתונים ומודל ההטמעה, כדי למנוע טעינה כבדה בעת ייבוא
    """
    global _collection
    if _collection is None:
        print("טוען את מודל ההטמעה...")
        embedding_function = SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        chroma_client = chromadb.PersistentClient(path=DB_PATH)
        _collection = chroma_client.get_or_create_collection(
            name="fnx_website_chunks_multilingual",
            embedding_function=embedding_function,
        )
    return _collection


def __getattr__(name):
    if name == "collection":
        return get_collection()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def save_chunks_to_chroma(chunks_with_metadata):
    """
    מקבל רשימה של קטעים עם המטא-דאטה שלהם ושומר אותם במסד הווקטורי
    """
    documents = []
    metadatas = []
    ids = []

    for item in chunks_with_metadata:
        documents.append(item["text"])
        metadatas.append({
            "url": item["metadata"]["url"],
            "title": item["metadata"]["title"]
        })
        ids.append(item["metadata"]["chunk_id"])

    print("מעבד וקטורים ושומר במסד הנתונים...")
    
    # הוספת הנתונים למסד הווקטורי (Chroma מייצר את הוקטורים אוטומטית או שנקדד ידנית)
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    
    print(f"נוספו בהצלחה {len(documents)} קטעים למסד הווקטורי!")

# דוגמה לאיך מריצים חיפוש בדיקה אחרי שהנתונים נשמרו:
def search_knowledge_base(query_text, n_results=5):
    """
    פונקציה שמחפשת את הקטעים הרלוונטיים ביותר לשאלה של המשתמש
    """
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    return results