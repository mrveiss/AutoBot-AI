# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cross-Language Pattern Detector

Issue #244: Main detector class that analyzes patterns across Python and
TypeScript/JavaScript codebases using:
- ChromaDB for semantic vector similarity
- Redis for caching and pattern indexing
- LLM for semantic analysis and embeddings
- Knowledge graph patterns for relationships
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .extractors import PythonPatternExtractor, TypeScriptPatternExtractor
from .models import (
    APIContractMismatch,
    CrossLanguageAnalysis,
    CrossLanguagePattern,
    DTOMismatch,
    PatternCategory,
    PatternMatch,
    PatternSeverity,
    PatternType,
    ValidationDuplication,
)

logger = logging.getLogger(__name__)

# Default directories to skip
_SKIP_DIRS: frozenset = frozenset({
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    "archive", "archives", "backup", "backups", ".mypy_cache",
})

# Similarity thresholds
SIMILARITY_HIGH = 0.85
SIMILARITY_MEDIUM = 0.70
SIMILARITY_LOW = 0.50

# ChromaDB collection name
PATTERNS_COLLECTION = "cross_language_patterns"

# Maximum patterns to process for semantic embedding (performance limit)
# Processing 12K+ patterns with individual LLM calls would take hours
# Sample the most significant patterns (DTOs, APIs, validators) first
MAX_PATTERNS_FOR_EMBEDDING = 500

# Issue #659: Batch embedding configuration for parallel processing
# Concurrent requests with semaphore limiting provides 5-10x speedup
EMBEDDING_BATCH_CONCURRENCY = 10  # Max concurrent embedding requests
EMBEDDING_BATCH_SIZE = 50  # Process embeddings in batches of this size


class CrossLanguagePatternDetector:
    """
    Detects patterns across multiple programming languages.

    Uses semantic similarity (LLM embeddings + ChromaDB) to find:
    - Duplicated business logic between Python and TypeScript
    - API contract mismatches
    - DTO/type inconsistencies
    - Validation rule duplication
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        use_llm: bool = True,
        use_cache: bool = True,
        embedding_model: str = "nomic-embed-text",
    ):
        """
        Initialize the detector.

        Args:
            project_root: Root directory to analyze
            use_llm: Whether to use LLM for semantic analysis
            use_cache: Whether to use Redis caching
            embedding_model: Model to use for embeddings (Ollama)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.use_llm = use_llm
        self.use_cache = use_cache
        self.embedding_model = embedding_model

        # Initialize extractors
        self.python_extractor = PythonPatternExtractor()
        self.typescript_extractor = TypeScriptPatternExtractor()

        # Lazy-loaded resources
        self._chromadb_client = None
        self._chromadb_collection = None
        self._redis_client = None
        self._llm_interface = None
        self._embedding_cache = None

        # Thread-safe initialization locks
        self._cache_lock = asyncio.Lock()

        # Statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._embeddings_generated = 0

    async def _get_chromadb_collection(self):
        """Get or create ChromaDB collection for patterns."""
        if self._chromadb_collection is None:
            try:
                from src.utils.async_chromadb_client import get_async_chromadb_client

                chromadb_path = self.project_root / "data" / "chromadb"
                self._chromadb_client = await get_async_chromadb_client(
                    db_path=str(chromadb_path)
                )
                self._chromadb_collection = await self._chromadb_client.get_or_create_collection(
                    name=PATTERNS_COLLECTION,
                    metadata={
                        "description": "Cross-language code pattern semantics",
                        "hnsw:space": "cosine",
                        "hnsw:construction_ef": 200,
                        "hnsw:search_ef": 100,
                        "hnsw:M": 24,
                    }
                )
                logger.info("ChromaDB collection '%s' initialized", PATTERNS_COLLECTION)
            except Exception as e:
                logger.error("Failed to initialize ChromaDB: %s", e)
                self._chromadb_collection = None
        return self._chromadb_collection

    async def _get_redis_client(self):
        """Get Redis client for caching."""
        if self._redis_client is None and self.use_cache:
            try:
                from src.utils.redis_client import get_redis_client

                self._redis_client = await get_redis_client(
                    async_client=True,
                    database="analytics"
                )
                logger.info("Redis client initialized for analytics")
            except Exception as e:
                logger.warning("Redis not available for caching: %s", e)
                self._redis_client = None
        return self._redis_client

    async def _get_embedding_cache(self):
        """Get embedding cache with thread-safe lazy initialization."""
        if self._embedding_cache is None:
            async with self._cache_lock:
                # Double-check pattern to avoid race condition
                if self._embedding_cache is None:
                    try:
                        from src.knowledge.embedding_cache import EmbeddingCache

                        self._embedding_cache = EmbeddingCache(
                            maxsize=500, ttl_seconds=3600
                        )
                    except ImportError:
                        self._embedding_cache = None
        return self._embedding_cache

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for text using LLM.

        Uses caching to avoid redundant embedding generation.
        """
        if not self.use_llm or not text.strip():
            return None

        # Check cache first
        cache = await self._get_embedding_cache()
        if cache:
            cached = await cache.get(text)
            if cached:
                self._cache_hits += 1
                return cached
            self._cache_misses += 1

        # Generate embedding using Ollama
        try:
            import aiohttp

            from src.config.ssot_config import get_config

            ssot = get_config()
            url = f"{ssot.ollama_url}/api/embeddings"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"model": self.embedding_model, "prompt": text},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        embedding = data.get("embedding")
                        if embedding:
                            self._embeddings_generated += 1
                            # Cache the embedding
                            if cache:
                                await cache.put(text, embedding)
                            return embedding
        except Exception as e:
            logger.warning("Failed to generate embedding: %s", e)

        return None

    async def _get_embeddings_batch(
        self,
        texts: List[str],
        concurrency: int = EMBEDDING_BATCH_CONCURRENCY,
    ) -> List[Optional[List[float]]]:
        """
        Get embeddings for multiple texts in parallel.

        Issue #659: Batch embedding generation with semaphore-limited concurrency.
        Provides 5-10x speedup vs sequential calls by overlapping network latency.

        500 texts × 100-200ms = 50-100s sequential → 5-10s with 10 concurrent requests

        Args:
            texts: List of texts to embed
            concurrency: Maximum concurrent requests (default: 10)

        Returns:
            List of embeddings (same order as input texts, None for failures)
        """
        if not self.use_llm or not texts:
            return [None] * len(texts)

        semaphore = asyncio.Semaphore(concurrency)

        async def get_one(text: str) -> Optional[List[float]]:
            async with semaphore:
                return await self._get_embedding(text)

        # Execute all embedding requests in parallel with semaphore limiting
        results = await asyncio.gather(*[get_one(text) for text in texts])

        logger.info(
            "Batch generated %d embeddings (%d concurrent)",
            sum(1 for r in results if r is not None),
            concurrency,
        )

        return list(results)

    async def _normalize_pattern(self, pattern: Dict[str, Any]) -> str:
        """
        Normalize pattern to language-independent representation.

        This creates a semantic description that can be compared across languages.
        """
        pattern_type = pattern.get("type", PatternType.UTILITY_FUNCTION)
        name = pattern.get("name", "unknown")
        # Note: code extracted for potential future use in semantic analysis
        _ = pattern.get("code", "")

        # Build normalized representation based on pattern type
        if pattern_type == PatternType.DTO_DEFINITION:
            fields = pattern.get("fields", [])
            field_strs = [
                f"{f.get('name')}:{f.get('type', 'any')}{'?' if f.get('optional') else ''}"
                for f in fields
            ]
            return f"DATA_TYPE {name} FIELDS({', '.join(field_strs)})"

        elif pattern_type == PatternType.API_ENDPOINT or pattern_type == PatternType.API_CALL:
            method = pattern.get("method", "GET")
            path = pattern.get("path", "")
            return f"API {method} {path}"

        elif pattern_type == PatternType.VALIDATION_RULE:
            validation_type = pattern.get("validation_type", "custom")
            return f"VALIDATION {validation_type} {name}"

        elif pattern_type == PatternType.UTILITY_FUNCTION:
            params = pattern.get("parameters", [])
            param_str = ", ".join(
                f"{p.get('name', 'arg')}:{p.get('type', 'any')}"
                for p in params
            ) if params else ""
            is_async = "ASYNC " if pattern.get("is_async") else ""
            return f"{is_async}FUNCTION {name}({param_str})"

        # Default: use code summary
        return f"{pattern_type.value if hasattr(pattern_type, 'value') else pattern_type}: {name}"

    def _should_skip_directory(self, path: Path) -> bool:
        """Check if directory should be skipped."""
        return any(skip in path.parts for skip in _SKIP_DIRS)

    async def _collect_files(self) -> Tuple[List[Path], List[Path], List[Path]]:
        """Collect files to analyze by language."""
        python_files = []
        typescript_files = []
        vue_files = []

        backend_dir = self.project_root / "backend"
        src_dir = self.project_root / "src"
        frontend_dir = self.project_root / "autobot-vue" / "src"

        # Collect Python files
        for search_dir in [backend_dir, src_dir]:
            if search_dir.exists():
                for file_path in search_dir.rglob("*.py"):
                    if not self._should_skip_directory(file_path):
                        python_files.append(file_path)

        # Collect TypeScript files
        if frontend_dir.exists():
            for ext in ["*.ts", "*.tsx", "*.js", "*.jsx"]:
                for file_path in frontend_dir.rglob(ext):
                    if not self._should_skip_directory(file_path):
                        typescript_files.append(file_path)

            # Collect Vue files separately
            for file_path in frontend_dir.rglob("*.vue"):
                if not self._should_skip_directory(file_path):
                    vue_files.append(file_path)

        return python_files, typescript_files, vue_files

    async def _extract_all_patterns(
        self,
        python_files: List[Path],
        typescript_files: List[Path],
        vue_files: List[Path],
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Extract patterns from all files."""
        python_patterns = []
        typescript_patterns = []
        vue_patterns = []

        # Extract Python patterns
        for file_path in python_files:
            try:
                patterns = self.python_extractor.extract_patterns(file_path)
                python_patterns.extend(patterns)
            except Exception as e:
                logger.warning("Failed to extract patterns from %s: %s", file_path, e)

        # Extract TypeScript patterns
        for file_path in typescript_files:
            try:
                patterns = self.typescript_extractor.extract_patterns(file_path)
                typescript_patterns.extend(patterns)
            except Exception as e:
                logger.warning("Failed to extract patterns from %s: %s", file_path, e)

        # Extract Vue patterns (using TypeScript extractor)
        for file_path in vue_files:
            try:
                patterns = self.typescript_extractor.extract_patterns(file_path)
                vue_patterns.extend(patterns)
            except Exception as e:
                logger.warning("Failed to extract patterns from %s: %s", file_path, e)

        return python_patterns, typescript_patterns, vue_patterns

    async def _find_dto_mismatches(
        self,
        python_patterns: List[Dict],
        typescript_patterns: List[Dict],
    ) -> List[DTOMismatch]:
        """Find mismatches between Python and TypeScript DTOs (Issue #665: refactored)."""
        mismatches = []

        # Get all DTOs
        python_dtos = {
            p["name"]: p for p in python_patterns
            if p.get("type") == PatternType.DTO_DEFINITION
        }
        ts_dtos = {
            p["name"]: p for p in typescript_patterns
            if p.get("type") == PatternType.DTO_DEFINITION
        }

        # Find common DTOs and check for mismatches
        common_names = set(python_dtos.keys()) & set(ts_dtos.keys())

        for name in common_names:
            py_dto = python_dtos[name]
            ts_dto = ts_dtos[name]
            mismatches.extend(self._compare_dto_fields(name, py_dto, ts_dto))

        return mismatches

    def _compare_dto_fields(
        self, name: str, py_dto: Dict, ts_dto: Dict
    ) -> List[DTOMismatch]:
        """Compare DTO fields and find mismatches (Issue #665: extracted helper)."""
        mismatches = []

        py_fields = {f["name"]: f for f in py_dto.get("fields", [])}
        ts_fields = {f["name"]: f for f in ts_dto.get("fields", [])}

        # Check for missing fields
        py_only = set(py_fields.keys()) - set(ts_fields.keys())
        ts_only = set(ts_fields.keys()) - set(py_fields.keys())

        for field_name in py_only:
            mismatches.append(self._create_dto_mismatch(
                name, py_dto, ts_dto, field_name, "missing_in_frontend",
                backend_definition=str(py_fields[field_name]),
                severity=PatternSeverity.HIGH,
                recommendation=f"Add field '{field_name}' to frontend interface '{name}'",
            ))

        for field_name in ts_only:
            mismatches.append(self._create_dto_mismatch(
                name, py_dto, ts_dto, field_name, "missing_in_backend",
                frontend_definition=str(ts_fields[field_name]),
                severity=PatternSeverity.MEDIUM,
                recommendation=f"Consider adding field '{field_name}' to backend model '{name}' or remove from frontend",
            ))

        # Check for type mismatches in common fields
        common_fields = set(py_fields.keys()) & set(ts_fields.keys())
        for field_name in common_fields:
            py_field = py_fields[field_name]
            ts_field = ts_fields[field_name]

            if py_field.get("optional") != ts_field.get("optional"):
                mismatches.append(self._create_dto_mismatch(
                    name, py_dto, ts_dto, field_name, "optional_mismatch",
                    backend_definition=f"optional={py_field.get('optional')}",
                    frontend_definition=f"optional={ts_field.get('optional')}",
                    severity=PatternSeverity.MEDIUM,
                    recommendation=f"Align optional status of field '{field_name}' between backend and frontend",
                ))

        return mismatches

    def _create_dto_mismatch(
        self,
        name: str,
        py_dto: Dict,
        ts_dto: Dict,
        field_name: str,
        mismatch_type: str,
        backend_definition: str = None,
        frontend_definition: str = None,
        severity: PatternSeverity = PatternSeverity.MEDIUM,
        recommendation: str = "",
    ) -> DTOMismatch:
        """Create a DTOMismatch object (Issue #665: extracted helper)."""
        return DTOMismatch(
            mismatch_id=f"dto_{name}_{field_name}_{uuid.uuid4().hex[:8]}",
            backend_type=name,
            frontend_type=name,
            backend_location=py_dto.get("location"),
            frontend_location=ts_dto.get("location"),
            field_name=field_name,
            mismatch_type=mismatch_type,
            backend_definition=backend_definition,
            frontend_definition=frontend_definition,
            severity=severity,
            recommendation=recommendation,
        )

    async def _find_validation_duplications(
        self,
        python_patterns: List[Dict],
        typescript_patterns: List[Dict],
    ) -> List[ValidationDuplication]:
        """Find duplicated validation logic across languages."""
        duplications = []

        # Get all validation patterns
        py_validations = [
            p for p in python_patterns
            if p.get("type") == PatternType.VALIDATION_RULE
        ]
        ts_validations = [
            p for p in typescript_patterns
            if p.get("type") == PatternType.VALIDATION_RULE
        ]

        # Group by validation type
        py_by_type: Dict[str, List[Dict]] = {}
        for v in py_validations:
            vtype = v.get("validation_type", "custom")
            if vtype:
                py_by_type.setdefault(vtype, []).append(v)

        ts_by_type: Dict[str, List[Dict]] = {}
        for v in ts_validations:
            vtype = v.get("validation_type", "custom")
            if vtype:
                ts_by_type.setdefault(vtype, []).append(v)

        # Find duplications
        common_types = set(py_by_type.keys()) & set(ts_by_type.keys())

        for vtype in common_types:
            py_validators = py_by_type[vtype]
            ts_validators = ts_by_type[vtype]

            # Issue #616: O(n²) pairwise comparison is BOUNDED to max 9 pairs per type
            # (3 py × 3 ts) to prevent combinatorial explosion while still finding matches
            for py_v in py_validators[:3]:
                for ts_v in ts_validators[:3]:
                    duplications.append(ValidationDuplication(
                        duplication_id=f"val_{vtype}_{uuid.uuid4().hex[:8]}",
                        validation_type=vtype,
                        python_location=py_v.get("location"),
                        typescript_location=ts_v.get("location"),
                        python_code=py_v.get("code", "")[:200],
                        typescript_code=ts_v.get("code", "")[:200],
                        similarity_score=0.8,  # Assume high similarity for same type
                        severity=PatternSeverity.MEDIUM,
                        recommendation=f"Consider consolidating '{vtype}' validation logic into a shared schema or specification",
                    ))

        return duplications

    async def _find_api_contract_mismatches(
        self,
        python_patterns: List[Dict],
        typescript_patterns: List[Dict],
    ) -> List[APIContractMismatch]:
        """Find mismatches between backend endpoints and frontend API calls."""
        mismatches = []

        # Get all API patterns
        backend_endpoints = {
            (p.get("method", "GET"), self._normalize_path(p.get("path", ""))): p
            for p in python_patterns
            if p.get("type") == PatternType.API_ENDPOINT
        }

        frontend_calls = {
            (p.get("method", "GET"), self._normalize_path(p.get("path", ""))): p
            for p in typescript_patterns
            if p.get("type") == PatternType.API_CALL
        }

        # Find orphaned endpoints (backend has, frontend doesn't call)
        backend_only = set(backend_endpoints.keys()) - set(frontend_calls.keys())
        for method, path in backend_only:
            ep = backend_endpoints[(method, path)]
            mismatches.append(APIContractMismatch(
                mismatch_id=f"api_orphan_{uuid.uuid4().hex[:8]}",
                endpoint_path=path,
                http_method=method,
                mismatch_type="orphaned_endpoint",
                backend_location=ep.get("location"),
                backend_definition=ep.get("code", "")[:200],
                severity=PatternSeverity.LOW,
                details="Backend endpoint has no matching frontend call",
                recommendation="Consider removing unused endpoint or add frontend integration",
            ))

        # Find missing endpoints (frontend calls, backend doesn't have)
        frontend_only = set(frontend_calls.keys()) - set(backend_endpoints.keys())
        for method, path in frontend_only:
            call = frontend_calls[(method, path)]
            # Skip dynamic paths
            if call.get("is_dynamic"):
                continue

            mismatches.append(APIContractMismatch(
                mismatch_id=f"api_missing_{uuid.uuid4().hex[:8]}",
                endpoint_path=path,
                http_method=method,
                mismatch_type="missing_endpoint",
                frontend_location=call.get("location"),
                frontend_call=call.get("code", "")[:200],
                severity=PatternSeverity.CRITICAL,
                details="Frontend calls endpoint that doesn't exist in backend",
                recommendation="Create backend endpoint or fix frontend API call",
            ))

        return mismatches

    def _normalize_path(self, path: str) -> str:
        """Normalize API path for comparison."""
        # Remove leading/trailing slashes
        path = path.strip("/")
        # Replace path parameters
        path = re.sub(r"\{[^}]+\}", "{param}", path)
        path = re.sub(r"\$\{[^}]+\}", "{param}", path)
        path = re.sub(r":\w+", "{param}", path)
        return f"/{path}"

    async def _build_patterns_with_embeddings(
        self,
        patterns: List[Dict],
        language: str,
    ) -> List[Dict]:
        """
        Build pattern objects with embeddings for a list of patterns.

        Issue #659: Uses batch embedding for 5-10x speedup via parallel requests.

        Args:
            patterns: Raw patterns to process
            language: Language identifier (python/typescript)

        Returns:
            List of patterns with embeddings added
        """
        prefix = "py_" if language == "python" else "ts_"
        result = []

        # Limit patterns to process for performance (individual LLM calls are slow)
        # Prioritize significant patterns: DTOs, APIs, validators over utility functions
        patterns_to_process = self._prioritize_patterns_for_embedding(patterns)

        if len(patterns_to_process) < len(patterns):
            logger.info(
                "Sampling %d of %d %s patterns for embedding",
                len(patterns_to_process), len(patterns), language
            )

        # Issue #659: Normalize all patterns first, then batch embed
        normalized_texts = []
        for p in patterns_to_process:
            normalized = await self._normalize_pattern(p)
            normalized_texts.append(normalized)

        # Batch generate embeddings with parallel requests (5-10x faster)
        embeddings = await self._get_embeddings_batch(normalized_texts)

        # Build result list with successful embeddings
        for i, (p, normalized, embedding) in enumerate(
            zip(patterns_to_process, normalized_texts, embeddings)
        ):
            if embedding:
                pattern_id = f"{prefix}{hashlib.sha256(normalized.encode()).hexdigest()[:12]}"
                result.append({
                    "id": pattern_id,
                    "pattern": p,
                    "normalized": normalized,
                    "embedding": embedding,
                    "language": language,
                })

        return result

    def _prioritize_patterns_for_embedding(self, patterns: List[Dict]) -> List[Dict]:
        """
        Prioritize patterns for embedding generation.

        Returns up to MAX_PATTERNS_FOR_EMBEDDING patterns, prioritizing:
        1. DTOs and type definitions
        2. API endpoints and routes
        3. Validators
        4. Other patterns (by code length for significance)
        """
        from .models import PatternType

        # Separate by priority
        high_priority = []  # DTOs, APIs, Validators
        normal_priority = []  # Everything else

        for p in patterns:
            pattern_type = p.get("type")
            if pattern_type in (
                PatternType.DTO_DEFINITION,
                PatternType.API_ENDPOINT,
                PatternType.VALIDATION_RULE,
                PatternType.TYPE_ALIAS,
            ):
                high_priority.append(p)
            else:
                normal_priority.append(p)

        # Sort normal priority by code length (longer = more significant)
        normal_priority.sort(key=lambda x: len(x.get("code", "")), reverse=True)

        # Combine with high priority first
        combined = high_priority + normal_priority

        # Apply limit
        return combined[:MAX_PATTERNS_FOR_EMBEDDING]

    async def _store_patterns_in_chromadb(
        self,
        collection,
        patterns: List[Dict],
    ) -> List[Dict]:
        """
        Store patterns in ChromaDB with error recovery.

        Args:
            collection: ChromaDB collection
            patterns: Patterns with embeddings to store

        Returns:
            List of successfully stored patterns
        """
        # Try batch insertion first
        try:
            await collection.add(
                ids=[p["id"] for p in patterns],
                embeddings=[p["embedding"] for p in patterns],
                documents=[p["normalized"] for p in patterns],
                metadatas=[{
                    "language": p["language"],
                    "type": str(p["pattern"].get("type", "unknown")),
                    "name": p["pattern"].get("name", ""),
                } for p in patterns],
            )
            return patterns
        except Exception as batch_error:
            logger.warning(
                "Batch insertion failed (%s), falling back to individual insertion",
                batch_error
            )

        # Fall back to individual insertion for error recovery
        stored_patterns = []
        for pattern in patterns:
            try:
                await collection.add(
                    ids=[pattern["id"]],
                    embeddings=[pattern["embedding"]],
                    documents=[pattern["normalized"]],
                    metadatas=[{
                        "language": pattern["language"],
                        "type": str(pattern["pattern"].get("type", "unknown")),
                        "name": pattern["pattern"].get("name", ""),
                    }],
                )
                stored_patterns.append(pattern)
            except Exception as individual_error:
                logger.debug(
                    "Failed to store pattern %s: %s",
                    pattern["id"],
                    individual_error
                )

        if stored_patterns:
            logger.info(
                "Recovered %d/%d patterns via individual insertion",
                len(stored_patterns),
                len(patterns)
            )
        else:
            logger.error("All pattern insertions failed")

        return stored_patterns

    async def _query_cross_language_matches(
        self,
        collection,
        python_patterns: List[Dict],
        typescript_patterns: List[Dict],
    ) -> List[PatternMatch]:
        """
        Query for similar patterns across Python and TypeScript.

        Args:
            collection: ChromaDB collection
            python_patterns: Python patterns with embeddings
            typescript_patterns: TypeScript patterns with embeddings

        Returns:
            List of pattern matches above similarity threshold
        """
        matches = []
        ts_pattern_lookup = {p["id"]: p for p in typescript_patterns}

        for py_p in python_patterns[:50]:  # Limit queries
            try:
                results = await collection.query(
                    query_embeddings=[py_p["embedding"]],
                    n_results=5,
                    where={"language": "typescript"},
                )

                if not results or not results.get("distances"):
                    continue

                for distance, doc_id in zip(
                    results["distances"][0],
                    results["ids"][0]
                ):
                    similarity = 1 - distance  # Convert distance to similarity

                    if similarity < SIMILARITY_MEDIUM:
                        continue

                    ts_pattern = ts_pattern_lookup.get(doc_id)
                    if ts_pattern:
                        matches.append(PatternMatch(
                            pattern_id=f"match_{uuid.uuid4().hex[:8]}",
                            similarity_score=similarity,
                            source_location=py_p["pattern"].get("location"),
                            target_location=ts_pattern["pattern"].get("location"),
                            source_code=py_p["pattern"].get("code", "")[:300],
                            target_code=ts_pattern["pattern"].get("code", "")[:300],
                            match_type="semantic",
                            confidence=similarity,
                            metadata={
                                "python_name": py_p["pattern"].get("name"),
                                "typescript_name": ts_pattern["pattern"].get("name"),
                                "pattern_type": str(py_p["pattern"].get("type")),
                            },
                        ))
            except Exception as e:
                logger.warning("Query failed for pattern %s: %s", py_p["id"], e)

        return matches

    async def _find_semantic_matches(
        self,
        python_patterns: List[Dict],
        typescript_patterns: List[Dict],
    ) -> List[PatternMatch]:
        """Find semantically similar patterns using embeddings."""
        if not self.use_llm:
            return []

        collection = await self._get_chromadb_collection()
        if not collection:
            logger.warning("ChromaDB not available for semantic matching")
            return []

        # Build patterns with embeddings for both languages
        python_with_emb = await self._build_patterns_with_embeddings(
            python_patterns, "python"
        )
        ts_with_emb = await self._build_patterns_with_embeddings(
            typescript_patterns, "typescript"
        )

        all_patterns = python_with_emb + ts_with_emb
        if not all_patterns:
            return []

        # Store in ChromaDB
        stored_patterns = await self._store_patterns_in_chromadb(collection, all_patterns)
        if not stored_patterns:
            return []

        # Filter stored patterns by language
        stored_python = [p for p in stored_patterns if p["language"] == "python"]
        stored_ts = [p for p in stored_patterns if p["language"] == "typescript"]

        # Query for cross-language matches
        return await self._query_cross_language_matches(
            collection, stored_python, stored_ts
        )

    async def _cache_results(
        self,
        analysis: CrossLanguageAnalysis
    ) -> None:
        """Cache analysis results in Redis."""
        redis = await self._get_redis_client()
        if not redis:
            return

        try:
            cache_key = f"cross_lang_analysis:{analysis.analysis_id}"
            cache_data = json.dumps(analysis.to_dict(), default=str)

            await redis.setex(cache_key, 3600, cache_data)  # 1 hour TTL
            logger.info("Cached analysis results: %s", cache_key)
        except Exception as e:
            logger.warning("Failed to cache results: %s", e)

    async def _run_pattern_detection(
        self, analysis: CrossLanguageAnalysis
    ) -> tuple[list, list]:
        """
        Collect files, extract patterns, and find mismatches.

        Returns:
            Tuple of (python_patterns, all_ts_patterns)
        """
        # Collect files
        python_files, typescript_files, vue_files = await self._collect_files()
        analysis.python_files_analyzed = len(python_files)
        analysis.typescript_files_analyzed = len(typescript_files)
        analysis.vue_files_analyzed = len(vue_files)

        logger.info(
            "Found %d Python, %d TypeScript, %d Vue files",
            len(python_files), len(typescript_files), len(vue_files)
        )

        # Extract patterns
        python_patterns, typescript_patterns, vue_patterns = await self._extract_all_patterns(
            python_files, typescript_files, vue_files
        )
        all_ts_patterns = typescript_patterns + vue_patterns

        logger.info(
            "Extracted %d Python, %d TypeScript/Vue patterns",
            len(python_patterns), len(all_ts_patterns)
        )

        # Find mismatches
        analysis.dto_mismatches = await self._find_dto_mismatches(python_patterns, all_ts_patterns)
        analysis.validation_duplications = await self._find_validation_duplications(python_patterns, all_ts_patterns)
        analysis.api_contract_mismatches = await self._find_api_contract_mismatches(python_patterns, all_ts_patterns)

        if self.use_llm:
            analysis.pattern_matches = await self._find_semantic_matches(python_patterns, all_ts_patterns)

        return python_patterns, all_ts_patterns

    def _convert_to_cross_language_patterns(
        self, patterns: list, analysis: CrossLanguageAnalysis
    ) -> None:
        """Convert extracted patterns to CrossLanguagePattern objects."""
        for p in patterns:
            pattern_type = p.get("type", PatternType.UTILITY_FUNCTION)
            if not isinstance(pattern_type, PatternType):
                continue

            category = p.get("category", PatternCategory.UTILITIES)
            if not isinstance(category, PatternCategory):
                category = PatternCategory.UTILITIES

            location = p.get("location")
            if not location:
                continue

            cross_pattern = CrossLanguagePattern(
                pattern_id=f"pattern_{uuid.uuid4().hex[:8]}",
                pattern_type=pattern_type,
                category=category,
                severity=PatternSeverity.INFO,
                name=p.get("name", "unknown"),
                description=f"{pattern_type.value}: {p.get('name', 'unknown')}",
            )

            if location.language == "python":
                cross_pattern.python_locations.append(location)
                cross_pattern.python_code = p.get("code", "")[:500]
            else:
                cross_pattern.typescript_locations.append(location)
                cross_pattern.typescript_code = p.get("code", "")[:500]

            analysis.patterns.append(cross_pattern)

    async def run_analysis(self) -> CrossLanguageAnalysis:
        """
        Run full cross-language pattern analysis.

        Returns:
            CrossLanguageAnalysis with all detected patterns and issues
        """
        start_time = time.time()
        analysis = CrossLanguageAnalysis(
            analysis_id=f"cla_{uuid.uuid4().hex[:12]}",
            scan_timestamp=datetime.now(),
        )

        logger.info("Starting cross-language pattern analysis on %s", self.project_root)

        try:
            # Run pattern detection and mismatch finding
            python_patterns, all_ts_patterns = await self._run_pattern_detection(analysis)

            # Convert to CrossLanguagePattern objects
            self._convert_to_cross_language_patterns(python_patterns + all_ts_patterns, analysis)

            # Calculate statistics and update metrics
            analysis.calculate_stats()
            analysis.analysis_time_ms = (time.time() - start_time) * 1000
            analysis.embeddings_generated = self._embeddings_generated
            analysis.cache_hits = self._cache_hits
            analysis.cache_misses = self._cache_misses

            await self._cache_results(analysis)

            logger.info(
                "Analysis complete: %d patterns, %d DTO mismatches, %d API mismatches, %d validation dups in %.2fms",
                analysis.total_patterns,
                len(analysis.dto_mismatches),
                len(analysis.api_contract_mismatches),
                len(analysis.validation_duplications),
                analysis.analysis_time_ms,
            )

        except Exception as e:
            logger.error("Analysis failed: %s", e, exc_info=True)
            analysis.errors.append(str(e))

        return analysis
