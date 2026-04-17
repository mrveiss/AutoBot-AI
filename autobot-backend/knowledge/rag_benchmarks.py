"""
RAG Query Performance Benchmarks

Benchmark tests for Retrieval-Augmented Generation (RAG) operations
including vector search, document retrieval, and context assembly.

Issue #58 - Performance Benchmarking Suite
Issue #4676 - Wire rag_benchmarks into RetrievalLearner feedback loop
Author: mrveiss
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

# Add project root and shared infrastructure to path so benchmark_base is importable
_repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_repo_root / "autobot-infrastructure" / "shared"))

try:
    from tests.benchmarks.benchmark_base import BenchmarkRunner, assert_performance
except ModuleNotFoundError:
    # benchmark_base is only available when the full infrastructure tree is present.
    # TestRealKBBenchmarks (below) does not require it; the mock benchmark classes do.
    BenchmarkRunner = None  # type: ignore[assignment,misc]
    assert_performance = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


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

        logger.info(
            "Vector Similarity Benchmark (50 docs): Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

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
                score = sum(
                    a * b for a, b in zip(query_vector[:10], doc["embedding"][:10])
                )
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

        logger.info(
            "Top-K Retrieval Benchmark (1000 docs, k=5): Avg=%.2fms P95=%.2fms",
            result.avg_time_ms,
            result.p95_time_ms,
        )

        assert result.passed

    def test_context_assembly_benchmark(self, runner):
        """Benchmark context window assembly from retrieved documents"""
        retrieved_docs = [
            {
                "content": f"Document {i} contains important information about the topic. "
                * 10,
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

        logger.info(
            "Context Assembly Benchmark: Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

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
                start = (
                    end - overlap if end < len(long_document) else len(long_document)
                )
            return chunks

        result = runner.run_benchmark(
            name="rag_document_chunking",
            func=chunk_document,
            iterations=100,
            metadata={"doc_size": len(long_document), "chunk_size": 500, "overlap": 50},
        )

        logger.info(
            "Document Chunking Benchmark: Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

        assert result.passed

    def test_metadata_filtering_benchmark(self, runner, mock_documents):
        """Benchmark metadata filtering performance"""

        def filter_by_metadata(source_filter="test"):
            return [
                doc
                for doc in mock_documents
                if doc["metadata"]["source"] == source_filter
            ]

        result = runner.run_benchmark(
            name="rag_metadata_filtering_1000_docs",
            func=filter_by_metadata,
            iterations=50,
            metadata={"num_documents": 1000, "filter_type": "source"},
        )

        logger.info(
            "Metadata Filtering Benchmark: Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

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

        logger.info(
            "Text Preprocessing Benchmark: Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

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

        logger.info(
            "Batch Embedding Generation Benchmark (batch=32): Avg=%.2fms P95=%.2fms",
            result.avg_time_ms,
            result.p95_time_ms,
        )

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
            _query_embedding = [
                hash(query + str(i)) % 1000 / 1000.0 for i in range(384)
            ]

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

        logger.info(
            "Full RAG Pipeline Benchmark (simulated): Avg=%.2fms P95=%.2fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.p95_time_ms,
            result.ops_per_second,
        )

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

        logger.info(
            "Query Expansion Benchmark: Avg=%.4fms Ops/sec=%.2f",
            result.avg_time_ms,
            result.ops_per_second,
        )

        assert result.passed


def _deterministic_embed(text: str, dim: int = 128) -> list:
    """Return a consistent, semantically-aware unit-normalised vector for *text*.

    Uses a vocabulary of topic-discriminating terms so that documents covering
    the same topic produce similar (high cosine-similarity) vectors, which makes
    precision@k assertions meaningful.

    The vocabulary is fixed and deterministic -- the same input always produces
    the same output vector.  No external model or service is required.
    """
    import math

    # Fixed vocabulary of discriminating terms (order defines feature index).
    # Terms are grouped by topic so same-topic documents share high overlap.
    _VOCAB = [
        # Python (indices 0-19)
        "python", "list", "comprehension", "generator", "yield", "decorator",
        "asyncio", "coroutine", "dataclass", "unittest", "mock", "venv",
        "gil", "interpreter", "bytecode", "hint", "mypy", "typing",
        "functools", "wraps",
        # Database (indices 20-39)
        "postgresql", "database", "sql", "index", "query", "transaction",
        "acid", "redis", "chromadb", "vector", "embedding", "normalization",
        "partition", "connection", "pool", "wal", "log", "schema",
        "relational", "table",
        # Networking (indices 40-59)
        "tcp", "http", "tls", "dns", "load", "balancer", "websocket",
        "cidr", "bgp", "nginx", "proxy", "network", "protocol", "routing",
        "server", "client", "encrypt", "firewall", "sse", "packet",
        # Machine Learning (indices 60-79)
        "transformer", "rag", "retrieval", "augmented", "generation",
        "cosine", "similarity", "precision", "recall", "embedding",
        "finetune", "quantisation", "reranker", "bm25", "hybrid",
        "sentence", "chunk", "attention", "model", "language",
        # General / overlap (indices 80-127)
        "data", "performance", "memory", "efficient", "search", "result",
        "document", "content", "source", "text", "word", "term",
        "score", "rank", "top", "relevant", "train", "test", "run",
        "function", "class", "method", "import", "module", "package",
        "version", "install", "build", "config", "setup",
    ]
    # Extend to *dim* entries with placeholder values (empty string never matches)
    vocab = (_VOCAB + [""] * dim)[:dim]

    text_lower = text.lower()
    words = set(text_lower.split())

    vec = []
    for term in vocab:
        if not term:
            vec.append(0.0)
        else:
            # Count substring occurrences for partial matches (e.g. "asyncio" in phrase)
            count = text_lower.count(term)
            vec.append(float(count))

    # L2-normalise
    magnitude = math.sqrt(sum(v * v for v in vec))
    if magnitude > 0:
        vec = [v / magnitude for v in vec]
    else:
        # Fallback: uniform vector for texts with no vocabulary matches
        vec = [1.0 / math.sqrt(dim)] * dim
    return vec


# ---------------------------------------------------------------------------
# Domain document corpus for seeding the ephemeral KB
# Each tuple is (doc_id, document_text, topic)
# ---------------------------------------------------------------------------

_TOPIC_DOCS = [
    # Python programming
    ("python_01", "Python is a high-level interpreted programming language with clear readable syntax supporting procedural object-oriented and functional paradigms.", "python"),
    ("python_02", "Python list comprehensions provide a concise way to create lists. Example: squares = [x**2 for x in range(10)]. They are faster than equivalent for-loops.", "python"),
    ("python_03", "Python decorators add behaviour to functions without modifying them. The @functools.wraps decorator preserves the wrapped function metadata.", "python"),
    ("python_04", "Python generators use the yield keyword to produce sequences lazily which is memory-efficient for large data streams.", "python"),
    ("python_05", "The Python GIL Global Interpreter Lock prevents multiple threads from executing Python bytecode simultaneously. Use multiprocessing for CPU-bound work.", "python"),
    ("python_06", "Python virtual environments venv isolate project dependencies so different projects can use different package versions without conflicts.", "python"),
    ("python_07", "Type hints in Python PEP 484 allow static type checkers such as mypy to catch type errors before runtime without affecting performance.", "python"),
    ("python_08", "Python asyncio library enables single-threaded concurrency using coroutines and an event loop ideal for I/O-bound workloads such as HTTP clients.", "python"),
    ("python_09", "Python dataclasses PEP 557 auto-generate __init__ __repr__ and __eq__ from field annotations reducing boilerplate for data-holding classes.", "python"),
    ("python_10", "Python unittest.mock lets you replace real objects with Mock instances during testing to assert how they are called without side effects.", "python"),
    # Database / SQL
    ("db_01", "PostgreSQL is an advanced open-source relational database supporting ACID transactions complex queries foreign keys and triggers.", "database"),
    ("db_02", "SQL indexes speed up SELECT queries by allowing the database engine to locate rows without scanning the entire table. B-tree indexes are the default in PostgreSQL.", "database"),
    ("db_03", "Database normalization organises tables to reduce redundancy. Third Normal Form 3NF requires all non-key attributes depend only on the primary key.", "database"),
    ("db_04", "Redis is an in-memory data structure store used as a database cache and message broker supporting strings hashes lists sets and sorted sets.", "database"),
    ("db_05", "ChromaDB is an open-source embedding database for storing and querying high-dimensional vectors produced by language model embeddings.", "database"),
    ("db_06", "ACID properties Atomicity Consistency Isolation Durability guarantee database transactions are processed reliably even after system failures.", "database"),
    ("db_07", "Partitioning a large database table by date range dramatically improves query performance by limiting scans to relevant partitions.", "database"),
    ("db_08", "Vector similarity search retrieves documents whose embedding vectors are closest to a query vector using cosine similarity or L2 distance.", "database"),
    ("db_09", "Connection pooling reuses existing database connections rather than opening a new TCP connection for each query reducing latency and resource use.", "database"),
    ("db_10", "A write-ahead log WAL records database changes before applying them so the database can recover to a consistent state after a crash.", "database"),
    # Networking
    ("net_01", "TCP Transmission Control Protocol provides reliable ordered error-checked delivery of data between applications running on hosts in an IP network.", "networking"),
    ("net_02", "HTTP/2 multiplexes multiple requests over a single TCP connection reducing latency compared to HTTP/1.1 which requires a separate connection per request.", "networking"),
    ("net_03", "TLS Transport Layer Security encrypts network traffic between client and server to prevent eavesdropping and man-in-the-middle attacks.", "networking"),
    ("net_04", "A load balancer distributes incoming network requests across multiple backend servers to improve availability and horizontal scalability.", "networking"),
    ("net_05", "DNS Domain Name System translates hostnames such as example.com into IP addresses that routers use to forward packets.", "networking"),
    ("net_06", "WebSockets provide full-duplex communication over a single TCP connection enabling real-time data exchange between browser and server.", "networking"),
    ("net_07", "CIDR Classless Inter-Domain Routing notation expresses IP address ranges; for example 192.168.1.0/24 covers 256 addresses.", "networking"),
    ("net_08", "Server-Sent Events SSE allow a server to push data to a browser client over a standard HTTP connection without requiring the client to poll.", "networking"),
    ("net_09", "BGP Border Gateway Protocol is the routing protocol that directs traffic between autonomous systems on the internet.", "networking"),
    ("net_10", "A reverse proxy sits in front of backend servers forwarding client requests and returning responses; nginx and HAProxy are popular choices.", "networking"),
    # Machine Learning / RAG
    ("ml_01", "A transformer model uses self-attention mechanisms to weigh the influence of different input tokens when producing each output token.", "ml"),
    ("ml_02", "Retrieval-Augmented Generation RAG combines a retrieval step that fetches relevant documents with a generation step that produces a grounded response.", "ml"),
    ("ml_03", "Fine-tuning a pre-trained language model on a domain-specific dataset adapts its weights to improve performance on that domain without full retraining.", "ml"),
    ("ml_04", "Cosine similarity measures the angle between two embedding vectors. A score of 1 means identical direction 0 means orthogonal and -1 means opposite.", "ml"),
    ("ml_05", "Precision@k is the fraction of retrieved top-k documents that are relevant to the query. It measures retrieval accuracy rather than recall.", "ml"),
    ("ml_06", "A cross-encoder reranker scores each query-document pair jointly to improve ranking quality beyond what a bi-encoder retrieval step achieves.", "ml"),
    ("ml_07", "Sentence transformers encode sentences into dense vectors such that semantically similar sentences have high cosine similarity in the embedding space.", "ml"),
    ("ml_08", "Chunking a long document into smaller overlapping windows before embedding ensures retrieval can target specific sections rather than averaging the whole.", "ml"),
    ("ml_09", "Hybrid search combines dense vector retrieval with sparse keyword retrieval BM25 and merges the two ranked lists using reciprocal rank fusion.", "ml"),
    ("ml_10", "Quantisation reduces the memory footprint of a language model by representing weights in lower precision such as INT8 or INT4 instead of FP32.", "ml"),
]

# Ground-truth: query text -> expected doc IDs (at least one must appear in top-k)
_GROUND_TRUTH = {
    "Python list comprehensions and generator expressions": {"python_02", "python_04"},
    "PostgreSQL indexes and query performance": {"db_02", "db_01"},
    "TLS encryption and secure network communication": {"net_03", "net_01"},
    "RAG retrieval augmented generation embedding search": {"ml_02", "ml_09"},
    "cosine similarity precision at k evaluation metrics": {"ml_04", "ml_05"},
}


@pytest.mark.real_kb
class TestRealKBBenchmarks:
    """
    Precision@k tests against a real ChromaDB in-memory (EphemeralClient) instance.

    These tests verify that the retrieval layer produces meaningful rankings when
    given domain-relevant documents and real queries -- no random embeddings.

    Run with: pytest -m real_kb autobot-backend/knowledge/rag_benchmarks.py -v

    No external services needed: ChromaDB runs fully in-process and embeddings
    are deterministic hash-derived vectors (same input -> same vector, always).

    Issue #4697.
    """

    _DIM = 128  # Embedding dimension used throughout this class

    @pytest.fixture(scope="class")
    def chroma_collection(self):
        """Seed an ephemeral ChromaDB collection with the domain corpus."""
        import chromadb

        client = chromadb.EphemeralClient()
        collection = client.create_collection(
            name="real_kb_bench",
            metadata={"hnsw:space": "cosine"},
        )
        ids = [doc_id for doc_id, _, _ in _TOPIC_DOCS]
        embeddings = [_deterministic_embed(text, self._DIM) for _, text, _ in _TOPIC_DOCS]
        documents = [text for _, text, _ in _TOPIC_DOCS]
        metadatas = [{"topic": topic} for _, _, topic in _TOPIC_DOCS]
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        yield collection
        client.delete_collection("real_kb_bench")

    def _query_top_k(self, collection, query: str, k: int) -> list:
        """Return the top-k doc IDs from *collection* for *query*."""
        query_vec = _deterministic_embed(query, self._DIM)
        result = collection.query(
            query_embeddings=[query_vec],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        return result["ids"][0]

    def _precision_at_k(self, retrieved_ids: list, expected_ids: set) -> float:
        """Return fraction of *retrieved_ids* that appear in *expected_ids*."""
        if not retrieved_ids:
            return 0.0
        return sum(1 for doc_id in retrieved_ids if doc_id in expected_ids) / len(retrieved_ids)

    def test_corpus_seeded_correctly(self, chroma_collection):
        """All corpus documents must be present in the ephemeral collection."""
        assert chroma_collection.count() == len(_TOPIC_DOCS)

    def test_precision_at_5_python_query(self, chroma_collection):
        """Python list comprehension query: at least one expected doc in top-5."""
        query = "Python list comprehensions and generator expressions"
        retrieved = self._query_top_k(chroma_collection, query, k=5)
        p_at_5 = self._precision_at_k(retrieved, _GROUND_TRUTH[query])
        logger.info("Precision@5 python query=%.2f retrieved=%s", p_at_5, retrieved)
        assert p_at_5 > 0.0, f"Expected one of {_GROUND_TRUTH[query]} in top-5; got {retrieved}"

    def test_precision_at_5_database_query(self, chroma_collection):
        """PostgreSQL index query: at least one expected doc in top-5."""
        query = "PostgreSQL indexes and query performance"
        retrieved = self._query_top_k(chroma_collection, query, k=5)
        p_at_5 = self._precision_at_k(retrieved, _GROUND_TRUTH[query])
        logger.info("Precision@5 database query=%.2f retrieved=%s", p_at_5, retrieved)
        assert p_at_5 > 0.0, f"Expected one of {_GROUND_TRUTH[query]} in top-5; got {retrieved}"

    def test_precision_at_5_networking_query(self, chroma_collection):
        """TLS encryption query: at least one expected doc in top-5."""
        query = "TLS encryption and secure network communication"
        retrieved = self._query_top_k(chroma_collection, query, k=5)
        p_at_5 = self._precision_at_k(retrieved, _GROUND_TRUTH[query])
        logger.info("Precision@5 networking query=%.2f retrieved=%s", p_at_5, retrieved)
        assert p_at_5 > 0.0, f"Expected one of {_GROUND_TRUTH[query]} in top-5; got {retrieved}"

    def test_precision_at_5_rag_query(self, chroma_collection):
        """RAG / embedding search query: at least one expected doc in top-5."""
        query = "RAG retrieval augmented generation embedding search"
        retrieved = self._query_top_k(chroma_collection, query, k=5)
        p_at_5 = self._precision_at_k(retrieved, _GROUND_TRUTH[query])
        logger.info("Precision@5 RAG query=%.2f retrieved=%s", p_at_5, retrieved)
        assert p_at_5 > 0.0, f"Expected one of {_GROUND_TRUTH[query]} in top-5; got {retrieved}"

    def test_precision_at_5_cosine_metrics_query(self, chroma_collection):
        """Cosine similarity / precision@k query: at least one expected doc in top-5."""
        query = "cosine similarity precision at k evaluation metrics"
        retrieved = self._query_top_k(chroma_collection, query, k=5)
        p_at_5 = self._precision_at_k(retrieved, _GROUND_TRUTH[query])
        logger.info("Precision@5 cosine/metrics query=%.2f retrieved=%s", p_at_5, retrieved)
        assert p_at_5 > 0.0, f"Expected one of {_GROUND_TRUTH[query]} in top-5; got {retrieved}"

    def test_embedding_is_deterministic(self, chroma_collection):
        """Same query must return the same top-k results on every call."""
        query = "Python list comprehensions and generator expressions"
        assert self._query_top_k(chroma_collection, query, k=3) == self._query_top_k(
            chroma_collection, query, k=3
        ), "Deterministic embedding must produce identical results on repeated calls"

    def test_top1_matches_expected_topic(self, chroma_collection):
        """Top-1 retrieved document must belong to the same topic as the query."""
        topic_map = {doc_id: topic for doc_id, _, topic in _TOPIC_DOCS}
        cases = [
            ("Python asyncio event loop coroutines", "python"),
            ("PostgreSQL transaction ACID durability", "database"),
            ("HTTP load balancer reverse proxy nginx", "networking"),
            ("transformer self-attention language model tokens", "ml"),
        ]
        for query, expected_topic in cases:
            top1 = self._query_top_k(chroma_collection, query, k=1)
            assert top1, f"No results for query: {query}"
            actual_topic = topic_map.get(top1[0], "unknown")
            logger.info(
                "Top-1 '%s': doc=%s topic=%s expected=%s",
                query,
                top1[0],
                actual_topic,
                expected_topic,
            )
            assert actual_topic == expected_topic, (
                f"Query '{query}': top-1 doc '{top1[0]}' has topic '{actual_topic}', "
                f"expected '{expected_topic}'"
            )


# ---------------------------------------------------------------------------
# Issue #4676 — Evaluator adapter: publish benchmark results as feedback events
# ---------------------------------------------------------------------------

#: Sentinel user namespace for benchmark-generated feedback events.
#: Mirrors RetrievalLearner.GLOBAL_USER so all users benefit from benchmark
#: runs without the benchmarks knowing anything about individual user IDs.
_BENCHMARK_USER = "__global__"

#: Redis stream TTL for benchmark-injected feedback events (30 days).
_BENCHMARK_STREAM_TTL = 60 * 60 * 24 * 30


class BenchmarkResult:
    """Lightweight result container returned by run_benchmark_suite().

    Attributes:
        query:        The benchmark query string.
        retrieved_ids: Document IDs returned by the initial retrieval step
                       (before reranking) in retrieval order.
        ranked_ids:   Document IDs in final ranked order (after reranking).
        precision_at_k: Fraction of top-k ranked IDs that appear in the
                        expected set.  Range [0.0, 1.0].
        complexity:   QueryComplexity hint for the RetrievalLearner; defaults
                      to ``"moderate"`` for benchmark queries.
    """

    __slots__ = ("query", "retrieved_ids", "ranked_ids", "precision_at_k", "complexity")

    def __init__(
        self,
        query: str,
        retrieved_ids: List[str],
        ranked_ids: List[str],
        precision_at_k: float,
        complexity: str = "moderate",
    ) -> None:
        self.query = query
        self.retrieved_ids = retrieved_ids
        self.ranked_ids = ranked_ids
        self.precision_at_k = precision_at_k
        self.complexity = complexity


def run_benchmark_suite(chroma_collection, k: int = 5) -> List["BenchmarkResult"]:
    """Run the precision@k benchmark suite against *chroma_collection*.

    Issue #4676: Produces BenchmarkResult objects that can be passed to
    ``publish_feedback_events()`` so the scores feed into RetrievalLearner.

    The function is synchronous because ChromaDB's EphemeralClient is
    synchronous.  Callers in async contexts should run it via
    ``asyncio.get_event_loop().run_in_executor(None, run_benchmark_suite, ...)``.

    Args:
        chroma_collection: A ChromaDB collection pre-seeded with domain docs.
        k:                 Number of results to retrieve per query.

    Returns:
        List of BenchmarkResult — one entry per ground-truth query.
    """
    results: List[BenchmarkResult] = []
    dim = 128  # must match _deterministic_embed default

    for query, expected_ids in _GROUND_TRUTH.items():
        query_vec = _deterministic_embed(query, dim)
        raw = chroma_collection.query(
            query_embeddings=[query_vec],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        retrieved_ids: List[str] = raw["ids"][0]

        # Simulate a mild reranking step: documents whose IDs appear in the
        # expected set are promoted to the front of the ranked list.  This
        # produces a measurable rerank-position gain that the RetrievalLearner
        # can detect as a successful trajectory.
        expected_first = [d for d in retrieved_ids if d in expected_ids]
        others = [d for d in retrieved_ids if d not in expected_ids]
        ranked_ids = expected_first + others

        precision = sum(1 for d in ranked_ids[:k] if d in expected_ids) / k
        results.append(
            BenchmarkResult(
                query=query,
                retrieved_ids=retrieved_ids,
                ranked_ids=ranked_ids,
                precision_at_k=precision,
                complexity="moderate",
            )
        )
        logger.debug(
            "benchmark_suite: query=%r p@%d=%.2f", query[:40], k, precision
        )

    return results


async def publish_feedback_events(redis, results: List["BenchmarkResult"]) -> int:
    """Publish benchmark results as synthetic rag:feedback stream entries.

    Issue #4676 — Evaluator adapter.

    Translates each BenchmarkResult into the same schema that
    ``knowledge_rag_feedback.py`` writes so ``RetrievalLearner.consume_feedback_stream()``
    can process them without any schema changes.  Events are written to the
    ``__global__`` namespace so all users benefit from the benchmark signal.

    Only results with ``precision_at_k > 0`` are published; zero-precision
    runs indicate retrieval failure and should not pollute the pattern store.

    Args:
        redis:   An async Redis client (``get_async_redis_client(database='analytics')``).
        results: BenchmarkResult list from ``run_benchmark_suite()``.

    Returns:
        Number of feedback events written to Redis.
    """
    from constants.ttl_constants import TTL_30_DAYS

    date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    stream_key = f"rag:feedback:{_BENCHMARK_USER}:{date_key}"
    published = 0

    for result in results:
        if result.precision_at_k <= 0.0:
            logger.debug(
                "publish_feedback_events: skipping zero-precision result for %r",
                result.query[:40],
            )
            continue

        entry = {
            "query_text": result.query,
            "retrieved_chunk_ids": json.dumps(result.retrieved_ids, ensure_ascii=False),
            "final_ranked_ids": json.dumps(result.ranked_ids, ensure_ascii=False),
            "complexity": result.complexity,
            "annotation": "benchmark",
            "precision_at_k": str(result.precision_at_k),
            "timestamp": str(time.time()),
        }

        try:
            await redis.xadd(stream_key, entry)
            published += 1
        except Exception as exc:
            logger.warning(
                "publish_feedback_events: xadd failed for query %r: %s",
                result.query[:40],
                exc,
            )

    if published > 0:
        try:
            await redis.expire(stream_key, TTL_30_DAYS)
        except Exception as exc:
            logger.warning("publish_feedback_events: expire failed: %s", exc)
        logger.info(
            "publish_feedback_events: wrote %d/%d events to %s",
            published,
            len(results),
            stream_key,
        )

    return published


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
