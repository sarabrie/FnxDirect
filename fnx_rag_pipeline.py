import os
# הגדרת קידוד סביבתי למניעת שגיאות תווים
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb

load_dotenv()

# 1. טעינת מפתח Firecrawl ממשתנה סביבה
FIRE_CRAWL_API_KEY = os.getenv("FIRE_CRAWL_API_KEY")
if not FIRE_CRAWL_API_KEY:
    raise RuntimeError("חסר FIRE_CRAWL_API_KEY. הגדירי אותו בקובץ .env.")

print("1. אתחול הכלים (Firecrawl ו-ChromaDB)...")
app = FirecrawlApp(api_key=FIRE_CRAWL_API_KEY)

# אתחול מסד הנתונים הווקטורי ChromaDB (יישמר בתיקייה מקומית בשם fnx_db)
chroma_client = chromadb.PersistentClient(path="./fnx_db")
collection = chroma_client.get_or_create_collection(name="fnx_website_chunks")

# רשימת כתובות הליבה הציבוריות באתר הפניקס
target_urls = [
    "https://www.fnx.co.il/",
    "https://www.fnx.co.il/claims",
    "https://www.fnx.co.il/insurance/home",
    "https://www.fnx.co.il/insurance/car",
    "https://www.fnx.co.il/insurance/travel"
]

all_chunks = []

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
        source_url = metadata.get('sourceURL') or metadata.get('url') or url if isinstance(metadata, dict) else url
        
        if markdown_content:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=600,
                chunk_overlap=100,
                separators=["\n\n", "\n", " ", ""]
            )
            
            chunks = text_splitter.split_text(markdown_content)
            
            for i, chunk in enumerate(chunks):
                all_chunks.append({
                    "text": chunk,
                    "metadata": {
                        "url": str(source_url),
                        "title": str(title),
                        "chunk_id": f"{source_url}#chunk_{i}"
                    }
                })
            print(f"-> נסרק בהצלחה ונוצרו {len(chunks)} קטעים עבור: {url}")
        else:
            print(f"-> העמוד {url} חזר ריק או ללא תוכן markdown.")
            
    except Exception as e:
        print(f"שגיאה בסריקת העמוד {url}: {e}")

print(f"\nסך הכל נוצרו {len(all_chunks)} קטעים. מתחיל בשמירה במסד הווקטורי...")

# 3. הכנסת ה-Chunks לתוך ChromaDB
if all_chunks:
    documents = []
    metadatas = []
    ids = []

    for item in all_chunks:
        documents.append(str(item["text"]))
        metadatas.append({
            "url": str(item["metadata"]["url"]),
            "title": str(item["metadata"]["title"])
        })
        ids.append(str(item["metadata"]["chunk_id"]))

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    print(f"\n3. הצלחה! כל {len(documents)} הקטעים נשמרו ונאנדקסו ב-ChromaDB בהצלחה.")
else:
    print("לא נמצאו קטעים לשמירה. בדקי את מפתח ה-API או את כתובות האתר.")