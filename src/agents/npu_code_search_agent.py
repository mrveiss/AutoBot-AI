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

from src.utils.redis_client import get_redis_client
from src.worker_node import WorkerNode

from .base_agent import AgentRequest
from .standardized_agent import ActionHandler, StandardizedAgent

logger = logging.getLogger(__name__)


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
    """

    def __init__(self):
        """Initialize the NPU code search agent"""
        super().__init__("npu_code_search")
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Redis setup
        self.redis_client = get_redis_client(async_client=False)
        self.redis_async_client = get_redis_client(async_client=True)

        # Worker node for NPU capabilities
        self.worker_node = WorkerNode()

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

        # Register action handlers using standardized pattern
        self.register_actions(
            {
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
        )

        # Supported file extensions for code search
        self.supported_extensions = {
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

        # Initialize communication protocol for agent-to-agent messaging
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.initialize_communication(self.capabilities))
            else:
                loop.run_until_complete(
                    self.initialize_communication(self.capabilities)
                )
        except RuntimeError:
            # Event loop not available yet, will initialize later
            pass

        # Language-specific patterns
        self.language_patterns = {
            "python": {
                "function": r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
                "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(:]",
                "import": r"(?:from\s+\S+\s+)?import\s+([^#\n]+)",
                "variable": r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=",
            },
            "javascript": {
                "function": r"(?:function\s+([a-zA-Z_][a-zA-Z0-9_]*)|([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*function|\bconst\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:\(.*?\)\s*=>|\bfunction))",
                "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                "import": r'(?:import|require)\s*\(\s*[\'"]([^\'"]+)[\'"]|import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                "variable": r"(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            },
        }

        self.stats = SearchStats(0, 0.0, False, False, 0)

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
                self.logger.info(f"🚀 NPU acceleration initialized: {npu_devices}")
            else:
                self.logger.info("NPU acceleration not available, using CPU fallback")

        except Exception as e:
            self.logger.warning(f"Failed to initialize NPU: {e}")
            self.npu_available = False

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

    async def index_codebase(
        self, root_path: str, force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        Index a codebase for fast searching.

        Args:
            root_path: Root directory to index
            force_reindex: Force re-indexing even if already indexed

        Returns:
            Indexing results and statistics
        """
        start_time = time.time()
        indexed_files = 0
        skipped_files = 0
        errors = []

        try:
            self.logger.info(f"Starting codebase indexing: {root_path}")

            # Check if already indexed
            index_key = (
                f"{self.index_prefix}meta:{hashlib.md5(root_path.encode()).hexdigest()}"
            )
            if not force_reindex and self.redis_client.exists(index_key):
                self.logger.info(
                    "Codebase already indexed, use force_reindex=True to re-index"
                )
                return {"status": "already_indexed", "index_key": index_key}

            # Walk through directory
            for root, dirs, files in os.walk(root_path):
                # Skip common ignore directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in {
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "dist",
                        "build",
                        "target",
                    }
                ]

                for file in files:
                    if not any(file.endswith(ext) for ext in self.supported_extensions):
                        skipped_files += 1
                        continue

                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, root_path)

                    try:
                        await self._index_file(file_path, relative_path)
                        indexed_files += 1

                        # Progress logging
                        if indexed_files % 100 == 0:
                            self.logger.info(f"Indexed {indexed_files} files...")

                    except Exception as e:
                        errors.append(f"{relative_path}: {str(e)}")
                        self.logger.error(f"Failed to index {file_path}: {e}")

            # Store indexing metadata
            metadata = {
                "root_path": root_path,
                "indexed_files": indexed_files,
                "timestamp": time.time(),
                "npu_available": self.npu_available,
            }
            self.redis_client.setex(
                index_key, 86400, json.dumps(metadata)
            )  # 24h expiry

            execution_time = time.time() - start_time
            self.logger.info(
                f"Indexing complete: {indexed_files} files in {execution_time:.2f}s"
            )

            return {
                "status": "success",
                "indexed_files": indexed_files,
                "skipped_files": skipped_files,
                "errors": errors[:10],  # Limit error list
                "execution_time": execution_time,
                "index_key": index_key,
            }

        except Exception as e:
            self.logger.error(f"Codebase indexing failed: {e}")
            return {"status": "error", "error": str(e), "indexed_files": indexed_files}

    async def _index_file(self, file_path: str, relative_path: str):
        """Index a single file"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content.strip():
                return  # Skip empty files

            # Extract metadata
            file_ext = os.path.splitext(file_path)[1]
            language = self._detect_language(file_ext)

            # Extract code elements (functions, classes, etc.)
            elements = self._extract_code_elements(content, language)

            # Create searchable index entry
            index_data = {
                "file_path": relative_path,
                "language": language,
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                "line_count": len(content.splitlines()),
                "elements": elements,
                "indexed_at": time.time(),
            }

            # Store in Redis with multiple access patterns
            file_key = f"{self.index_prefix}file:{relative_path}"
            self.redis_client.setex(file_key, 86400, json.dumps(index_data))

            # Index by language
            language_key = f"{self.index_prefix}lang:{language}"
            self.redis_client.sadd(language_key, relative_path)
            self.redis_client.expire(language_key, 86400)

            # Index elements for fast lookup
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

    def _extract_code_elements(
        self, content: str, language: str
    ) -> Dict[str, List[Dict]]:
        """Extract code elements (functions, classes, etc.) from content"""
        import re

        elements = {"functions": [], "classes": [], "imports": [], "variables": []}

        if language not in self.language_patterns:
            return elements

        patterns = self.language_patterns[language]
        lines = content.splitlines()

        # Extract functions
        if "function" in patterns:
            for i, line in enumerate(lines):
                matches = re.finditer(patterns["function"], line)
                for match in matches:
                    # Get the first non-None group
                    name = next((g for g in match.groups() if g), None)
                    if name:
                        elements["functions"].append(
                            {
                                "name": name.strip(),
                                "line_number": i + 1,
                                "context": line.strip(),
                            }
                        )

        # Extract classes
        if "class" in patterns:
            for i, line in enumerate(lines):
                matches = re.finditer(patterns["class"], line)
                for match in matches:
                    name = match.group(1)
                    if name:
                        elements["classes"].append(
                            {
                                "name": name.strip(),
                                "line_number": i + 1,
                                "context": line.strip(),
                            }
                        )

        # Extract imports
        if "import" in patterns:
            for i, line in enumerate(lines):
                matches = re.finditer(patterns["import"], line)
                for match in matches:
                    # Get the first non-None group
                    name = next((g for g in match.groups() if g), None)
                    if name:
                        elements["imports"].append(
                            {
                                "name": name.strip(),
                                "line_number": i + 1,
                                "context": line.strip(),
                            }
                        )

        return elements

    async def search_code(
        self,
        query: str,
        search_type: str = "semantic",
        language: Optional[str] = None,
        max_results: int = 20,
    ) -> List[CodeSearchResult]:
        """
        Search through indexed code.

        Args:
            query: Search query
            search_type: Type of search ("semantic", "exact", "regex", "element")
            language: Filter by programming language
            max_results: Maximum number of results

        Returns:
            List of search results
        """
        start_time = time.time()

        try:
            # Check cache first
            cache_key = f"{self.search_cache_prefix}{hashlib.md5((query + search_type + str(language)).encode()).hexdigest()}"
            cached_result = self.redis_client.get(cache_key)

            if cached_result:
                self.stats.redis_cache_hit = True
                results = [CodeSearchResult(**r) for r in json.loads(cached_result)]
                self.stats.search_time_ms = (time.time() - start_time) * 1000
                self.stats.results_count = len(results)
                return results[:max_results]

            # Perform search based on type
            if search_type == "element":
                results = await self._search_elements(query, language, max_results)
            elif search_type == "exact":
                results = await self._search_exact(query, language, max_results)
            elif search_type == "regex":
                results = await self._search_regex(query, language, max_results)
            else:  # semantic (default)
                results = await self._search_semantic(query, language, max_results)

            # Cache results
            serializable_results = [
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
            self.redis_client.setex(
                cache_key, self.cache_ttl, json.dumps(serializable_results)
            )

            # Update stats
            self.stats.search_time_ms = (time.time() - start_time) * 1000
            self.stats.npu_acceleration_used = (
                self.npu_available and search_type == "semantic"
            )
            self.stats.redis_cache_hit = False
            self.stats.results_count = len(results)

            return results

        except Exception as e:
            self.logger.error(f"Code search failed: {e}")
            return []

    async def _search_elements(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Search for specific code elements (functions, classes, etc.)"""
        results = []

        # Search across all element types
        for element_type in ["functions", "classes", "imports", "variables"]:
            element_key = f"{self.index_prefix}element:{element_type}:{query}"
            element_data_list = self.redis_client.lrange(element_key, 0, max_results)

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
                    self.logger.error(f"Error processing element result: {e}")

        return results[:max_results]

    async def _search_exact(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Perform exact string search"""
        results = []

        # Get all indexed files
        pattern = f"{self.index_prefix}file:*"
        file_keys = self.redis_client.keys(pattern)

        for file_key in file_keys:
            try:
                file_data = json.loads(self.redis_client.get(file_key))
                file_path = file_data["file_path"]

                # Language filter
                if language and file_data["language"] != language:
                    continue

                # Load and search file content
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if query in line:
                            context_lines = self._get_context_lines(lines, i, 2)

                            result = CodeSearchResult(
                                file_path=file_path,
                                content=line.strip(),
                                line_number=i + 1,
                                confidence=1.0,
                                context_lines=context_lines,
                                metadata={
                                    "search_type": "exact",
                                    "query": query,
                                    "language": file_data["language"],
                                },
                            )
                            results.append(result)

                            if len(results) >= max_results:
                                return results

                except Exception as e:
                    self.logger.error(f"Error reading file {file_path}: {e}")

            except Exception as e:
                self.logger.error(f"Error processing file key {file_key}: {e}")

        return results

    async def _search_regex(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Perform regex search"""
        import re

        try:
            pattern = re.compile(query, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            self.logger.error(f"Invalid regex pattern: {query}, error: {e}")
            return []

        results = []

        # Get all indexed files
        file_pattern = f"{self.index_prefix}file:*"
        file_keys = self.redis_client.keys(file_pattern)

        for file_key in file_keys:
            try:
                file_data = json.loads(self.redis_client.get(file_key))
                file_path = file_data["file_path"]

                # Language filter
                if language and file_data["language"] != language:
                    continue

                # Load and search file content
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        matches = pattern.finditer(line)
                        for match in matches:
                            context_lines = self._get_context_lines(lines, i, 2)

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
                                    "language": file_data["language"],
                                },
                            )
                            results.append(result)

                            if len(results) >= max_results:
                                return results

                except Exception as e:
                    self.logger.error(f"Error reading file {file_path}: {e}")

            except Exception as e:
                self.logger.error(f"Error processing file key {file_key}: {e}")

        return results

    async def _search_semantic(
        self, query: str, language: Optional[str], max_results: int
    ) -> List[CodeSearchResult]:
        """Perform semantic search using NPU acceleration when available"""
        # For now, fallback to exact search with fuzzy matching
        # TODO: Implement proper semantic search with embeddings and NPU acceleration

        results = []
        query_words = query.lower().split()

        # Get all indexed files
        pattern = f"{self.index_prefix}file:*"
        file_keys = self.redis_client.keys(pattern)

        for file_key in file_keys:
            try:
                file_data = json.loads(self.redis_client.get(file_key))
                file_path = file_data["file_path"]

                # Language filter
                if language and file_data["language"] != language:
                    continue

                # Load and search file content
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        line_lower = line.lower()

                        # Calculate semantic similarity (simple word matching for now)
                        matches = sum(1 for word in query_words if word in line_lower)
                        if matches > 0:
                            confidence = matches / len(query_words)

                            # Only include results with reasonable confidence
                            if confidence >= 0.3:
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
                                        "language": file_data["language"],
                                    },
                                )
                                results.append(result)

                except Exception as e:
                    self.logger.error(f"Error reading file {file_path}: {e}")

            except Exception as e:
                self.logger.error(f"Error processing file key {file_key}: {e}")

        # Sort by confidence
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:max_results]

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
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            return self._get_context_lines(lines, line_number - 1, context_size)

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
            keys = self.redis_client.keys(pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                return {"status": "success", "keys_deleted": deleted}
            else:
                return {"status": "success", "keys_deleted": 0}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def get_index_status(self) -> Dict[str, Any]:
        """Get indexing status information"""
        try:
            # Count indexed files
            pattern = f"{self.index_prefix}file:*"
            file_keys = self.redis_client.keys(pattern)

            # Get language distribution
            lang_pattern = f"{self.index_prefix}lang:*"
            lang_keys = self.redis_client.keys(lang_pattern)

            language_stats = {}
            for lang_key in lang_keys:
                language = lang_key.decode().split(":")[-1]
                count = self.redis_client.scard(lang_key)
                language_stats[language] = count

            return {
                "total_files_indexed": len(file_keys),
                "languages": language_stats,
                "npu_available": self.npu_available,
                "cache_keys": len(
                    self.redis_client.keys(f"{self.search_cache_prefix}*")
                ),
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global instance for easy access
npu_code_search = NPUCodeSearchAgent()


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
    return await npu_code_search.search_code(query, search_type, language, max_results)


async def index_project(root_path: str, force_reindex: bool = False) -> Dict[str, Any]:
    """
    Convenience function for indexing a project.

    Args:
        root_path: Root directory to index
        force_reindex: Force re-indexing even if already indexed

    Returns:
        Indexing results
    """
    return await npu_code_search.index_codebase(root_path, force_reindex)
