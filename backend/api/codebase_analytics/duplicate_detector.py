# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Duplicate Code Detector for Codebase Analytics (Issue #528)

Detects duplicate code blocks across the codebase using:
1. Hash-based detection for exact/near-exact duplicates
2. Structural similarity for code blocks
3. Integration with ChromaDB for semantic similarity (Issue #554)

Part of EPIC #217 - Advanced Code Intelligence Methods

Issue #554: Enhanced with Vector/Redis/LLM infrastructure:
- ChromaDB for semantic code similarity via embeddings
- Redis for caching analysis results
- LLM embeddings for detecting semantically similar code patterns
"""

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Issue #659: MinHash LSH for O(n) expected duplicate detection
# Issue #665: Provide type stubs when datasketch not installed for helper signatures
try:
    from datasketch import MinHash, MinHashLSH

    LSH_AVAILABLE = True
except ImportError:
    LSH_AVAILABLE = False
    # Provide placeholder types for function signatures when datasketch not installed
    MinHash = Any  # type: ignore[misc, assignment]
    MinHashLSH = Any  # type: ignore[misc, assignment]

from src.utils.file_categorization import (
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# Issue #554: Flag to enable semantic analysis infrastructure
SEMANTIC_ANALYSIS_AVAILABLE = False
SemanticAnalysisMixin = None

try:
    from src.code_intelligence.analytics_infrastructure import (
        SemanticAnalysisMixin as _SemanticAnalysisMixin,
    )

    SemanticAnalysisMixin = _SemanticAnalysisMixin
    SEMANTIC_ANALYSIS_AVAILABLE = True
except ImportError:
    logger.debug("SemanticAnalysisMixin not available - semantic features disabled")


# =============================================================================
# Configuration Constants
# =============================================================================

# Minimum lines for a code block to be considered for duplicate detection
# Issue #609: Reduced from 5 to 4 to catch more smaller duplicates
MIN_DUPLICATE_LINES = 4
# Minimum characters for a code block
MIN_DUPLICATE_CHARS = 80
# Similarity thresholds
HIGH_SIMILARITY_THRESHOLD = 0.90
MEDIUM_SIMILARITY_THRESHOLD = 0.70
LOW_SIMILARITY_THRESHOLD = 0.50
# Maximum files to scan (0 = no limit, scan all files)
# Issue #609: No limit on files - scan entire codebase
MAX_FILES_TO_SCAN = 0
# Maximum duplicates to return (0 = no limit)
# Issue #609: Return all duplicates found (no artificial limit)
MAX_DUPLICATES_RETURNED = 0
# Maximum blocks for O(n^2) similarity comparison
# Issue #609: Exact hash matches have no limit (O(n) via hash grouping)
# Similarity comparison is O(n^2), so we sample larger blocks for performance
# 500 blocks = ~125K comparisons, targets <30s runtime for similarity phase
# (Previous 2000 blocks = 2M+ comparisons was causing 60s timeouts)
MAX_BLOCKS_FOR_SIMILARITY = 500

# Issue #659: LSH Configuration for approximate similarity search
# LSH provides O(n) expected complexity vs O(n^2) for pairwise comparison
# Precision/recall tradeoff controlled by num_perm and threshold
LSH_NUM_PERMUTATIONS = 128  # Higher = more precision, slower. 128=~95% recall, 256=~98%
LSH_SIMILARITY_THRESHOLD = 0.5  # Minimum similarity for LSH candidate pairs
LSH_ENABLED = True  # Set False to disable LSH and use O(n^2) fallback


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class CodeBlock:
    """Represents a block of code for duplicate detection."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    normalized_content: str
    content_hash: str
    line_count: int
    # Issue #659: Pre-computed token set for 30-40% faster similarity computation
    # Avoids recomputing tokens on every comparison
    token_set: Set[str] = field(default_factory=set)


@dataclass
class DuplicatePair:
    """Represents a pair of duplicate code blocks."""

    file1: str
    file2: str
    start_line1: int
    end_line1: int
    start_line2: int
    end_line2: int
    similarity: float
    line_count: int
    code_snippet: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "file1": self.file1,
            "file2": self.file2,
            "start_line1": self.start_line1,
            "end_line1": self.end_line1,
            "start_line2": self.start_line2,
            "end_line2": self.end_line2,
            "similarity": round(self.similarity * 100, 1),
            "lines": self.line_count,
            "code_snippet": self.code_snippet[:200] if self.code_snippet else "",
        }


@dataclass
class DuplicateAnalysis:
    """Complete duplicate code analysis result."""

    total_duplicates: int
    high_similarity_count: int
    medium_similarity_count: int
    low_similarity_count: int
    total_duplicate_lines: int
    duplicates: List[DuplicatePair] = field(default_factory=list)
    files_analyzed: int = 0
    scan_timestamp: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_duplicates": self.total_duplicates,
            "high_similarity_count": self.high_similarity_count,
            "medium_similarity_count": self.medium_similarity_count,
            "low_similarity_count": self.low_similarity_count,
            "total_duplicate_lines": self.total_duplicate_lines,
            "files_analyzed": self.files_analyzed,
            "scan_timestamp": self.scan_timestamp,
            "duplicates": [d.to_dict() for d in self.duplicates],
        }


# =============================================================================
# Helper Functions
# =============================================================================


def _normalize_code(content: str) -> str:
    """
    Normalize code for comparison by removing:
    - Comments
    - Whitespace variations
    - String literals (replace with placeholder)
    """
    # Remove single-line comments
    content = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)

    # Remove multi-line comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r'""".*?"""', '""', content, flags=re.DOTALL)
    content = re.sub(r"'''.*?'''", "''", content, flags=re.DOTALL)

    # Normalize string literals
    content = re.sub(r'"[^"]*"', '"STR"', content)
    content = re.sub(r"'[^']*'", "'STR'", content)

    # Normalize whitespace
    content = re.sub(r"\s+", " ", content)

    return content.strip().lower()


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_code_blocks(file_path: str, content: str) -> List[CodeBlock]:
    """
    Extract meaningful code blocks from file content.

    Uses a sliding window approach to find contiguous code blocks.
    """
    lines = content.split("\n")
    blocks = []

    # Skip files that are too short
    if len(lines) < MIN_DUPLICATE_LINES:
        return blocks

    # Extract function/class blocks for Python
    if file_path.endswith(".py"):
        blocks.extend(_extract_python_blocks(file_path, lines))

    # Extract function blocks for JS/TS/Vue
    elif any(file_path.endswith(ext) for ext in [".js", ".ts", ".vue", ".jsx", ".tsx"]):
        blocks.extend(_extract_js_blocks(file_path, lines))

    # Fallback: sliding window for generic blocks
    if not blocks:
        blocks.extend(_extract_sliding_window_blocks(file_path, lines))

    return blocks


def _extract_python_blocks(file_path: str, lines: List[str]) -> List[CodeBlock]:
    """Extract Python function and class blocks."""
    blocks = []
    current_block_start = None

    for i, line in enumerate(lines):
        stripped = line.lstrip()

        # Detect function or class definition
        if stripped.startswith(("def ", "async def ", "class ")):
            # Save previous block if exists
            if current_block_start is not None:
                block_content = "\n".join(lines[current_block_start:i])
                if len(block_content) >= MIN_DUPLICATE_CHARS:
                    normalized = _normalize_code(block_content)
                    # Issue #659: Pre-compute token set for faster similarity
                    token_set = set(normalized.split())
                    blocks.append(
                        CodeBlock(
                            file_path=file_path,
                            start_line=current_block_start + 1,
                            end_line=i,
                            content=block_content,
                            normalized_content=normalized,
                            content_hash=_compute_hash(normalized),
                            line_count=i - current_block_start,
                            token_set=token_set,
                        )
                    )

            current_block_start = i
            # Track indentation for future use in duplicate grouping
            _ = len(line) - len(stripped)

    # Don't forget the last block
    if current_block_start is not None:
        block_content = "\n".join(lines[current_block_start:])
        if len(block_content) >= MIN_DUPLICATE_CHARS:
            normalized = _normalize_code(block_content)
            # Issue #659: Pre-compute token set for faster similarity
            token_set = set(normalized.split())
            blocks.append(
                CodeBlock(
                    file_path=file_path,
                    start_line=current_block_start + 1,
                    end_line=len(lines),
                    content=block_content,
                    normalized_content=normalized,
                    content_hash=_compute_hash(normalized),
                    line_count=len(lines) - current_block_start,
                    token_set=token_set,
                )
            )

    return blocks


def _extract_js_blocks(file_path: str, lines: List[str]) -> List[CodeBlock]:
    """Extract JavaScript/TypeScript function blocks."""
    blocks = []
    content = "\n".join(lines)

    # Pattern for functions
    func_pattern = re.compile(
        r"(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))"
        r"[^{]*\{",
        re.MULTILINE,
    )

    for match in func_pattern.finditer(content):
        start_pos = match.start()
        start_line = content[:start_pos].count("\n")

        # Find matching closing brace
        brace_count = 1
        pos = match.end()
        while pos < len(content) and brace_count > 0:
            if content[pos] == "{":
                brace_count += 1
            elif content[pos] == "}":
                brace_count -= 1
            pos += 1

        end_line = content[:pos].count("\n")
        block_content = content[start_pos:pos]

        if (
            len(block_content) >= MIN_DUPLICATE_CHARS
            and (end_line - start_line) >= MIN_DUPLICATE_LINES
        ):
            normalized = _normalize_code(block_content)
            # Issue #659: Pre-compute token set for faster similarity
            token_set = set(normalized.split())
            blocks.append(
                CodeBlock(
                    file_path=file_path,
                    start_line=start_line + 1,
                    end_line=end_line + 1,
                    content=block_content,
                    normalized_content=normalized,
                    content_hash=_compute_hash(normalized),
                    line_count=end_line - start_line + 1,
                    token_set=token_set,
                )
            )

    return blocks


def _extract_sliding_window_blocks(
    file_path: str, lines: List[str], window_size: int = 10
) -> List[CodeBlock]:
    """Extract blocks using sliding window for generic files."""
    blocks = []

    for i in range(0, len(lines) - window_size + 1, window_size // 2):
        block_lines = lines[i : i + window_size]
        block_content = "\n".join(block_lines)

        # Skip mostly empty blocks
        if len(block_content.strip()) < MIN_DUPLICATE_CHARS:
            continue

        normalized = _normalize_code(block_content)
        if len(normalized) < 50:  # Skip if normalized content is too short
            continue

        # Issue #659: Pre-compute token set for faster similarity
        token_set = set(normalized.split())
        blocks.append(
            CodeBlock(
                file_path=file_path,
                start_line=i + 1,
                end_line=i + window_size,
                content=block_content,
                normalized_content=normalized,
                content_hash=_compute_hash(normalized),
                line_count=window_size,
                token_set=token_set,
            )
        )

    return blocks


def _compute_similarity(block1: CodeBlock, block2: CodeBlock) -> float:
    """
    Compute similarity between two code blocks.

    Uses a combination of:
    1. Hash equality (exact match = 1.0)
    2. Jaccard similarity for near matches

    Issue #659: Uses pre-computed token_set for 30-40% faster computation.
    """
    # Exact hash match
    if block1.content_hash == block2.content_hash:
        return 1.0

    # Compute character-level similarity
    s1 = block1.normalized_content
    s2 = block2.normalized_content

    # Quick length check
    len_ratio = (
        min(len(s1), len(s2)) / max(len(s1), len(s2))
        if max(len(s1), len(s2)) > 0
        else 0
    )
    if len_ratio < 0.5:
        return 0.0

    # Issue #659: Use pre-computed token sets if available (30-40% faster)
    tokens1 = block1.token_set if block1.token_set else set(s1.split())
    tokens2 = block2.token_set if block2.token_set else set(s2.split())

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    return intersection / union if union > 0 else 0.0


def _build_minhash(
    token_set: Set[str], num_perm: int = LSH_NUM_PERMUTATIONS
) -> "MinHash":
    """
    Build MinHash signature for a token set.

    Issue #659: Core LSH building block for O(n) expected similarity search.

    Args:
        token_set: Set of tokens from normalized code
        num_perm: Number of permutations (higher = more precision)

    Returns:
        MinHash object for LSH indexing
    """
    m = MinHash(num_perm=num_perm)
    for token in token_set:
        m.update(token.encode("utf-8"))
    return m


def _build_minhash_signatures(
    blocks: List[CodeBlock],
    num_perm: int,
) -> Dict[int, MinHash]:
    """
    Build MinHash signatures for all code blocks.

    Issue #665: Extracted from _find_lsh_candidates to improve maintainability.

    Args:
        blocks: List of code blocks
        num_perm: Number of MinHash permutations

    Returns:
        Dictionary mapping block index to MinHash signature
    """
    minhashes: Dict[int, MinHash] = {}
    for idx, block in enumerate(blocks):
        token_set = (
            block.token_set
            if block.token_set
            else set(block.normalized_content.split())
        )
        if token_set:
            minhashes[idx] = _build_minhash(token_set, num_perm)
    return minhashes


def _build_lsh_index(
    minhashes: Dict[int, MinHash],
    threshold: float,
    num_perm: int,
) -> MinHashLSH:
    """
    Create LSH index and insert all MinHash signatures.

    Issue #665: Extracted from _find_lsh_candidates to improve maintainability.

    Args:
        minhashes: Dictionary of MinHash signatures
        threshold: Minimum Jaccard similarity threshold
        num_perm: Number of MinHash permutations

    Returns:
        Populated MinHashLSH index
    """
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    for idx, mh in minhashes.items():
        try:
            lsh.insert(str(idx), mh)
        except ValueError:
            # Duplicate key - skip (can happen if blocks are identical)
            pass
    return lsh


def _query_lsh_candidates(
    blocks: List[CodeBlock],
    minhashes: Dict[int, MinHash],
    lsh: MinHashLSH,
) -> List[Tuple[int, int, float]]:
    """
    Query LSH index for candidate duplicate pairs.

    Issue #665: Extracted from _find_lsh_candidates to improve maintainability.

    Args:
        blocks: List of code blocks
        minhashes: Dictionary of MinHash signatures
        lsh: Populated LSH index

    Returns:
        List of (idx1, idx2, exact_similarity) tuples
    """
    candidates: List[Tuple[int, int, float]] = []
    seen_pairs: Set[Tuple[int, int]] = set()

    for idx, mh in minhashes.items():
        result = lsh.query(mh)

        for candidate_key in result:
            candidate_idx = int(candidate_key)

            # Skip self-matches
            if candidate_idx == idx:
                continue

            # Create ordered pair key to avoid duplicates
            pair_key = (min(idx, candidate_idx), max(idx, candidate_idx))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Compute exact similarity for candidates (filter false positives)
            exact_sim = _compute_similarity(blocks[idx], blocks[candidate_idx])
            if exact_sim >= LOW_SIMILARITY_THRESHOLD:
                candidates.append((idx, candidate_idx, exact_sim))

    return candidates


def _find_lsh_candidates(
    blocks: List[CodeBlock],
    threshold: float = LSH_SIMILARITY_THRESHOLD,
    num_perm: int = LSH_NUM_PERMUTATIONS,
) -> List[Tuple[int, int, float]]:
    """
    Find candidate duplicate pairs using Locality-Sensitive Hashing.

    Issue #659: O(n) expected complexity vs O(n²) for brute force.
    Issue #665: Refactored to use extracted helpers for each phase.

    Algorithm:
    1. Build MinHash signatures for all blocks - O(n)
    2. Insert into LSH index - O(n)
    3. Query each block for candidates - O(n) expected
    4. Compute exact similarity only for candidates - O(candidates)

    Precision/recall tradeoffs:
    - threshold=0.5, num_perm=128: ~95% recall, ~90% precision
    - threshold=0.5, num_perm=256: ~98% recall, ~95% precision

    Args:
        blocks: List of code blocks to search
        threshold: Minimum Jaccard similarity for candidates
        num_perm: Number of MinHash permutations

    Returns:
        List of (idx1, idx2, exact_similarity) tuples for candidate pairs
    """
    if not LSH_AVAILABLE:
        logger.warning("datasketch not available, falling back to O(n²) comparison")
        return []

    if len(blocks) < 2:
        return []

    logger.info(
        "Building LSH index for %d blocks (num_perm=%d, threshold=%.2f)",
        len(blocks),
        num_perm,
        threshold,
    )

    # Phase 1: Build MinHash signatures - O(n) (Issue #665: uses helper)
    minhashes = _build_minhash_signatures(blocks, num_perm)

    # Phase 2: Create LSH index - O(n) (Issue #665: uses helper)
    lsh = _build_lsh_index(minhashes, threshold, num_perm)

    # Phase 3: Query for candidates - O(n) expected (Issue #665: uses helper)
    candidates = _query_lsh_candidates(blocks, minhashes, lsh)

    logger.info(
        "LSH found %d candidate pairs from %d blocks", len(candidates), len(blocks)
    )
    return candidates


# =============================================================================
# Main Detector Class
# =============================================================================


# Issue #554: Dynamic base class selection for semantic analysis support
_BaseClass = SemanticAnalysisMixin if SEMANTIC_ANALYSIS_AVAILABLE else object


class DuplicateCodeDetector(_BaseClass):
    """
    Detects duplicate code blocks across the codebase.

    Issue #554: Enhanced with optional Vector/Redis/LLM infrastructure:
    - use_semantic_analysis=True enables ChromaDB embeddings for semantic similarity
    - Semantic duplicates catch renamed/refactored code with same intent
    - Results cached in Redis for performance

    Usage:
        # Standard detection (hash + token similarity)
        detector = DuplicateCodeDetector()
        analysis = detector.run_analysis()

        # With semantic analysis (requires ChromaDB + Ollama)
        detector = DuplicateCodeDetector(use_semantic_analysis=True)
        analysis = await detector.run_analysis_async()
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        min_similarity: float = LOW_SIMILARITY_THRESHOLD,
        use_semantic_analysis: bool = False,
    ):
        """
        Initialize the duplicate detector.

        Args:
            project_root: Root directory to scan (defaults to AutoBot project)
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            use_semantic_analysis: Enable LLM-based semantic duplicate detection (Issue #554)
        """
        # Issue #554: Initialize semantic analysis infrastructure if enabled
        self.use_semantic_analysis = (
            use_semantic_analysis and SEMANTIC_ANALYSIS_AVAILABLE
        )

        if self.use_semantic_analysis:
            super().__init__()
            self._init_infrastructure(
                collection_name="duplicate_code_vectors",
                use_llm=True,
                use_cache=True,
                redis_database="analytics",
            )

        if project_root:
            self.project_root = Path(project_root)
        else:
            # Default to AutoBot project root
            self.project_root = Path(__file__).resolve().parents[3]

        self.min_similarity = min_similarity
        self.code_extensions = (
            PYTHON_EXTENSIONS | JS_EXTENSIONS | TS_EXTENSIONS | VUE_EXTENSIONS
        )

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped."""
        path_parts = set(path.parts)
        return bool(path_parts & SKIP_DIRS)

    def _get_files_to_scan(self) -> List[Path]:
        """Get list of files to scan for duplicates."""
        files = []

        for ext in self.code_extensions:
            pattern = f"**/*{ext}"
            for file_path in self.project_root.glob(pattern):
                if self._should_skip_path(file_path):
                    continue
                if file_path.is_file():
                    files.append(file_path)
                    # Issue #609: MAX_FILES_TO_SCAN=0 means no limit
                    if MAX_FILES_TO_SCAN > 0 and len(files) >= MAX_FILES_TO_SCAN:
                        logger.warning(
                            "Reached max files limit (%d), stopping scan",
                            MAX_FILES_TO_SCAN,
                        )
                        return files

        return files

    def _extract_all_blocks(self, files: List[Path]) -> List[CodeBlock]:
        """Extract code blocks from all files (Issue #560: extracted)."""
        all_blocks: List[CodeBlock] = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                blocks = _extract_code_blocks(str(file_path), content)
                all_blocks.extend(blocks)
            except Exception as e:
                logger.debug("Failed to process %s: %s", file_path, e)
        return all_blocks

    def _find_exact_duplicates(
        self,
        hash_groups: Dict[str, List[CodeBlock]],
        seen_pairs: Set[Tuple[str, str]],
    ) -> List[DuplicatePair]:
        """Find exact hash-based duplicates (Issue #560: extracted).

        Issue #616: O(n²) pairwise comparison is NECESSARY for duplicate detection.
        Already optimized with: (1) hash-based grouping, (2) early continue for
        same-file pairs, (3) seen_pairs set for O(1) deduplication.
        """
        duplicates: List[DuplicatePair] = []

        for blocks in hash_groups.values():
            if len(blocks) <= 1:
                continue

            for i, block1 in enumerate(blocks):
                for block2 in blocks[i + 1 :]:
                    if block1.file_path == block2.file_path:
                        continue

                    pair_key = tuple(
                        sorted(
                            [
                                f"{block1.file_path}:{block1.start_line}",
                                f"{block2.file_path}:{block2.start_line}",
                            ]
                        )
                    )
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    duplicates.append(
                        DuplicatePair(
                            file1=block1.file_path,
                            file2=block2.file_path,
                            start_line1=block1.start_line,
                            end_line1=block1.end_line,
                            start_line2=block2.start_line,
                            end_line2=block2.end_line,
                            similarity=1.0,
                            line_count=block1.line_count,
                            code_snippet=block1.content[:200],
                        )
                    )

        return duplicates

    def _process_lsh_candidates(
        self,
        all_blocks: List[CodeBlock],
        lsh_candidates: List[Tuple[int, int, float]],
        seen_pairs: Set[Tuple[str, str]],
    ) -> List[DuplicatePair]:
        """
        Process LSH candidate pairs into DuplicatePair results.

        Issue #665: Extracted from _find_similar_duplicates for single responsibility.
        Issue #659: Original LSH processing logic.
        """
        duplicates: List[DuplicatePair] = []

        for idx1, idx2, similarity in lsh_candidates:
            block1 = all_blocks[idx1]
            block2 = all_blocks[idx2]

            if block1.file_path == block2.file_path:
                continue

            if block1.content_hash == block2.content_hash:
                continue

            pair_key = tuple(
                sorted(
                    [
                        f"{block1.file_path}:{block1.start_line}",
                        f"{block2.file_path}:{block2.start_line}",
                    ]
                )
            )
            if pair_key in seen_pairs:
                continue

            if similarity >= self.min_similarity:
                seen_pairs.add(pair_key)
                duplicates.append(
                    DuplicatePair(
                        file1=block1.file_path,
                        file2=block2.file_path,
                        start_line1=block1.start_line,
                        end_line1=block1.end_line,
                        start_line2=block2.start_line,
                        end_line2=block2.end_line,
                        similarity=similarity,
                        line_count=(block1.line_count + block2.line_count) // 2,
                        code_snippet=block1.content[:200],
                    )
                )

        return duplicates

    def _pairwise_similarity_search(
        self,
        blocks_to_compare: List[CodeBlock],
        seen_pairs: Set[Tuple[str, str]],
    ) -> List[DuplicatePair]:
        """
        O(n²) pairwise similarity comparison fallback.

        Issue #665: Extracted from _find_similar_duplicates for single responsibility.
        Issue #609: Original pairwise comparison logic.
        """
        duplicates: List[DuplicatePair] = []

        for i, block1 in enumerate(blocks_to_compare):
            for block2 in blocks_to_compare[i + 1 :]:
                if block1.file_path == block2.file_path:
                    continue

                if block1.content_hash == block2.content_hash:
                    continue

                pair_key = tuple(
                    sorted(
                        [
                            f"{block1.file_path}:{block1.start_line}",
                            f"{block2.file_path}:{block2.start_line}",
                        ]
                    )
                )
                if pair_key in seen_pairs:
                    continue

                similarity = _compute_similarity(block1, block2)
                if similarity >= self.min_similarity:
                    seen_pairs.add(pair_key)
                    duplicates.append(
                        DuplicatePair(
                            file1=block1.file_path,
                            file2=block2.file_path,
                            start_line1=block1.start_line,
                            end_line1=block1.end_line,
                            start_line2=block2.start_line,
                            end_line2=block2.end_line,
                            similarity=similarity,
                            line_count=(block1.line_count + block2.line_count) // 2,
                            code_snippet=block1.content[:200],
                        )
                    )

        return duplicates

    def _find_similar_duplicates(
        self,
        all_blocks: List[CodeBlock],
        seen_pairs: Set[Tuple[str, str]],
    ) -> List[DuplicatePair]:
        """Find similarity-based duplicates (Issue #560, #609, #659: LSH optimized).

        Issue #659: Uses Locality-Sensitive Hashing (LSH) for O(n) expected complexity
        instead of O(n²) pairwise comparison. LSH is 10-100x faster for large codebases.
        Falls back to O(n²) if datasketch is not available or LSH is disabled.

        Issue #665: Refactored to extract helper methods.
        """
        # Issue #659: Use LSH for O(n) expected similarity search
        if LSH_ENABLED and LSH_AVAILABLE and len(all_blocks) > 10:
            logger.info("Using LSH for similarity search on %d blocks", len(all_blocks))

            lsh_candidates = _find_lsh_candidates(
                all_blocks,
                threshold=LSH_SIMILARITY_THRESHOLD,
                num_perm=LSH_NUM_PERMUTATIONS,
            )

            return self._process_lsh_candidates(all_blocks, lsh_candidates, seen_pairs)

        # Fallback: O(n²) pairwise comparison
        logger.info("Using O(n²) fallback for similarity search")

        blocks_to_compare = all_blocks
        if (
            MAX_BLOCKS_FOR_SIMILARITY > 0
            and len(all_blocks) > MAX_BLOCKS_FOR_SIMILARITY
        ):
            sorted_blocks = sorted(all_blocks, key=lambda b: b.line_count, reverse=True)
            blocks_to_compare = sorted_blocks[:MAX_BLOCKS_FOR_SIMILARITY]
            logger.info(
                "Sampling %d of %d blocks for similarity comparison",
                len(blocks_to_compare),
                len(all_blocks),
            )

        return self._pairwise_similarity_search(blocks_to_compare, seen_pairs)

    def _calculate_statistics(
        self,
        duplicates: List[DuplicatePair],
    ) -> Tuple[int, int, int, int]:
        """Calculate duplicate statistics (Issue #560: extracted)."""
        high_count = sum(
            1 for d in duplicates if d.similarity >= HIGH_SIMILARITY_THRESHOLD
        )
        medium_count = sum(
            1
            for d in duplicates
            if MEDIUM_SIMILARITY_THRESHOLD <= d.similarity < HIGH_SIMILARITY_THRESHOLD
        )
        low_count = sum(
            1
            for d in duplicates
            if LOW_SIMILARITY_THRESHOLD <= d.similarity < MEDIUM_SIMILARITY_THRESHOLD
        )
        total_lines = sum(d.line_count for d in duplicates)
        return high_count, medium_count, low_count, total_lines

    def run_analysis(self) -> DuplicateAnalysis:
        """
        Run duplicate code analysis on the codebase.

        Issue #560: Refactored to use helper methods for better maintainability.

        Returns:
            DuplicateAnalysis with all detected duplicates
        """
        logger.info("Starting duplicate code detection in %s", self.project_root)

        files = self._get_files_to_scan()
        logger.info("Found %d files to scan", len(files))

        # Extract all code blocks
        all_blocks = self._extract_all_blocks(files)
        logger.info("Extracted %d code blocks", len(all_blocks))

        # Group blocks by hash for exact matches
        hash_groups: Dict[str, List[CodeBlock]] = defaultdict(list)
        for block in all_blocks:
            hash_groups[block.content_hash].append(block)

        # Find duplicates using both methods
        seen_pairs: Set[Tuple[str, str]] = set()
        duplicates = self._find_exact_duplicates(hash_groups, seen_pairs)
        duplicates.extend(self._find_similar_duplicates(all_blocks, seen_pairs))

        # Sort and optionally limit results (0 = no limit)
        duplicates.sort(key=lambda x: x.similarity, reverse=True)
        if MAX_DUPLICATES_RETURNED > 0:
            duplicates = duplicates[:MAX_DUPLICATES_RETURNED]

        # Calculate statistics
        high_count, medium_count, low_count, total_lines = self._calculate_statistics(
            duplicates
        )

        analysis = DuplicateAnalysis(
            total_duplicates=len(duplicates),
            high_similarity_count=high_count,
            medium_similarity_count=medium_count,
            low_similarity_count=low_count,
            total_duplicate_lines=total_lines,
            duplicates=duplicates,
            files_analyzed=len(files),
            scan_timestamp=datetime.now().isoformat(),
        )

        logger.info(
            "Duplicate detection complete: %d duplicates found (%d high, %d medium, %d low)",
            len(duplicates),
            high_count,
            medium_count,
            low_count,
        )

        return analysis

    # =========================================================================
    # Issue #554: Async Semantic Analysis Methods
    # =========================================================================

    def _sample_blocks_for_analysis(
        self, all_blocks: List[CodeBlock], analysis_type: str = "semantic"
    ) -> List[CodeBlock]:
        """
        Sample blocks if there are too many for efficient analysis.

        Issue #620: Extracted from _find_semantic_duplicates_async.

        Args:
            all_blocks: List of all code blocks
            analysis_type: Type of analysis for logging

        Returns:
            Sampled list of blocks (or original if under limit)
        """
        if (
            MAX_BLOCKS_FOR_SIMILARITY > 0
            and len(all_blocks) > MAX_BLOCKS_FOR_SIMILARITY
        ):
            sorted_blocks = sorted(all_blocks, key=lambda b: b.line_count, reverse=True)
            sampled = sorted_blocks[:MAX_BLOCKS_FOR_SIMILARITY]
            logger.info(
                "Sampling %d of %d blocks for %s analysis",
                len(sampled),
                len(all_blocks),
                analysis_type,
            )
            return sampled
        return all_blocks

    def _create_duplicate_pair(
        self,
        block1: CodeBlock,
        block2: CodeBlock,
        similarity: float,
    ) -> DuplicatePair:
        """
        Create a DuplicatePair from two code blocks.

        Issue #620: Extracted from _find_semantic_duplicates_async.

        Args:
            block1: First code block
            block2: Second code block
            similarity: Similarity score between blocks

        Returns:
            DuplicatePair object
        """
        return DuplicatePair(
            file1=block1.file_path,
            file2=block2.file_path,
            start_line1=block1.start_line,
            end_line1=block1.end_line,
            start_line2=block2.start_line,
            end_line2=block2.end_line,
            similarity=similarity,
            line_count=(block1.line_count + block2.line_count) // 2,
            code_snippet=block1.content[:200],
        )

    async def _find_semantic_duplicates_async(
        self,
        all_blocks: List[CodeBlock],
        seen_pairs: Set[Tuple[str, str]],
    ) -> List[DuplicatePair]:
        """
        Find semantically similar code blocks using LLM embeddings.

        Issue #554: Uses ChromaDB vector storage and cosine similarity.
        Issue #620: Refactored to use extracted helper methods.

        Args:
            all_blocks: List of code blocks to analyze
            seen_pairs: Set of already-detected pairs to skip

        Returns:
            List of semantically similar duplicate pairs
        """
        if not self.use_semantic_analysis:
            return []

        duplicates: List[DuplicatePair] = []
        blocks_to_compare = self._sample_blocks_for_analysis(all_blocks, "semantic")

        # Generate embeddings and compute similarities
        codes = [block.normalized_content for block in blocks_to_compare]
        embeddings = await self._get_embeddings_batch(codes)
        similarity_pairs = self._compute_batch_similarities(
            embeddings, min_similarity=self.min_similarity
        )

        for i, j, similarity in similarity_pairs:
            block1, block2 = blocks_to_compare[i], blocks_to_compare[j]

            # Skip same file
            if block1.file_path == block2.file_path:
                continue

            # Skip if already found by other methods
            pair_key = tuple(
                sorted(
                    [
                        f"{block1.file_path}:{block1.start_line}",
                        f"{block2.file_path}:{block2.start_line}",
                    ]
                )
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            duplicates.append(self._create_duplicate_pair(block1, block2, similarity))

        logger.info("Semantic analysis found %d additional duplicates", len(duplicates))
        return duplicates

    async def _collect_all_duplicates(
        self,
        all_blocks: List[CodeBlock],
    ) -> List[DuplicatePair]:
        """
        Collect duplicates using all detection methods.

        Issue #665: Extracted from run_analysis_async to reduce function length.

        Args:
            all_blocks: List of code blocks to analyze

        Returns:
            List of all detected duplicate pairs
        """
        # Group blocks by hash for exact matches
        hash_groups: Dict[str, List[CodeBlock]] = defaultdict(list)
        for block in all_blocks:
            hash_groups[block.content_hash].append(block)

        # Find duplicates using all methods
        seen_pairs: Set[Tuple[str, str]] = set()
        duplicates = self._find_exact_duplicates(hash_groups, seen_pairs)
        duplicates.extend(self._find_similar_duplicates(all_blocks, seen_pairs))

        # Add semantic duplicates if enabled
        if self.use_semantic_analysis:
            semantic_dups = await self._find_semantic_duplicates_async(
                all_blocks, seen_pairs
            )
            duplicates.extend(semantic_dups)

        return duplicates

    def _build_duplicate_analysis(
        self,
        duplicates: List[DuplicatePair],
        files_count: int,
    ) -> DuplicateAnalysis:
        """
        Build DuplicateAnalysis from duplicate pairs.

        Issue #665: Extracted from run_analysis_async to reduce function length.

        Args:
            duplicates: List of detected duplicate pairs
            files_count: Number of files analyzed

        Returns:
            DuplicateAnalysis with statistics
        """
        # Sort and optionally limit results
        duplicates.sort(key=lambda x: x.similarity, reverse=True)
        if MAX_DUPLICATES_RETURNED > 0:
            duplicates = duplicates[:MAX_DUPLICATES_RETURNED]

        # Calculate statistics
        high_count, medium_count, low_count, total_lines = self._calculate_statistics(
            duplicates
        )

        return DuplicateAnalysis(
            total_duplicates=len(duplicates),
            high_similarity_count=high_count,
            medium_similarity_count=medium_count,
            low_similarity_count=low_count,
            total_duplicate_lines=total_lines,
            duplicates=duplicates,
            files_analyzed=files_count,
            scan_timestamp=datetime.now().isoformat(),
        )

    async def run_analysis_async(self) -> DuplicateAnalysis:
        """
        Run duplicate code analysis with semantic similarity.

        Issue #554: Async version that includes LLM-based semantic
        duplicate detection in addition to hash and token methods.
        Issue #665: Refactored to use extracted helper methods.

        Returns:
            DuplicateAnalysis with all detected duplicates (including semantic)
        """
        logger.info(
            "Starting duplicate detection with semantic analysis in %s",
            self.project_root,
        )

        # Check for cached results first
        cache_key = f"dup_analysis:{self.project_root}"
        if self.use_semantic_analysis:
            cached = await self._get_cached_result(
                cache_key, prefix="duplicate_detector"
            )
            if cached:
                logger.info("Returning cached duplicate analysis")
                return DuplicateAnalysis(**cached)

        files = self._get_files_to_scan()
        logger.info("Found %d files to scan", len(files))

        # Extract all code blocks
        all_blocks = self._extract_all_blocks(files)
        logger.info("Extracted %d code blocks", len(all_blocks))

        # Issue #665: Use helper to collect duplicates
        duplicates = await self._collect_all_duplicates(all_blocks)

        # Issue #665: Use helper to build analysis
        analysis = self._build_duplicate_analysis(duplicates, len(files))

        # Cache results
        if self.use_semantic_analysis:
            await self._cache_result(
                cache_key,
                analysis.to_dict(),
                prefix="duplicate_detector",
                ttl=3600,  # 1 hour cache
            )

        logger.info(
            "Duplicate detection complete: %d duplicates found (%d high, %d medium, %d low)",
            analysis.total_duplicates,
            analysis.high_similarity_count,
            analysis.medium_similarity_count,
            analysis.low_similarity_count,
        )

        return analysis

    def get_infrastructure_metrics(self) -> Dict[str, Any]:
        """
        Get infrastructure metrics for monitoring.

        Issue #554: Returns cache hits, embeddings generated, etc.
        """
        if self.use_semantic_analysis:
            return self._get_infrastructure_metrics()
        return {}


# =============================================================================
# Convenience Functions
# =============================================================================


def detect_duplicates(project_root: Optional[str] = None) -> DuplicateAnalysis:
    """
    Run duplicate code detection on a project.

    Args:
        project_root: Root directory to scan

    Returns:
        DuplicateAnalysis with results
    """
    detector = DuplicateCodeDetector(project_root=project_root)
    return detector.run_analysis()


async def detect_duplicates_async(
    project_root: Optional[str] = None,
    use_semantic_analysis: bool = True,
) -> DuplicateAnalysis:
    """
    Run duplicate code detection with semantic analysis.

    Issue #554: Async version with LLM-based semantic duplicate detection.

    Args:
        project_root: Root directory to scan
        use_semantic_analysis: Enable semantic analysis (default True)

    Returns:
        DuplicateAnalysis with results including semantic duplicates
    """
    detector = DuplicateCodeDetector(
        project_root=project_root,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await detector.run_analysis_async()
