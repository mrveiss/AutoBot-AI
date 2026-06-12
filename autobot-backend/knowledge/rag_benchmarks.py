# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
RAG Query Performance Benchmarks

Benchmark tests for Retrieval-Augmented Generation (RAG) operations
including vector search, document retrieval, and context assembly.

Issue #58 - Performance Benchmarking Suite
Issue #4676 - Wire rag_benchmarks into RetrievalLearner feedback loop
Issue #5074 - Enforce held-out dev/test split for benchmark runs
Author: mrveiss
"""

import enum
import hashlib
import json
import random
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Set

import pytest

from autobot_shared.logging_manager import get_logger

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

logger = get_logger(__name__)


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
        return [
            [random.random() for _ in range(384)] for _ in range(100)
        ]  # nosec B311 - mock embedding vectors for benchmarks, not cryptographic

    @pytest.fixture
    def mock_documents(self):
        """Generate mock documents for retrieval"""
        return [
            {
                "id": f"doc_{i}",
                "content": f"This is test document {i} with some content for testing RAG retrieval performance.",
                "metadata": {"source": "test", "page": i},
                "embedding": [
                    random.random() for _ in range(384)
                ],  # nosec B311 - mock embedding for benchmark, not cryptographic
            }
            for i in range(1000)
        ]

    def test_vector_similarity_computation_benchmark(self, runner, mock_embeddings):
        """Benchmark vector similarity computation"""
        import numpy as np

        query_vector = np.array(
            [random.random() for _ in range(384)]
        )  # nosec B311 - mock query vector for benchmark, not cryptographic
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

        query_vector = [
            random.random() for _ in range(384)
        ]  # nosec B311 - mock query vector for benchmark, not cryptographic
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
                start = end - overlap if end < len(long_document) else len(long_document)
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
            return [doc for doc in mock_documents if doc["metadata"]["source"] == source_filter]

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
            [hash(query + str(i)) % 1000 / 1000.0 for i in range(384)]

            # 2. Vector search (simulated - quick sleep for realism)
            time.sleep(0.001)  # Simulate 1ms DB query
            retrieved_docs = [{"content": f"Doc {i}", "score": 0.9 - i * 0.05} for i in range(5)]

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
        "python",
        "list",
        "comprehension",
        "generator",
        "yield",
        "decorator",
        "asyncio",
        "coroutine",
        "dataclass",
        "unittest",
        "mock",
        "venv",
        "gil",
        "interpreter",
        "bytecode",
        "hint",
        "mypy",
        "typing",
        "functools",
        "wraps",
        # Database (indices 20-39)
        "postgresql",
        "database",
        "sql",
        "index",
        "query",
        "transaction",
        "acid",
        "redis",
        "chromadb",
        "vector",
        "embedding",
        "normalization",
        "partition",
        "connection",
        "pool",
        "wal",
        "log",
        "schema",
        "relational",
        "table",
        # Networking (indices 40-59)
        "tcp",
        "http",
        "tls",
        "dns",
        "load",
        "balancer",
        "websocket",
        "cidr",
        "bgp",
        "nginx",
        "proxy",
        "network",
        "protocol",
        "routing",
        "server",
        "client",
        "encrypt",
        "firewall",
        "sse",
        "packet",
        # Machine Learning (indices 60-79)
        "transformer",
        "rag",
        "retrieval",
        "augmented",
        "generation",
        "cosine",
        "similarity",
        "precision",
        "recall",
        "embedding",
        "finetune",
        "quantisation",
        "reranker",
        "bm25",
        "hybrid",
        "sentence",
        "chunk",
        "attention",
        "model",
        "language",
        # General / overlap (indices 80-127)
        "data",
        "performance",
        "memory",
        "efficient",
        "search",
        "result",
        "document",
        "content",
        "source",
        "text",
        "word",
        "term",
        "score",
        "rank",
        "top",
        "relevant",
        "train",
        "test",
        "run",
        "function",
        "class",
        "method",
        "import",
        "module",
        "package",
        "version",
        "install",
        "build",
        "config",
        "setup",
    ]
    # Extend to *dim* entries with placeholder values (empty string never matches)
    vocab = (_VOCAB + [""] * dim)[:dim]

    text_lower = text.lower()
    set(text_lower.split())

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
    (
        "python_01",
        "Python is a high-level interpreted programming language with clear readable syntax supporting procedural object-oriented and functional paradigms.",
        "python",
    ),
    (
        "python_02",
        "Python list comprehensions provide a concise way to create lists. Example: squares = [x**2 for x in range(10)]. They are faster than equivalent for-loops.",
        "python",
    ),
    (
        "python_03",
        "Python decorators add behaviour to functions without modifying them. The @functools.wraps decorator preserves the wrapped function metadata.",
        "python",
    ),
    (
        "python_04",
        "Python generators use the yield keyword to produce sequences lazily which is memory-efficient for large data streams.",
        "python",
    ),
    (
        "python_05",
        "The Python GIL Global Interpreter Lock prevents multiple threads from executing Python bytecode simultaneously. Use multiprocessing for CPU-bound work.",
        "python",
    ),
    (
        "python_06",
        "Python virtual environments venv isolate project dependencies so different projects can use different package versions without conflicts.",
        "python",
    ),
    (
        "python_07",
        "Type hints in Python PEP 484 allow static type checkers such as mypy to catch type errors before runtime without affecting performance.",
        "python",
    ),
    (
        "python_08",
        "Python asyncio library enables single-threaded concurrency using coroutines and an event loop ideal for I/O-bound workloads such as HTTP clients.",
        "python",
    ),
    (
        "python_09",
        "Python dataclasses PEP 557 auto-generate __init__ __repr__ and __eq__ from field annotations reducing boilerplate for data-holding classes.",
        "python",
    ),
    (
        "python_10",
        "Python unittest.mock lets you replace real objects with Mock instances during testing to assert how they are called without side effects.",
        "python",
    ),
    # Database / SQL
    (
        "db_01",
        "PostgreSQL is an advanced open-source relational database supporting ACID transactions complex queries foreign keys and triggers.",
        "database",
    ),
    (
        "db_02",
        "SQL indexes speed up SELECT queries by allowing the database engine to locate rows without scanning the entire table. B-tree indexes are the default in PostgreSQL.",
        "database",
    ),
    (
        "db_03",
        "Database normalization organises tables to reduce redundancy. Third Normal Form 3NF requires all non-key attributes depend only on the primary key.",
        "database",
    ),
    (
        "db_04",
        "Redis is an in-memory data structure store used as a database cache and message broker supporting strings hashes lists sets and sorted sets.",
        "database",
    ),
    (
        "db_05",
        "ChromaDB is an open-source embedding database for storing and querying high-dimensional vectors produced by language model embeddings.",
        "database",
    ),
    (
        "db_06",
        "ACID properties Atomicity Consistency Isolation Durability guarantee database transactions are processed reliably even after system failures.",
        "database",
    ),
    (
        "db_07",
        "Partitioning a large database table by date range dramatically improves query performance by limiting scans to relevant partitions.",
        "database",
    ),
    (
        "db_08",
        "Vector similarity search retrieves documents whose embedding vectors are closest to a query vector using cosine similarity or L2 distance.",
        "database",
    ),
    (
        "db_09",
        "Connection pooling reuses existing database connections rather than opening a new TCP connection for each query reducing latency and resource use.",
        "database",
    ),
    (
        "db_10",
        "A write-ahead log WAL records database changes before applying them so the database can recover to a consistent state after a crash.",
        "database",
    ),
    # Networking
    (
        "net_01",
        "TCP Transmission Control Protocol provides reliable ordered error-checked delivery of data between applications running on hosts in an IP network.",
        "networking",
    ),
    (
        "net_02",
        "HTTP/2 multiplexes multiple requests over a single TCP connection reducing latency compared to HTTP/1.1 which requires a separate connection per request.",
        "networking",
    ),
    (
        "net_03",
        "TLS Transport Layer Security encrypts network traffic between client and server to prevent eavesdropping and man-in-the-middle attacks.",
        "networking",
    ),
    (
        "net_04",
        "A load balancer distributes incoming network requests across multiple backend servers to improve availability and horizontal scalability.",
        "networking",
    ),
    (
        "net_05",
        "DNS Domain Name System translates hostnames such as example.com into IP addresses that routers use to forward packets.",
        "networking",
    ),
    (
        "net_06",
        "WebSockets provide full-duplex communication over a single TCP connection enabling real-time data exchange between browser and server.",
        "networking",
    ),
    (
        "net_07",
        "CIDR Classless Inter-Domain Routing notation expresses IP address ranges; for example 192.168.1.0/24 covers 256 addresses.",
        "networking",
    ),
    (
        "net_08",
        "Server-Sent Events SSE allow a server to push data to a browser client over a standard HTTP connection without requiring the client to poll.",
        "networking",
    ),
    (
        "net_09",
        "BGP Border Gateway Protocol is the routing protocol that directs traffic between autonomous systems on the internet.",
        "networking",
    ),
    (
        "net_10",
        "A reverse proxy sits in front of backend servers forwarding client requests and returning responses; nginx and HAProxy are popular choices.",
        "networking",
    ),
    # Machine Learning / RAG
    (
        "ml_01",
        "A transformer model uses self-attention mechanisms to weigh the influence of different input tokens when producing each output token.",
        "ml",
    ),
    (
        "ml_02",
        "Retrieval-Augmented Generation RAG combines a retrieval step that fetches relevant documents with a generation step that produces a grounded response.",
        "ml",
    ),
    (
        "ml_03",
        "Fine-tuning a pre-trained language model on a domain-specific dataset adapts its weights to improve performance on that domain without full retraining.",
        "ml",
    ),
    (
        "ml_04",
        "Cosine similarity measures the angle between two embedding vectors. A score of 1 means identical direction 0 means orthogonal and -1 means opposite.",
        "ml",
    ),
    (
        "ml_05",
        "Precision@k is the fraction of retrieved top-k documents that are relevant to the query. It measures retrieval accuracy rather than recall.",
        "ml",
    ),
    (
        "ml_06",
        "A cross-encoder reranker scores each query-document pair jointly to improve ranking quality beyond what a bi-encoder retrieval step achieves.",
        "ml",
    ),
    (
        "ml_07",
        "Sentence transformers encode sentences into dense vectors such that semantically similar sentences have high cosine similarity in the embedding space.",
        "ml",
    ),
    (
        "ml_08",
        "Chunking a long document into smaller overlapping windows before embedding ensures retrieval can target specific sections rather than averaging the whole.",
        "ml",
    ),
    (
        "ml_09",
        "Hybrid search combines dense vector retrieval with sparse keyword retrieval BM25 and merges the two ranked lists using reciprocal rank fusion.",
        "ml",
    ),
    (
        "ml_10",
        "Quantisation reduces the memory footprint of a language model by representing weights in lower precision such as INT8 or INT4 instead of FP32.",
        "ml",
    ),
]

# Ground-truth: query text -> expected doc IDs (at least one must appear in top-k)
# Issue #5196: dataset grown from 5 to ≥50 queries across five categories.
# Category tags (for human orientation only — not parsed by code):
#   [factual]        direct knowledge questions about a well-defined concept
#   [procedural]     how-to / step-by-step questions
#   [multi-hop]      questions requiring reasoning across two related concepts
#   [troubleshooting] diagnostic / "why is X broken" questions
#   [edge-case]      boundary conditions and exceptional behaviour
_GROUND_TRUTH = {
    # ------------------------------------------------------------------ original 5
    "Python list comprehensions and generator expressions": {"python_02", "python_04"},
    "PostgreSQL indexes and query performance": {"db_02", "db_01"},
    "TLS encryption and secure network communication": {"net_03", "net_01"},
    "RAG retrieval augmented generation embedding search": {"ml_02", "ml_09"},
    "cosine similarity precision at k evaluation metrics": {"ml_04", "ml_05"},
    # ------------------------------------------------------------------ [factual] — Python
    "Python GIL Global Interpreter Lock threading bytecode": {"python_05"},
    "Python type hints mypy static type checking PEP 484": {"python_07"},
    "Python asyncio event loop coroutines I/O bound": {"python_08"},
    "Python dataclasses PEP 557 auto-generated init repr eq": {"python_09"},
    "Python unittest mock testing side effects assertions": {"python_10"},
    "Python virtual environments venv package isolation": {"python_06"},
    "Python decorators functools wraps metadata preservation": {"python_03"},
    "Python high-level interpreted language syntax paradigms": {"python_01"},
    # ------------------------------------------------------------------ [factual] — Database
    "Redis in-memory data structure store cache message broker": {"db_04"},
    "ChromaDB embedding database vector storage language model": {"db_05"},
    "ACID atomicity consistency isolation durability transactions": {"db_06"},
    "database connection pooling TCP reuse latency": {"db_09"},
    "write-ahead log WAL database crash recovery consistency": {"db_10"},
    "database table partitioning date range query performance": {"db_07"},
    "vector similarity search cosine distance embeddings": {"db_08"},
    "SQL database normalization third normal form redundancy": {"db_03"},
    # ------------------------------------------------------------------ [factual] — Networking
    "TCP reliable ordered error-checked data delivery": {"net_01"},
    "HTTP/2 multiplexing single TCP connection latency": {"net_02"},
    "DNS domain name system hostname IP address translation": {"net_05"},
    "WebSockets full-duplex real-time browser server communication": {"net_06"},
    "CIDR classless inter-domain routing IP address ranges": {"net_07"},
    "Server-Sent Events SSE server push HTTP browser": {"net_08"},
    "BGP border gateway protocol autonomous systems internet routing": {"net_09"},
    "reverse proxy nginx HAProxy backend forwarding": {"net_10"},
    # ------------------------------------------------------------------ [factual] — ML / RAG
    "transformer self-attention mechanism input tokens weights": {"ml_01"},
    "fine-tuning pre-trained language model domain-specific dataset": {"ml_03"},
    "cross-encoder reranker query document pair scoring ranking": {"ml_06"},
    "sentence transformers dense vectors semantic similarity embeddings": {"ml_07"},
    "document chunking overlapping windows embedding retrieval": {"ml_08"},
    "BM25 hybrid search dense sparse retrieval reciprocal rank fusion": {"ml_09"},
    "quantisation INT8 INT4 model memory footprint weights": {"ml_10"},
    # ------------------------------------------------------------------ [procedural]
    "how to create a Python virtual environment and install packages": {"python_06"},
    "steps to add a type hint to a Python function and check with mypy": {"python_07"},
    "how to write an async Python coroutine using asyncio and await": {"python_08"},
    "how to apply a Python decorator to preserve function metadata": {"python_03"},
    "how to create a PostgreSQL index to speed up a slow SELECT query": {"db_02"},
    "steps to configure Redis as a cache for a Python web application": {"db_04"},
    "how to set up connection pooling for PostgreSQL in a Python service": {"db_09"},
    "how to ingest documents into ChromaDB for vector similarity search": {"db_05"},
    "steps to enable TLS on a web server for encrypted client connections": {"net_03"},
    "how to configure nginx as a reverse proxy for a backend service": {"net_10"},
    "how to implement Server-Sent Events SSE endpoint in a Python server": {"net_08"},
    "steps to fine-tune a language model on a domain-specific corpus": {"ml_03"},
    "how to chunk documents before embedding them for RAG retrieval": {"ml_08"},
    "how to combine dense and sparse retrieval using hybrid search BM25": {"ml_09"},
    # ------------------------------------------------------------------ [multi-hop]
    "how does Python asyncio interact with PostgreSQL connection pools for scalable I/O": {
        "python_08",
        "db_09",
    },
    "how do transformer embeddings enable vector similarity search in ChromaDB": {
        "ml_01",
        "db_05",
    },
    "how does TLS affect load balancer configuration for HTTPS termination": {
        "net_03",
        "net_04",
    },
    "relationship between Python GIL and asyncio for concurrent database queries": {
        "python_05",
        "python_08",
    },
    "how does document chunking affect precision at k in RAG evaluation": {
        "ml_08",
        "ml_05",
    },
    "why does database write-ahead logging complement ACID transaction guarantees": {
        "db_10",
        "db_06",
    },
    "how does fine-tuning interact with quantisation for memory-efficient deployment": {
        "ml_03",
        "ml_10",
    },
    "how does HTTP/2 multiplexing reduce load on reverse proxy backends": {
        "net_02",
        "net_10",
    },
    "how do PostgreSQL partitions and indexes work together to accelerate queries": {
        "db_07",
        "db_02",
    },
    "how does sentence transformer encoding feed into a cross-encoder reranker": {
        "ml_07",
        "ml_06",
    },
    # ------------------------------------------------------------------ [troubleshooting]
    "why are Python threads not achieving parallelism on CPU-bound work": {"python_05"},
    "why does a PostgreSQL SELECT query remain slow despite having an index": {
        "db_02",
        "db_07",
    },
    "why is Redis returning stale data after a server restart": {"db_04", "db_10"},
    "why does a TLS handshake fail when connecting to a backend service": {"net_03"},
    "why is ChromaDB returning low-relevance results for a domain query": {
        "db_05",
        "ml_07",
    },
    "why does RAG retrieval return irrelevant documents for a specific query": {
        "ml_02",
        "ml_08",
    },
    "why does cosine similarity score poorly for short queries in the embedding space": {
        "ml_04",
        "ml_07",
    },
    "why is connection pool exhausted under high concurrency in a Python service": {
        "db_09",
        "python_08",
    },
    "why does a DNS lookup return incorrect IP after a server migration": {"net_05"},
    "why are Server-Sent Events disconnecting frequently from a browser client": {
        "net_08",
        "net_06",
    },
    # ------------------------------------------------------------------ [edge-case]
    "behaviour of Python GIL when using multiprocessing instead of threading": {
        "python_05",
    },
    "what happens when a PostgreSQL write-ahead log fills up during high write load": {
        "db_10",
        "db_06",
    },
    "how does chromadb handle duplicate document IDs on repeated insertion": {"db_05"},
    "behaviour of cosine similarity when comparing a zero-magnitude embedding vector": {
        "ml_04",
    },
    "what happens to active WebSocket connections when a backend server restarts": {
        "net_06",
        "net_04",
    },
    "how does quantisation affect model output quality at very low bit widths INT4": {
        "ml_10",
    },
    "what happens when document chunk size exceeds the language model context window": {
        "ml_08",
        "ml_01",
    },
    "behaviour of Python dataclass when a mutable default value is used in a field": {
        "python_09",
    },
    "what happens to in-flight Redis operations during a Redis server failover": {
        "db_04",
    },
    "how does BGP react when an upstream autonomous system announces a longer prefix": {
        "net_09",
    },
}


# ---------------------------------------------------------------------------
# Issue #5074 — Held-out dev/test split enforcement
# ---------------------------------------------------------------------------


class BenchmarkSplit(str, enum.Enum):
    """Which portion of the dataset a benchmark run touches.

    - ``DEV``: tuning / hyperparameter search.  Results NOT suitable for
      external reporting.
    - ``TEST``: final held-out evaluation.  Results MAY be reported externally
      provided no tuning touched the test IDs in this run.
    - ``ALL``: combined DEV+TEST (for internal reporting only — ``held_out_score``
      is always False here).
    """

    DEV = "dev"
    TEST = "test"
    ALL = "all"


def _deterministic_dev_test_split(query_ids: List[str], dev_fraction: float = 0.8) -> Dict[str, Set[str]]:
    """Split *query_ids* into ``dev_ids`` and ``test_ids`` deterministically.

    Uses SHA-256 of each query string modulo 100 as a sort key; a query ``q``
    lands in DEV when ``int(sha256(q).hexdigest(), 16) % 100 < dev_fraction*100``.
    This means:
      - The same query always lands in the same split across runs (reproducible).
      - Adding or removing queries doesn't reshuffle the existing assignments.

    Args:
        query_ids:    List of query identifiers (query text works as the ID).
        dev_fraction: Fraction of queries routed to DEV.  Default 0.8 (80/20).

    Returns:
        ``{"dev_ids": set[str], "test_ids": set[str]}`` — disjoint and
        covering ``query_ids``.
    """
    threshold = int(dev_fraction * 100)
    dev_ids: Set[str] = set()
    test_ids: Set[str] = set()
    for qid in query_ids:
        h = hashlib.sha256(qid.encode("utf-8")).hexdigest()
        bucket = int(h, 16) % 100
        if bucket < threshold:
            dev_ids.add(qid)
        else:
            test_ids.add(qid)
    # Guarantee both splits are non-empty for tiny datasets: if one side is
    # empty, move the deterministically-smallest-hash query from the other.
    if query_ids and (not dev_ids or not test_ids):
        if not test_ids:
            move = sorted(dev_ids, key=lambda q: hashlib.sha256(q.encode()).hexdigest())[-1]
            dev_ids.remove(move)
            test_ids.add(move)
        elif not dev_ids:
            move = sorted(test_ids, key=lambda q: hashlib.sha256(q.encode()).hexdigest())[0]
            test_ids.remove(move)
            dev_ids.add(move)
    return {"dev_ids": dev_ids, "test_ids": test_ids}


@dataclass
class BenchmarkDataset:
    """Explicit dev/test split for a benchmark dataset.

    Issue #5074: formalizes train/dev/test hygiene so that a number
    published externally can only come from the held-out TEST split.

    Access to ground-truth IDs is tracked per-split so ``BenchmarkHarness``
    can assert that ``tune()`` never touches ``test_ids`` and ``score()``
    never touches ``dev_ids``.
    """

    ground_truth: Dict[str, Set[str]]
    dev_ids: Set[str] = field(default_factory=set)
    test_ids: Set[str] = field(default_factory=set)

    # Access tracking — reset at the start of each tune/score call.
    _accessed_dev: Set[str] = field(default_factory=set, init=False, repr=False)
    _accessed_test: Set[str] = field(default_factory=set, init=False, repr=False)
    _enforce_dev_only: bool = field(default=False, init=False, repr=False)
    _enforce_test_only: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_ground_truth(
        cls,
        ground_truth: Dict[str, Set[str]],
        dev_fraction: float = 0.8,
    ) -> "BenchmarkDataset":
        """Build a dataset with a deterministic hash-based dev/test split."""
        split = _deterministic_dev_test_split(sorted(ground_truth.keys()), dev_fraction=dev_fraction)
        return cls(
            ground_truth=dict(ground_truth),
            dev_ids=split["dev_ids"],
            test_ids=split["test_ids"],
        )

    def iter_split(self, split: "BenchmarkSplit") -> List[str]:
        """Return the list of query IDs for *split* (sorted for determinism)."""
        if split == BenchmarkSplit.DEV:
            return sorted(self.dev_ids)
        if split == BenchmarkSplit.TEST:
            return sorted(self.test_ids)
        if split == BenchmarkSplit.ALL:
            return sorted(self.dev_ids | self.test_ids)
        raise ValueError(f"Unknown split: {split!r}")

    def expected(self, query_id: str) -> Set[str]:
        """Return expected doc IDs for *query_id*, tracking access per split.

        Raises RuntimeError if enforcement is active and the caller crosses
        the split boundary (e.g. tune() touching a test_id).
        """
        if query_id in self.dev_ids:
            if self._enforce_test_only:
                raise RuntimeError(f"score() accessed dev query_id={query_id!r}; " "test-only enforcement is active")
            self._accessed_dev.add(query_id)
        elif query_id in self.test_ids:
            if self._enforce_dev_only:
                raise RuntimeError(f"tune() accessed test query_id={query_id!r}; " "dev-only enforcement is active")
            self._accessed_test.add(query_id)
        else:
            raise KeyError(f"query_id {query_id!r} is not in any split of this dataset")
        return set(self.ground_truth[query_id])

    def reset_access(self) -> None:
        """Clear per-run access tracking."""
        self._accessed_dev.clear()
        self._accessed_test.clear()

    @contextmanager
    def enforce_dev_only(self):
        """Context manager: raise if caller accesses any test_id."""
        prev = self._enforce_dev_only
        self._enforce_dev_only = True
        try:
            yield self
        finally:
            self._enforce_dev_only = prev

    @contextmanager
    def enforce_test_only(self):
        """Context manager: raise if caller accesses any dev_id."""
        prev = self._enforce_test_only
        self._enforce_test_only = True
        try:
            yield self
        finally:
            self._enforce_test_only = prev

    @property
    def dev_size(self) -> int:
        return len(self.dev_ids)

    @property
    def test_size(self) -> int:
        return len(self.test_ids)

    @property
    def accessed_dev(self) -> Set[str]:
        return set(self._accessed_dev)

    @property
    def accessed_test(self) -> Set[str]:
        return set(self._accessed_test)


def get_default_dataset() -> BenchmarkDataset:
    """Return the canonical BenchmarkDataset derived from ``_GROUND_TRUTH``."""
    return BenchmarkDataset.from_ground_truth(_GROUND_TRUTH, dev_fraction=0.8)


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
                f"Query '{query}': top-1 doc '{top1[0]}' has topic '{actual_topic}', " f"expected '{expected_topic}'"
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
        split_used:   Which split this query was drawn from
                      (``"dev"`` | ``"test"`` | ``"all"``).  Issue #5074.
    """

    __slots__ = (
        "query",
        "retrieved_ids",
        "ranked_ids",
        "precision_at_k",
        "complexity",
        "split_used",
    )

    def __init__(
        self,
        query: str,
        retrieved_ids: List[str],
        ranked_ids: List[str],
        precision_at_k: float,
        complexity: str = "moderate",
        split_used: str = BenchmarkSplit.ALL.value,
    ) -> None:
        self.query = query
        self.retrieved_ids = retrieved_ids
        self.ranked_ids = ranked_ids
        self.precision_at_k = precision_at_k
        self.complexity = complexity
        self.split_used = split_used


@dataclass
class BenchmarkRunReport:
    """Aggregate report returned by ``BenchmarkHarness.tune/score/run``.

    Issue #5074: every run carries its split metadata so downstream consumers
    (API response, feedback publisher, docs) can prove whether a reported
    score was actually held out.

    Attributes:
        split_used:    Which split produced these results (``"dev"``/``"test"``/``"all"``).
        dev_size:      Total number of dev queries in the dataset.
        test_size:     Total number of test queries in the dataset.
        tuned_on_dev:  True iff a tune() pass was completed on this dataset
                       before this run (harness-level state).
        held_out_score: True iff ``split_used == "test"`` **and** this run
                        touched only ``test_ids`` (no dev-set leakage) **and**
                        at least one ``test_id`` was actually accessed.
                        Any other combination is False (Issue #5160: empty
                        runs must not be labelled held-out).
        mean_precision_at_k: Mean precision@k across results in the run.
        results:       The underlying BenchmarkResult list.
    """

    split_used: str
    dev_size: int
    test_size: int
    tuned_on_dev: bool
    held_out_score: bool
    mean_precision_at_k: float
    results: List["BenchmarkResult"]

    def as_dict(self) -> dict:
        return {
            "split_used": self.split_used,
            "dev_size": self.dev_size,
            "test_size": self.test_size,
            "tuned_on_dev": self.tuned_on_dev,
            "held_out_score": self.held_out_score,
            "mean_precision_at_k": self.mean_precision_at_k,
            "num_results": len(self.results),
        }


class BenchmarkHarness:
    """Enforces held-out dev/test discipline for RAG benchmarks.

    Issue #5074.  Use ``harness.tune(fn)`` while searching hyperparameters
    and ``harness.score(fn)`` for the final held-out number.  Any cross-split
    access raises ``RuntimeError`` — the guard is runtime-checked, not advisory.

    Example:
        harness = BenchmarkHarness(dataset=get_default_dataset())

        # Tune on dev only (score will be labelled held_out_score=False).
        tune_report = harness.tune(lambda ds: run_benchmark_suite(
            collection, dataset=ds, split=BenchmarkSplit.DEV,
        ))

        # Final held-out score on test only.
        test_report = harness.score(lambda ds: run_benchmark_suite(
            collection, dataset=ds, split=BenchmarkSplit.TEST,
        ))
        assert test_report.held_out_score is True
    """

    def __init__(self, dataset: BenchmarkDataset) -> None:
        self.dataset = dataset
        self._tuned_on_dev: bool = False

    @property
    def tuned_on_dev(self) -> bool:
        return self._tuned_on_dev

    def _build_report(
        self,
        split: BenchmarkSplit,
        results: List["BenchmarkResult"],
        touched_test: bool,
    ) -> BenchmarkRunReport:
        mean_p = sum(r.precision_at_k for r in results) / len(results) if results else 0.0
        held_out = (
            split == BenchmarkSplit.TEST
            and not touched_test_leakage(self.dataset, split)
            and len(self.dataset.accessed_test) > 0
        )
        return BenchmarkRunReport(
            split_used=split.value,
            dev_size=self.dataset.dev_size,
            test_size=self.dataset.test_size,
            tuned_on_dev=self._tuned_on_dev,
            held_out_score=held_out,
            mean_precision_at_k=mean_p,
            results=results,
        )

    def tune(
        self,
        harness_fn: Callable[[BenchmarkDataset], List["BenchmarkResult"]],
    ) -> BenchmarkRunReport:
        """Run *harness_fn* under dev-only enforcement.

        ``harness_fn`` receives the dataset and MUST only call
        ``dataset.expected(qid)`` for qid in ``dataset.dev_ids``.  Any
        access to a test_id raises RuntimeError.
        """
        self.dataset.reset_access()
        with self.dataset.enforce_dev_only():
            results = harness_fn(self.dataset)
        self._tuned_on_dev = True
        return self._build_report(BenchmarkSplit.DEV, results, touched_test=False)

    def score(
        self,
        scorer_fn: Callable[[BenchmarkDataset], List["BenchmarkResult"]],
    ) -> BenchmarkRunReport:
        """Run *scorer_fn* under test-only enforcement.

        ``scorer_fn`` receives the dataset and MUST only call
        ``dataset.expected(qid)`` for qid in ``dataset.test_ids``.  Any
        access to a dev_id raises RuntimeError.
        """
        self.dataset.reset_access()
        with self.dataset.enforce_test_only():
            results = scorer_fn(self.dataset)
        if not self.dataset.accessed_test:
            raise RuntimeError("score() called but no test_ids were accessed — " "harness returned zero results")
        return self._build_report(BenchmarkSplit.TEST, results, touched_test=False)

    def run(
        self,
        runner_fn: Callable[[BenchmarkDataset], List["BenchmarkResult"]],
        split: BenchmarkSplit = BenchmarkSplit.TEST,
    ) -> BenchmarkRunReport:
        """Generic entry point; dispatches to tune / score / combined run."""
        if split == BenchmarkSplit.DEV:
            return self.tune(runner_fn)
        if split == BenchmarkSplit.TEST:
            return self.score(runner_fn)
        if split == BenchmarkSplit.ALL:
            self.dataset.reset_access()
            results = runner_fn(self.dataset)
            mean_p = sum(r.precision_at_k for r in results) / len(results) if results else 0.0
            return BenchmarkRunReport(
                split_used=BenchmarkSplit.ALL.value,
                dev_size=self.dataset.dev_size,
                test_size=self.dataset.test_size,
                tuned_on_dev=self._tuned_on_dev,
                held_out_score=False,
                mean_precision_at_k=mean_p,
                results=results,
            )
        raise ValueError(f"Unknown split: {split!r}")


def touched_test_leakage(dataset: BenchmarkDataset, split: BenchmarkSplit) -> bool:
    """Return True if a run labelled *split* actually touched the wrong side.

    This is the runtime check that turns ``held_out_score`` from a hope into
    a fact: if TEST was the declared split but the run accessed dev_ids, the
    score is leaky and ``held_out_score`` must be False.
    """
    if split == BenchmarkSplit.TEST:
        return bool(dataset.accessed_dev)
    if split == BenchmarkSplit.DEV:
        return bool(dataset.accessed_test)
    return False


def run_benchmark_suite(
    chroma_collection,
    k: int = 5,
    dataset: BenchmarkDataset | None = None,
    split: BenchmarkSplit = BenchmarkSplit.ALL,
) -> List["BenchmarkResult"]:
    """Run the precision@k benchmark suite against *chroma_collection*.

    Issue #4676: Produces BenchmarkResult objects that can be passed to
    ``publish_feedback_events()`` so the scores feed into RetrievalLearner.
    Issue #5074: Accepts an explicit *dataset* and *split* so the same suite
    can serve both tuning (DEV) and held-out scoring (TEST).

    The function is synchronous because ChromaDB's EphemeralClient is
    synchronous.  Callers in async contexts should run it via
    ``loop.run_in_executor(None, run_benchmark_suite, ...)``.

    Args:
        chroma_collection: A ChromaDB collection pre-seeded with domain docs.
        k:                 Number of results to retrieve per query.
        dataset:           Optional BenchmarkDataset.  If omitted, defaults to
                           ``get_default_dataset()`` which has an 80/20 split.
        split:             Which portion of the dataset to run against.

    Returns:
        List of BenchmarkResult — one entry per query in the requested split.
    """
    if dataset is None:
        dataset = get_default_dataset()

    results: List[BenchmarkResult] = []
    dim = 128  # must match _deterministic_embed default

    for query in dataset.iter_split(split):
        expected_ids = dataset.expected(query)
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
                split_used=split.value,
            )
        )
        logger.debug(
            "benchmark_suite: query=%r split=%s p@%d=%.2f",
            query[:40],
            split.value,
            k,
            precision,
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
            # Issue #5074: tag each event with the split it came from so
            # RetrievalLearner can exclude test-set feedback from training.
            "split_used": getattr(result, "split_used", BenchmarkSplit.ALL.value),
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
