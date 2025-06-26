# src/knowledge_base.py
import os
import sqlite3
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import pandas as pd
from docx import Document as DocxDocument # To avoid conflict with Document class in other libraries
from pypdf import PdfReader
import re
import yaml
from sentence_transformers import SentenceTransformer

class KnowledgeBase:
    def __init__(self, config_path="config/config.yaml"):
        self.config = self._load_config(config_path)
        kb_config = self.config['knowledge_base']
        
        self.db_path = kb_config['db_path']
        self.vector_store_type = kb_config['vector_store_type']
        self.chromadb_path = kb_config['chromadb_path']
        self.embedding_model_name = kb_config['embedding_model']
        self.chunk_size = kb_config['chunk_size']
        self.chunk_overlap = kb_config['chunk_overlap']

        self.embedding_function = self._get_embedding_function()
        
        self._init_sqlite_db()
        self._init_vector_store()

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _get_embedding_function(self):
        # Using SentenceTransformer for embeddings
        # This will download the model if not already present
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model_name
        )

    def _init_sqlite_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table for structured facts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                metadata TEXT, -- JSON string of metadata
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table for document metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                path TEXT NOT NULL,
                num_chunks INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print(f"SQLite DB initialized at {self.db_path}")

    def _init_vector_store(self):
        if self.vector_store_type == "chromadb":
            os.makedirs(self.chromadb_path, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.chromadb_path)
            self.collection = self.chroma_client.get_or_create_collection(
                name="autobot_knowledge",
                embedding_function=self.embedding_function
            )
            print(f"ChromaDB initialized at {self.chromadb_path}")
        elif self.vector_store_type == "faiss":
            # FAISS integration would require more setup (e.g., storing index on disk)
            # For now, this is a placeholder.
            print("FAISS integration not fully implemented. Using ChromaDB as default.")
            # Fallback to ChromaDB if FAISS is selected but not fully implemented
            os.makedirs(self.chromadb_path, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.chromadb_path)
            self.collection = self.chroma_client.get_or_create_collection(
                name="autobot_knowledge",
                embedding_function=self.embedding_function
            )
        else:
            raise ValueError(f"Unsupported vector store type: {self.vector_store_type}")

    def _load_document(self, file_path: str, file_type: str) -> str:
        content = ""
        if file_type == "txt":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif file_type == "pdf":
            reader = PdfReader(file_path)
            for page in reader.pages:
                content += page.extract_text() + "\n"
        elif file_type == "csv":
            df = pd.read_csv(file_path)
            content = df.to_string() # Convert DataFrame to string representation
        elif file_type == "docx":
            doc = DocxDocument(file_path)
            for para in doc.paragraphs:
                content += para.text + "\n"
        else:
            raise ValueError(f"Unsupported file type for loading: {file_type}")
        return content

    def _split_text(self, text: str) -> List[str]:
        # Simple text splitting by paragraphs/lines, then by chunk size
        # A more advanced splitter (e.g., Langchain's RecursiveCharacterTextSplitter) could be used
        paragraphs = re.split(r'\n\s*\n', text) # Split by double newlines (paragraphs)
        chunks = []
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) + 1 <= self.chunk_size:
                current_chunk += (para + "\n")
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    def add_file(self, file_path: str, file_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Processes a file, extracts text, chunks it, embeds it, and stores in vector store.
        Also stores file metadata in SQLite.
        """
        try:
            content = self._load_document(file_path, file_type)
            chunks = self._split_text(content)
            
            if not chunks:
                return {"status": "error", "message": "No content extracted or chunks generated."}

            # Store document metadata in SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents (filename, file_type, path, num_chunks) VALUES (?, ?, ?, ?)",
                (os.path.basename(file_path), file_type, file_path, len(chunks))
            )
            doc_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Prepare data for ChromaDB
            documents = []
            metadatas = []
            ids = []
            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                chunk_metadata = {
                    "doc_id": doc_id,
                    "filename": os.path.basename(file_path),
                    "file_type": file_type,
                    "chunk_index": i,
                    **(metadata if metadata else {}) # Add custom metadata if provided
                }
                metadatas.append(chunk_metadata)
                ids.append(f"doc_{doc_id}_chunk_{i}")
            
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Added {len(chunks)} chunks from {file_path} to ChromaDB.")
            return {"status": "success", "message": f"File '{file_path}' processed and added to KB.", "doc_id": doc_id, "num_chunks": len(chunks)}
        except Exception as e:
            print(f"Error adding file {file_path} to KB: {e}")
            return {"status": "error", "message": f"Error adding file to KB: {e}"}

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Searches the vector store for relevant information based on a query.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            retrieved_info = []
            if results and results['documents']:
                for i in range(len(results['documents'][0])):
                    retrieved_info.append({
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i]
                    })
            print(f"Found {len(retrieved_info)} relevant chunks for query: '{query}'")
            return retrieved_info
        except Exception as e:
            print(f"Error searching knowledge base: {e}")
            return []

    def store_fact(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Stores a structured fact in the SQLite database.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            cursor.execute(
                "INSERT INTO facts (content, metadata) VALUES (?, ?)",
                (content, metadata_json)
            )
            fact_id = cursor.lastrowid
            conn.commit()
            print(f"Fact stored with ID: {fact_id}")
            return {"status": "success", "message": "Fact stored successfully.", "fact_id": fact_id}
        except Exception as e:
            print(f"Error storing fact: {e}")
            return {"status": "error", "message": f"Error storing fact: {e}"}
        finally:
            conn.close()

    def get_fact(self, fact_id: Optional[int] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves facts from the SQLite database by ID or by searching content.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        facts = []
        try:
            if fact_id:
                cursor.execute("SELECT id, content, metadata, timestamp FROM facts WHERE id = ?", (fact_id,))
            elif query:
                cursor.execute("SELECT id, content, metadata, timestamp FROM facts WHERE content LIKE ?", (f"%{query}%",))
            else:
                cursor.execute("SELECT id, content, metadata, timestamp FROM facts")
            
            rows = cursor.fetchall()
            for row in rows:
                fact = {
                    "id": row[0],
                    "content": row[1],
                    "metadata": json.loads(row[2]) if row[2] else {},
                    "timestamp": row[3]
                }
                facts.append(fact)
            print(f"Retrieved {len(facts)} facts.")
            return facts
        except Exception as e:
            print(f"Error retrieving facts: {e}")
            return []
        finally:
            conn.close()

# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        print("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    # Create dummy files for testing
    os.makedirs("data/test_files", exist_ok=True)
    with open("data/test_files/example.txt", "w") as f:
        f.write("This is a test document about artificial intelligence. AI is a rapidly evolving field.")
    
    # Create a dummy PDF (requires a PDF writer, or just use a simple one)
    # For simplicity, we'll just create a dummy file and assume it's a PDF for testing purposes
    # In a real scenario, you'd need a proper PDF file.
    with open("data/test_files/dummy.pdf", "w") as f:
        f.write("This is a dummy PDF content. It talks about machine learning.")

    # Create a dummy CSV
    pd.DataFrame({'col1': [1, 2], 'col2': ['A', 'B']}).to_csv("data/test_files/data.csv", index=False)

    # Create a dummy DOCX
    doc = DocxDocument()
    doc.add_paragraph("This is a sample DOCX document. It contains some important information.")
    doc.save("data/test_files/sample.docx")

    kb = KnowledgeBase()

    print("\n--- Testing add_file ---")
    kb.add_file("data/test_files/example.txt", "txt")
    kb.add_file("data/test_files/dummy.pdf", "pdf") # This will likely fail if not a real PDF
    kb.add_file("data/test_files/data.csv", "csv")
    kb.add_file("data/test_files/sample.docx", "docx")

    print("\n--- Testing store_fact ---")
    kb.store_fact("The capital of France is Paris.", {"source": "manual_entry"})
    kb.store_fact("Python is a programming language.", {"category": "programming"})

    print("\n--- Testing get_fact ---")
    print("All facts:")
    print(kb.get_fact())
    print("Fact with ID 1:")
    print(kb.get_fact(fact_id=1))
    print("Facts containing 'programming':")
    print(kb.get_fact(query="programming"))

    print("\n--- Testing search (vector store) ---")
    search_results = kb.search("What is AI?")
    for res in search_results:
        print(f"Content: {res['content']}\nMetadata: {res['metadata']}\nDistance: {res['distance']}\n---")

    # Clean up dummy files
    # os.remove("data/test_files/example.txt")
    # os.remove("data/test_files/dummy.pdf")
    # os.remove("data/test_files/data.csv")
    # os.remove("data/test_files/sample.docx")
    # os.rmdir("data/test_files")
    # os.remove(kb.db_path)
    # import shutil
    # shutil.rmtree(kb.chromadb_path)
