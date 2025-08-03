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

import pandas as pd
from docx import Document as DocxDocument
from pypdf import PdfReader

# Import the centralized ConfigManager
from src.config import config as global_config_manager
# Import centralized Redis client utility
from src.utils.redis_client import get_redis_client

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
        # Use memory.redis configuration for consistency
        memory_config = global_config_manager.get('memory', {})
        redis_config = memory_config.get('redis', {})
        self.redis_host = redis_config.get('host', 'localhost')
        self.redis_port = redis_config.get('port', 6379)
        self.redis_password = redis_config.get('password', os.getenv('REDIS_PASSWORD'))
        self.redis_db = redis_config.get('db', 0)
        self.redis_index_name = redis_config.get('index_name', 'autobot_knowledge_index')

        # Initialize Redis client for direct use (e.g., for facts/logs)
        # Use centralized Redis client utility
        self.redis_client = get_redis_client(async_client=True)
        if self.redis_client:
            logging.info(f"Redis client initialized via centralized utility")
        else:
            logging.warning("Redis client not available - Redis may be disabled in configuration")

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
        if not self.redis_client:
            return {"status": "error", "message": "Redis client not available - Redis may be disabled"}
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
        if not self.redis_client:
            return []
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
                if all_keys:
                    # PERFORMANCE OPTIMIZATION: Use Redis pipeline for batch operations
                    pipe = self.redis_client.pipeline()
                    for key in all_keys:
                        pipe.hgetall(key)
                    results = await pipe.execute()
                    
                    for key, fact_data in zip(all_keys, results):
                        if fact_data and query.lower() in fact_data.get("content", "").lower():
                            facts.append({
                                "id": int(key.split(":")[1]),
                                "content": fact_data.get("content"),
                                "metadata": json.loads(fact_data.get("metadata", "{}")),
                                "timestamp": fact_data.get("timestamp")
                            })
            else:
                all_keys: List[str] = cast(List[str], await self.redis_client.keys("fact:*"))
                if all_keys:
                    # PERFORMANCE OPTIMIZATION: Use Redis pipeline for batch operations
                    pipe = self.redis_client.pipeline()
                    for key in all_keys:
                        pipe.hgetall(key)
                    results = await pipe.execute()
                    
                    for key, fact_data in zip(all_keys, results):
                        if fact_data:
                            facts.append({
                                "id": int(key.split(":")[1]),
                                "content": fact_data.get("content"),
                                "metadata": json.loads(fact_data.get("metadata", "{}")),
                                "timestamp": fact_data.get("timestamp")
                            })
            logging.info(f"Retrieved {len(facts)} facts from Redis using optimized pipeline.")
            return facts
        except Exception as e:
            logging.error(f"Error retrieving facts from Redis: {str(e)}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the knowledge base."""
        stats = {
            "total_documents": 0,
            "total_chunks": 0,
            "categories": [],
            "total_facts": 0
        }
        if not self.redis_client:
            return stats
        try:
            # Get stats from LlamaIndex vector store (approximate count)
            if self.vector_store:
                # This is a placeholder as LlamaIndex RedisVectorStore doesn't expose direct count
                all_doc_keys = await self.redis_client.keys(f"{self.redis_index_name}:doc:*")
                stats["total_documents"] = len(all_doc_keys)
                stats["total_chunks"] = len(all_doc_keys)  # Simple approximation
                
                # Collect categories from metadata if possible
                categories = set()
                for key in all_doc_keys[:10]:  # Limit to avoid performance issues
                    try:
                        doc_data = await self.redis_client.hgetall(key)
                        if doc_data and "metadata" in doc_data:
                            metadata = json.loads(doc_data.get("metadata", "{}"))
                            if "category" in metadata:
                                categories.add(metadata["category"])
                    except Exception:
                        pass
                stats["categories"] = list(categories)

            # Get stats from Redis facts
            all_fact_keys = await self.redis_client.keys("fact:*")
            stats["total_facts"] = len(all_fact_keys)

            logging.info(f"Knowledge base stats: {stats}")
            return stats
        except Exception as e:
            logging.error(f"Error getting knowledge base stats: {str(e)}")
            return stats

    async def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed statistics about the knowledge base."""
        from datetime import datetime
        
        detailed_stats = {
            "total_size": 0,  # in bytes
            "avg_chunk_size": 0,  # in characters
            "last_updated": "N/A",
            "searches_24h": 0,
            "top_category": "N/A",
            "fact_types": {}  # e.g., {"manual_input": 10, "web_link": 5}
        }
        if not self.redis_client:
            return detailed_stats
        try:
            # Total size and average chunk size calculation for facts
            all_fact_keys = await self.redis_client.keys("fact:*")
            total_content_length = 0
            fact_type_counts = {}
            latest_timestamp = 0

            for key in all_fact_keys:
                fact_data: Dict[str, str] = await self.redis_client.hgetall(key)
                if fact_data:
                    content = fact_data.get("content", "")
                    total_content_length += len(content)
                    
                    metadata = json.loads(fact_data.get("metadata", "{}"))
                    source_type = metadata.get("source", "unknown")
                    fact_type_counts[source_type] = fact_type_counts.get(source_type, 0) + 1
                    
                    timestamp = int(fact_data.get("timestamp", "0"))
                    if timestamp > latest_timestamp:
                        latest_timestamp = timestamp
            
            detailed_stats["total_size"] = total_content_length
            if len(all_fact_keys) > 0:
                detailed_stats["avg_chunk_size"] = total_content_length // len(all_fact_keys)
            
            if latest_timestamp > 0:
                detailed_stats["last_updated"] = datetime.fromtimestamp(latest_timestamp).isoformat()
            
            detailed_stats["fact_types"] = fact_type_counts

            # Placeholder for search queries and top category (would need separate logging/tracking)
            detailed_stats["searches_24h"] = 0  # Needs implementation
            if fact_type_counts:
                detailed_stats["top_category"] = max(fact_type_counts, key=fact_type_counts.get)

            logging.info(f"Detailed knowledge base stats: {detailed_stats}")
            return detailed_stats
        except Exception as e:
            logging.error(f"Error getting detailed knowledge base stats: {str(e)}")
            return detailed_stats

    async def export_all_data(self) -> List[Dict[str, Any]]:
        """Export all stored knowledge base data (facts and potentially vector store metadata)."""
        if not self.redis_client:
            return []
        exported_data = []
        try:
            # Export facts from Redis
            all_fact_keys = await self.redis_client.keys("fact:*")
            for key in all_fact_keys:
                fact_data: Dict[str, str] = await self.redis_client.hgetall(key)
                if fact_data:
                    exported_data.append({
                        "id": int(key.split(":")[1]),
                        "content": fact_data.get("content"),
                        "metadata": json.loads(fact_data.get("metadata", "{}")),
                        "timestamp": fact_data.get("timestamp"),
                        "type": "fact"
                    })
            
            # Export data from LlamaIndex (more complex, usually involves iterating nodes)
            if self.index:
                all_doc_keys = await self.redis_client.keys(f"{self.redis_index_name}:doc:*")
                for key in all_doc_keys:
                    # Fetch the actual document/node data if needed, or just metadata
                    exported_data.append({
                        "id": key,
                        "content": "LlamaIndex Document (content not directly exported here)",
                        "metadata": {"source": "LlamaIndex", "key": key},
                        "type": "document_reference"
                    })

            logging.info(f"Exported {len(exported_data)} items from knowledge base.")
            return exported_data
        except Exception as e:
            logging.error(f"Error exporting knowledge base data: {str(e)}")
            return []

    async def get_all_facts(self, collection: str = "default") -> List[Dict[str, Any]]:
        """Get all facts, optionally filtered by collection"""
        if not self.redis_client:
            return []
        facts = []
        try:
            all_keys: List[str] = cast(List[str], await self.redis_client.keys("fact:*"))
            if all_keys:
                # PERFORMANCE OPTIMIZATION: Use Redis pipeline for batch operations
                pipe = self.redis_client.pipeline()
                for key in all_keys:
                    pipe.hgetall(key)
                results = await pipe.execute()
                
                for key, fact_data in zip(all_keys, results):
                    if fact_data:
                        metadata = json.loads(fact_data.get("metadata", "{}"))
                        fact_collection = metadata.get("collection", "default")
                        
                        if collection == "all" or fact_collection == collection:
                            facts.append({
                                "id": int(key.split(":")[1]),
                                "content": fact_data.get("content"),
                                "metadata": metadata,
                                "timestamp": fact_data.get("timestamp"),
                                "collection": fact_collection
                            })
            
            # Sort by timestamp descending
            facts.sort(key=lambda x: int(x.get("timestamp", "0")), reverse=True)
            logging.info(f"Retrieved {len(facts)} facts from Redis using optimized pipeline.")
            return facts
        except Exception as e:
            logging.error(f"Error retrieving all facts from Redis: {str(e)}")
            return []

    async def update_fact(self, fact_id: int, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update an existing fact"""
        try:
            fact_key = f"fact:{fact_id}"
            existing_data = await self.redis_client.hgetall(fact_key)
            
            if not existing_data:
                return False
            
            # Update with new data
            import time
            updated_data = {
                "content": content,
                "metadata": json.dumps(metadata) if metadata else "{}",
                "timestamp": existing_data.get("timestamp", str(int(time.time())))  # Keep original timestamp
            }
            
            await self.redis_client.hset(fact_key, mapping=updated_data)
            logging.info(f"Fact {fact_id} updated successfully.")
            return True
        except Exception as e:
            logging.error(f"Error updating fact {fact_id}: {str(e)}")
            return False

    async def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID"""
        try:
            fact_key = f"fact:{fact_id}"
            result = await self.redis_client.delete(fact_key)
            
            if result:
                logging.info(f"Fact {fact_id} deleted successfully.")
                return True
            else:
                logging.warning(f"Fact {fact_id} not found for deletion.")
                return False
        except Exception as e:
            logging.error(f"Error deleting fact {fact_id}: {str(e)}")
            return False

    async def cleanup_old_entries(self, days_to_keep: int) -> Dict[str, Any]:
        """Remove knowledge base entries (facts) older than a specified number of days."""
        from datetime import datetime
        
        removed_count = 0
        try:
            cutoff_timestamp = int(datetime.now().timestamp()) - (days_to_keep * 24 * 3600)
            all_fact_keys = await self.redis_client.keys("fact:*")
            
            for key in all_fact_keys:
                fact_data: Dict[str, str] = await self.redis_client.hgetall(key)
                if fact_data:
                    timestamp = int(fact_data.get("timestamp", "0"))
                    if timestamp < cutoff_timestamp:
                        await self.redis_client.delete(key)
                        removed_count += 1
            
            logging.info(f"Cleaned up {removed_count} old knowledge base entries (facts).")
            return {"status": "success", "removed_count": removed_count}
        except Exception as e:
            logging.error(f"Error cleaning up old entries: {str(e)}")
            return {"status": "error", "message": f"Error cleaning up: {str(e)}", "removed_count": 0}
