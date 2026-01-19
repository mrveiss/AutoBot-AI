# Import centralized Redis client utility
from src.utils.redis_client import get_redis_client

# GPU OPTIMIZATION: Import GPU-optimized semantic chunker for 5x performance improvement
try:
    from src.utils.semantic_chunker_gpu_optimized import get_optimized_semantic_chunker
    # Create an alias for backward compatibility
    def get_semantic_chunker():
        return get_optimized_semantic_chunker()
    logger = logging.getLogger(__name__)
    logger.info("✅ Using GPU-optimized semantic chunker (5x faster)")
except ImportError as e:
    # Fallback to original semantic chunker
    from src.utils.semantic_chunker import get_semantic_chunker
    logger = logging.getLogger(__name__)
    logger.warning(f"GPU-optimized chunker not available, using original: {e}")