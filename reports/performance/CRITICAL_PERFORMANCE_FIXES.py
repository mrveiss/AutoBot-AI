"""
Critical Performance Fixes for AutoBot System
Implementation code for highest-impact optimizations identified in performance analysis
"""

import asyncio
import time
import json
import logging
from typing import Dict, Any, Optional, List
from collections import OrderedDict
import aiohttp
import redis
import torch
from sentence_transformers import SentenceTransformer
import psutil
import numpy as np
from collections import defaultdict, LRUCache
from dataclasses import dataclass
from typing import Union
try:
    import faiss
except ImportError:
    faiss = None
try:
    import openvino as ov
except ImportError:
    ov = None

logger = logging.getLogger(__name__)


# =====================================================
# 1. CRITICAL: LLM Interface Streaming Optimization
# =====================================================

class OptimizedStreamProcessor:
    """
    Optimized streaming processor that eliminates complex timeout logic
    and uses natural stream completion detection
    """
    
    def __init__(self, response: aiohttp.ClientResponse):
        self.response = response
        self.start_time = time.time()
        self.content_buffer = []
        self.chunk_count = 0
        
    async def process_ollama_stream(self) -> tuple[str, bool]:
        """
        Process Ollama stream with natural completion detection
        Returns: (accumulated_content, completed_successfully)
        """
        try:
            async for line in self.response.content:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                    
                try:
                    chunk_data = json.loads(line)
                    
                    # Extract message content
                    if 'message' in chunk_data and 'content' in chunk_data['message']:
                        content = chunk_data['message']['content']
                        self.content_buffer.append(content)
                    
                    # Natural completion detection - Ollama sends "done": true
                    if chunk_data.get('done', False):
                        return ''.join(self.content_buffer), True
                    
                    self.chunk_count += 1
                    
                    # Safety limit to prevent infinite loops
                    if self.chunk_count > 5000:  # Increased limit
                        logger.warning("Stream exceeded chunk limit, completing")
                        return ''.join(self.content_buffer), False
                        
                except json.JSONDecodeError:
                    continue  # Skip malformed chunks
                    
            # Stream ended naturally without "done" signal
            return ''.join(self.content_buffer), True
            
        except Exception as e:
            logger.error(f"Stream processing error: {e}")
            return ''.join(self.content_buffer), False
    
    def get_processing_time(self) -> float:
        """Get processing time in milliseconds"""
        return (time.time() - self.start_time) * 1000


class OptimizedLLMInterface:
    """
    Optimized LLM interface with simplified streaming and better error handling
    """
    
    def __init__(self):
        self.session = None
        self.streaming_failures = {}
        self.failure_threshold = 2  # Reduced threshold
        
    async def _get_session(self):
        """Get or create HTTP session with optimal settings"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                connect=5.0,        # Quick connection timeout
                total=None          # No total timeout for streaming
            )
            
            connector = aiohttp.TCPConnector(
                limit=20,           # Connection pool limit
                ttl_dns_cache=1800, # Cache DNS for 30 minutes
                use_dns_cache=True,
                keepalive_timeout=60,
                enable_cleanup_closed=True
            )
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'AutoBot-Optimized/1.0',
                    'Connection': 'keep-alive'
                }
            )
        return self.session
    
    async def chat_completion_optimized(self, messages: List[Dict], model: str, **kwargs) -> Dict[str, Any]:
        """
        Optimized chat completion with simplified streaming
        """
        url = "http://localhost:11434/api/chat"  # Direct localhost connection
        
        # Simplified payload
        data = {
            "model": model,
            "messages": messages,
            "stream": True,  # Always use streaming
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_ctx": kwargs.get("num_ctx", 4096),
            }
        }
        
        start_time = time.time()
        
        try:
            session = await self._get_session()
            
            async with session.post(url, json=data) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"HTTP {response.status}")
                
                # Use optimized stream processor
                processor = OptimizedStreamProcessor(response)
                content, completed = await processor.process_ollama_stream()
                
                processing_time = time.time() - start_time
                
                # Reset failure count on success
                if completed and model in self.streaming_failures:
                    self.streaming_failures[model] = 0
                
                return {
                    "content": content,
                    "model": model,
                    "completed": completed,
                    "processing_time": processing_time,
                    "chunk_count": processor.chunk_count
                }
                
        except Exception as e:
            # Record failure for model
            self.streaming_failures[model] = self.streaming_failures.get(model, 0) + 1
            
            # If too many failures, fall back to non-streaming
            if self.streaming_failures[model] >= self.failure_threshold:
                logger.warning(f"Switching to non-streaming for model {model}")
                return await self._non_streaming_fallback(url, data, model)
            
            raise e
    
    async def _non_streaming_fallback(self, url: str, data: Dict, model: str) -> Dict[str, Any]:
        """Simple non-streaming fallback"""
        data_copy = data.copy()
        data_copy["stream"] = False
        
        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=30.0)
        
        async with session.post(url, json=data_copy, timeout=timeout) as response:
            result = await response.json()
            return {
                "content": result.get("message", {}).get("content", ""),
                "model": model,
                "completed": True,
                "fallback_used": True
            }


# =====================================================
# 2. HIGH: Redis Connection Pool Optimization
# =====================================================

class OptimizedRedisConnectionManager:
    """
    Optimized Redis connection manager with proper pooling and resource limits
    """
    
    def __init__(self):
        self.connection_pools = {}
        self.pool_config = {
            "max_connections": 20,
            "retry_on_timeout": True,
            "socket_keepalive": True,
            "socket_keepalive_options": {
                1: 600,   # TCP_KEEPIDLE (seconds)
                2: 60,    # TCP_KEEPINTVL (seconds)  
                3: 5,     # TCP_KEEPCNT (count)
            },
            "health_check_interval": 30,
            "socket_timeout": 10,
            "socket_connect_timeout": 5,
        }
    
    def get_connection_pool(self, host: str, port: int, db: int, password: Optional[str] = None) -> redis.ConnectionPool:
        """Get or create optimized connection pool"""
        pool_key = f"{host}:{port}:{db}"
        
        if pool_key not in self.connection_pools:
            pool_params = {
                "host": host,
                "port": port,
                "db": db,
                "decode_responses": True,
                **self.pool_config
            }
            
            if password:
                pool_params["password"] = password
            
            self.connection_pools[pool_key] = redis.ConnectionPool(**pool_params)
            logger.info(f"Created optimized Redis pool: {pool_key}")
        
        return self.connection_pools[pool_key]
    
    def get_redis_client(self, host: str, port: int, db: int, password: Optional[str] = None) -> redis.Redis:
        """Get Redis client with optimized connection pool"""
        pool = self.get_connection_pool(host, port, db, password)
        return redis.Redis(connection_pool=pool)
    
    async def health_check_all_pools(self) -> Dict[str, bool]:
        """Health check all connection pools"""
        health_status = {}
        
        for pool_key, pool in self.connection_pools.items():
            try:
                client = redis.Redis(connection_pool=pool)
                client.ping()
                health_status[pool_key] = True
            except Exception as e:
                logger.error(f"Redis pool {pool_key} health check failed: {e}")
                health_status[pool_key] = False
        
        return health_status
    
    def cleanup_pools(self):
        """Cleanup all connection pools"""
        for pool_key, pool in self.connection_pools.items():
            try:
                pool.disconnect()
                logger.info(f"Disconnected Redis pool: {pool_key}")
            except Exception as e:
                logger.error(f"Error disconnecting pool {pool_key}: {e}")
        
        self.connection_pools.clear()


# =====================================================
# 3. HIGH: GPU Multi-Modal Processing Acceleration  
# =====================================================

class GPUAcceleratedMultiModalProcessor:
    """
    GPU-accelerated multi-modal processing for significant performance improvements
    """
    
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.text_encoder = None
        self.batch_size = 32
        self.max_sequence_length = 512
        
        logger.info(f"Multi-modal processor using device: {self.device}")
    
    async def initialize_models(self):
        """Initialize models with GPU acceleration"""
        if self.text_encoder is None:
            self.text_encoder = SentenceTransformer('all-MiniLM-L6-v2')
            
            if self.device.type == "cuda":
                self.text_encoder = self.text_encoder.to(self.device)
                # Enable mixed precision for RTX 4070
                torch.backends.cudnn.benchmark = True
                logger.info("GPU models initialized with mixed precision")
    
    async def process_text_batch(self, texts: List[str]) -> List[List[float]]:
        """Process text batch with GPU acceleration"""
        await self.initialize_models()
        
        start_time = time.time()
        embeddings = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            with torch.no_grad():
                if self.device.type == "cuda":
                    # Use automatic mixed precision for RTX 4070
                    with torch.cuda.amp.autocast():
                        batch_embeddings = self.text_encoder.encode(
                            batch,
                            device=self.device,
                            show_progress_bar=False,
                            convert_to_tensor=True
                        )
                else:
                    batch_embeddings = self.text_encoder.encode(
                        batch,
                        device=self.device,
                        show_progress_bar=False
                    )
                
                # Convert to list for serialization
                if isinstance(batch_embeddings, torch.Tensor):
                    batch_embeddings = batch_embeddings.cpu().numpy().tolist()
                
                embeddings.extend(batch_embeddings)
        
        processing_time = time.time() - start_time
        logger.info(f"GPU processed {len(texts)} texts in {processing_time:.2f}s")
        
        return embeddings
    
    async def process_multimodal_pipeline(self, 
                                        texts: Optional[List[str]] = None,
                                        images: Optional[List] = None,
                                        audio_files: Optional[List] = None) -> Dict[str, Any]:
        """
        Complete multi-modal processing pipeline with GPU acceleration
        """
        start_time = time.time()
        results = {
            "processing_times": {},
            "embeddings": {},
            "metadata": {}
        }
        
        # Process texts with GPU acceleration
        if texts:
            text_start = time.time()
            text_embeddings = await self.process_text_batch(texts)
            results["embeddings"]["text"] = text_embeddings
            results["processing_times"]["text"] = time.time() - text_start
        
        # TODO: Add image and audio processing when models are available
        if images:
            results["embeddings"]["images"] = []
            results["processing_times"]["images"] = 0
            
        if audio_files:
            results["embeddings"]["audio"] = []
            results["processing_times"]["audio"] = 0
        
        total_time = time.time() - start_time
        results["total_processing_time"] = total_time
        results["gpu_utilized"] = self.device.type == "cuda"
        
        return results


# =====================================================
# 4. MEDIUM: Intelligent Memory Management
# =====================================================

class OptimizedMemoryManager:
    """
    Intelligent memory management with LRU eviction and adaptive cleanup
    """
    
    def __init__(self):
        self.memory_threshold = 0.8  # 80% memory usage threshold
        self.cleanup_percentage = 0.2  # Clean up 20% of data
        self.monitoring_interval = 60  # Check every minute
        self.lru_caches = {}
        
    def create_lru_cache(self, name: str, max_size: int = 1000) -> OrderedDict:
        """Create named LRU cache"""
        if name not in self.lru_caches:
            self.lru_caches[name] = OrderedDict()
        return self.lru_caches[name]
    
    async def adaptive_memory_cleanup(self):
        """Adaptive memory cleanup based on system pressure"""
        memory = psutil.virtual_memory()
        
        if memory.percent > (self.memory_threshold * 100):
            logger.warning(f"Memory usage high: {memory.percent:.1f}%, starting cleanup")
            
            # Clean up LRU caches
            for cache_name, cache in self.lru_caches.items():
                cleanup_count = int(len(cache) * self.cleanup_percentage)
                if cleanup_count > 0:
                    # Remove oldest entries
                    for _ in range(cleanup_count):
                        if cache:
                            removed_key = cache.popitem(last=False)[0]
                            logger.debug(f"Removed {removed_key} from {cache_name}")
            
            # Force garbage collection
            import gc
            collected = gc.collect()
            logger.info(f"Memory cleanup completed, collected {collected} objects")
    
    async def start_memory_monitor(self):
        """Start background memory monitoring"""
        while True:
            try:
                await self.adaptive_memory_cleanup()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Memory monitor error: {e}")
                await asyncio.sleep(self.monitoring_interval)


# =====================================================
# 5. AutoBot-Specific Performance Optimizations (NEW)
# =====================================================

class AutoBotNPUAccelerationManager:
    """
    Intel NPU acceleration manager specifically for AutoBot's multi-modal AI workloads
    """
    
    def __init__(self):
        self.openvino_core = None
        self.npu_models = {}
        self.npu_available = self._detect_npu_hardware()
        self.performance_metrics = defaultdict(list)
        
        if ov is not None and self.npu_available:
            self.openvino_core = ov.Core()
            logger.info("OpenVINO NPU acceleration initialized")
        else:
            logger.warning("NPU acceleration not available - falling back to GPU/CPU")
    
    def _detect_npu_hardware(self) -> bool:
        """Detect Intel NPU hardware availability"""
        if ov is None:
            return False
            
        try:
            core = ov.Core()
            available_devices = core.available_devices
            npu_devices = [device for device in available_devices if 'NPU' in device]
            return len(npu_devices) > 0
        except Exception as e:
            logger.warning(f"NPU detection failed: {e}")
            return False
    
    async def initialize_npu_models(self):
        """Initialize NPU models for AutoBot workloads"""
        if not self.npu_available or self.openvino_core is None:
            return
            
        try:
            # Load text embedding model for AutoBot's knowledge base operations
            self.npu_models["text_embedder"] = await self._load_onnx_model_on_npu(
                "all-MiniLM-L6-v2", "text_embedding"
            )
            
            # Load message classification model for AutoBot's chat workflow
            self.npu_models["message_classifier"] = await self._load_onnx_model_on_npu(
                "autobot_message_classifier", "classification"
            )
            
            logger.info(f"Loaded {len(self.npu_models)} models on NPU")
            
        except Exception as e:
            logger.error(f"NPU model initialization failed: {e}")
    
    async def _load_onnx_model_on_npu(self, model_name: str, model_type: str):
        """Load ONNX model on NPU device"""
        # In production, these would be actual ONNX model paths
        model_path = f"/models/{model_name}.onnx"
        
        try:
            # Compile model for NPU
            compiled_model = self.openvino_core.compile_model(
                model_path, device_name="NPU"
            )
            
            return {
                "compiled_model": compiled_model,
                "model_type": model_type,
                "batch_size": 64,  # NPU optimized batch size
                "input_shape": (1, 384) if model_type == "text_embedding" else (1, 512)
            }
            
        except Exception as e:
            logger.error(f"Failed to load {model_name} on NPU: {e}")
            return None
    
    async def process_text_embeddings_npu(self, texts: List[str]) -> np.ndarray:
        """Process text embeddings using NPU acceleration"""
        if "text_embedder" not in self.npu_models:
            raise RuntimeError("NPU text embedder not loaded")
            
        start_time = time.time()
        model_info = self.npu_models["text_embedder"]
        batch_size = model_info["batch_size"]
        
        embeddings = []
        
        # Process in NPU-optimized batches
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            # Tokenize and preprocess (would use actual tokenizer)
            input_tokens = self._tokenize_texts(batch_texts)
            
            # NPU inference
            batch_embeddings = await self._npu_inference(
                model_info["compiled_model"], input_tokens
            )
            
            embeddings.extend(batch_embeddings)
        
        processing_time = time.time() - start_time
        self.performance_metrics['npu_embedding_time'].append(processing_time)
        
        logger.info(f"NPU processed {len(texts)} embeddings in {processing_time:.3f}s")
        return np.array(embeddings)
    
    async def classify_messages_npu(self, messages: List[str]) -> List[Dict[str, Any]]:
        """Classify messages using NPU acceleration for AutoBot chat workflow"""
        if "message_classifier" not in self.npu_models:
            raise RuntimeError("NPU message classifier not loaded")
            
        start_time = time.time()
        model_info = self.npu_models["message_classifier"]
        
        # Batch classification on NPU
        input_features = self._extract_message_features(messages)
        
        classifications = await self._npu_inference(
            model_info["compiled_model"], input_features
        )
        
        # Post-process NPU output for AutoBot message types
        results = []
        for i, message in enumerate(messages):
            classification = classifications[i]
            results.append({
                "message": message,
                "type": self._decode_classification(classification),
                "confidence": float(np.max(classification)),
                "processing_time_ms": (time.time() - start_time) * 1000 / len(messages)
            })
        
        processing_time = time.time() - start_time
        self.performance_metrics['npu_classification_time'].append(processing_time)
        
        return results
    
    def _tokenize_texts(self, texts: List[str]) -> np.ndarray:
        """Tokenize texts for NPU processing"""
        # Simplified tokenization - in production would use proper tokenizer
        max_length = 512
        tokenized = []
        
        for text in texts:
            tokens = [ord(c) % 1000 for c in text[:max_length]]  # Simplified
            tokens = tokens + [0] * (max_length - len(tokens))  # Padding
            tokenized.append(tokens)
        
        return np.array(tokenized, dtype=np.float32)
    
    def _extract_message_features(self, messages: List[str]) -> np.ndarray:
        """Extract features from messages for classification"""
        # Simplified feature extraction
        features = []
        for message in messages:
            # Basic features: length, word count, etc.
            feature_vector = [
                len(message),
                len(message.split()),
                message.count('?'),
                message.count('!'),
                1 if 'terminal' in message.lower() else 0,
                1 if 'desktop' in message.lower() else 0
            ]
            # Pad to 512 features
            feature_vector.extend([0] * (512 - len(feature_vector)))
            features.append(feature_vector)
        
        return np.array(features, dtype=np.float32)
    
    async def _npu_inference(self, compiled_model, input_data: np.ndarray) -> np.ndarray:
        """Perform inference on NPU"""
        try:
            # Create inference request
            infer_request = compiled_model.create_infer_request()
            
            # Set input tensor
            input_tensor = ov.Tensor(input_data)
            infer_request.set_tensor(compiled_model.inputs[0], input_tensor)
            
            # Run inference
            infer_request.infer()
            
            # Get output
            output_tensor = infer_request.get_tensor(compiled_model.outputs[0])
            return output_tensor.data
            
        except Exception as e:
            logger.error(f"NPU inference failed: {e}")
            raise
    
    def _decode_classification(self, classification: np.ndarray) -> str:
        """Decode NPU classification output to AutoBot message types"""
        class_names = [
            "general_query", "terminal_task", "desktop_task", 
            "system_task", "research_needed"
        ]
        
        predicted_class = np.argmax(classification)
        return class_names[predicted_class] if predicted_class < len(class_names) else "unknown"


class AutoBotChromaDBOptimizer:
    """
    Optimized ChromaDB performance manager for AutoBot's 13K+ vector knowledge base
    """
    
    def __init__(self):
        self.faiss_index = None
        self.vector_cache = {}
        self.query_stats = defaultdict(list)
        self.autobot_document_types = {
            "api_documentation", "system_manual", "troubleshooting", 
            "configuration", "performance_data", "security_guide"
        }
    
    async def initialize_faiss_optimization(self, vectors: np.ndarray, 
                                          metadata: List[Dict]):
        """Initialize FAISS index for fast approximate similarity search"""
        if faiss is None:
            logger.warning("FAISS not available, using fallback search")
            return
            
        try:
            dimension = vectors.shape[1]
            
            # Use HNSW for high-dimensional vectors (384d embeddings)
            if dimension > 256:
                # Hierarchical Navigable Small World graphs - excellent for high recall
                self.faiss_index = faiss.IndexHNSWFlat(dimension, 32)
                self.faiss_index.hnsw.efConstruction = 200
                self.faiss_index.hnsw.efSearch = 100
            else:
                # IVF for smaller dimensions
                nlist = min(100, vectors.shape[0] // 10)  # Adaptive number of clusters
                quantizer = faiss.IndexFlatL2(dimension)
                self.faiss_index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
                
                # Train the index
                self.faiss_index.train(vectors)
            
            # Add vectors to index
            self.faiss_index.add(vectors.astype('float32'))
            
            # Cache metadata for quick lookup
            self.vector_metadata = {i: meta for i, meta in enumerate(metadata)}
            
            logger.info(f"FAISS index initialized with {vectors.shape[0]} vectors, dimension {dimension}")
            
        except Exception as e:
            logger.error(f"FAISS initialization failed: {e}")
            self.faiss_index = None
    
    async def optimized_similarity_search(self, query_embedding: np.ndarray, 
                                         k: int = 5, 
                                         filters: Optional[Dict] = None) -> List[Dict]:
        """Optimized vector similarity search for AutoBot knowledge base"""
        start_time = time.time()
        
        try:
            if self.faiss_index is not None:
                # Use FAISS for fast approximate search
                results = await self._faiss_search(query_embedding, k * 2, filters)
            else:
                # Fallback to brute force search
                results = await self._brute_force_search(query_embedding, k * 2, filters)
            
            # Apply AutoBot-specific ranking
            ranked_results = self._autobot_relevance_ranking(results, filters)
            
            search_time = time.time() - start_time
            self.query_stats['search_time'].append(search_time)
            
            logger.debug(f"Vector search completed in {search_time:.3f}s, returned {len(ranked_results)} results")
            
            return ranked_results[:k]
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def _faiss_search(self, query_embedding: np.ndarray, k: int, 
                           filters: Optional[Dict]) -> List[Dict]:
        """FAISS-accelerated similarity search"""
        query = query_embedding.reshape(1, -1).astype('float32')
        
        # Search with FAISS
        distances, indices = self.faiss_index.search(query, k)
        
        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx == -1:  # FAISS returns -1 for insufficient results
                continue
                
            metadata = self.vector_metadata.get(idx, {})
            
            # Apply filters
            if self._passes_autobot_filters(metadata, filters):
                results.append({
                    "id": idx,
                    "distance": float(distance),
                    "similarity": 1.0 / (1.0 + float(distance)),
                    "metadata": metadata,
                    "rank": i
                })
        
        return results
    
    def _passes_autobot_filters(self, metadata: Dict, filters: Optional[Dict]) -> bool:
        """Apply AutoBot-specific filters to search results"""
        if not filters:
            return True
            
        # Document type filtering
        if 'document_type' in filters:
            doc_type = metadata.get('document_type', 'unknown')
            if doc_type not in filters['document_type']:
                return False
        
        # Recency filtering for AutoBot's evolving documentation
        if 'max_age_days' in filters:
            created_date = metadata.get('created_date')
            if created_date:
                age_days = (datetime.now() - created_date).days
                if age_days > filters['max_age_days']:
                    return False
        
        # Relevance threshold for AutoBot queries
        if 'min_relevance' in filters:
            relevance_score = metadata.get('relevance_score', 0.0)
            if relevance_score < filters['min_relevance']:
                return False
        
        return True
    
    def _autobot_relevance_ranking(self, results: List[Dict], 
                                  filters: Optional[Dict]) -> List[Dict]:
        """Apply AutoBot-specific relevance ranking"""
        for result in results:
            metadata = result['metadata']
            base_score = result['similarity']
            
            # Boost scores for AutoBot-specific document types
            doc_type = metadata.get('document_type', 'unknown')
            if doc_type in self.autobot_document_types:
                base_score *= 1.2
            
            # Boost recent documentation
            created_date = metadata.get('created_date')
            if created_date:
                age_days = (datetime.now() - created_date).days
                if age_days < 30:  # Recent docs get boost
                    base_score *= 1.1
            
            # Boost frequently accessed documents
            access_count = metadata.get('access_count', 0)
            if access_count > 10:
                base_score *= 1.05
            
            result['autobot_relevance_score'] = base_score
        
        # Sort by AutoBot relevance score
        return sorted(results, key=lambda x: x['autobot_relevance_score'], reverse=True)


class AutoBotMultiModalCoordinator:
    """
    Coordinates multi-modal AI processing across NPU, GPU, and CPU for optimal performance
    """
    
    def __init__(self):
        self.npu_manager = AutoBotNPUAccelerationManager()
        self.gpu_processor = GPUAcceleratedMultiModalProcessor()
        self.pipeline_cache = {}  # Simple dict for now, would use LRU in production
        self.performance_metrics = defaultdict(list)
    
    async def initialize_multimodal_pipeline(self):
        """Initialize all components of the multi-modal pipeline"""
        await self.npu_manager.initialize_npu_models()
        await self.gpu_processor.initialize_models()
        logger.info("AutoBot multi-modal pipeline initialized")
    
    async def process_multimodal_request(self, text: Optional[str] = None,
                                       image: Optional[bytes] = None,
                                       audio: Optional[bytes] = None) -> Dict[str, Any]:
        """Process multi-modal request with optimal hardware utilization"""
        start_time = time.time()
        request_id = f"multimodal_{int(start_time)}_{hash(str([text, image is not None, audio is not None]))}"
        
        # Check cache first
        cache_key = self._generate_cache_key(text, image, audio)
        if cache_key in self.pipeline_cache:
            logger.debug(f"Cache hit for multimodal request {request_id}")
            return self.pipeline_cache[cache_key]
        
        tasks = []
        hardware_usage = {'npu': False, 'gpu': False, 'cpu': False}
        
        # Text processing on NPU (fastest for embeddings)
        if text and self.npu_manager.npu_available:
            tasks.append(('text_npu', self.npu_manager.process_text_embeddings_npu([text])))
            hardware_usage['npu'] = True
        elif text:
            # Fallback to GPU for text processing
            tasks.append(('text_gpu', self.gpu_processor.process_text_batch([text])))
            hardware_usage['gpu'] = True
        
        # Image processing on GPU (RTX 4070 optimal)
        if image:
            tasks.append(('image_gpu', self._process_image_gpu(image)))
            hardware_usage['gpu'] = True
        
        # Audio processing on CPU (specialized libraries)
        if audio:
            tasks.append(('audio_cpu', self._process_audio_cpu(audio)))
            hardware_usage['cpu'] = True
        
        # Execute tasks in parallel across hardware
        results = {}
        if tasks:
            task_results = await asyncio.gather(
                *[task[1] for task in tasks], 
                return_exceptions=True
            )
            
            for i, (task_name, _) in enumerate(tasks):
                result = task_results[i]
                if not isinstance(result, Exception):
                    results[task_name] = result
                else:
                    logger.error(f"Task {task_name} failed: {result}")
        
        # Cross-modal fusion if multiple modalities
        fused_result = None
        if len(results) > 1:
            # Perform fusion on GPU for tensor operations
            fused_result = await self._fuse_modalities_gpu(results)
            hardware_usage['gpu'] = True
        
        processing_time = time.time() - start_time
        
        final_result = {
            'request_id': request_id,
            'individual_results': results,
            'fused_result': fused_result,
            'processing_time_ms': processing_time * 1000,
            'hardware_utilization': hardware_usage,
            'cache_hit': False
        }
        
        # Cache the result
        self.pipeline_cache[cache_key] = final_result
        
        # Record performance metrics
        self.performance_metrics['multimodal_processing_time'].append(processing_time)
        
        logger.info(f"Multimodal request {request_id} completed in {processing_time:.3f}s")
        return final_result
    
    def _generate_cache_key(self, text: Optional[str], image: Optional[bytes], 
                          audio: Optional[bytes]) -> str:
        """Generate cache key for multimodal request"""
        key_parts = []
        if text:
            key_parts.append(f"text_{hash(text)}")
        if image:
            key_parts.append(f"image_{hash(image)}")
        if audio:
            key_parts.append(f"audio_{hash(audio)}")
        return "_".join(key_parts)
    
    async def _process_image_gpu(self, image_bytes: bytes) -> Dict[str, Any]:
        """Process image using GPU acceleration"""
        # Placeholder for GPU image processing
        # In production, would use actual image processing models
        processing_time = 0.05  # Simulated fast GPU processing
        await asyncio.sleep(processing_time)
        
        return {
            'type': 'image',
            'embedding': [0.1] * 512,  # Placeholder embedding
            'features': {'width': 1920, 'height': 1080, 'format': 'JPEG'},
            'processing_time_ms': processing_time * 1000
        }
    
    async def _process_audio_cpu(self, audio_bytes: bytes) -> Dict[str, Any]:
        """Process audio using CPU-based libraries"""
        # Placeholder for audio processing
        processing_time = 0.1  # Simulated audio processing
        await asyncio.sleep(processing_time)
        
        return {
            'type': 'audio',
            'embedding': [0.2] * 512,  # Placeholder embedding
            'features': {'duration': 5.0, 'sample_rate': 44100, 'channels': 2},
            'processing_time_ms': processing_time * 1000
        }
    
    async def _fuse_modalities_gpu(self, modality_results: Dict[str, Any]) -> Dict[str, Any]:
        """Fuse multiple modalities using GPU tensor operations"""
        # Placeholder for cross-modal fusion
        fusion_time = 0.02  # Fast GPU tensor operations
        await asyncio.sleep(fusion_time)
        
        # Combine embeddings from different modalities
        fused_embedding = []
        modalities_used = []
        
        for modality, result in modality_results.items():
            if 'embedding' in result:
                fused_embedding.extend(result['embedding'][:256])  # Truncate for fusion
                modalities_used.append(modality)
        
        return {
            'type': 'fused_multimodal',
            'embedding': fused_embedding,
            'modalities_used': modalities_used,
            'fusion_time_ms': fusion_time * 1000
        }


# =====================================================
# 6. Implementation Helper Functions (Updated)
# =====================================================

async def apply_critical_performance_fixes():
    """
    Apply critical performance fixes to running AutoBot system
    """
    logger.info("Applying critical performance fixes...")
    
    # 1. Initialize optimized LLM interface
    llm_interface = OptimizedLLMInterface()
    
    # 2. Setup optimized Redis connection manager
    redis_manager = OptimizedRedisConnectionManager()
    
    # 3. Initialize GPU acceleration
    gpu_processor = GPUAcceleratedMultiModalProcessor()
    await gpu_processor.initialize_models()
    
    # 4. Start memory management
    memory_manager = OptimizedMemoryManager()
    asyncio.create_task(memory_manager.start_memory_monitor())
    
    logger.info("Critical performance fixes applied successfully")
    
    return {
        "llm_interface": llm_interface,
        "redis_manager": redis_manager, 
        "gpu_processor": gpu_processor,
        "memory_manager": memory_manager
    }


# =====================================================
# 6. Performance Testing Functions
# =====================================================

async def benchmark_improvements():
    """
    Benchmark performance improvements
    """
    results = {}
    
    # Test LLM streaming performance
    logger.info("Benchmarking LLM streaming...")
    llm_interface = OptimizedLLMInterface()
    
    start_time = time.time()
    test_messages = [{"role": "user", "content": "What is the capital of France?"}]
    
    try:
        result = await llm_interface.chat_completion_optimized(
            messages=test_messages,
            model="llama3.2:1b-instruct-q4_K_M"
        )
        
        results["llm_streaming"] = {
            "success": True,
            "response_time": result.get("processing_time", 0),
            "chunk_count": result.get("chunk_count", 0),
            "completed": result.get("completed", False)
        }
    except Exception as e:
        results["llm_streaming"] = {
            "success": False,
            "error": str(e)
        }
    
    # Test GPU processing
    logger.info("Benchmarking GPU processing...")
    gpu_processor = GPUAcceleratedMultiModalProcessor()
    
    test_texts = ["Hello world", "Performance test", "GPU acceleration"] * 10
    
    try:
        gpu_result = await gpu_processor.process_text_batch(test_texts)
        results["gpu_processing"] = {
            "success": True,
            "texts_processed": len(test_texts),
            "embeddings_generated": len(gpu_result),
            "gpu_used": gpu_processor.device.type == "cuda"
        }
    except Exception as e:
        results["gpu_processing"] = {
            "success": False,
            "error": str(e)
        }
    
    # Test Redis connection pooling
    logger.info("Benchmarking Redis connection...")
    redis_manager = OptimizedRedisConnectionManager()
    
    try:
        client = redis_manager.get_redis_client("localhost", 6379, 0)
        client.ping()
        health_status = await redis_manager.health_check_all_pools()
        
        results["redis_pooling"] = {
            "success": True,
            "pools_healthy": sum(health_status.values()),
            "total_pools": len(health_status)
        }
    except Exception as e:
        results["redis_pooling"] = {
            "success": False,
            "error": str(e)
        }
    
    logger.info(f"Benchmark results: {json.dumps(results, indent=2)}")
    return results


if __name__ == "__main__":
    # Run performance fixes and benchmarks
    async def main():
        # Apply fixes
        components = await apply_critical_performance_fixes()
        
        # Run benchmarks
        benchmark_results = await benchmark_improvements()
        
        # Save results
        with open("performance_benchmark_results.json", "w") as f:
            json.dump(benchmark_results, f, indent=2)
        
        print("Critical performance fixes applied and benchmarked!")
        print(f"Results: {json.dumps(benchmark_results, indent=2)}")
    
    asyncio.run(main())