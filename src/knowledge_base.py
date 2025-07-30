import os
import logging
import json
from typing import List, Dict, Any, Optional, cast
import asyncio

from llama_index.core import VectorStoreIndex, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.storage_context import StorageContext
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.core import ServiceContext, Settings

import redis.asyncio as redis
from redis.asyncio import Redis

import pandas as pd
from docx import Document as DocxDocument
from pypdf import PdfReader

# Import the centralized ConfigManager
from src.config import config as global_config_manager

class KnowledgeBase:
    def __init__(self):
        # Remove config_path and direct config loading
        
        # Network share path (if applicable)
        self.network_share_path = global_config_manager.get_nested('network_share.path')
        self.network_username = global_config_manager.get_nested('network_share.username', os.getenv('NETWORK_SHARE_USERNAME'))
        self.network_password = global_config_manager.get_nested('network_share.password', os.getenv('NETWORK_SHARE_PASSWORD'))

        # LlamaIndex specific settings from config
        self.vector_store_type = global_config_manager.get_nested('llama_index.vector_store.type', 'redis')
        self.embedding_model_name = global_config_manager.get_nested('llama_index.embedding.model', 'nomic-embed-text')
        self.chunk_size = global_config_manager.get_nested('llama_index.chunk_size', 512)
        self.chunk_overlap = global_config_manager.get_nested('llama_index.chunk_overlap', 20)

        # Redis configuration for LlamaIndex vector store
        redis_vector_store_config = global_config_manager.get_nested('llama_index.vector_store.redis', {})
        self.redis_host = redis_vector_store_config.get('host', 'localhost')
        self.redis_port = redis_vector_store_config.get('port', 6379)
        self.redis_password = redis_vector_store_config.get('password', os.getenv('REDIS_PASSWORD'))
        self.redis_db = redis_vector_store_config.get('db', 0)
        self.redis_index_name = redis_vector_store_config.get('index_name', 'autobot_knowledge_index')

        # Initialize Redis client for direct use (e.g., for facts/logs)
        # This uses the general memory.redis config, not specifically llama_index.vector_store.redis
        general_redis_config = global_config_manager.get_redis_config()
        self.redis_client: Redis = cast(Redis, redis.Redis(
            host=general_redis_config.get('host', 'localhost'),
            port=general_redis_config.get('port', 6379),
            password=general_redis_config.get('password', os.getenv('REDIS_PASSWORD')),
            db=general_redis_config.get('db', 1), # Use db 1 for general memory as per config.yaml
            decode_responses=True
        ))
        logging.info(f"Redis client initialized for host: {general_redis_config.get('host', 'localhost')}:{general_redis_config.get('port', 6379)} (DB: {general_redis_config.get('db', 1)})")

        self.llm = None
        self.embed_model = None
        self.vector_store = None
        self.storage_context = None
        self.index = None
        self.query_engine = None

    def _resolve_path(self, configured_path: str) -> str:
        if self.network_share_path and not os.path.isabs(configured_path):
            return os.path.join(self.network_share_path, configured_path)
        return configured_path

    async def ainit(self): # Removed llm_config parameter
        """
        Asynchronously initializes LlamaIndex components including LLM, Embedding model, and Vector Store.
        """
        llm_config_data = global_config_manager.get_llm_config() # Get LLM config from global manager
        llm_provider = llm_config_data.get('provider', 'ollama')
        llm_model = llm_config_data.get('model', 'phi:2.7b') # Use phi:2.7b as default
        llm_base_url = llm_config_data.get('ollama', {}).get('base_url', 'http://localhost:11434')

        if llm_provider == 'ollama':
            self.llm = LlamaIndexOllamaLLM(model=llm_model, base_url=llm_base_url)
            self.embed_model = LlamaIndexOllamaEmbedding(model_name=self.embedding_model_name, base_url=llm_base_url)
        else:
            logging.warning(f"LLM provider '{llm_provider}' not fully implemented for LlamaIndex. Defaulting to Ollama.")
            self.llm = LlamaIndexOllamaLLM(model=llm_model, base_url=llm_base_url)
            self.embed_model = LlamaIndexOllamaEmbedding(model_name=self.embedding_model_name, base_url=llm_base_url)

        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.chunk_size = self.chunk_size
        Settings.chunk_overlap = self.chunk_overlap
        Settings.node_parser = SentenceSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)

        try:
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
            self.vector_store = None
            logging.warning("Redis vector store disabled due to configuration issues.")

        if self.vector_store is not None:
            self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            try:
                self.index = VectorStoreIndex.from_vector_store(
                    self.vector_store,
                    storage_context=self.storage_context
                )
                logging.info("LlamaIndex VectorStoreIndex loaded from existing Redis store.")
            except Exception as e:
                logging.warning(f"Could not load existing LlamaIndex from Redis: {e}. Creating a new index.")
                self.index = VectorStoreIndex.from_documents([], storage_context=self.storage_context)
            
            self.query_engine = self.index.as_query_engine(llm=self.llm)
            logging.info("LlamaIndex VectorStoreIndex and QueryEngine initialized.")
        else:
            logging.warning("Creating in-memory VectorStoreIndex without Redis due to initialization issues.")
            self.index = VectorStoreIndex.from_documents([])
            self.query_engine = self.index.as_query_engine(llm=self.llm)
            logging.info("In-memory VectorStoreIndex and QueryEngine initialized.")

    async def add_file(self, file_path: str, file_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            
            self.index.insert(document)
            
            logging.info(f"File '{file_path}' processed and added to LlamaIndex (Redis).")
            return {"status": "success", "message": f"File '{file_path}' processed and added to KB."}
        except Exception as e:
            logging.error(f"Error adding file {file_path} to KB: {str(e)}")
            return {"status": "error", "message": f"Error adding file to KB: {str(e)}"}

    async def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        if self.query_engine is None:
            logging.error("KnowledgeBase not initialized. Call ainit() first.")
            return []
        try:
            response = self.query_engine.query(query)
            
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
        facts = []
        try:
            if fact_id:
                fact_data: Dict[str, str] = await self.redis_client.hgetall(f"fact:{fact_id}")
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
                    fact_data: Dict[str, str] = await self.redis_client.hgetall(key)
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
                    fact_data: Dict[str, str] = await self.redis_client.hgetall(key)
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
