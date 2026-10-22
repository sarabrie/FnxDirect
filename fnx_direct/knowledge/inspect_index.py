"""
Developer tool for the ChromaDB index.
    python -m fnx_direct.knowledge.inspect_index              # chunk count + a peek at the first chunks
    python -m fnx_direct.knowledge.inspect_index "<question>" # the 5 chunks closest to a question
"""
import sys

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from fnx_direct.config import COLLECTION_NAME, EMBEDDING_MODEL, VECTOR_DB_PATH


def _open_collection():
    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL),
    )


def show_summary(collection, sample_size=3):
    print(f"סך הכל קטעים שנשמרו במסד הנתונים: {collection.count()}")
    sample = collection.peek(limit=sample_size)
    print("\nהצצה לנתונים הראשונים במסד:")
    for i, (document, metadata) in enumerate(zip(sample["documents"], sample["metadatas"]), 1):
        print(f"\n[פריט {i}]")
        print(f"מקור (URL): {metadata.get('url')}")
        print(f"כותרת: {metadata.get('title')}")
        print(f"תוכן חלקי: {document[:150]}...")


def search(collection, question, n_results=5):
    print(f"\n--- מחפש תשובה לשאלה: '{question}' ---")
    results = collection.query(query_texts=[question], n_results=n_results)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    if not documents:
        print("לא נמצא מידע רלוונטי באתר.")
        return
    print("\nהנה הקטעים שנמצאו באתר הפניקס:")
    for i, (document, metadata) in enumerate(zip(documents, metadatas), 1):
        print(f"\n[קטע {i}]")
        print(f"תוכן: {document}")
        print(f"מקור (URL): {metadata.get('url', 'לא ידוע')}")


if __name__ == "__main__":
    index = _open_collection()
    if len(sys.argv) > 1:
        search(index, " ".join(sys.argv[1:]))
    else:
        show_summary(index)
