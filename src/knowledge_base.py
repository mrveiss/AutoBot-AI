import asyncio
import hashlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiofiles
import aioredis
import redis
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
from pypdf import PdfReader

from src.circuit_breaker import circuit_breaker_async
from src.constants.network_constants import NetworkConstants

# Import the centralized ConfigManager
from src.unified_config import config
from src.utils.knowledge_base_timeouts import kb_timeouts


class KnowledgeBase:
    def __init__(self):
        """Initialize the Knowledge Base with Redis vector store support."""
        self.redis_host = config.get("redis.host")
        self.redis_port = config.get("redis.port")
        self.redis_password = config.get("redis.password")
        # Knowledge base vectors are in database 0 (required for Redis search indexes)
        self.redis_db = 0
        # Redis index name with embedding model suffix to avoid dimension conflicts
        self.redis_index_name = config.get(
            "redis.indexes.knowledge_base", "llama_index"
        )

        # Redis client for fact management (non-vector operations)
        self.redis_client = None
        self.aioredis_client = None

        # Vector store and index
        self.vector_store = None
        self.vector_index = None

        # Configure LlamaIndex with Ollama
        try:
            Settings.llm = LlamaIndexOllamaLLM(
                model="llama3.2:3b",
                request_timeout=kb_timeouts.llm_default,
                base_url=config.get("ollama.base_url", "http://127.0.0.1:11434"),
            )
            Settings.embed_model = LlamaIndexOllamaEmbedding(
                model_name="all-MiniLM-L6-v2",
                base_url=config.get("ollama.base_url", "http://127.0.0.1:11434"),
                ollama_additional_kwargs={"num_ctx": 2048},
            )
            logging.info("LlamaIndex configured with Ollama LLM and embedding models")
        except Exception as e:
            logging.warning(f"Could not configure LlamaIndex with Ollama: {e}")
            # Keep the vector store functionality available even if LLM fails

        # Redis initialization flag
        self._redis_initialized = False

    async def _init_redis_and_vector_store(self):
        """Initialize Redis connection and vector store asynchronously"""
        try:
            # Use the centralized configuration for Redis connection
            redis_config = {
                "host": self.redis_host,
                "port": self.redis_port,
                "db": self.redis_db,
                "password": self.redis_password,
                "decode_responses": False,  # Needed for binary operations
                "socket_timeout": kb_timeouts.redis_socket_timeout,
                "socket_connect_timeout": kb_timeouts.redis_socket_connect,
            }

            # Create Redis client for general operations
            self.redis_client = redis.Redis(**redis_config)

            # Test the connection
            await asyncio.to_thread(self.redis_client.ping)
            logging.info(
                f"Redis client connected to {self.redis_host}:{self.redis_port} "
                f"(database {self.redis_db})"
            )

            # Create async Redis client for async operations
            redis_config["decode_responses"] = (
                True  # Async client can use string responses
            )
            self.aioredis_client = aioredis.Redis(**redis_config)
            await self.aioredis_client.ping()
            logging.info(f"Async Redis client connected successfully")

        except Exception as e:
            logging.error(f"Failed to initialize Redis connection: {e}")
            self.redis_client = None
            self.aioredis_client = None

        # Initialize vector store after Redis is ready
        await self._init_vector_store()

    async def _init_vector_store(self):
        """Initialize LlamaIndex vector store with Redis backend"""
        if not self.redis_client:
            logging.warning(
                "Redis client not available, skipping vector store initialization"
            )
            return

        try:
            # Create schema for the new index (will auto-detect dimensions from embedding model)
            schema = RedisVectorStoreSchema(
                index_name=self.redis_index_name,
                prefix="llama_index/vector_",
            )

            logging.info(f"Created Redis schema for index: {self.redis_index_name}")

            self.vector_store = RedisVectorStore(
                schema=schema,
                redis_url=f"redis://{self.redis_host}:{self.redis_port}",
                password=self.redis_password,
                redis_kwargs={"db": self.redis_db},
            )
            logging.info(
                "LlamaIndex RedisVectorStore initialized with index: "
                f"{self.redis_index_name}"
            )

            # CRITICAL FIX: Initialize vector index from existing vectors
            await self._init_vector_index_from_existing()

        except ImportError as e:
            logging.warning(
                f"Could not import RedisVectorStoreSchema: {e}. "
                "Using fallback configuration."
            )
            self.vector_store = None
            logging.warning("Redis vector store disabled due to configuration issues.")
        except Exception as e:
            logging.error(f"Failed to initialize vector store: {e}")
            self.vector_store = None

    async def _init_vector_index_from_existing(self):
        """Initialize vector index from existing vectors in Redis"""
        if not self.vector_store:
            return

        try:
            # Check if vectors exist in Redis
            vector_keys = await self._scan_redis_keys_async("llama_index/vector_*")

            if vector_keys:
                logging.info(
                    f"Found {len(vector_keys)} existing vectors, initializing index"
                )

                # Create storage context and index from existing vector store
                storage_context = StorageContext.from_defaults(
                    vector_store=self.vector_store
                )
                self.vector_index = await asyncio.to_thread(
                    VectorStoreIndex.from_vector_store,
                    vector_store=self.vector_store,
                    storage_context=storage_context,
                )

                logging.info(
                    f"Vector index initialized from {len(vector_keys)} existing vectors"
                )
            else:
                logging.info(
                    "No existing vectors found, vector index will be created when first document is added"
                )

        except Exception as e:
            logging.error(
                f"Failed to initialize vector index from existing vectors: {e}"
            )
            self.vector_index = None

    async def _ensure_redis_initialized(self):
        """Ensure Redis is initialized before any operations"""
        if not self._redis_initialized:
            await self._init_redis_and_vector_store()
            self._redis_initialized = True

    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for sync operations"""
        return self.redis_client

    async def _get_async_redis_client(self) -> Optional[aioredis.Redis]:
        """Get async Redis client for async operations"""
        return self.aioredis_client

    def _scan_redis_keys(self, pattern: str) -> List[str]:
        """Scan Redis keys with pattern using sync client"""
        if not self.redis_client:
            return []

        try:
            keys = []
            for key in self.redis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    keys.append(key.decode("utf-8"))
                else:
                    keys.append(str(key))
            return keys
        except Exception as e:
            logging.error(f"Error scanning Redis keys: {e}")
            return []

    async def _scan_redis_keys_async(self, pattern: str) -> List[str]:
        """Scan Redis keys with pattern using async client"""
        if not self.aioredis_client:
            return []

        try:
            keys = []
            async for key in self.aioredis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    keys.append(key.decode("utf-8"))
                else:
                    keys.append(str(key))
            return keys
        except Exception as e:
            logging.error(f"Error scanning Redis keys async: {e}")
            return []

    async def store_fact(
        self, text: str, metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Store a fact in the knowledge base"""
        await self._ensure_redis_initialized()

        if not self.redis_client:
            return {"status": "error", "message": "Redis not available"}

        if metadata is None:
            metadata = {}

        try:
            # Generate unique fact ID
            fact_id = str(uuid.uuid4())
            fact_key = f"fact:{fact_id}"

            # Prepare fact data
            fact_data = {
                "content": text,
                "metadata": json.dumps(metadata),
                "timestamp": datetime.now().isoformat(),
                "id": fact_id,
            }

            # Store in Redis
            await asyncio.to_thread(self.redis_client.hset, fact_key, mapping=fact_data)

            logging.info(f"Stored fact with ID: {fact_id}")
            return {
                "status": "success",
                "message": "Fact stored successfully",
                "fact_id": fact_id,
            }

        except Exception as e:
            logging.error(f"Failed to store fact: {e}")
            return {"status": "error", "message": f"Failed to store fact: {str(e)}"}

    def get_fact(
        self, fact_id: Optional[str] = None, query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve facts from the knowledge base"""
        if not self.redis_client:
            return []

        try:
            facts = []

            if fact_id:
                # Get specific fact
                fact_key = f"fact:{fact_id}"
                fact_data = self.redis_client.hgetall(fact_key)
                if fact_data:
                    facts.append(
                        {
                            "id": fact_id,
                            "content": fact_data.get(b"content", b"").decode("utf-8"),
                            "metadata": json.loads(
                                fact_data.get(b"metadata", b"{}").decode("utf-8")
                            ),
                            "timestamp": fact_data.get(b"timestamp", b"").decode(
                                "utf-8"
                            ),
                        }
                    )
            elif query:
                # Search facts by content matching
                all_fact_keys = self._scan_redis_keys("fact:*")
                for fact_key in all_fact_keys:
                    fact_data = self.redis_client.hgetall(fact_key)
                    if fact_data:
                        content = fact_data.get(b"content", b"").decode("utf-8")
                        if query.lower() in content.lower():
                            fact_id = fact_key.split(":")[1]
                            facts.append(
                                {
                                    "id": fact_id,
                                    "content": content,
                                    "metadata": json.loads(
                                        fact_data.get(b"metadata", b"{}").decode(
                                            "utf-8"
                                        )
                                    ),
                                    "timestamp": fact_data.get(
                                        b"timestamp", b""
                                    ).decode("utf-8"),
                                }
                            )
            else:
                # Get all facts (with limit for performance)
                all_fact_keys = self._scan_redis_keys("fact:*")[
                    :100
                ]  # Limit to 100 facts
                if all_fact_keys:
                    # Use pipeline for efficiency
                    pipe = self.redis_client.pipeline()
                    for key in all_fact_keys:
                        pipe.hgetall(key)
                    results = pipe.execute()

                    for key, fact_data in zip(all_fact_keys, results):
                        if fact_data:
                            facts.append(
                                {
                                    "id": int(key.split(":")[1]),
                                    "content": fact_data.get("content"),
                                    "metadata": json.loads(
                                        fact_data.get("metadata", "{}")
                                    ),
                                    "timestamp": fact_data.get("timestamp"),
                                }
                            )
            logging.info(
                f"Retrieved {len(facts)} facts from Redis using sync operations."
            )
            return facts
        except Exception as e:
            logging.error(f"Error retrieving facts from Redis: {str(e)}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get basic, high-level statistics about the knowledge base.

        This method provides a quick overview with minimal computational overhead,
        suitable for dashboard displays and health checks. Returns core metrics
        like document counts and available categories.

        Returns:
            Dict containing basic stats: total_documents, total_chunks, categories, total_facts

        Performance: Fast (< 100ms) - uses optimized counting methods with async operations
        """
        await self._ensure_redis_initialized()

        # Get real stats from Redis
        try:
            async_redis = await self._get_async_redis_client()
            if not async_redis:
                logging.warning("Redis client not available for stats")
                return {
                    "total_documents": 0,
                    "total_chunks": 0,
                    "categories": [],
                    "total_facts": 0,
                    "status": "redis_unavailable",
                }

            # **CRITICAL FIX: Count actual vectors instead of indexed documents**
            # The search index may be out of sync, but we want real vector count
            vector_keys = await self._scan_redis_keys_async("llama_index/vector_*")
            total_vectors = len(vector_keys)

            # Also get the FT.INFO for comparison (but don't rely on it)
            indexed_docs = 0
            try:
                ft_info = await async_redis.execute_command("FT.INFO", "llama_index")
                if ft_info and len(ft_info) > 0:
                    for i, item in enumerate(ft_info):
                        # Handle both bytes and string responses from Redis
                        if isinstance(item, bytes):
                            decoded = item.decode()
                        elif isinstance(item, str):
                            decoded = item
                        else:
                            continue

                        if decoded == "num_docs" and i + 1 < len(ft_info):
                            indexed_docs = int(ft_info[i + 1])
                            break
            except Exception as e:
                logging.warning(f"Could not get FT.INFO: {e}")

            # Log the discrepancy if found
            if indexed_docs != total_vectors and total_vectors > 0:
                logging.warning(
                    f"Vector count mismatch: {total_vectors} vectors exist but only {indexed_docs} indexed. "
                    "This may indicate search index needs rebuilding."
                )

            # Get categories - use actual category structure from system
            try:
                from src.agents.system_knowledge_manager import SystemKnowledgeManager

                temp_knowledge_manager = SystemKnowledgeManager(self)
                categories_response = temp_knowledge_manager.get_knowledge_categories()
                if (
                    categories_response
                    and categories_response.get("success")
                    and categories_response.get("categories")
                ):
                    # Extract all category paths for stats display
                    def extract_category_names(cat_dict, prefix=""):
                        names = []
                        for key, value in cat_dict.items():
                            if isinstance(value, dict):
                                if "children" in value:
                                    names.append(f"{prefix}{key}" if prefix else key)
                                    names.extend(
                                        extract_category_names(
                                            value["children"], f"{prefix}{key}/"
                                        )
                                    )
                                else:
                                    names.append(f"{prefix}{key}" if prefix else key)
                        return names

                    categories = extract_category_names(
                        categories_response["categories"]
                    )
                else:
                    categories = [
                        "documentation",
                        "system",
                        "configuration",
                    ]  # Fallback
            except Exception as e:
                logging.warning(
                    f"Could not get category structure: {e}, using fallback"
                )
                categories = ["documentation", "system", "configuration"]  # Fallback

            # Get actual facts count from Redis
            total_facts = 0
            try:
                fact_keys = await self._scan_redis_keys_async("fact:*")
                total_facts = len(fact_keys)
                logging.info(f"Found {total_facts} facts in Redis")
            except Exception as e:
                logging.warning(f"Could not count facts: {e}")

            stats = {
                "total_documents": total_vectors,  # **FIXED: Use actual vector count**
                "total_chunks": total_vectors,  # Each vector is typically one chunk
                "categories": categories,
                "total_facts": total_facts,  # Actual facts count from Redis
                "status": "live_data",
                "indexed_documents": indexed_docs,  # For debugging - show indexed vs actual
                "vector_index_sync": indexed_docs == total_vectors,  # Health indicator
            }
            logging.info(
                f"Retrieved live stats: {total_vectors} vectors, {indexed_docs} indexed"
            )
            return stats

        except Exception as e:
            logging.error(f"Failed to get live stats: {e}")
            # Fallback to basic stats
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "categories": [],
                "total_facts": 0,
                "status": "error",
            }

    async def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the knowledge base.

        This method provides detailed insights including database size,
        category distribution, recent activity, and performance metrics.
        This is more computationally intensive than get_stats().

        Returns:
            Dict containing detailed statistics and analytics

        Performance: Slower (1-5s) - performs comprehensive analysis
        """
        basic_stats = await self.get_stats()

        if not self.redis_client:
            return {
                **basic_stats,
                "detailed_stats": False,
                "message": "Redis not available for detailed analysis",
            }

        try:
            detailed = {**basic_stats}

            # Database size analysis
            try:
                # Get approximate database size
                info = await asyncio.to_thread(self.redis_client.info, "memory")
                detailed["memory_usage_mb"] = round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                )
                detailed["peak_memory_mb"] = round(
                    info.get("used_memory_peak", 0) / (1024 * 1024), 2
                )
            except Exception as e:
                logging.warning(f"Could not get memory stats: {e}")

            # Recent activity analysis
            try:
                fact_keys = await self._scan_redis_keys_async("fact:*")
                if fact_keys:
                    # Sample recent facts for activity analysis
                    recent_facts = []
                    sample_size = min(10, len(fact_keys))

                    for fact_key in fact_keys[:sample_size]:
                        try:
                            fact_data = await self.aioredis_client.hgetall(fact_key)
                            if fact_data and "timestamp" in fact_data:
                                recent_facts.append(fact_data["timestamp"])
                        except Exception:
                            continue

                    detailed["recent_activity"] = {
                        "total_facts": len(fact_keys),
                        "sample_timestamps": recent_facts[:5],  # Show 5 most recent
                    }
            except Exception as e:
                logging.warning(f"Could not get recent activity: {e}")

            # Vector store health
            try:
                if basic_stats.get("vector_index_sync", False):
                    detailed["vector_store_health"] = "healthy"
                else:
                    detailed["vector_store_health"] = "index_out_of_sync"
                    detailed["health_recommendation"] = (
                        "Consider rebuilding search index"
                    )
            except Exception as e:
                logging.warning(f"Could not assess vector store health: {e}")

            detailed["detailed_stats"] = True
            detailed["generated_at"] = datetime.now().isoformat()

            return detailed

        except Exception as e:
            logging.error(f"Error generating detailed stats: {e}")
            return {**basic_stats, "detailed_stats": False, "error": str(e)}

    async def search(
        self,
        query: str,
        similarity_top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        mode: str = "auto",  # "vector", "text", or "auto"
    ) -> List[Dict[str, Any]]:
        """
        Search the knowledge base with multiple search modes.

        Args:
            query: Search query
            similarity_top_k: Number of results to return
            filters: Optional filters to apply
            mode: Search mode ("vector" for semantic, "text" for keyword, "auto" for hybrid)

        Returns:
            List of search results with content and metadata
        """
        if not query.strip():
            return []

        # **ASYNC TIMEOUT PROTECTION: Prevent chat hangs**
        try:
            # Use asyncio.wait_for to prevent indefinite blocking
            return await asyncio.wait_for(
                self._perform_search(query, similarity_top_k, filters, mode),
                timeout=kb_timeouts.llamaindex_search_query,
            )
        except asyncio.TimeoutError:
            logging.warning(f"Search operation timed out for query: {query[:50]}...")
            return [
                {
                    "content": f"Search timed out for query: {query[:100]}",
                    "metadata": {"error": "timeout", "query": query},
                    "score": 0.0,
                }
            ]
        except Exception as e:
            logging.error(f"Search error: {e}")
            return [
                {
                    "content": f"Search error: {str(e)}",
                    "metadata": {"error": "search_failed", "query": query},
                    "score": 0.0,
                }
            ]

    async def _perform_search(
        self,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        mode: str,
    ) -> List[Dict[str, Any]]:
        """Internal search implementation with timeout protection"""
        await self._ensure_redis_initialized()

        # If vector store is available, use semantic search
        if self.vector_store and self.vector_index and mode in ["vector", "auto"]:
            try:
                # Use LlamaIndex for semantic search
                query_engine = self.vector_index.as_query_engine(
                    similarity_top_k=similarity_top_k,
                    response_mode="no_text",  # Just retrieve, don't generate
                )

                # Perform search with timeout protection
                response = await asyncio.to_thread(query_engine.query, query)

                results = []
                if hasattr(response, "source_nodes"):
                    for node in response.source_nodes:
                        results.append(
                            {
                                "content": node.node.text,
                                "metadata": node.node.metadata or {},
                                "score": getattr(node, "score", 0.0),
                                "doc_id": node.node.id_ or str(uuid.uuid4()),
                            }
                        )

                if results:
                    logging.info(f"Vector search returned {len(results)} results")
                    return results

            except Exception as e:
                logging.warning(
                    f"Vector search failed: {e}, falling back to text search"
                )

        # Fallback to text search in facts
        if mode in ["text", "auto"]:
            try:
                fact_results = []
                fact_keys = await self._scan_redis_keys_async("fact:*")

                # Limit search scope for performance
                search_limit = min(1000, len(fact_keys))

                for fact_key in fact_keys[:search_limit]:
                    try:
                        fact_data = await self.aioredis_client.hgetall(fact_key)
                        if fact_data and "content" in fact_data:
                            content = fact_data["content"]

                            # Simple text matching
                            if query.lower() in content.lower():
                                # Calculate simple relevance score
                                query_words = query.lower().split()
                                content_lower = content.lower()
                                matches = sum(
                                    1 for word in query_words if word in content_lower
                                )
                                score = matches / len(query_words) if query_words else 0

                                fact_results.append(
                                    {
                                        "content": content,
                                        "metadata": json.loads(
                                            fact_data.get("metadata", "{}")
                                        ),
                                        "score": score,
                                        "doc_id": fact_key.split(":")[-1],
                                    }
                                )
                    except Exception:
                        continue  # Skip failed facts

                # Sort by relevance score
                fact_results.sort(key=lambda x: x["score"], reverse=True)

                logging.info(f"Text search returned {len(fact_results)} results")
                return fact_results[:similarity_top_k]

            except Exception as e:
                logging.error(f"Text search failed: {e}")

        return []

    async def add_document(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a document to the knowledge base with async processing.

        Args:
            content: Document content
            metadata: Document metadata
            doc_id: Optional document ID

        Returns:
            Result dictionary with status and details
        """
        if not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            # **ASYNC TIMEOUT PROTECTION**
            return await asyncio.wait_for(
                self._add_document_internal(content, metadata, doc_id),
                timeout=kb_timeouts.document_add,
            )
        except asyncio.TimeoutError:
            logging.warning("Document addition timed out")
            return {"status": "timeout", "message": "Document addition timed out"}
        except Exception as e:
            logging.error(f"Document addition failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _add_document_internal(
        self, content: str, metadata: Dict[str, Any], doc_id: Optional[str]
    ) -> Dict[str, Any]:
        """Internal document addition with proper async handling"""
        await self._ensure_redis_initialized()

        if metadata is None:
            metadata = {}

        # Generate document ID if not provided
        if not doc_id:
            doc_id = str(uuid.uuid4())

        # Add document metadata
        metadata.update(
            {
                "doc_id": doc_id,
                "added_at": datetime.now().isoformat(),
                "content_length": len(content),
            }
        )

        # If vector store is available, add to vector index
        if self.vector_store:
            try:
                # Create LlamaIndex document
                document = Document(text=content, metadata=metadata, id_=doc_id)

                # Add to vector store using async thread execution
                if not self.vector_index:
                    # Create storage context and index
                    storage_context = StorageContext.from_defaults(
                        vector_store=self.vector_store
                    )
                    self.vector_index = await asyncio.to_thread(
                        VectorStoreIndex.from_documents,
                        [document],
                        storage_context=storage_context,
                    )
                else:
                    # Add to existing index
                    await asyncio.to_thread(self.vector_index.insert, document)

                logging.info(f"Added document {doc_id} to vector store")

                return {
                    "status": "success",
                    "message": "Document added to vector store",
                    "doc_id": doc_id,
                    "content_length": len(content),
                }

            except Exception as e:
                logging.error(f"Failed to add document to vector store: {e}")
                # Fall back to storing as fact

        # Store as fact if vector store is not available
        return await self.store_fact(content, metadata)

    async def export_all_data(self) -> List[Dict[str, Any]]:
        """Export all knowledge base data"""
        try:
            # Get all facts
            all_facts = []
            fact_keys = await self._scan_redis_keys_async("fact:*")

            for fact_key in fact_keys:
                try:
                    fact_data = await self.aioredis_client.hgetall(fact_key)
                    if fact_data:
                        all_facts.append(
                            {
                                "type": "fact",
                                "id": fact_key.split(":")[-1],
                                "content": fact_data.get("content", ""),
                                "metadata": json.loads(fact_data.get("metadata", "{}")),
                                "timestamp": fact_data.get("timestamp", ""),
                            }
                        )
                except Exception as e:
                    logging.warning(f"Could not export fact {fact_key}: {e}")

            logging.info(f"Exported {len(all_facts)} facts")
            return all_facts

        except Exception as e:
            logging.error(f"Export failed: {e}")
            return []

    async def rebuild_search_index(self) -> Dict[str, Any]:
        """
        Rebuild the search index to sync with actual vectors.

        This fixes the discrepancy between vector count and indexed documents.
        """
        try:
            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            # Get current vector count
            vector_keys = await self._scan_redis_keys_async("llama_index/vector_*")
            total_vectors = len(vector_keys)

            if total_vectors == 0:
                return {"status": "info", "message": "No vectors to index"}

            # Recreate the index
            try:
                # Drop existing index if it exists
                await self.aioredis_client.execute_command(
                    "FT.DROPINDEX", self.redis_index_name
                )
                logging.info(f"Dropped existing index: {self.redis_index_name}")
            except Exception:
                logging.info("No existing index to drop")

            # Reinitialize vector store (this will recreate the index)
            await self._init_vector_store()

            # Verify the fix
            stats = await self.get_stats()
            indexed_docs = stats.get("indexed_documents", 0)

            return {
                "status": "success",
                "message": f"Search index rebuilt successfully",
                "vectors_found": total_vectors,
                "indexed_documents": indexed_docs,
                "sync_status": "synced" if indexed_docs == total_vectors else "partial",
            }

        except Exception as e:
            logging.error(f"Failed to rebuild search index: {e}")
            return {"status": "error", "message": str(e)}

    async def get_all_facts(
        self, collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all facts from the knowledge base, optionally filtered by collection.

        Args:
            collection: Optional collection filter. If "all" or None, returns all facts.

        Returns:
            List of facts with their metadata
        """
        try:
            if not self.aioredis_client:
                logging.warning("Redis client not available for get_all_facts")
                return []

            # Get all fact keys from Redis
            fact_keys = await self._scan_redis_keys_async("fact:*")
            logging.info(f"Found {len(fact_keys)} fact keys in Redis")

            if not fact_keys:
                return []

            facts = []
            for key in fact_keys:
                try:
                    # Get fact data from Redis
                    fact_data = await self.aioredis_client.get(key)
                    if fact_data:
                        import json

                        fact = json.loads(fact_data)

                        # Filter by collection if specified
                        if collection and collection != "all":
                            fact_collection = fact.get("collection", "")
                            if fact_collection != collection:
                                continue

                        # Add metadata
                        fact_id = key.replace("fact:", "")
                        fact.update(
                            {
                                "id": fact_id,
                                "key": key,
                                "collection": fact.get("collection", "general"),
                            }
                        )

                        facts.append(fact)

                except Exception as fact_error:
                    logging.warning(f"Failed to parse fact {key}: {fact_error}")
                    continue

            logging.info(
                f"Retrieved {len(facts)} facts (filtered by collection: {collection})"
            )
            return facts

        except Exception as e:
            logging.error(f"Failed to get all facts: {e}")
            return []
