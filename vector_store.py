import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# 1. טעינת מודל ההטמעה (Embedding Model) שמתרגם טקסט לווקטורים
# אנחנו משתמשים במודל קוד פתוח מעולה מבית HuggingFace
print("טוען את מודל ההטמעה...")
embedding_function = SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# 2. אתחול מסד הנתונים הווקטורי ChromaDB (נשמר באופן מקומי בתיקייה בשם fnx_db)
chroma_client = chromadb.PersistentClient(path="./fnx_db")
collection = chroma_client.get_or_create_collection(
    name="fnx_website_chunks_multilingual",
    embedding_function=embedding_function,
)

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