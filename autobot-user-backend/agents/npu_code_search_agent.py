# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU-Powered Code Search Agent

A high-performance agent that uses NPU acceleration with Redis for searching
through codebases. Combines OpenVINO NPU optimization with Redis indexing
for fast semantic code search.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiofiles

from code_embedding_generator import get_code_embedding_generator
from npu_semantic_search import get_npu_search_engine
from autobot_shared.redis_client import get_redis_client
from worker_node import WorkerNode

from .base_agent import AgentRequest
from .standardized_agent import ActionHandler, StandardizedAgent

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for code element types
_CODE_ELEMENT_TYPES = ("functions", "classes", "imports", "variables")

# Issue #380: Module-level frozenset for ignored directories in code search
_IGNORED_DIRS = frozenset(
    {"node_modules", "__pycache__", ".git", "dist", "build", "target"}
)


@dataclass
class CodeSearchResult:
    """Result of code search operation"""

    file_path: str
    content: str
    line_number: int
    confidence: float
    context_lines: List[str]
    metadata: Dict[str, Any]


@dataclass
class SearchStats:
    """Search performance statistics"""

    total_files_indexed: int
    search_time_ms: float
    npu_acceleration_used: bool
    redis_cache_hit: bool
    results_count: int


class NPUCodeSearchAgent(StandardizedAgent):
    """
    NPU-accelerated code search agent using Redis for indexing.

    Features:
    - NPU-accelerated semantic similarity (when available)
    - Redis-based indexing for fast lookups
    - Multi-language code understanding
    - Context-aware search results
    - Performance monitoring

    Issue #281: Extracted helper methods for initialization.
    """

    @staticmethod
    def _get_supported_extensions() -> set:
        """Get set of supported file extensions for code search."""
        return {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".cs",
            ".rb",
            ".go",
            ".rs",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".clj",
            ".elm",
            ".hs",
            ".ml",
            ".sh",
            ".bash",
            ".zsh",
            ".ps1",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".scss",
            ".less",
            ".sql",
            ".r",
            ".m",
            ".pl",
            ".lua",
            ".vim",
            ".md",
        }

    @staticmethod
    def _get_action_handlers() -> Dict[str, ActionHandler]:
        """Get action handlers for the agent."""
        return {
            "search_code": ActionHandler(
                handler_method="handle_search_code",
                required_params=["query"],
                optional_params=["max_results", "file_patterns"],
                description="Search for code using NPU-accelerated semantic search",
            ),
            "index_directory": ActionHandler(
                handler_method="handle_index_directory",
                required_params=["directory"],
                optional_params=["force_reindex"],
                description="Index a directory for code search",
            ),
            "get_capabilities": ActionHandler(
                handler_method="handle_get_capabilities",
                description="Get agent capabilities",
            ),
        }

    @staticmethod
    def _get_language_patterns() -> Dict[str, Dict[str, str]]:
        """Get language-specific code patterns for parsing."""
        return {
            "python": {
                "function": r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
                "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(:]",
                "import": r"(?:from\s+\S+\s+)?import\s+([^#\n]+)",
                "variable": r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=",
            },
            "javascript": {
                "function": (
                    r"(?:function\s+([a-zA-Z_][a-zA-Z0-9_]*)|"
                    r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*function|"
                    r"\bconst\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:\(.*?\)\s*=>|\bfunction))"
                ),
                "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                "import": (
                    r'(?:import|require)\s*\(\s*[\'"]([^\'"]+)[\'"]|'
                    r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'
                ),
                "variable": r"(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            },
        }

    def _init_communication(self) -> None:
        """Initialize communication protocol for agent-to-agent messaging."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.initialize_communication(self.capabilities))
            else:
                loop.run_until_complete(
                    self.initialize_communication(self.capabilities)
                )
        except RuntimeError:
            logger.debug(
                "Event loop not available, will initialize communication later"
            )

    def __init__(self):
        """
        Initialize the NPU code search agent.

        Issue #281: Refactored from 135 lines to use extracted helper methods.
        """
        super().__init__("npu_code_search")
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Redis setup
        self.redis_client = get_redis_client(async_client=False)
        self.redis_async_client = get_redis_client(async_client=True)

        # Worker node for NPU capabilities
        self.worker_node = WorkerNode()
        self.npu_search_engine = None  # NPU Semantic Search Engine (Issue #68)

        # Search configuration
        self.index_prefix = "autobot:code:index:"
        self.search_cache_prefix = "autobot:search:cache:"
        self.cache_ttl = 3600  # 1 hour cache

        # NPU optimization
        self.npu_available = False
        self.openvino_core = None
        self._init_npu()

        # Define capabilities
        self.capabilities = [
            "code_search",
            "semantic_similarity",
            "npu_acceleration",
            "redis_indexing",
            "file_indexing",
            "pattern_matching",
        ]

        # Register action handlers and initialize data
        self.register_actions(self._get_action_handlers())
        self.supported_extensions = self._get_supported_extensions()
        self.language_patterns = self._get_language_patterns()
        self.stats = SearchStats(0, 0.0, False, False, 0)

        # Initialize communication protocol
        self._init_communication()

    def _init_npu(self):
        """Initialize NPU acceleration if available"""
        try:
            # Check worker capabilities for NPU
            capabilities = self.worker_node.detect_capabilities()
            self.npu_available = capabilities.get("openvino_npu_available", False)

            if self.npu_available:
                from openvino.runtime import Core

                self.openvino_core = Core()
                npu_devices = capabilities.get("openvino_npu_devices", [])
                self.logger.info("🚀 NPU acceleration initialized: %s", npu_devices)
            else:
                self.logger.info("NPU acceleration not available, using CPU fallback")

        except Exception as e:
            self.logger.warning("Failed to initialize NPU: %s", e)
            self.npu_available = False

    async def _ensure_search_engine_initialized(self):
        """Lazy-initialize NPU semantic search engine when needed (Issue #68)"""
        if self.npu_search_engine is None:
            self.logger.info("Initializing NPU Semantic Search Engine...")
            self.npu_search_engine = await get_npu_search_engine()
            self.logger.info("✅ NPU Semantic Search Engine initialized")

    async def handle_search_code(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle code search action"""
        query = request.payload["query"]
        max_results = request.payload.get("max_results", 10)
        file_patterns = request.payload.get("file_patterns", [])

        results = await self.search_code(
            query=query, max_results=max_results, file_patterns=file_patterns
        )

        return {
            "search_results": [
                {
                    "file_path": r.file_path,
                    "content": r.content,
                    "line_number": r.line_number,
                    "confidence": r.confidence,
                    "context_lines": r.context_lines,
                    "metadata": r.metadata,
                }
                for r in results
            ]
        }

    async def handle_index_directory(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle directory indexing action"""
        directory = request.payload["directory"]
        force_reindex = request.payload.get("force_reindex", False)

        stats = await self.index_codebase(directory, force_reindex)
        return {"indexing_stats": stats}

    async def handle_get_capabilities(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle capabilities request"""
        return {"capabilities": self.capabilities}

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports"""
        return self.capabilities

    def _is_ignored_dir(self, dirname: str) -> bool:
        """Check if directory should be ignored (Issue #334 - extracted helper)."""
        if dirname.startswith("."):
            return True
        return dirname in _IGNORED_DIRS  # Issue #380: use module constant

    def _is_supported_file(self, filename: str) -> bool:
        """Check if file has supported extension (Issue #334 - extracted helper)."""
        return any(filename.endswith(ext) for ext in self.supported_extensions)

    async def _index_directory_files(
        self, root: str, files: list, root_path: str, errors: list
    ) -> tuple:
        """Index files in a directory (Issue #334 - extracted helper)."""
        indexed = 0
        skipped = 0
        for file in files:
            if not self._is_supported_file(file):
                skipped += 1
                continue
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, root_path)
            try:
                await self._index_file(file_path, relative_path)
                indexed += 1
                if indexed % 100 == 0:
                    self.logger.info("Indexed %s files...", indexed)
            except Exception as e:
                errors.append(f"{relative_path}: {str(e)}")
                self.logger.error("Failed to index %s: %s", file_path, e)
        return indexed, skipped

    def _get_index_key(self, root_path: str) -> str:
        """Generate index key for root path (Issue #398: extracted)."""
        return f"{self.index_prefix}meta:{hashlib.md5(root_path.encode(), usedforsecurity=False).hexdigest()}"

    async def _store_index_metadata(
        self, index_key: str, root_path: str, indexed_files: int
    ) -> None:
        """Store indexing metadata to Redis (Issue #398: extracted)."""
        metadata = {
            "root_path": root_path,
            "indexed_files": indexed_files,
            "timestamp": time.time(),
            "npu_available": self.npu_available,
        }
        await asyncio.to_thread(
            self.redis_client.setex, index_key, 86400, json.dumps(metadata)
        )

    def _build_index_result(
        self,
        indexed_files: int,
        skipped_files: int,
        errors: list,
        execution_time: float,
        index_key: str,
    ) -> Dict[str, Any]:
        """Build indexing result dict (Issue #398: extracted)."""
        return {
            "status": "success",
            "indexed_files": indexed_files,
            "skipped_files": skipped_files,
            "errors": errors[:10],
            "execution_time": execution_time,
            "index_key": index_key,
        }

    async def index_codebase(
        self, root_path: str, force_reindex: bool = False
    ) -> Dict[str, Any]:
        """Index a codebase for fast searching (Issue #398: refactored)."""
        start_time = time.time()
        indexed_files = 0
        skipped_files = 0
        errors = []

        try:
            self.logger.info("Starting codebase indexing: %s", root_path)
            index_key = self._get_index_key(root_path)

            already_indexed = await asyncio.to_thread(
                self.redis_client.exists, index_key
            )
            if not force_reindex and already_indexed:
                self.logger.info(
                    "Codebase already indexed, use force_reindex=True to re-index"
                )
                return {"status": "already_indexed", "index_key": index_key}

            for root, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if not self._is_ignored_dir(d)]
                indexed, skipped = await self._index_directory_files(
                    root, files, root_path, errors
                )
                indexed_files += indexed
                skipped_files += skipped

            await self._store_index_metadata(index_key, root_path, indexed_files)
            execution_time = time.time() - start_time
            self.logger.info(
                "Indexing complete: %d files in %.2fs", indexed_files, execution_time
            )
            return self._build_index_result(
                indexed_files, skipped_files, errors, execution_time, index_key
            )

        except Exception as e:
            self.logger.error("Codebase indexing failed: %s", e)
            return {"status": "error", "error": str(e), "indexed_files": indexed_files}

    def _build_file_index_data(
        self, relative_path: str, language: str, content: str, elements: Dict[str, List]
    ) -> Dict[str, Any]:
        """Build file index data dict (Issue #398: extracted)."""
        return {
            "file_path": relative_path,
            "language": language,
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            "line_count": len(content.splitlines()),
            "elements": elements,
            "indexed_at": time.time(),
        }

    def _store_file_to_redis(
        self,
        file_key: str,
        language_key: str,
        index_data_json: str,
        relative_path: str,
        elements: Dict[str, List],
    ) -> None:
        """Store file index to Redis (Issue #398: extracted)."""
        self.redis_client.setex(file_key, 86400, index_data_json)
        self.redis_client.sadd(language_key, relative_path)
        self.redis_client.expire(language_key, 86400)
        for element_type, element_list in elements.items():
            for element in element_list:
                element_key = (
                    f"{self.index_prefix}element:{element_type}:{element['name']}"
                )
                element_data = {
                    "file_path": relative_path,
                    "line_number": element.get("line_number", 0),
                    "context": element.get("context", ""),
                }
                self.redis_client.lpush(element_key, json.dumps(element_data))
                self.redis_client.expire(element_key, 86400)

    def _extract_element_code(
        self, content: str, line_number: int, element_type: str, max_lines: int = 50
    ) -> str:
        """
        Extract code for a specific element with context.

        Issue #207: Extract function/class code for embedding generation.

        Args:
            content: Full file content
            line_number: Starting line of the element
            element_type: 'function' or 'class'
            max_lines: Maximum lines to extract

        Returns:
            Code snippet for the element
        """
        lines = content.splitlines()
        if line_number < 1 or line_number > len(lines):
            return ""

        start_idx = line_number - 1
        end_idx = min(start_idx + max_lines, len(lines))

        start_line = lines[start_idx]
        base_indent = len(start_line) - len(start_line.lstrip())

        for i in range(start_idx + 1, end_idx):
            line = lines[i]
            if not line.strip():
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent and line.strip():
                end_idx = i
                break

        return "\n".join(lines[start_idx:end_idx])

    async def _store_single_element_embedding(
        self,
        element: Dict,
        element_type: str,
        content: str,
        relative_path: str,
        language: str,
        embedding_generator: Any,
    ) -> bool:
        """Store embedding for a single code element. Issue #620.

        Args:
            element: Code element dictionary with name and line_number
            element_type: Type of element (functions, classes)
            content: Full file content
            relative_path: Relative path to file
            language: Programming language
            embedding_generator: Embedding generator instance

        Returns:
            True if embedding stored successfully. Issue #620.
        """
        element_code = self._extract_element_code(
            content, element["line_number"], element_type
        )
        if not element_code.strip():
            return False

        content_hash = hashlib.sha256(element_code.encode()).hexdigest()
        result = await embedding_generator.generate_embedding(element_code, language)

        singular_type = (
            element_type.rstrip("es") if element_type.endswith("es") else element_type
        )
        doc_id = await self.npu_search_engine.store_code_embedding(
            embedding=result.embedding,
            code_content=element_code,
            file_path=relative_path,
            line_number=element["line_number"],
            element_type=singular_type,
            element_name=element["name"],
            language=language,
            content_hash=content_hash,
        )

        if doc_id:
            element["embedding_id"] = doc_id
            return True
        return False

    async def _generate_and_store_embeddings(
        self,
        content: str,
        relative_path: str,
        language: str,
        elements: Dict[str, List[Dict]],
    ) -> int:
        """Generate and store embeddings for code elements. Issue #207, #620."""
        try:
            embedding_generator = await get_code_embedding_generator()
            await self._ensure_search_engine_initialized()

            stored_count = 0
            for element_type in ["functions", "classes"]:
                for element in elements.get(element_type, []):
                    if await self._store_single_element_embedding(
                        element,
                        element_type,
                        content,
                        relative_path,
                        language,
                        embedding_generator,
                    ):
                        stored_count += 1

            return stored_count

        except Exception as e:
            self.logger.warning(
                "Failed to generate embeddings for %s: %s", relative_path, e
            )
            return 0

    async def _index_file(self, file_path: str, relative_path: str):
        """Index a single file with embeddings (Issue #207, #398: refactored)."""
        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()

            if not content.strip():
                return

            file_ext = os.path.splitext(file_path)[1]
            language = self._detect_language(file_ext)
            elements = self._extract_code_elements(content, language)

            embedding_count = await self._generate_and_store_embeddings(
                content, relative_path, language, elements
            )

            if embedding_count > 0:
                self.logger.debug(
                    "Generated %d embeddings for %s", embedding_count, relative_path
                )

            index_data = self._build_file_index_data(
                relative_path, language, content, elements
            )

            file_key = f"{self.index_prefix}file:{relative_path}"
            language_key = f"{self.index_prefix}lang:{language}"
            index_data_json = json.dumps(index_data)

            await asyncio.to_thread(
                self._store_file_to_redis,
                file_key,
                language_key,
                index_data_json,
                relative_path,
                elements,
            )

        except OSError as e:
            raise OSError(f"Failed to read file {file_path}: {e}")
        except Exception as e:
            raise Exception(f"Failed to index file {file_path}: {e}")

    def _detect_language(self, file_ext: str) -> str:
        """Detect programming language from file extension"""
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".cs": "csharp",
            ".rb": "ruby",
            ".go": "go",
            ".rs": "rust",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "zsh",
            ".ps1": "powershell",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".md": "markdown",
        }
        return language_map.get(file_ext.lower(), "unknown")

    def _extract_elements_by_pattern(
        self,
        lines: List[str],
        pattern: str,
        use_first_group: bool = False,
    ) -> List[Dict]:
        """
        Extract code elements matching a regex pattern from source lines.

        Issue #281: Extracted helper to reduce repetition in _extract_code_elements.

        Args:
            lines: Source code lines to search
            pattern: Regex pattern to match
            use_first_group: If True, use first non-None group; otherwise use group(1)

        Returns:
            List of element dicts with name, line_number, and context
        """
        import re

        elements = []
        for i, line in enumerate(lines):
            matches = re.finditer(pattern, line)
            for match in matches:
                if use_first_group:
                    name = next((g for g in match.groups() if g), None)
                else:
                    name = match.group(1)
                if name:
                    elements.append(
                        {
                            "name": name.strip(),
                            "line_number": i + 1,
                            "context": line.strip(),
                        }
                    )
        return elements

    def _extract_code_elements(
        self, content: str, language: str
    ) -> Dict[str, List[Dict]]:
        """Extract code elements (functions, classes, etc.) from content"""
        elements = {"functions": [], "classes": [], "imports": [], "variables": []}

        if language not in self.language_patterns:
            return elements

        patterns = self.language_patterns[language]
        lines = content.splitlines()

        # Issue #281: Use extracted helper for all element types
        if "function" in patterns:
            elements["functions"] = self._extract_elements_by_pattern(
                lines, patterns["function"], use_first_group=True
            )

        if "class" in patterns:
            elements["classes"] = self._extract_elements_by_pattern(
                lines, patterns["class"], use_first_group=False
            )

        if "import" in patterns:
            elements["imports"] = self._extract_elements_by_pattern(
                lines, patterns["import"], use_first_group=True
            )

        return elements

    def _get_search_cache_key(
        self, query: str, search_type: str, language: Optional[str]
    ) -> str:
        """Generate search cache key (Issue #398: extracted)."""
        cache_input = query + search_type + str(language)
        return f"{self.search_cache_prefix}{hashlib.md5(cache_input.encode(), usedforsecurity=False).hexdigest()}"

    def _serialize_results(
        self, results: List[CodeSearchResult]
    ) -> List[Dict[str, Any]]:
        """Serialize results for caching (Issue #398: extracted)."""
        return [
            {
                "file_path": r.file_path,
                "content": r.content,
                "line_number": r.line_number,
                "confidence": r.confidence,
                "context_lines": r.context_lines,
                "metadata": r.metadata,
            }
            for r in results
        ]

    def _merge_semantic_result(
        self,
        result: CodeSearchResult,
        merged: Dict[tuple, CodeSearchResult],
        semantic_weight: float,
    ) -> None:
        """Merge a semantic result into the combined results dict. Issue #620.

        Args:
            result: Semantic search result to merge
            merged: Dictionary of merged results keyed by (file_path, line_number)
            semantic_weight: Weight multiplier for semantic scores
        """
        key = (result.file_path, result.line_number)
        weighted_score = result.confidence * semantic_weight
        merged[key] = CodeSearchResult(
            file_path=result.file_path,
            content=result.content,
            line_number=result.line_number,
            confidence=weighted_score,
            context_lines=result.context_lines,
            metadata={
                **result.metadata,
                "search_type": "hybrid",
                "semantic_score": result.confidence,
            },
        )

    def _merge_keyword_result(
        self,
        result: CodeSearchResult,
        merged: Dict[tuple, CodeSearchResult],
        keyword_weight: float,
    ) -> None:
        """Merge a keyword result into the combined results dict. Issue #620.

        Args:
            result: Keyword search result to merge
            merged: Dictionary of merged results keyed by (file_path, line_number)
            keyword_weight: Weight multiplier for keyword scores
        """
        key = (result.file_path, result.line_number)
        keyword_score = result.confidence * keyword_weight

        if key in merged:
            merged[key].confidence += keyword_score
            merged[key].metadata["keyword_score"] = result.confidence
            merged[key].metadata["combined"] = True
        else:
            merged[key] = CodeSearchResult(
                file_path=result.file_path,
                content=result.content,
                line_number=result.line_number,
                confidence=keyword_score,
                context_lines=result.context_lines,
                metadata={
                    **result.metadata,
                    "search_type": "hybrid",
                    "keyword_score": result.confidence,
                },
            )

    async def _search_hybrid(
        self,
        query: str,
        language: Optional[str],
        max_results: int,
        semantic_weight: float = 0.7,
    ) -> List[CodeSearchResult]:
        """Perform hybrid search combining semantic and keyword matching. Issue #207, #620.

        Args:
            query: Search query
            language: Filter by language
            max_results: Maximum results
            semantic_weight: Weight for semantic results (0-1)

        Returns:
            Combined and ranked results
        """
        keyword_weight = 1.0 - semantic_weight
        semantic_results = []
        keyword_results = []

        try:
            semantic_results = await self._search_code_embeddings(
                query, language, max_results * 2
            )
        except Exception as e:
            self.logger.warning("Hybrid: semantic search failed: %s", e)

        try:
            keyword_results = await self._search_exact(query, language, max_results * 2)
        except Exception as e:
            self.logger.warning("Hybrid: keyword search failed: %s", e)

        merged: Dict[tuple, CodeSearchResult] = {}
        for result in semantic_results:
            self._merge_semantic_result(result, merged, semantic_weight)
        for result in keyword_results:
            self._merge_keyword_result(result, merged, keyword_weight)

        results = sorted(merged.values(), key=lambda x: x.confidence, reverse=True)
        self.logger.info(
            "Hybrid search: %d results (semantic: %d, keyword: %d)",
            len(results),
            len(semantic_results),
            len(keyword_results),
        )
        return results[:max_results]

    async def _execute_search_by_type(
        self, query: str, search_type: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Execute search based on type (Issue #207, #398: extracted)."""
        if search_type == "element":
            return await self._search_elements(query, language, max_results)
        elif search_type == "exact":
            return await self._search_exact(query, language, max_results)
        elif search_type == "regex":
            return await self._search_regex(query, language, max_results)
        elif search_type == "hybrid":
            return await self._search_hybrid(query, language, max_results)
        return await self._search_semantic(query, language, max_results)

    async def search_code(
        self,
        query: str,
        search_type: str = "semantic",
        language: Optional[str] = None,
        max_results: int = 20,
    ) -> List[CodeSearchResult]:
        """Search through indexed code (Issue #398: refactored)."""
        start_time = time.time()

        try:
            cache_key = self._get_search_cache_key(query, search_type, language)
            cached_result = await asyncio.to_thread(self.redis_client.get, cache_key)

            if cached_result:
                self.stats.redis_cache_hit = True
                results = [CodeSearchResult(**r) for r in json.loads(cached_result)]
                self.stats.search_time_ms = (time.time() - start_time) * 1000
                self.stats.results_count = len(results)
                return results[:max_results]

            results = await self._execute_search_by_type(
                query, search_type, language, max_results
            )
            serializable_results = self._serialize_results(results)
            await asyncio.to_thread(
                self.redis_client.setex,
                cache_key,
                self.cache_ttl,
                json.dumps(serializable_results),
            )

            self.stats.search_time_ms = (time.time() - start_time) * 1000
            self.stats.npu_acceleration_used = (
                self.npu_available and search_type == "semantic"
            )
            self.stats.redis_cache_hit = False
            self.stats.results_count = len(results)
            return results

        except Exception as e:
            self.logger.error("Code search failed: %s", e)
            return []

    async def _search_elements(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Search for specific code elements (functions, classes, etc.)"""
        results = []

        # Search across all element types - Issue #380: Use module-level tuple
        for element_type in _CODE_ELEMENT_TYPES:
            element_key = f"{self.index_prefix}element:{element_type}:{query}"
            # Issue #361 - avoid blocking
            element_data_list = await asyncio.to_thread(
                self.redis_client.lrange, element_key, 0, max_results
            )

            for element_data in element_data_list:
                try:
                    element = json.loads(element_data)
                    file_path = element["file_path"]

                    # Language filter
                    if language and not self._file_matches_language(
                        file_path, language
                    ):
                        continue

                    # Load file content for context
                    content_lines = await self._get_file_context(
                        file_path, element["line_number"]
                    )

                    result = CodeSearchResult(
                        file_path=file_path,
                        content=element.get("context", ""),
                        line_number=element["line_number"],
                        confidence=1.0,  # Exact match
                        context_lines=content_lines,
                        metadata={
                            "element_type": element_type,
                            "search_type": "element",
                            "query": query,
                        },
                    )
                    results.append(result)

                except Exception as e:
                    self.logger.error("Error processing element result: %s", e)

        return results[:max_results]

    def _search_lines_for_query(
        self, lines: List[str], query: str, file_path: str, language: str
    ) -> List[CodeSearchResult]:
        """Search lines for exact query match (Issue #334 - extracted helper)."""
        results = []
        for i, line in enumerate(lines):
            if query not in line:
                continue
            context_lines = self._get_context_lines(lines, i, 2)
            result = CodeSearchResult(
                file_path=file_path,
                content=line.strip(),
                line_number=i + 1,
                confidence=1.0,
                context_lines=context_lines,
                metadata={"search_type": "exact", "query": query, "language": language},
            )
            results.append(result)
        return results

    async def _search_file_exact(
        self, file_data: Dict[str, Any], query: str, language: Optional[str]
    ) -> List[CodeSearchResult]:
        """Search single file for exact matches (Issue #334 - extracted helper)."""
        file_path = file_data["file_path"]
        file_language = file_data["language"]

        if language and file_language != language:
            return []

        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()
            lines = content.splitlines()
            return self._search_lines_for_query(lines, query, file_path, file_language)
        except OSError as e:
            self.logger.error("Failed to read file %s: %s", file_path, e)
        except Exception as e:
            self.logger.error("Error processing file %s: %s", file_path, e)
        return []

    async def _search_exact(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Perform exact string search"""
        results = []
        pattern = f"{self.index_prefix}file:*"
        # Issue #361 - avoid blocking
        file_keys = await asyncio.to_thread(self.redis_client.keys, pattern)

        for file_key in file_keys:
            try:
                # Issue #361 - avoid blocking
                file_data_raw = await asyncio.to_thread(self.redis_client.get, file_key)
                file_data = json.loads(file_data_raw)
                file_results = await self._search_file_exact(file_data, query, language)
                results.extend(file_results)
                if len(results) >= max_results:
                    return results[:max_results]
            except Exception as e:
                self.logger.error("Error processing file key %s: %s", file_key, e)

        return results

    def _search_lines_regex(
        self, lines: List[str], pattern, query: str, file_path: str, language: str
    ) -> List[CodeSearchResult]:
        """Search lines with regex pattern (Issue #334 - extracted helper)."""
        results = []
        for i, line in enumerate(lines):
            matches = list(pattern.finditer(line))
            if not matches:
                continue
            context_lines = self._get_context_lines(lines, i, 2)
            # Create one result per match
            for match in matches:
                result = CodeSearchResult(
                    file_path=file_path,
                    content=line.strip(),
                    line_number=i + 1,
                    confidence=0.9,
                    context_lines=context_lines,
                    metadata={
                        "search_type": "regex",
                        "query": query,
                        "match": match.group(),
                        "language": language,
                    },
                )
                results.append(result)
        return results

    async def _search_file_regex(
        self, file_data: Dict[str, Any], pattern, query: str, language: Optional[str]
    ) -> List[CodeSearchResult]:
        """Search single file with regex (Issue #334 - extracted helper)."""
        file_path = file_data["file_path"]
        file_language = file_data["language"]

        if language and file_language != language:
            return []

        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()
            lines = content.splitlines()
            return self._search_lines_regex(
                lines, pattern, query, file_path, file_language
            )
        except OSError as e:
            self.logger.error("Failed to read file %s: %s", file_path, e)
        except Exception as e:
            self.logger.error("Error processing file %s: %s", file_path, e)
        return []

    async def _search_regex(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Perform regex search"""
        import re

        try:
            pattern = re.compile(query, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            self.logger.error("Invalid regex pattern: %s, error: %s", query, e)
            return []

        results = []
        file_pattern = f"{self.index_prefix}file:*"
        # Issue #361 - avoid blocking
        file_keys = await asyncio.to_thread(self.redis_client.keys, file_pattern)

        for file_key in file_keys:
            try:
                # Issue #361 - avoid blocking
                file_data_raw = await asyncio.to_thread(self.redis_client.get, file_key)
                file_data = json.loads(file_data_raw)
                file_results = await self._search_file_regex(
                    file_data, pattern, query, language
                )
                results.extend(file_results)
                if len(results) >= max_results:
                    return results[:max_results]
            except Exception as e:
                self.logger.error("Error processing file key %s: %s", file_key, e)

        return results

    def _calculate_semantic_match(
        self, line: str, query_words: List[str]
    ) -> Optional[tuple]:
        """Calculate semantic match score for a line (Issue #334 - extracted helper)."""
        line_lower = line.lower()
        matches = sum(1 for word in query_words if word in line_lower)
        if matches == 0:
            return None
        confidence = matches / len(query_words)
        if confidence < 0.3:
            return None
        return (matches, confidence)

    def _search_lines_semantic(
        self,
        lines: List[str],
        query: str,
        query_words: List[str],
        file_path: str,
        language: str,
    ) -> List[CodeSearchResult]:
        """Search lines with semantic matching (Issue #334 - extracted helper)."""
        results = []
        for i, line in enumerate(lines):
            match_info = self._calculate_semantic_match(line, query_words)
            if not match_info:
                continue
            matches, confidence = match_info
            context_lines = self._get_context_lines(lines, i, 2)
            result = CodeSearchResult(
                file_path=file_path,
                content=line.strip(),
                line_number=i + 1,
                confidence=confidence,
                context_lines=context_lines,
                metadata={
                    "search_type": "semantic",
                    "query": query,
                    "matches": matches,
                    "language": language,
                },
            )
            results.append(result)
        return results

    async def _search_file_semantic(
        self,
        file_data: Dict[str, Any],
        query: str,
        query_words: List[str],
        language: Optional[str],
    ) -> List[CodeSearchResult]:
        """Search single file semantically (Issue #334 - extracted helper)."""
        file_path = file_data["file_path"]
        file_language = file_data["language"]

        if language and file_language != language:
            return []

        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()
            lines = content.splitlines()
            return self._search_lines_semantic(
                lines, query, query_words, file_path, file_language
            )
        except OSError as e:
            self.logger.error("Failed to read file %s: %s", file_path, e)
        except Exception as e:
            self.logger.error("Error processing file %s: %s", file_path, e)
        return []

    async def _convert_npu_result(self, result: Any) -> CodeSearchResult:
        """Convert NPU search result to CodeSearchResult (Issue #398: extracted)."""
        file_path = result.metadata.get("file_path", "unknown")
        line_number = result.metadata.get("line_number", 0)
        context_lines = await self._get_file_context(
            file_path, line_number, context_size=3
        )
        return CodeSearchResult(
            file_path=file_path,
            content=result.content,
            line_number=line_number,
            confidence=result.score,
            context_lines=context_lines,
            metadata={
                **result.metadata,
                "device_used": result.device_used,
                "processing_time_ms": result.processing_time_ms,
                "embedding_model": result.embedding_model,
            },
        )

    async def _run_npu_semantic_search(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Run NPU-accelerated semantic search (Issue #398: extracted)."""
        await self._ensure_search_engine_initialized()
        search_results, metrics = await self.npu_search_engine.enhanced_search(
            query=query,
            similarity_top_k=max_results,
            filters={"language": language} if language else None,
            enable_npu_acceleration=self.npu_available,
        )
        code_results = [await self._convert_npu_result(r) for r in search_results]
        self.stats = SearchStats(
            total_files_indexed=len(code_results),
            search_time_ms=metrics.total_search_time_ms,
            npu_acceleration_used=(metrics.device_used != "cpu_fallback"),
            redis_cache_hit=False,
            results_count=len(code_results),
        )
        self.logger.info(
            "✅ Semantic search: %d results in %.2fms using %s",
            len(code_results),
            metrics.total_search_time_ms,
            metrics.device_used,
        )
        return code_results

    async def _convert_embedding_search_result(
        self, sr: Dict[str, Any], query: str, device_used: str
    ) -> CodeSearchResult:
        """Convert a single embedding search result to CodeSearchResult. Issue #620.

        Args:
            sr: Raw search result dict with content, metadata, score
            query: Original search query for metadata
            device_used: Device identifier for metadata

        Returns:
            Converted CodeSearchResult object. Issue #620.
        """
        metadata = sr["metadata"]
        file_path = metadata.get("file_path", "unknown")
        line_number = metadata.get("line_number", 0)
        context_lines = await self._get_file_context(file_path, line_number)

        return CodeSearchResult(
            file_path=file_path,
            content=sr["content"][:500],
            line_number=line_number,
            confidence=sr["score"],
            context_lines=context_lines,
            metadata={
                "element_type": metadata.get("element_type"),
                "element_name": metadata.get("element_name"),
                "language": metadata.get("language"),
                "search_type": "semantic_embedding",
                "device_used": device_used,
                "query": query,
            },
        )

    def _update_embedding_search_stats(
        self, results: List[CodeSearchResult], search_time: float, query_result: Any
    ) -> None:
        """Update search statistics after embedding search. Issue #620.

        Args:
            results: List of search results
            search_time: Search duration in milliseconds
            query_result: Query result object with device_used and cache_hit
        """
        self.stats = SearchStats(
            total_files_indexed=len(results),
            search_time_ms=search_time,
            npu_acceleration_used=(query_result.device_used in ["npu", "gpu"]),
            redis_cache_hit=query_result.cache_hit,
            results_count=len(results),
        )

    async def _search_code_embeddings(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Search code embeddings using CodeBERT. Issue #207, #620.

        Args:
            query: Search query (natural language or code)
            language: Filter by programming language
            max_results: Maximum results to return

        Returns:
            List of CodeSearchResult
        """
        start_time = time.time()

        try:
            embedding_generator = await get_code_embedding_generator()
            await self._ensure_search_engine_initialized()

            query_result = await embedding_generator.generate_embedding(
                query, language or "python"
            )

            search_results = await self.npu_search_engine.search_code_embeddings(
                query_embedding=query_result.embedding,
                language=language,
                max_results=max_results,
                similarity_threshold=0.4,
            )

            results = [
                await self._convert_embedding_search_result(
                    sr, query, query_result.device_used
                )
                for sr in search_results
            ]

            search_time = (time.time() - start_time) * 1000
            self._update_embedding_search_stats(results, search_time, query_result)
            self.logger.info(
                "Code embedding search: %d results in %.2fms using %s",
                len(results),
                search_time,
                query_result.device_used,
            )
            return results

        except Exception as e:
            self.logger.error("Code embedding search failed: %s", e)
            raise

    async def _fallback_word_matching(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """
        Fallback word-matching when embedding search unavailable.

        Issue #207: Deprecated fallback, prefer semantic search.
        """
        results = []
        query_words = query.lower().split()
        pattern = f"{self.index_prefix}file:*"
        file_keys = await asyncio.to_thread(self.redis_client.keys, pattern)

        for file_key in file_keys:
            try:
                file_data_raw = await asyncio.to_thread(self.redis_client.get, file_key)
                file_data = json.loads(file_data_raw)
                file_results = await self._search_file_semantic(
                    file_data, query, query_words, language
                )
                results.extend(file_results)
            except Exception as file_error:
                self.logger.error(
                    "Error processing file key %s: %s", file_key, file_error
                )

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:max_results]

    async def _search_semantic(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """
        Perform semantic search using code embeddings.

        Issue #207: NPU-accelerated semantic code search.

        Tries:
        1. Code embedding search (ChromaDB + CodeBERT)
        2. General NPU semantic search (knowledge base)
        3. Word-matching fallback (deprecated)
        """
        try:
            return await self._search_code_embeddings(query, language, max_results)
        except Exception as e:
            self.logger.warning(
                "Code embedding search failed: %s, trying NPU search", e
            )

        try:
            return await self._run_npu_semantic_search(query, language, max_results)
        except Exception as e:
            self.logger.warning(
                "NPU semantic search failed: %s, using word matching", e
            )

        return await self._fallback_word_matching(query, language, max_results)

    def _file_matches_language(self, file_path: str, language: str) -> bool:
        """Check if file matches the specified language"""
        file_ext = os.path.splitext(file_path)[1]
        detected_language = self._detect_language(file_ext)
        return detected_language == language

    async def _get_file_context(
        self, file_path: str, line_number: int, context_size: int = 3
    ) -> List[str]:
        """Get context lines around a specific line number"""
        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()
                lines = content.splitlines(keepends=True)

            return self._get_context_lines(lines, line_number - 1, context_size)

        except OSError as e:
            self.logger.error("Failed to read file %s: %s", file_path, e)
            return []
        except Exception as e:
            self.logger.error(
                f"Error getting context for {file_path}:{line_number}: {e}"
            )
            return []

    def _get_context_lines(
        self, lines: List[str], center_index: int, context_size: int
    ) -> List[str]:
        """Get context lines around a center index"""
        start = max(0, center_index - context_size)
        end = min(len(lines), center_index + context_size + 1)

        context = []
        for i in range(start, end):
            prefix = ">>> " if i == center_index else "    "
            context.append(f"{prefix}{i + 1}: {lines[i].rstrip()}")

        return context

    def get_search_stats(self) -> SearchStats:
        """Get current search statistics"""
        return self.stats

    async def clear_cache(self) -> Dict[str, Any]:
        """Clear search cache"""
        try:
            pattern = f"{self.search_cache_prefix}*"

            # Issue #361 - avoid blocking
            def _clear_cache():
                keys = self.redis_client.keys(pattern)
                if keys:
                    return self.redis_client.delete(*keys)
                return 0

            deleted = await asyncio.to_thread(_clear_cache)
            return {"status": "success", "keys_deleted": deleted}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def get_index_status(self) -> Dict[str, Any]:
        """Get indexing status information"""
        try:
            # Issue #361 - avoid blocking - run all Redis ops in thread pool
            def _fetch_index_status():
                # Count indexed files
                pattern = f"{self.index_prefix}file:*"
                file_keys = self.redis_client.keys(pattern)

                # Get language distribution
                lang_pattern = f"{self.index_prefix}lang:*"
                lang_keys = self.redis_client.keys(lang_pattern)

                language_stats = {}
                for lang_key in lang_keys:
                    if isinstance(lang_key, bytes):
                        language = lang_key.decode().split(":")[-1]
                    else:
                        language = lang_key.split(":")[-1]
                    count = self.redis_client.scard(lang_key)
                    language_stats[language] = count

                cache_keys = self.redis_client.keys(f"{self.search_cache_prefix}*")
                return len(file_keys), language_stats, len(cache_keys)

            file_count, language_stats, cache_count = await asyncio.to_thread(
                _fetch_index_status
            )

            return {
                "total_files_indexed": file_count,
                "languages": language_stats,
                "npu_available": self.npu_available,
                "cache_keys": cache_count,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}


# Singleton instance (thread-safe)
import threading

_npu_code_search = None
_npu_code_search_lock = threading.Lock()


def get_npu_code_search():
    """Get or create the NPU code search agent instance (thread-safe)"""
    global _npu_code_search
    if _npu_code_search is None:
        with _npu_code_search_lock:
            # Double-check after acquiring lock
            if _npu_code_search is None:
                _npu_code_search = NPUCodeSearchAgent()
    return _npu_code_search


async def search_codebase(
    query: str,
    search_type: str = "semantic",
    language: Optional[str] = None,
    max_results: int = 20,
) -> List[CodeSearchResult]:
    """
    Convenience function for code searching.

    Args:
        query: Search query
        search_type: Type of search ("semantic", "exact", "regex", "element")
        language: Filter by programming language
        max_results: Maximum number of results

    Returns:
        List of search results
    """
    return await get_npu_code_search().search_code(
        query, search_type, language, max_results
    )


async def index_project(root_path: str, force_reindex: bool = False) -> Dict[str, Any]:
    """
    Convenience function for indexing a project.

    Args:
        root_path: Root directory to index
        force_reindex: Force re-indexing even if already indexed

    Returns:
        Indexing results
    """
    return await get_npu_code_search().index_codebase(root_path, force_reindex)
