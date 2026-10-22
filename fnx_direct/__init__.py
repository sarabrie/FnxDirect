"""
FNX Direct — a RAG assistant that answers questions from the Phoenix (הפניקס) website.

Packages:
    knowledge  website topics, crawling and indexing into ChromaDB
    search     the search-engine process (embedding model + ChromaDB) and its client
    assistant  retrieval, prompt building and answer streaming with Gemini
    history    conversations, messages, feedback and the answer cache (SQLite)
    auth       accounts, tokens, Google OAuth and per-user preferences (SQLite)
    ui         Streamlit pages, components and static assets

Keep this file free of imports: the search worker process imports the package too.
"""
