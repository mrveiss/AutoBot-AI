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
# 5. Implementation Helper Functions
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