"""
Maritime RAG System
Query ship tracking data using natural language

Demonstrates:
1. RAG (Retrieval Augmented Generation) fundamentals
2. Geospatial data handling
3. Time-series queries
4. Anomaly detection context
"""

import os
import json
from dotenv import load_dotenv

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

load_dotenv()

# Use Gemini 2.5 Flash as per user preferences
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def load_documents(filepath="maritime_documents.json"):
    """Load maritime documents for RAG"""
    with open(filepath, "r") as f:
        docs = json.load(f)
    return docs


def create_vector_store(documents):
    """Create ChromaDB vector store from documents"""

    # Initialize Gemini embeddings
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=GOOGLE_API_KEY
    )

    # Extract texts and metadata
    texts = [doc["content"] for doc in documents]
    metadatas = [doc["metadata"] for doc in documents]

    # Create vector store
    vector_store = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory="./chroma_db"
    )

    print(f"Created vector store with {len(texts)} documents")
    return vector_store


def create_rag_chain(vector_store):
    """Create RAG chain for maritime queries"""

    # Initialize Gemini 2.5 Flash
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GOOGLE_API_KEY,
        temperature=0.1
    )

    # Custom prompt for maritime domain
    prompt_template = """You are a Maritime Domain Awareness AI assistant for the Indian Navy.
You analyze ship tracking (AIS) data to provide insights about vessel movements, detect anomalies, and answer queries about maritime activity.

Use the following context from our maritime database to answer the question.
If you don't know the answer based on the context, say so clearly.

Context:
{context}

Question: {question}

Provide a clear, concise answer. If relevant, mention:
- Ship names and MMSI numbers
- Locations (coordinates or port names)
- Any anomalies or suspicious behavior
- Relevant timestamps

Answer:"""

    PROMPT = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # Create retrieval chain
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_store.as_retriever(search_kwargs={"k": 5}),
        chain_type_kwargs={"prompt": PROMPT},
        return_source_documents=True
    )

    return qa_chain


def query_maritime_data(qa_chain, question):
    """Query the maritime RAG system"""
    result = qa_chain({"query": question})

    print("\n" + "="*60)
    print(f"Question: {question}")
    print("="*60)
    print(f"\nAnswer: {result['result']}")

    print("\n--- Source Documents ---")
    for i, doc in enumerate(result['source_documents'][:3]):
        print(f"\n[{i+1}] {doc.metadata.get('type', 'unknown')}:")
        print(doc.page_content[:200] + "...")

    return result


def main():
    """Main function to run maritime RAG demo"""

    print("="*60)
    print("MARITIME RAG SYSTEM")
    print("Blurgs.ai Interview Prep Demo")
    print("="*60)

    # Check for API key
    if not GOOGLE_API_KEY:
        print("\nERROR: Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable")
        print("Example: set GOOGLE_API_KEY=your_api_key_here")
        return

    # Load documents
    print("\n1. Loading maritime documents...")
    try:
        documents = load_documents()
        print(f"   Loaded {len(documents)} documents")
    except FileNotFoundError:
        print("   Documents not found. Generating sample data first...")
        import sample_ais_data
        sample_ais_data.generate_dataset().to_csv("ais_data.csv", index=False)
        docs = sample_ais_data.create_maritime_documents(sample_ais_data.generate_dataset())
        with open("maritime_documents.json", "w") as f:
            json.dump(docs, f, indent=2)
        documents = docs

    # Create vector store
    print("\n2. Creating vector store (embeddings)...")
    vector_store = create_vector_store(documents)

    # Create RAG chain
    print("\n3. Initializing RAG chain with Gemini 2.5 Flash...")
    qa_chain = create_rag_chain(vector_store)

    # Demo queries
    print("\n4. Running demo queries...")

    demo_questions = [
        "What ships are currently traveling between Mumbai and Singapore?",
        "Are there any anomalies or suspicious vessels detected?",
        "Show me all tanker ships and their current routes",
        "What is the activity near Kochi port?",
        "Which ship has the highest average speed?",
    ]

    for question in demo_questions:
        query_maritime_data(qa_chain, question)
        print("\n")

    # Interactive mode
    print("\n" + "="*60)
    print("INTERACTIVE MODE")
    print("Type your questions about maritime data (or 'quit' to exit)")
    print("="*60)

    while True:
        question = input("\nYour question: ").strip()
        if question.lower() in ['quit', 'exit', 'q']:
            break
        if question:
            query_maritime_data(qa_chain, question)


if __name__ == "__main__":
    main()
