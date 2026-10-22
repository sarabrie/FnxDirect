import os
# הגדרת קידוד סביבתי למניעת שגיאות תווים
os.environ["PYTHONIOENCODING"] = "utf-8"

from pathlib import Path
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from topics import topic_for_url

load_dotenv()

DB_PATH = str(Path(__file__).resolve().parent / "fnx_db")

DEFAULT_TARGET_URLS = [
    "https://www.fnx.co.il/customer-service/",
    "https://www.fnx.co.il/claims-customer-service/",
    "https://www.fnx.co.il/apartment-insurance/",
    "https://www.fnx.co.il/car-insurance/",
    "https://www.fnx.co.il/travel-insurance/"
]


def run_pipeline(target_urls=None):
    target_urls = target_urls or DEFAULT_TARGET_URLS

    # 1. טעינת מפתח Firecrawl ממשתנה סביבה
    fire_crawl_api_key = os.getenv("FIRE_CRAWL_API_KEY")
    if not fire_crawl_api_key:
        raise RuntimeError("חסר FIRE_CRAWL_API_KEY. הגדירו אותו בקובץ .env לפני הרצת הסריקה.")

    print("1. אתחול הכלים (Firecrawl ו-ChromaDB)...")
    app = FirecrawlApp(api_key=fire_crawl_api_key)

    # אתחול מסד הנתונים הווקטורי ChromaDB (יישמר בתיקייה מקומית בשם fnx_db)
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    collection = chroma_client.get_or_create_collection(
        name="fnx_website_chunks_multilingual",
        embedding_function=SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )

    successful_pages = {}
    print("\n2. מתחיל בסריקת עמודי המפתח של הפניקס...")

    for url in target_urls:
        try:
            # קריאת סריקה ממוקדת לעמוד
            scrape_result = app.scrape_url(url, formats=['markdown'])

            # חילוץ בטוח של התוכן
            if isinstance(scrape_result, dict):
                markdown_content = scrape_result.get('markdown', '')
                metadata = scrape_result.get('metadata', {})
            else:
                markdown_content = getattr(scrape_result, 'markdown', '')
                metadata = getattr(scrape_result, 'metadata', {})

            title = metadata.get('title', 'הפניקס') if isinstance(metadata, dict) else getattr(metadata, 'title', 'הפניקס')

            if markdown_content:
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=600,
                    chunk_overlap=100,
                    separators=["\n\n", "\n", " ", ""]
                )

                chunks = text_splitter.split_text(markdown_content)

                successful_pages[url] = {
                    "title": str(title),
                    "chunks": chunks,
                }
                print(f"-> נסרק בהצלחה ונוצרו {len(chunks)} קטעים עבור: {url}")
            else:
                print(f"-> העמוד {url} חזר ריק או ללא תוכן markdown.")

        except Exception as e:
            print(f"שגיאה בסריקת העמוד {url}: {e}")

    total_chunks = sum(len(page["chunks"]) for page in successful_pages.values())
    print(f"\nסך הכל נוצרו {total_chunks} קטעים. מתחיל בעדכון מסד הנתונים הווקטורי...")

    # 3. עדכון כל עמוד שנסרק בהצלחה וניקוי הקטעים הישנים שנותרו ממנו
    if successful_pages:
        for url, page in successful_pages.items():
            documents = [str(chunk) for chunk in page["chunks"]]
            metadatas = [
                {"url": url, "title": page["title"], "topic": topic_for_url(url)}
                for _ in documents
            ]
            ids = [f"{url}#chunk_{i}" for i in range(len(documents))]

            existing = collection.get(where={"url": url}, include=["metadatas"])
            stale_ids = [chunk_id for chunk_id in existing["ids"] if chunk_id not in ids]

            collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            if stale_ids:
                collection.delete(ids=stale_ids)

        print(f"\n3. הצלחה! {total_chunks} קטעים מ-{len(successful_pages)} עמודים עודכנו ב-ChromaDB.")
    else:
        print("לא נמצאו עמודים לסריקה. מסד הנתונים הקיים לא שונה.")


if __name__ == "__main__":
    run_pipeline()