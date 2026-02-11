"""
Code Analysis System using Redis and NPU acceleration
Analyzes codebase for duplicate functions and refactoring opportunities
"""

import ast
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import config
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class CodeFunction:
    """Represents a function in the codebase"""

    file_path: str
    name: str
    start_line: int
    end_line: int
    source_code: str
    ast_hash: str
    signature: str
    docstring: Optional[str]
    imports: List[str]
    calls: List[str]
    complexity: int
    embedding: Optional[np.ndarray] = None


@dataclass
class DuplicateGroup:
    """Group of duplicate or similar functions"""

    functions: List[CodeFunction]
    similarity_score: float
    refactoring_suggestion: str
    estimated_lines_saved: int


class CodeAnalyzer:
    """Analyzes code for duplicates using Redis caching and NPU acceleration"""

    def __init__(self, redis_client=None, use_npu: bool = True):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.use_npu = use_npu
        self.config = config

        # Caching keys
        self.FUNCTION_KEY = "code_analysis:function:{}"
        self.EMBEDDING_KEY = "code_analysis:embedding:{}"
        self.DUPLICATE_KEY = "code_analysis:duplicates"
        self.INDEX_KEY = "code_analysis:index"

        # Analysis configuration
        self.similarity_threshold = 0.85
        self.vectorizer = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 3),
            stop_words=["self", "return", "if", "else", "try", "except"],
        )

        logger.info(f"Code Analyzer initialized (NPU: {self.use_npu})")

    async def analyze_codebase(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze entire codebase for duplicates and refactoring opportunities"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        # Step 1: Extract all functions
        logger.info(f"Extracting functions from {root_path}")
        functions = await self._extract_all_functions(root_path, patterns)
        logger.info(f"Found {len(functions)} functions")

        # Step 2: Generate embeddings (using NPU if available)
        logger.info("Generating function embeddings")
        await self._generate_embeddings(functions)

        # Step 3: Find duplicates using similarity search
        logger.info("Finding duplicate functions")
        duplicate_groups = await self._find_duplicates(functions)

        # Step 4: Analyze patterns and suggest refactoring
        logger.info("Analyzing patterns and generating suggestions")
        refactoring_suggestions = await self._generate_refactoring_suggestions(
            duplicate_groups
        )

        # Step 5: Calculate metrics
        metrics = self._calculate_metrics(functions, duplicate_groups)

        analysis_time = time.time() - start_time

        results = {
            "total_functions": len(functions),
            "duplicate_groups": len(duplicate_groups),
            "total_duplicates": sum(len(g.functions) for g in duplicate_groups),
            "lines_that_could_be_saved": sum(
                g.estimated_lines_saved for g in duplicate_groups
            ),
            "analysis_time_seconds": analysis_time,
            "used_npu": self.use_npu,
            "duplicate_details": [
                self._serialize_duplicate_group(g) for g in duplicate_groups
            ],
            "refactoring_suggestions": refactoring_suggestions,
            "metrics": metrics,
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Analysis complete in {analysis_time:.2f}s")
        return results

    async def _extract_all_functions(
        self, root_path: str, patterns: List[str]
    ) -> List[CodeFunction]:
        """Extract all functions from Python files"""

        functions = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file():
                    try:
                        functions.extend(
                            await self._extract_functions_from_file(str(file_path))
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse {file_path}: {e}")

        return functions

    async def _extract_functions_from_file(self, file_path: str) -> List[CodeFunction]:
        """Extract functions from a single Python file"""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=file_path)
            functions = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func = self._extract_function_info(node, source, file_path)
                    if func:
                        functions.append(func)
                        # Cache function info
                        await self._cache_function(func)

            return functions

        except Exception as e:
            logger.error(f"Error extracting functions from {file_path}: {e}")
            return []

    def _extract_function_info(
        self, node: ast.AST, source: str, file_path: str
    ) -> Optional[CodeFunction]:
        """Extract detailed information about a function"""

        try:
            # Get function source code
            lines = source.splitlines()
            start_line = node.lineno - 1
            end_line = node.end_lineno or len(lines)
            func_source = "\n".join(lines[start_line:end_line])

            # Generate AST hash for exact duplicate detection
            ast_dump = ast.dump(node, annotate_fields=False)
            ast_hash = hashlib.md5(ast_dump.encode()).hexdigest()

            # Extract signature
            args = []
            if hasattr(node, "args"):
                for arg in node.args.args:
                    args.append(arg.arg)
            signature = f"{node.name}({', '.join(args)})"

            # Extract docstring
            docstring = ast.get_docstring(node)

            # Extract imports used in function
            imports = self._extract_imports(node)

            # Extract function calls
            calls = self._extract_calls(node)

            # Calculate cyclomatic complexity
            complexity = self._calculate_complexity(node)

            return CodeFunction(
                file_path=file_path,
                name=node.name,
                start_line=node.lineno,
                end_line=node.end_lineno or len(lines),
                source_code=func_source,
                ast_hash=ast_hash,
                signature=signature,
                docstring=docstring,
                imports=imports,
                calls=calls,
                complexity=complexity,
            )

        except Exception as e:
            logger.error(f"Error extracting function info: {e}")
            return None

    def _extract_imports(self, node: ast.AST) -> List[str]:
        """Extract imports used within a function"""
        imports = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                imports.append(child.id)
        return list(set(imports))

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """Extract function calls within a function"""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return calls

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity of a function"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1

        return complexity

    async def _generate_embeddings(self, functions: List[CodeFunction]):
        """Generate embeddings for functions using TF-IDF or NPU"""

        if not functions:
            return

        # Prepare text for embedding
        func_texts = []
        for func in functions:
            # Combine various aspects of the function for embedding
            text = f"{func.name} {func.signature} {func.docstring or ''} {' '.join(func.calls)}"
            func_texts.append(text)

        if self.use_npu and await self._check_npu_available():
            # Use NPU for embedding generation (would require NPU-optimized model)
            embeddings = await self._generate_npu_embeddings(func_texts)
        else:
            # Use CPU-based TF-IDF
            embeddings = self.vectorizer.fit_transform(func_texts).toarray()

        # Assign embeddings to functions
        for i, func in enumerate(functions):
            func.embedding = embeddings[i]
            # Cache embedding
            await self._cache_embedding(func.ast_hash, embeddings[i])

    async def _check_npu_available(self) -> bool:
        """Check if NPU worker is available"""
        try:
            # Would check NPU worker status via API
            # For now, return False as NPU embedding model not implemented
            return False
        except Exception:
            return False

    async def _generate_npu_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using NPU acceleration"""
        # This would call the NPU worker API for batch embedding generation
        # For now, fallback to regular embeddings
        return self.vectorizer.fit_transform(texts).toarray()

    async def _find_duplicates(
        self, functions: List[CodeFunction]
    ) -> List[DuplicateGroup]:
        """Find duplicate and similar functions using embeddings"""

        duplicate_groups = []
        processed = set()

        # First pass: Find exact duplicates by AST hash
        hash_groups = {}
        for func in functions:
            if func.ast_hash not in hash_groups:
                hash_groups[func.ast_hash] = []
            hash_groups[func.ast_hash].append(func)

        for ast_hash, group in hash_groups.items():
            if len(group) > 1:
                duplicate_groups.append(
                    DuplicateGroup(
                        functions=group,
                        similarity_score=1.0,
                        refactoring_suggestion="Extract to shared utility function",
                        estimated_lines_saved=sum(
                            f.end_line - f.start_line for f in group[1:]
                        ),
                    )
                )
                processed.update(f"{f.file_path}:{f.name}" for f in group)

        # Second pass: Find similar functions by embedding similarity
        if any(f.embedding is not None for f in functions):
            embeddings = np.array(
                [f.embedding for f in functions if f.embedding is not None]
            )
            similarities = cosine_similarity(embeddings)

            for i in range(len(functions)):
                if f"{functions[i].file_path}:{functions[i].name}" in processed:
                    continue

                similar_indices = np.where(similarities[i] > self.similarity_threshold)[
                    0
                ]
                if len(similar_indices) > 1:
                    similar_funcs = [functions[j] for j in similar_indices]

                    # Skip if already processed
                    if any(
                        f"{f.file_path}:{f.name}" in processed for f in similar_funcs
                    ):
                        continue

                    duplicate_groups.append(
                        DuplicateGroup(
                            functions=similar_funcs,
                            similarity_score=float(
                                np.mean(similarities[i][similar_indices])
                            ),
                            refactoring_suggestion="Consider extracting common logic",
                            estimated_lines_saved=self._estimate_lines_saved(
                                similar_funcs
                            ),
                        )
                    )
                    processed.update(f"{f.file_path}:{f.name}" for f in similar_funcs)

        return duplicate_groups

    def _estimate_lines_saved(self, functions: List[CodeFunction]) -> int:
        """Estimate lines that could be saved by refactoring"""
        if not functions:
            return 0

        # Assume we keep the longest function and replace others with calls
        max_lines = max(f.end_line - f.start_line for f in functions)
        total_lines = sum(f.end_line - f.start_line for f in functions)

        # Each replaced function would be ~3 lines (import + call + newline)
        replacement_lines = (len(functions) - 1) * 3

        return max(0, total_lines - max_lines - replacement_lines)

    async def _generate_refactoring_suggestions(
        self, duplicate_groups: List[DuplicateGroup]
    ) -> List[Dict[str, Any]]:
        """Generate specific refactoring suggestions"""

        suggestions = []

        for group in duplicate_groups:
            if group.similarity_score == 1.0:
                # Exact duplicates
                suggestion = {
                    "type": "exact_duplicate",
                    "priority": "high",
                    "description": f"Functions {', '.join(f.name for f in group.functions)} are exact duplicates",
                    "action": "Create a shared utility function in src/utils/",
                    "affected_files": list(set(f.file_path for f in group.functions)),
                    "example_refactoring": self._generate_refactoring_example(group),
                }
            else:
                # Similar functions
                suggestion = {
                    "type": "similar_functions",
                    "priority": "medium",
                    "description": (
                        f"Functions {', '.join(f.name for f in group.functions)} "
                        f"are {group.similarity_score:.0%} similar"
                    ),
                    "action": "Extract common logic to base function with parameters",
                    "affected_files": list(set(f.file_path for f in group.functions)),
                    "differences": self._analyze_differences(group.functions),
                }

            suggestions.append(suggestion)

        return suggestions

    def _generate_refactoring_example(self, group: DuplicateGroup) -> str:
        """Generate example refactored code"""

        func = group.functions[0]
        module_name = Path(func.file_path).stem

        example = f"""
# In src/utils/{module_name}_utils.py:
{func.source_code}

# In original files, replace with:
from utils.{module_name}_utils import {func.name}
"""

        return example.strip()

    def _analyze_differences(self, functions: List[CodeFunction]) -> List[str]:
        """Analyze differences between similar functions"""

        differences = []

        # Compare signatures
        signatures = set(f.signature for f in functions)
        if len(signatures) > 1:
            differences.append(f"Different signatures: {', '.join(signatures)}")

        # Compare complexity
        complexities = [f.complexity for f in functions]
        if max(complexities) - min(complexities) > 2:
            differences.append(
                f"Varying complexity: {min(complexities)}-{max(complexities)}"
            )

        # Compare called functions
        all_calls = set()
        for f in functions:
            all_calls.update(f.calls)

        common_calls = set(functions[0].calls)
        for f in functions[1:]:
            common_calls &= set(f.calls)

        unique_calls = all_calls - common_calls
        if unique_calls:
            differences.append(f"Different function calls: {', '.join(unique_calls)}")

        return differences

    def _calculate_metrics(
        self, functions: List[CodeFunction], duplicate_groups: List[DuplicateGroup]
    ) -> Dict[str, Any]:
        """Calculate code quality metrics"""

        total_lines = sum(f.end_line - f.start_line for f in functions)
        duplicate_lines = sum(
            sum(f.end_line - f.start_line for f in g.functions[1:])
            for g in duplicate_groups
        )

        metrics = {
            "total_lines_of_code": total_lines,
            "duplicate_lines": duplicate_lines,
            "duplication_percentage": (duplicate_lines / total_lines * 100)
            if total_lines > 0
            else 0,
            "average_function_length": total_lines / len(functions) if functions else 0,
            "average_complexity": sum(f.complexity for f in functions) / len(functions)
            if functions
            else 0,
            "functions_by_complexity": {
                "low": len([f for f in functions if f.complexity <= 5]),
                "medium": len([f for f in functions if 5 < f.complexity <= 10]),
                "high": len([f for f in functions if f.complexity > 10]),
            },
        }

        return metrics

    def _serialize_duplicate_group(self, group: DuplicateGroup) -> Dict[str, Any]:
        """Serialize duplicate group for output"""

        return {
            "similarity_score": group.similarity_score,
            "refactoring_suggestion": group.refactoring_suggestion,
            "estimated_lines_saved": group.estimated_lines_saved,
            "functions": [
                {
                    "file": f.file_path,
                    "name": f.name,
                    "line_range": f"{f.start_line}-{f.end_line}",
                    "signature": f.signature,
                    "complexity": f.complexity,
                }
                for f in group.functions
            ],
        }

    async def _cache_function(self, func: CodeFunction):
        """Cache function information in Redis"""
        if self.redis_client:
            try:
                key = self.FUNCTION_KEY.format(func.ast_hash)
                value = json.dumps(
                    {
                        "file_path": func.file_path,
                        "name": func.name,
                        "start_line": func.start_line,
                        "end_line": func.end_line,
                        "signature": func.signature,
                        "complexity": func.complexity,
                    }
                )
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
            except Exception as e:
                logger.warning(f"Failed to cache function: {e}")

    async def _cache_embedding(self, ast_hash: str, embedding: np.ndarray):
        """Cache function embedding in Redis"""
        if self.redis_client:
            try:
                key = self.EMBEDDING_KEY.format(ast_hash)
                # Convert numpy array to bytes for Redis storage
                value = embedding.tobytes()
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
            except Exception as e:
                logger.warning(f"Failed to cache embedding: {e}")

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.DUPLICATE_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                # Clear all analysis keys
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="code_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")

    async def get_cached_results(self) -> Optional[Dict[str, Any]]:
        """Get cached analysis results"""
        if self.redis_client:
            try:
                value = await self.redis_client.get(self.DUPLICATE_KEY)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Failed to get cached results: {e}")
        return None


async def main():
    """Example usage of code analyzer"""

    analyzer = CodeAnalyzer(use_npu=True)

    # Analyze the codebase
    results = await analyzer.analyze_codebase(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    logger.info(f"\n=== Code Analysis Results ===")
    logger.info(f"Total functions analyzed: {results['total_functions']}")
    logger.info(f"Duplicate groups found: {results['duplicate_groups']}")
    logger.info(f"Total duplicate functions: {results['total_duplicates']}")
    logger.info(f"Lines that could be saved: {results['lines_that_could_be_saved']}")
    logger.info(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print top duplicates
    logger.info(f"\n=== Top Duplicate Groups ===")
    for i, group in enumerate(results["duplicate_details"][:5], 1):
        logger.info(f"\n{i}. Similarity: {group['similarity_score']:.0%}")
        logger.info(f"   Suggestion: {group['refactoring_suggestion']}")
        logger.info(f"   Lines saved: {group['estimated_lines_saved']}")
        logger.info("   Functions:")
        for func in group["functions"]:
            logger.info(f"   - {func['file']}:{func['line_range']} - {func['name']}")

    # Print refactoring suggestions
    logger.info(f"\n=== Refactoring Suggestions ===")
    for i, suggestion in enumerate(results["refactoring_suggestions"][:5], 1):
        logger.info(f"\n{i}. {suggestion['type']} ({suggestion['priority']} priority)")
        logger.info(f"   {suggestion['description']}")
        logger.info(f"   Action: {suggestion['action']}")
        logger.info(f"   Files: {', '.join(suggestion['affected_files'])}")


if __name__ == "__main__":
    asyncio.run(main())
