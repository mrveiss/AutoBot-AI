"""
RAG Query Performance Benchmarks

Benchmark tests for Retrieval-Augmented Generation (RAG) operations
including vector search, document retrieval, and context assembly.

Issue #58 - Performance Benchmarking Suite
Author: mrveiss
"""

import random
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.benchmarks.benchmark_base import (
    BenchmarkRunner,
    assert_performance,
)


class TestRAGQueryBenchmarks:
    """Benchmark tests for RAG operations"""

    @pytest.fixture
    def runner(self):
        """Create benchmark runner"""
        return BenchmarkRunner(warmup_iterations=2, default_iterations=10)

    @pytest.fixture
    def mock_embeddings(self):
        """Generate mock embedding vectors"""
        # Simulate 384-dimensional embeddings (all-MiniLM-L6-v2 style)
        return [[random.random() for _ in range(384)] for _ in range(100)]

    @pytest.fixture
    def mock_documents(self):
        """Generate mock documents for retrieval"""
        return [
            {
                "id": f"doc_{i}",
                "content": f"This is test document {i} with some content for testing RAG retrieval performance.",
                "metadata": {"source": "test", "page": i},
                "embedding": [random.random() for _ in range(384)],
            }
            for i in range(1000)
        ]

    def test_vector_similarity_computation_benchmark(self, runner, mock_embeddings):
        """Benchmark vector similarity computation"""
        import numpy as np

        query_vector = np.array([random.random() for _ in range(384)])
        doc_vectors = np.array(mock_embeddings[:50])

        def compute_similarity():
            # Cosine similarity
            query_norm = query_vector / np.linalg.norm(query_vector)
            doc_norms = doc_vectors / np.linalg.norm(doc_vectors, axis=1, keepdims=True)
            similarities = np.dot(doc_norms, query_norm)
            return similarities

        result = runner.run_benchmark(
            name="rag_vector_similarity_50_docs",
            func=compute_similarity,
            iterations=100,
            metadata={"num_documents": 50, "vector_dim": 384},
        )

        print(f"\nVector Similarity Benchmark (50 docs):")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # Vector similarity should be fast
        assert_performance(result, max_avg_ms=5.0, min_ops_per_second=200)

    def test_top_k_retrieval_benchmark(self, runner, mock_documents):
        """Benchmark top-k document retrieval"""
        import heapq
        import random

        query_vector = [random.random() for _ in range(384)]
        documents = mock_documents

        def retrieve_top_k(k=5):
            # Simulate similarity scoring
            scored_docs = []
            for doc in documents:
                # Simple dot product for speed
                score = sum(a * b for a, b in zip(query_vector[:10], doc["embedding"][:10]))
                scored_docs.append((score, doc))

            # Get top k
            top_k = heapq.nlargest(k, scored_docs, key=lambda x: x[0])
            return [doc for score, doc in top_k]

        result = runner.run_benchmark(
            name="rag_top_k_retrieval_1000_docs",
            func=lambda: retrieve_top_k(5),
            iterations=20,
            metadata={"num_documents": 1000, "top_k": 5},
        )

        print(f"\nTop-K Retrieval Benchmark (1000 docs, k=5):")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")

        assert result.passed

    def test_context_assembly_benchmark(self, runner):
        """Benchmark context window assembly from retrieved documents"""
        retrieved_docs = [
            {
                "content": f"Document {i} contains important information about the topic. " * 10,
                "metadata": {"source": f"source_{i}", "relevance": 0.9 - i * 0.1},
            }
            for i in range(10)
        ]

        def assemble_context(max_tokens=2048):
            context_parts = []
            current_tokens = 0

            for doc in retrieved_docs:
                # Approximate token count (chars / 4)
                doc_tokens = len(doc["content"]) // 4
                if current_tokens + doc_tokens <= max_tokens:
                    context_parts.append(doc["content"])
                    current_tokens += doc_tokens
                else:
                    break

            return "\n\n".join(context_parts)

        result = runner.run_benchmark(
            name="rag_context_assembly",
            func=assemble_context,
            iterations=100,
            metadata={"max_tokens": 2048, "num_docs": 10},
        )

        print(f"\nContext Assembly Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # Context assembly should be very fast
        assert_performance(result, max_avg_ms=1.0, min_ops_per_second=1000)

    def test_document_chunking_benchmark(self, runner):
        """Benchmark document chunking for indexing"""
        long_document = "This is a paragraph of text. " * 500  # ~15000 chars

        def chunk_document(chunk_size=500, overlap=50):
            chunks = []
            start = 0
            while start < len(long_document):
                end = min(start + chunk_size, len(long_document))
                chunks.append(long_document[start:end])
                start = end - overlap if end < len(long_document) else len(long_document)
            return chunks

        result = runner.run_benchmark(
            name="rag_document_chunking",
            func=chunk_document,
            iterations=100,
            metadata={"doc_size": len(long_document), "chunk_size": 500, "overlap": 50},
        )

        print(f"\nDocument Chunking Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed

    def test_metadata_filtering_benchmark(self, runner, mock_documents):
        """Benchmark metadata filtering performance"""

        def filter_by_metadata(source_filter="test"):
            return [doc for doc in mock_documents if doc["metadata"]["source"] == source_filter]

        result = runner.run_benchmark(
            name="rag_metadata_filtering_1000_docs",
            func=filter_by_metadata,
            iterations=50,
            metadata={"num_documents": 1000, "filter_type": "source"},
        )

        print(f"\nMetadata Filtering Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed


class TestEmbeddingBenchmarks:
    """Benchmark embedding generation operations"""

    @pytest.fixture
    def runner(self):
        return BenchmarkRunner(warmup_iterations=1, default_iterations=5)

    def test_text_preprocessing_benchmark(self, runner):
        """Benchmark text preprocessing for embeddings"""
        import re

        sample_text = """
        This is a sample document with various formatting.
        It contains multiple sentences and paragraphs.

        Special characters: @#$%^&*()
        Numbers: 12345
        URLs: https://example.com
        """

        def preprocess():
            # Lowercase
            text = sample_text.lower()
            # Remove special chars
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            # Normalize whitespace
            text = " ".join(text.split())
            return text

        result = runner.run_benchmark(
            name="embedding_text_preprocessing",
            func=preprocess,
            iterations=100,
            metadata={"text_length": len(sample_text)},
        )

        print(f"\nText Preprocessing Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed

    def test_batch_embedding_simulation_benchmark(self, runner):
        """Benchmark batch embedding generation (simulated)"""
        texts = [f"Document {i} content for embedding generation" for i in range(32)]

        def generate_batch_embeddings():
            # Simulate embedding generation (in practice, would call model)
            embeddings = []
            for text in texts:
                # Simulate work (hash-based fake embedding)
                embedding = [hash(text + str(i)) % 1000 / 1000.0 for i in range(384)]
                embeddings.append(embedding)
            return embeddings

        result = runner.run_benchmark(
            name="embedding_batch_generation_32",
            func=generate_batch_embeddings,
            iterations=10,
            metadata={"batch_size": 32, "embedding_dim": 384},
        )

        print(f"\nBatch Embedding Generation Benchmark (batch=32):")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")

        assert result.passed


class TestRAGPipelineBenchmarks:
    """End-to-end RAG pipeline benchmarks"""

    @pytest.fixture
    def runner(self):
        return BenchmarkRunner(warmup_iterations=1, default_iterations=5)

    def test_full_rag_query_simulation(self, runner):
        """Benchmark complete RAG query pipeline (simulated)"""
        import time

        def simulate_rag_pipeline():
            # 1. Query embedding (simulated)
            query = "What is the best approach for performance optimization?"
            query_embedding = [hash(query + str(i)) % 1000 / 1000.0 for i in range(384)]

            # 2. Vector search (simulated - quick sleep for realism)
            time.sleep(0.001)  # Simulate 1ms DB query
            retrieved_docs = [
                {"content": f"Doc {i}", "score": 0.9 - i * 0.05} for i in range(5)
            ]

            # 3. Reranking (simulated)
            reranked = sorted(retrieved_docs, key=lambda x: x["score"], reverse=True)

            # 4. Context assembly
            context = "\n".join([doc["content"] for doc in reranked[:3]])

            # 5. Prompt construction
            prompt = f"Context: {context}\n\nQuestion: {query}\n\nAnswer:"

            return prompt

        result = runner.run_benchmark(
            name="rag_full_pipeline_simulation",
            func=simulate_rag_pipeline,
            iterations=20,
            metadata={"stages": ["embed", "search", "rerank", "assemble", "prompt"]},
        )

        print(f"\nFull RAG Pipeline Benchmark (simulated):")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # Full pipeline should complete in reasonable time
        assert_performance(result, max_avg_ms=50.0)

    def test_query_expansion_benchmark(self, runner):
        """Benchmark query expansion for better retrieval"""

        def expand_query(query="performance optimization"):
            # Simple synonym-based expansion
            synonyms = {
                "performance": ["speed", "efficiency", "throughput"],
                "optimization": ["improvement", "tuning", "enhancement"],
            }

            expanded_terms = []
            for word in query.split():
                expanded_terms.append(word)
                if word in synonyms:
                    expanded_terms.extend(synonyms[word])

            return " ".join(expanded_terms)

        result = runner.run_benchmark(
            name="rag_query_expansion",
            func=expand_query,
            iterations=100,
            metadata={"method": "synonym_based"},
        )

        print(f"\nQuery Expansion Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
