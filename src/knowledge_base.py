# src/knowledge_base.py
import os
import logging
import json
import yaml
from typing import List, Dict, Any, Optional, cast
import asyncio # Import asyncio for async operations

# LlamaIndex imports
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.storage_context import StorageContext
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.core import ServiceContext, Settings

# Redis client for direct interaction (e.g., for chat history, logs)
import redis.asyncio as redis # Use async Redis client
from redis.asyncio import Redis # Explicitly import Redis client type

# Imports for file loading
import pandas as pd
from docx import Document as DocxDocument
from pypdf import PdfReader

class KnowledgeBase:
    def __init__(self, config_path="config/config.yaml"):
        self.config_path = os.path.abspath(config_path)
        self.config = self._load_config(config_path)

        # Correctly access llm_config
        self.llm_config_data = self.config.get('llm_config', {})

        # Construct kb_config from existing config structure
        # Assuming knowledge base related settings are under 'memory' or top-level
        self.network_share_path = self.config.get('network_share_path') # Assuming this might be a top-level key
        self.network_username = self.config.get('network_username', os.getenv('NETWORK_SHARE_USERNAME'))
        self.network_password = self.config.get('network_password', os.getenv('NETWORK_SHARE_PASSWORD'))

        # Default values for LlamaIndex specific settings, as they are not explicitly in config.yaml
        # These should ideally be in a 'knowledge_base' section in config.yaml
        self.vector_store_type = "redis" # Hardcoding as per current setup
        self.embedding_model_name = self.llm_config_data.get('ollama', {}).get('models', {}).get('tinyllama', 'tinyllama:latest') # Use a default or specific embedding model
        self.chunk_size = 512 # Default value
        self.chunk_overlap = 20 # Default value

        # Redis configuration from 'memory' section
        redis_memory_config = self.config.get('memory', {}).get('redis', {})
        self.redis_host = redis_memory_config.get('host', 'localhost')
        self.redis_port = redis_memory_config.get('port', 6379)
        self.redis_password = redis_memory_config.get('password', os.getenv('REDIS_PASSWORD'))
        self.redis_db = redis_memory_config.get('db', 0)
        self.redis_index_name = redis_memory_config.get('index_name', 'autobot_knowledge_index') # Add index_name to redis config if not present

        # Initialize Redis client for direct use (e.g., for facts/logs if not via LlamaIndex)
        self.redis_client: Redis = cast(Redis, redis.Redis( # Explicitly cast to Redis from redis.asyncio
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            db=self.redis_db,
            decode_responses=True # Decode responses to Python strings
        ))
        logging.info(f"Redis client initialized for host: {self.redis_host}:{self.redis_port}")

        # LlamaIndex components will be initialized in an async method
        self.llm = None
        self.embed_model = None
        self.vector_store = None
        self.storage_context = None
        self.index = None
        self.query_engine = None

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _resolve_path(self, configured_path: str) -> str:
        """Resolves the final path by potentially prepending the network share path."""
        if self.network_share_path and not os.path.isabs(configured_path):
            return os.path.join(self.network_share_path, configured_path)
        return configured_path

    async def ainit(self, llm_config: Dict[str, Any]):
        """
        Asynchronously initializes LlamaIndex components including LLM, Embedding model, and Vector Store.
        This method should be called after the KnowledgeBase object is created.
        """
        # Configure LLM for LlamaIndex
        llm_provider = llm_config.get('provider', 'ollama')
        llm_model = llm_config.get('model', 'llama2') # Default to llama2 for Ollama
        llm_base_url = llm_config.get('base_url', 'http://localhost:11434')

        if llm_provider == 'ollama':
            self.llm = LlamaIndexOllamaLLM(model=llm_model, base_url=llm_base_url)
            self.embed_model = LlamaIndexOllamaEmbedding(model_name=self.embedding_model_name, base_url=llm_base_url)
        else:
            # Placeholder for other LLM providers, e.g., OpenAI, Anthropic
            logging.warning(f"LLM provider '{llm_provider}' not fully implemented for LlamaIndex. Defaulting to Ollama.")
            self.llm = LlamaIndexOllamaLLM(model=llm_model, base_url=llm_base_url)
            self.embed_model = LlamaIndexOllamaEmbedding(model_name=self.embedding_model_name, base_url=llm_base_url)

        # Configure LlamaIndex Settings
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.chunk_size = self.chunk_size
        Settings.chunk_overlap = self.chunk_overlap
        Settings.node_parser = SentenceSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)

        # Initialize Redis Vector Store with proper IndexSchema
        try:
            # Create a schema for the Redis vector store
            schema = RedisVectorStoreSchema(
                index_name=self.redis_index_name,
                prefix="doc",
                overwrite=False
            )
            
            self.vector_store = RedisVectorStore(
                schema=schema,
                redis_url=f"redis://{self.redis_host}:{self.redis_port}",
                password=self.redis_password,
                redis_kwargs={"db": self.redis_db}
            )
            logging.info(f"LlamaIndex RedisVectorStore initialized with index: {self.redis_index_name}")
        except ImportError as e:
            logging.warning(f"Could not import RedisVectorStoreSchema: {e}. Using fallback configuration.")
            # Fallback: temporarily disable vector store to allow startup
            self.vector_store = None
            logging.warning("Redis vector store disabled due to configuration issues.")

        # Initialize StorageContext and VectorStoreIndex
        if self.vector_store is not None:
            self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            # We need to load the index from the vector store if it exists, otherwise create a new one
            try:
                self.index = VectorStoreIndex.from_vector_store(
                    self.vector_store,
                    storage_context=self.storage_context,
                    service_context=ServiceContext.from_defaults(llm=self.llm, embed_model=self.embed_model) # Explicitly pass service_context
                )
                logging.info("LlamaIndex VectorStoreIndex loaded from existing Redis store.")
            except Exception as e:
                logging.warning(f"Could not load existing LlamaIndex from Redis: {e}. Creating a new index.")
                self.index = VectorStoreIndex.from_documents([], storage_context=self.storage_context)
            
            self.query_engine = self.index.as_query_engine(llm=self.llm)
            logging.info("LlamaIndex VectorStoreIndex and QueryEngine initialized.")
        else:
            # Fallback: create a simple in-memory index without Redis
            logging.warning("Creating in-memory VectorStoreIndex without Redis due to initialization issues.")
            self.index = VectorStoreIndex.from_documents([])
            self.query_engine = self.index.as_query_engine(llm=self.llm)
            logging.info("In-memory VectorStoreIndex and QueryEngine initialized.")

    async def add_file(self, file_path: str, file_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Processes a file, extracts text, chunks it, embeds it, and stores in LlamaIndex (Redis).
        """
        if self.index is None:
            logging.error("KnowledgeBase not initialized. Call ainit() first.")
            return {"status": "error", "message": "KnowledgeBase not initialized. Call ainit() first."}
        try:
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
                content = df.to_string()
            elif file_type == "docx":
                doc = DocxDocument(file_path)
                for para in doc.paragraphs:
                    content += para.text + "\n"
            else:
                logging.warning(f"Unsupported file type for direct loading by LlamaIndex: {file_type}. Attempting as generic text.")
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

            doc_metadata = {
                "filename": os.path.basename(file_path),
                "file_type": file_type,
                "original_path": file_path,
                **(metadata if metadata else {})
            }
            document = Document(text=content, metadata=doc_metadata)
            
            self.index.insert(document) # Insert operation is synchronous
            
            logging.info(f"File '{file_path}' processed and added to LlamaIndex (Redis).")
            return {"status": "success", "message": f"File '{file_path}' processed and added to KB."}
        except Exception as e:
            logging.error(f"Error adding file {file_path} to KB: {str(e)}")
            return {"status": "error", "message": f"Error adding file to KB: {str(e)}"}

    async def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Searches the LlamaIndex for relevant information based on a query.
        """
        if self.query_engine is None:
            logging.error("KnowledgeBase not initialized. Call ainit() first.")
            return [] # Return empty list to match signature
        try:
            response = self.query_engine.query(query) # Query operation is synchronous
            
            retrieved_info = []
            for node in response.source_nodes:
                retrieved_info.append({
                    "content": node.text,
                    "metadata": node.metadata,
                    "score": node.score
                })
            logging.info(f"Found {len(retrieved_info)} relevant chunks for query: '{query}'")
            return retrieved_info
        except Exception as e:
            logging.error(f"Error searching knowledge base: {str(e)}")
            return []

    async def store_fact(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Stores a structured fact directly into Redis as a key-value pair or a hash.
        """
        try:
            import time
            fact_id = await self.redis_client.incr('fact_id_counter')
            fact_key = f"fact:{fact_id}"
            fact_data = {
                "content": content,
                "metadata": json.dumps(metadata) if metadata else "{}",
                "timestamp": str(int(time.time()))
            }
            await self.redis_client.hset(fact_key, mapping=fact_data)
            logging.info(f"Fact stored in Redis with ID: {fact_id}")
            return {"status": "success", "message": "Fact stored successfully.", "fact_id": fact_id}
        except Exception as e:
            logging.error(f"Error storing fact in Redis: {str(e)}")
            return {"status": "error", "message": f"Error storing fact: {str(e)}"}

    async def get_fact(self, fact_id: Optional[int] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves facts from Redis by ID or by searching content (simple string match for now).
        """
        facts = []
        try:
            if fact_id:
                fact_data: Dict[str, str] = await self.redis_client.hgetall(f"fact:{fact_id}") # type: ignore
                if fact_data:
                    facts.append({
                        "id": fact_id,
                        "content": fact_data.get("content"),
                        "metadata": json.loads(fact_data.get("metadata", "{}")),
                        "timestamp": fact_data.get("timestamp")
                    })
            elif query:
                all_keys: List[str] = cast(List[str], await self.redis_client.keys("fact:*"))
                for key in all_keys:
                    fact_data: Dict[str, str] = await self.redis_client.hgetall(key) # type: ignore
                    if fact_data and query.lower() in fact_data.get("content", "").lower():
                        facts.append({
                            "id": int(key.split(":")[1]),
                            "content": fact_data.get("content"),
                            "metadata": json.loads(fact_data.get("metadata", "{}")),
                            "timestamp": fact_data.get("timestamp")
                        })
            else:
                all_keys: List[str] = cast(List[str], await self.redis_client.keys("fact:*"))
                for key in all_keys:
                    fact_data: Dict[str, str] = await self.redis_client.hgetall(key) # type: ignore
                    facts.append({
                        "id": int(key.split(":")[1]),
                        "content": fact_data.get("content"),
                        "metadata": json.loads(fact_data.get("metadata", "{}")),
                        "timestamp": fact_data.get("timestamp")
                    })
            logging.info(f"Retrieved {len(facts)} facts from Redis.")
            return facts
        except Exception as e:
            logging.error(f"Error retrieving facts from Redis: {str(e)}")
            return []

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
    import pandas as pd
    pd.DataFrame({'col1': [1, 2], 'col2': ['A', 'B']}).to_csv("data/test_files/data.csv", index=False)

    # Create a dummy DOCX
    from docx import Document as DocxDocument
    doc = DocxDocument()
    doc.add_paragraph("This is a sample DOCX document. It contains some important information.")
    doc.save("data/test_files/sample.docx")

    async def main_test():
        kb = KnowledgeBase()
        # Initialize LlamaIndex components after KnowledgeBase is created
        # Pass the actual llm_config_data from the loaded config
        await kb.ainit(kb.llm_config_data)

        print("\n--- Testing add_file ---")
        add_file_result = await kb.add_file("data/test_files/example.txt", "txt")
        print(add_file_result)
        # await kb.add_file("data/test_files/dummy.pdf", "pdf") # This will likely fail if not a real PDF
        add_file_result = await kb.add_file("data/test_files/data.csv", "csv")
        print(add_file_result)
        add_file_result = await kb.add_file("data/test_files/sample.docx", "docx")
        print(add_file_result)

        print("\n--- Testing store_fact ---")
        store_fact_result = await kb.store_fact("The capital of France is Paris.", {"source": "manual_entry"})
        print(store_fact_result)
        store_fact_result = await kb.store_fact("Python is a programming language.", {"category": "programming"})
        print(store_fact_result)

        print("\n--- Testing get_fact ---")
        print("All facts:")
        print(await kb.get_fact())
        print("Fact with ID 1:")
        print(await kb.get_fact(fact_id=1))
        print("Facts containing 'programming':")
        print(await kb.get_fact(query="programming"))

        print("\n--- Testing search (vector store) ---")
        search_results = await kb.search("What is AI?")
        for res in search_results:
            print(f"Content: {res['content']}\nMetadata: {res['metadata']}\nScore: {res['score']}\n---")

        # Clean up dummy files
        # os.remove("data/test_files/example.txt")
        # os.remove("data/test_files/dummy.pdf")
        # os.remove("data/test_files/data.csv")
        # os.remove("data/test_files/sample.docx")
        # os.rmdir("data/test_files")
        # import shutil
        # shutil.rmtree(kb.chromadb_path) # This path is no longer used for LlamaIndex/Redis

    asyncio.run(main_test())
