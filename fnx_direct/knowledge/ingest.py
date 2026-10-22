"""
Crawls the Phoenix website pages with Firecrawl, splits them into chunks and upserts them into
the ChromaDB index. Run:  python -m fnx_direct.knowledge.ingest
"""
import os

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from firecrawl import FirecrawlApp
from langchain_text_splitters import RecursiveCharacterTextSplitter

from fnx_direct.config import COLLECTION_NAME, EMBEDDING_MODEL, VECTOR_DB_PATH
from fnx_direct.knowledge.topics import topic_for_url

DEFAULT_TARGET_URLS = [
    "https://www.fnx.co.il/customer-service/",
    "https://www.fnx.co.il/claims-customer-service/",
    "https://www.fnx.co.il/apartment-insurance/",
    "https://www.fnx.co.il/car-insurance/",
    "https://www.fnx.co.il/travel-insurance/",
]

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100


def _open_collection():
    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL),
    )


def _scrape(app, url, splitter):
    """Returns {"title", "chunks"} for one page, or None if it came back empty."""
    result = app.scrape_url(url, formats=["markdown"])
    if isinstance(result, dict):
        markdown = result.get("markdown", "")
        metadata = result.get("metadata", {})
    else:
        markdown = getattr(result, "markdown", "")
        metadata = getattr(result, "metadata", {})
    if not markdown:
        return None
    title = metadata.get("title", "הפניקס") if isinstance(metadata, dict) else getattr(metadata, "title", "הפניקס")
    return {"title": str(title), "chunks": splitter.split_text(markdown)}


def _replace_page_chunks(collection, url, page):
    """Upserts the page's chunks and removes chunks left over from an older, longer version."""
    documents = [str(chunk) for chunk in page["chunks"]]
    metadatas = [{"url": url, "title": page["title"], "topic": topic_for_url(url)} for _ in documents]
    ids = [f"{url}#chunk_{i}" for i in range(len(documents))]

    existing = collection.get(where={"url": url}, include=["metadatas"])
    stale_ids = [chunk_id for chunk_id in existing["ids"] if chunk_id not in ids]

    collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    if stale_ids:
        collection.delete(ids=stale_ids)


def run_pipeline(target_urls=None):
    target_urls = target_urls or DEFAULT_TARGET_URLS

    api_key = os.getenv("FIRE_CRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("חסר FIRE_CRAWL_API_KEY. הגדירו אותו בקובץ .env לפני הרצת הסריקה.")

    print("1. אתחול הכלים (Firecrawl ו-ChromaDB)...")
    app = FirecrawlApp(api_key=api_key)
    collection = _open_collection()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )

    print("\n2. מתחיל בסריקת עמודי המפתח של הפניקס...")
    pages = {}
    for url in target_urls:
        try:
            page = _scrape(app, url, splitter)
        except Exception as error:
            print(f"שגיאה בסריקת העמוד {url}: {error}")
            continue
        if page is None:
            print(f"-> העמוד {url} חזר ריק או ללא תוכן markdown.")
            continue
        pages[url] = page
        print(f"-> נסרק בהצלחה ונוצרו {len(page['chunks'])} קטעים עבור: {url}")

    if not pages:
        print("לא נמצאו עמודים לסריקה. מסד הנתונים הקיים לא שונה.")
        return

    total_chunks = sum(len(page["chunks"]) for page in pages.values())
    print(f"\nסך הכל נוצרו {total_chunks} קטעים. מתחיל בעדכון מסד הנתונים הווקטורי...")
    for url, page in pages.items():
        _replace_page_chunks(collection, url, page)
    print(f"\n3. הצלחה! {total_chunks} קטעים מ-{len(pages)} עמודים עודכנו ב-ChromaDB.")


if __name__ == "__main__":
    run_pipeline()
