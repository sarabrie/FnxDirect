import chromadb

# 1. טעינת מסד הנתונים הקיים
chroma_client = chromadb.PersistentClient(path="./fnx_db")
collection = chroma_client.get_collection(name="fnx_website_chunks")

# 2. בדיקת מספר הנתונים הכולל שנשמרו
count = collection.count()
print(f"סך הכל קטעים שנשמרו במסד הנתונים: {count}")

# 3. שליפת הצצה לכמה קטעים ראשונים כדי לוודא את תוכנם והמקור שלהם
sample_data = collection.peek(limit=3)

print("\nהצצה לנתונים הראשונים במסד:")
for i in range(len(sample_data['documents'])):
    print(f"\n[פריט {i+1}]")
    print(f"מקור (URL): {sample_data['metadatas'][i].get('url')}")
    print(f"כותרת: {sample_data['metadatas'][i].get('title')}")
    print(f"תוכן חלקי: {sample_data['documents'][i][:150]}...")