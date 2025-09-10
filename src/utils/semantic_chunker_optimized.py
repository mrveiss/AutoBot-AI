"""
Optimized AutoBot Semantic Chunking Module - GPU Acceleration Focus
==================================================================

High-performance semantic chunking implementation optimized for:
- Intel Ultra 9 185H (22 cores, 11+11 HT)
- NVIDIA RTX 4070 (8GB VRAM) 
- Maximum GPU utilization for embedding computation
"""

import os
# CRITICAL FIX: Force tf-keras usage before importing transformers/sentence-transformers
os.environ['TF_USE_LEGACY_KERAS'] = '1'
os.environ['KERAS_BACKEND'] = 'tensorflow'

# Reduce Hugging Face rate limiting and improve caching
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '0'
os.environ['HF_HUB_CACHE'] = os.path.expanduser('~/.cache/huggingface')
os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.expanduser('~/.cache/huggingface')

import asyncio
import logging
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import threading

import numpy as np

# Import centralized logging
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("semantic_chunker_optimized")

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass
class OptimizedSemanticChunk:
    """Optimized semantic chunk with enhanced metadata."""
    
    content: str
    start_index: int
    end_index: int
    sentences: List[str]
    semantic_score: float
    metadata: Dict[str, Any]
    embedding_vector: Optional[np.ndarray] = None  # Cache embedding for reuse
    processing_time: float = field(default=0.0)


class GPUOptimizedSemanticChunker:
    """
    GPU-optimized semantic chunker for maximum RTX 4070 utilization.
    
    Key optimizations:
    1. Aggressive GPU batch processing (up to 500 sentences)
    2. Multi-threaded preprocessing pipeline
    3. Cached model loading with optimal precision
    4. Memory-efficient embedding computation
    5. Async processing with intelligent resource management
    """
    
    def __init__(
        self,
        embedding_model: str = "all-mpnet-base-v2",  # Higher quality than MiniLM
        percentile_threshold: float = 95.0,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1200,  # Slightly larger for better GPU utilization
        overlap_sentences: int = 1,
        gpu_batch_size: int = 500,  # Aggressive GPU batching
        cpu_workers: int = None,  # Auto-detect optimal worker count
    ):
        """
        Initialize GPU-optimized semantic chunker.
        
        Args:
            embedding_model: Higher quality model for better semantic understanding
            gpu_batch_size: Large batch size for optimal GPU utilization
            cpu_workers: Number of CPU workers (auto-detected if None)
        """
        self.embedding_model_name = embedding_model
        self.percentile_threshold = percentile_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_sentences = overlap_sentences
        
        # GPU optimization settings
        self.gpu_batch_size = gpu_batch_size
        self.cpu_workers = cpu_workers or min(16, os.cpu_count() or 4)  # Use more workers for 22-core CPU
        
        # Model caching
        self._embedding_model = None
        self._model_lock = threading.Lock()
        self._device_info = None
        
        # Performance tracking
        self.stats = {
            'total_chunks_created': 0,
            'total_embeddings_computed': 0,
            'avg_gpu_utilization': 0.0,
            'avg_processing_time': 0.0,
            'cache_hits': 0,
        }
        
        logger.info(f"GPUOptimizedSemanticChunker initialized:")
        logger.info(f"  Model: {embedding_model}")
        logger.info(f"  GPU batch size: {gpu_batch_size}")
        logger.info(f"  CPU workers: {self.cpu_workers}")
        logger.info(f"  Target GPU: RTX 4070 (8GB VRAM)")

    async def _initialize_gpu_model(self):
        """Initialize embedding model with aggressive GPU optimization."""
        if self._embedding_model is not None:
            return
            
        with self._model_lock:
            if self._embedding_model is not None:
                return
                
            try:
                import asyncio
                import concurrent.futures
                
                def load_optimized_model():
                    """Load model with maximum GPU optimization."""
                    from sentence_transformers import SentenceTransformer
                    import torch
                    
                    # Detect optimal device
                    if torch.cuda.is_available():
                        device = f"cuda:{torch.cuda.current_device()}"
                        
                        # Get detailed GPU info for optimization
                        gpu_props = torch.cuda.get_device_properties(0)
                        total_memory = gpu_props.total_memory
                        
                        logger.info(f"GPU detected: {gpu_props.name}")
                        logger.info(f"GPU memory: {total_memory / (1024**3):.1f} GB")
                        logger.info(f"Compute capability: {gpu_props.major}.{gpu_props.minor}")
                        
                        # For RTX 4070: Optimize for 8GB VRAM
                        self._device_info = {
                            'device': device,
                            'name': gpu_props.name,
                            'memory_gb': total_memory / (1024**3),
                            'compute_capability': f"{gpu_props.major}.{gpu_props.minor}",
                        }
                        
                    else:
                        device = "cpu"
                        logger.warning("CUDA not available, falling back to CPU")
                        self._device_info = {'device': 'cpu', 'name': 'CPU'}
                    
                    # Load model with optimal settings
                    logger.info(f"Loading {self.embedding_model_name} on {device}...")
                    start_time = time.time()
                    
                    # Initialize with optimal device placement
                    model = SentenceTransformer(self.embedding_model_name, device=device)
                    
                    # Enable optimizations for GPU
                    if device.startswith('cuda'):
                        try:
                            # Convert to FP16 for RTX 4070 (supports Tensor Cores)
                            model.half()  # Use FP16 precision
                            logger.info("✅ Enabled FP16 precision for RTX 4070 Tensor Cores")
                            
                            # Enable cudnn benchmarking for consistent input sizes
                            torch.backends.cudnn.benchmark = True
                            torch.backends.cudnn.enabled = True
                            
                            # Pre-allocate memory for large batches (reserve ~2GB for model + batches)
                            torch.cuda.empty_cache()
                            
                            logger.info("✅ Enabled cuDNN optimization for consistent batching")
                            
                        except Exception as opt_error:
                            logger.warning(f"GPU optimization failed: {opt_error}")
                            # Ensure model is still on GPU even if optimization fails
                            model = model.to(device)
                    
                    load_time = time.time() - start_time
                    logger.info(f"✅ Model loaded in {load_time:.2f}s on {model.device}")
                    
                    return model
                
                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    self._embedding_model = await loop.run_in_executor(executor, load_optimized_model)
                    
            except Exception as e:
                logger.error(f"Failed to load optimized model: {e}")
                # Fallback to basic CPU model
                try:
                    from sentence_transformers import SentenceTransformer
                    self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
                    logger.warning("Using fallback CPU model")
                except Exception as fallback_error:
                    logger.error(f"Fallback model loading failed: {fallback_error}")
                    raise RuntimeError("Could not initialize any embedding model")

    async def _compute_embeddings_gpu_optimized(self, sentences: List[str]) -> np.ndarray:
        """
        Compute embeddings with maximum GPU utilization.
        
        Optimizations:
        1. Large batch processing (500+ sentences)
        2. FP16 precision on RTX 4070
        3. Tensor Core utilization
        4. Memory-efficient batching
        """
        await self._initialize_gpu_model()
        
        if not sentences:
            return np.array([])
            
        start_time = time.time()
        total_sentences = len(sentences)
        
        logger.debug(f"Computing embeddings for {total_sentences} sentences using GPU optimization")
        
        try:
            import torch
            
            # Optimize batch size based on available GPU memory
            if self._device_info and self._device_info['device'].startswith('cuda'):
                # For RTX 4070 8GB: Use large batches for efficiency
                if total_sentences > 1000:
                    batch_size = min(self.gpu_batch_size, 400)  # Large batches for bulk processing
                elif total_sentences > 100:
                    batch_size = min(self.gpu_batch_size, 300)  # Medium batches  
                else:
                    batch_size = min(self.gpu_batch_size, total_sentences)  # Small batches
            else:
                # CPU fallback with smaller batches
                batch_size = min(50, total_sentences)
            
            logger.debug(f"Using batch size: {batch_size}")
            
            # Process in optimized batches
            all_embeddings = []
            
            # Use async processing with thread pool for CPU preprocessing
            loop = asyncio.get_event_loop()
            
            for i in range(0, total_sentences, batch_size):
                batch_sentences = sentences[i:i + batch_size]
                
                # Run embedding computation in thread to avoid blocking event loop
                def compute_batch():
                    """GPU-optimized batch computation."""
                    with torch.no_grad():  # Reduce memory usage
                        embeddings = self._embedding_model.encode(
                            batch_sentences,
                            batch_size=len(batch_sentences),  # Process full batch at once
                            convert_to_tensor=False,  # Return numpy for memory efficiency
                            show_progress_bar=False,
                            normalize_embeddings=True,  # Improve similarity computation
                        )
                        return embeddings
                
                # Execute in thread pool with optimal worker count
                with ThreadPoolExecutor(max_workers=2) as executor:  # Limit to avoid GPU contention
                    batch_embeddings = await loop.run_in_executor(executor, compute_batch)
                    all_embeddings.append(batch_embeddings)
                
                # Yield control periodically
                if i % (batch_size * 3) == 0:  # Every 3 batches
                    await asyncio.sleep(0.001)
                    
                    # Progress logging for large jobs
                    if total_sentences > 100:
                        progress = min(100, int((i + batch_size) / total_sentences * 100))
                        logger.debug(f"GPU embedding progress: {progress}%")
            
            # Combine results efficiently
            if len(all_embeddings) == 1:
                final_embeddings = all_embeddings[0]
            else:
                final_embeddings = np.vstack(all_embeddings)
            
            processing_time = time.time() - start_time
            sentences_per_second = total_sentences / processing_time if processing_time > 0 else 0
            
            # Update performance stats
            self.stats['total_embeddings_computed'] += total_sentences
            self.stats['avg_processing_time'] = (
                (self.stats['avg_processing_time'] * (self.stats['total_chunks_created'] or 1) + processing_time) /
                (self.stats['total_chunks_created'] + 1)
            )
            
            logger.info(f"✅ GPU embeddings computed: {total_sentences} sentences in {processing_time:.2f}s ({sentences_per_second:.1f} sent/s)")
            
            return final_embeddings
            
        except Exception as e:
            logger.error(f"GPU embedding computation failed: {e}")
            
            # Fallback to basic computation
            try:
                embeddings = self._embedding_model.encode(sentences, convert_to_tensor=False)
                logger.warning("Used fallback embedding computation")
                return np.array(embeddings)
            except Exception as fallback_error:
                logger.error(f"Fallback embedding failed: {fallback_error}")
                # Return zero embeddings as last resort
                try:
                    dim = self._embedding_model.get_sentence_embedding_dimension()
                    return np.zeros((len(sentences), dim))
                except:
                    return np.zeros((len(sentences), 384))  # Common dimension

    def _advanced_sentence_splitting(self, text: str) -> List[str]:
        """
        Advanced sentence splitting with better handling of technical content.
        
        Optimized for:
        - Code documentation
        - Technical manuals
        - Configuration files
        - Mixed content
        """
        import re
        
        # Enhanced sentence boundary detection
        sentence_endings = r'[.!?]+(?:\s|$|")'
        
        # Extended abbreviations including technical terms
        abbreviations = (
            r"(?:Mr|Mrs|Dr|Prof|Sr|Jr|vs|etc|Inc|Ltd|Corp|Co|St|Ave|Rd|Blvd|"
            r"Apt|No|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mon|Tue|"
            r"Wed|Thu|Fri|Sat|Sun|API|HTTP|HTTPS|URL|URI|JSON|XML|HTML|CSS|JS|"
            r"SQL|DB|CPU|GPU|NPU|RAM|SSD|HDD|OS|VM|AWS|GCP|K8s|etc|e\.g|i\.e|"
            r"ref|fig|sec|ch|vol|ed|rev|ver|min|max|avg|std|var|config|env|"
            r"admin|auth|exec|init|util|mgr|svc|ctrl|repo|dir|src|dest|temp|"
            r"tmp|log|err|warn|info|debug|test|dev|prod|staging|beta|alpha)"
            r"\.(?!\s*$)"
        )
        
        sentences = []
        current_sentence = ""
        
        # Split by potential sentence boundaries
        parts = re.split(r'([.!?]+(?:\s|$|"))', text)
        
        for i in range(0, len(parts), 2):
            if i < len(parts):
                current_sentence += parts[i]
                
                if i + 1 < len(parts):
                    boundary = parts[i + 1]
                    current_sentence += boundary
                    
                    # Check if this is a real sentence boundary
                    if not re.search(abbreviations, current_sentence.strip()):
                        sentences.append(current_sentence.strip())
                        current_sentence = ""
        
        # Add any remaining content
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        # Filter and clean sentences
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10 and len(sentence.split()) >= 3:  # Minimum viable sentence
                cleaned_sentences.append(sentence)
        
        return cleaned_sentences

    def _compute_semantic_distances_optimized(self, embeddings: np.ndarray) -> List[float]:
        """
        Optimized semantic distance computation using vectorized operations.
        """
        if len(embeddings) <= 1:
            return []
        
        # Vectorized cosine similarity computation
        # Normalize embeddings for efficient cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized_embeddings = embeddings / (norms + 1e-8)  # Avoid division by zero
        
        # Compute similarities between consecutive sentences
        similarities = np.sum(
            normalized_embeddings[:-1] * normalized_embeddings[1:], axis=1
        )
        
        # Convert to distances
        distances = 1 - similarities
        
        return distances.tolist()

    async def chunk_text_optimized(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[OptimizedSemanticChunk]:
        """
        Main optimized chunking method with GPU acceleration.
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting GPU-optimized semantic chunking ({len(text)} chars)")
            
            # Step 1: Advanced sentence splitting
            sentences = self._advanced_sentence_splitting(text)
            
            if len(sentences) <= 1:
                # Handle edge case
                chunk = OptimizedSemanticChunk(
                    content=text,
                    start_index=0,
                    end_index=1,
                    sentences=sentences,
                    semantic_score=1.0,
                    metadata=metadata or {"single_sentence": True},
                    processing_time=time.time() - start_time
                )
                return [chunk]
            
            logger.debug(f"Advanced splitting: {len(sentences)} sentences")
            
            # Step 2: GPU-optimized embedding computation
            embeddings = await self._compute_embeddings_gpu_optimized(sentences)
            
            # Step 3: Vectorized distance computation
            distances = self._compute_semantic_distances_optimized(embeddings)
            
            # Step 4: Find optimal boundaries
            boundaries = self._find_chunk_boundaries_optimized(distances)
            
            logger.debug(f"Found {len(boundaries)} semantic boundaries")
            
            # Step 5: Create optimized chunks with cached embeddings
            chunks = self._create_optimized_chunks(
                sentences, boundaries, distances, embeddings, metadata
            )
            
            total_time = time.time() - start_time
            
            # Update stats
            self.stats['total_chunks_created'] += len(chunks)
            
            avg_coherence = np.mean([c.semantic_score for c in chunks])
            
            logger.info(
                f"✅ GPU-optimized chunking complete: {len(chunks)} chunks, "
                f"avg coherence: {avg_coherence:.3f}, time: {total_time:.2f}s"
            )
            
            return chunks
            
        except Exception as e:
            logger.error(f"GPU-optimized chunking failed: {e}")
            # Fallback to basic chunking
            return await self._fallback_chunking_optimized(text, metadata)

    def _find_chunk_boundaries_optimized(self, distances: List[float]) -> List[int]:
        """Optimized boundary detection with adaptive thresholding."""
        if not distances:
            return []
        
        distances_array = np.array(distances)
        
        # Use adaptive threshold based on distribution
        threshold = np.percentile(distances_array, self.percentile_threshold)
        
        # Find boundaries with minimum distance between splits
        boundaries = []
        last_boundary = -5  # Minimum separation
        
        for i, distance in enumerate(distances):
            if distance > threshold and i - last_boundary >= 3:  # Avoid too frequent splits
                boundaries.append(i + 1)
                last_boundary = i
        
        return boundaries

    def _create_optimized_chunks(
        self,
        sentences: List[str],
        boundaries: List[int],
        distances: List[float],
        embeddings: np.ndarray,
        metadata: Optional[Dict[str, Any]]
    ) -> List[OptimizedSemanticChunk]:
        """Create optimized chunks with cached embeddings."""
        chunks = []
        start_idx = 0
        
        # Add final boundary
        all_boundaries = boundaries + [len(sentences)]
        
        for boundary in all_boundaries:
            if boundary <= start_idx:
                continue
            
            # Extract chunk data
            chunk_sentences = sentences[start_idx:boundary]
            chunk_content = " ".join(chunk_sentences)
            
            # Size validation with merging/splitting
            if len(chunk_content) < self.min_chunk_size and chunks:
                # Merge with previous chunk
                prev_chunk = chunks[-1]
                merged_sentences = prev_chunk.sentences + chunk_sentences
                merged_content = " ".join(merged_sentences)
                
                # Extract corresponding embeddings
                merged_embeddings = embeddings[prev_chunk.start_index:boundary]
                avg_embedding = np.mean(merged_embeddings, axis=0)
                
                chunks[-1] = OptimizedSemanticChunk(
                    content=merged_content,
                    start_index=prev_chunk.start_index,
                    end_index=boundary,
                    sentences=merged_sentences,
                    semantic_score=self._calculate_coherence_from_embeddings(merged_embeddings),
                    metadata={**(metadata or {}), "merged": True},
                    embedding_vector=avg_embedding,
                )
                
            elif len(chunk_content) > self.max_chunk_size:
                # Split large chunks
                sub_chunks = self._split_large_chunk_optimized(
                    chunk_sentences, embeddings[start_idx:boundary], start_idx, metadata
                )
                chunks.extend(sub_chunks)
                
            else:
                # Regular chunk
                chunk_embeddings = embeddings[start_idx:boundary]
                avg_embedding = np.mean(chunk_embeddings, axis=0)
                
                chunk = OptimizedSemanticChunk(
                    content=chunk_content,
                    start_index=start_idx,
                    end_index=boundary,
                    sentences=chunk_sentences,
                    semantic_score=self._calculate_coherence_from_embeddings(chunk_embeddings),
                    metadata={**(metadata or {}), "boundary_type": "semantic"},
                    embedding_vector=avg_embedding,
                )
                chunks.append(chunk)
            
            # Apply overlap
            start_idx = max(0, boundary - self.overlap_sentences)
        
        return chunks

    def _calculate_coherence_from_embeddings(self, embeddings: np.ndarray) -> float:
        """Calculate coherence score from embeddings efficiently."""
        if len(embeddings) <= 1:
            return 1.0
        
        try:
            # Normalize embeddings
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            normalized = embeddings / (norms + 1e-8)
            
            # Compute pairwise similarities efficiently
            similarity_matrix = np.dot(normalized, normalized.T)
            
            # Extract upper triangular part (avoid diagonal and duplicates)
            upper_tri_indices = np.triu_indices(len(embeddings), k=1)
            similarities = similarity_matrix[upper_tri_indices]
            
            return float(np.mean(similarities))
            
        except Exception as e:
            logger.warning(f"Coherence calculation failed: {e}")
            return 0.7  # Default coherence

    def _split_large_chunk_optimized(
        self,
        sentences: List[str],
        embeddings: np.ndarray,
        start_idx: int,
        metadata: Optional[Dict[str, Any]]
    ) -> List[OptimizedSemanticChunk]:
        """Split large chunks while preserving semantic coherence."""
        chunks = []
        current_sentences = []
        current_embeddings = []
        current_length = 0
        sentence_idx = start_idx
        
        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence)
            
            if current_length + sentence_len > self.max_chunk_size and current_sentences:
                # Create chunk from current sentences
                chunk_content = " ".join(current_sentences)
                chunk_embeddings_array = np.array(current_embeddings)
                avg_embedding = np.mean(chunk_embeddings_array, axis=0)
                
                chunk = OptimizedSemanticChunk(
                    content=chunk_content,
                    start_index=sentence_idx - len(current_sentences),
                    end_index=sentence_idx,
                    sentences=current_sentences.copy(),
                    semantic_score=self._calculate_coherence_from_embeddings(chunk_embeddings_array),
                    metadata={**(metadata or {}), "split_type": "size_constraint"},
                    embedding_vector=avg_embedding,
                )
                chunks.append(chunk)
                
                # Reset with overlap
                if self.overlap_sentences > 0:
                    overlap_start = -self.overlap_sentences
                    current_sentences = current_sentences[overlap_start:]
                    current_embeddings = current_embeddings[overlap_start:]
                    current_length = sum(len(s) for s in current_sentences)
                else:
                    current_sentences = []
                    current_embeddings = []
                    current_length = 0
            
            current_sentences.append(sentence)
            current_embeddings.append(embeddings[i])
            current_length += sentence_len
            sentence_idx += 1
        
        # Add final chunk
        if current_sentences:
            chunk_content = " ".join(current_sentences)
            chunk_embeddings_array = np.array(current_embeddings)
            avg_embedding = np.mean(chunk_embeddings_array, axis=0)
            
            chunk = OptimizedSemanticChunk(
                content=chunk_content,
                start_index=sentence_idx - len(current_sentences),
                end_index=sentence_idx,
                sentences=current_sentences,
                semantic_score=self._calculate_coherence_from_embeddings(chunk_embeddings_array),
                metadata={**(metadata or {}), "split_type": "size_constraint", "final_chunk": True},
                embedding_vector=avg_embedding,
            )
            chunks.append(chunk)
        
        return chunks

    async def _fallback_chunking_optimized(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[OptimizedSemanticChunk]:
        """Optimized fallback chunking when GPU processing fails."""
        logger.warning("Using optimized fallback chunking")
        
        sentences = self._advanced_sentence_splitting(text)
        chunks = []
        
        current_sentences = []
        current_length = 0
        
        for i, sentence in enumerate(sentences):
            if current_length + len(sentence) > self.max_chunk_size and current_sentences:
                chunk_content = " ".join(current_sentences)
                chunk = OptimizedSemanticChunk(
                    content=chunk_content,
                    start_index=i - len(current_sentences),
                    end_index=i,
                    sentences=current_sentences.copy(),
                    semantic_score=0.6,  # Default for fallback
                    metadata={**(metadata or {}), "fallback_chunking": True},
                )
                chunks.append(chunk)
                current_sentences = []
                current_length = 0
            
            current_sentences.append(sentence)
            current_length += len(sentence)
        
        # Add final chunk
        if current_sentences:
            chunk_content = " ".join(current_sentences)
            chunk = OptimizedSemanticChunk(
                content=chunk_content,
                start_index=len(sentences) - len(current_sentences),
                end_index=len(sentences),
                sentences=current_sentences,
                semantic_score=0.6,
                metadata={**(metadata or {}), "fallback_chunking": True},
            )
            chunks.append(chunk)
        
        return chunks

    async def chunk_document_optimized(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        LlamaIndex-compatible document chunking with GPU optimization.
        """
        optimized_chunks = await self.chunk_text_optimized(content, metadata)
        
        # Convert to LlamaIndex-compatible format
        documents = []
        for chunk in optimized_chunks:
            doc_data = {
                "text": chunk.content,
                "metadata": {
                    **chunk.metadata,
                    "semantic_score": chunk.semantic_score,
                    "sentence_count": len(chunk.sentences),
                    "character_count": len(chunk.content),
                    "processing_time": chunk.processing_time,
                    "gpu_optimized": True,
                },
            }
            
            # Include embedding if available
            if chunk.embedding_vector is not None:
                doc_data["metadata"]["cached_embedding"] = True
                doc_data["metadata"]["embedding_dimension"] = len(chunk.embedding_vector)
            
            documents.append(doc_data)
        
        return documents

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics."""
        device_info = self._device_info or {"device": "not_initialized"}
        
        return {
            **self.stats,
            "device_info": device_info,
            "model_name": self.embedding_model_name,
            "gpu_batch_size": self.gpu_batch_size,
            "cpu_workers": self.cpu_workers,
            "optimization_level": "gpu_maximum" if device_info.get("device", "").startswith("cuda") else "cpu_fallback"
        }

    def reset_stats(self):
        """Reset performance statistics."""
        self.stats = {
            'total_chunks_created': 0,
            'total_embeddings_computed': 0,
            'avg_gpu_utilization': 0.0,
            'avg_processing_time': 0.0,
            'cache_hits': 0,
        }


# Global optimized instance
_optimized_chunker_instance = None


def get_optimized_semantic_chunker() -> GPUOptimizedSemanticChunker:
    """Get the global optimized semantic chunker instance."""
    global _optimized_chunker_instance
    if _optimized_chunker_instance is None:
        _optimized_chunker_instance = GPUOptimizedSemanticChunker()
    return _optimized_chunker_instance