# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from utils.file_categorization import (
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
    is_skipped_path,
)

from .duplicate_blocks import MIN_DUPLICATE_LINES, CodeBlock, make_block
from .duplicate_clusters import (
    KIND_EXACT,
    KIND_STRUCTURAL,
    DuplicateCluster,
    cluster_similar_pairs,
    find_identical_clusters,
    merge_adjacent_clusters,
)
from .duplicate_lsh import CANCEL_CHECK_INTERVAL, LSH_AVAILABLE, eligible_indices, find_lsh_candidates

logger = get_logger(__name__)

# Issue #554: Flag to enable semantic analysis infrastructure
SEMANTIC_ANALYSIS_AVAILABLE = False
SemanticAnalysisMixin = None

try:
    from code_intelligence.analytics_infrastructure import SemanticAnalysisMixin as _SemanticAnalysisMixin

    SemanticAnalysisMixin = _SemanticAnalysisMixin
    SEMANTIC_ANALYSIS_AVAILABLE = True
except ImportError:
    logger.debug("SemanticAnalysisMixin not available - semantic features disabled")


# Issue #1225: JS/TS function detection pattern (hoisted from _extract_js_blocks)
_JS_FUNC_RE = re.compile(
    r"(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*" r"(?:async\s+)?(?:function|\([^)]*\)\s*=>))" r"[^{]*\{",
    re.MULTILINE,
)

# =============================================================================
# Configuration Constants
# =============================================================================

# Similarity thresholds
HIGH_SIMILARITY_THRESHOLD = 0.90
MEDIUM_SIMILARITY_THRESHOLD = 0.70
LOW_SIMILARITY_THRESHOLD = 0.50
# Maximum files to scan (0 = no limit, scan all files)
# Issue #609: No limit on files - scan entire codebase
MAX_FILES_TO_SCAN = 0
# Maximum duplicate clusters RETURNED (0 = no limit). The count and the statistics
# always describe every cluster found; only the list is cut, and the analysis says so
# (`truncated`). "No artificial limit" (#609) meant 2.5 million pairs on AutoBot's
# own tree -- nothing a panel can show, a Redis result, or a JSON response (#18067).
MAX_DUPLICATES_RETURNED = env_int("AUTOBOT_DUPLICATE_MAX_RETURNED", 5000)
# Maximum blocks for O(n^2) similarity comparison
# Issue #609: Exact hash matches have no limit (O(n) via hash grouping)
# Similarity comparison is O(n^2), so we sample larger blocks for performance
# 500 blocks = ~125K comparisons, targets <30s runtime for similarity phase
# (Previous 2000 blocks = 2M+ comparisons was causing 60s timeouts)
MAX_BLOCKS_FOR_SIMILARITY = 500

# LSH configuration (num_perm, token floor, cancel interval) lives in duplicate_lsh.py.


# =============================================================================
# Data Models
# =============================================================================


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
    duplicates: List[DuplicateCluster] = field(default_factory=list)
    files_analyzed: int = 0
    scan_timestamp: str = ""
    # #22157: ``total_duplicates`` counts clusters, ``total_locations`` the places
    # they occupy; exact (equal code) and structural (equal once string literals are
    # erased) are counted apart, and the excluded trees are part of the answer.
    total_locations: int = 0
    exact_cluster_count: int = 0
    structural_cluster_count: int = 0
    excluded_dirs: List[str] = field(default_factory=lambda: sorted(SKIP_DIRS))

    @classmethod
    def from_dict(cls, cached: Dict) -> "DuplicateAnalysis":
        """Rebuild an analysis from its ``to_dict`` form (the Redis cache entry).

        ``to_dict`` carries derived keys (``truncated``) and cluster rows as dicts, so
        ``cls(**cached)`` raised TypeError and every cache hit fell through (#22157).
        """
        fields = {k: v for k, v in cached.items() if k not in ("truncated", "duplicates")}
        return cls(duplicates=[DuplicateCluster.from_dict(r) for r in cached.get("duplicates", [])], **fields)

    @property
    def truncated(self) -> bool:
        """True when ``duplicates`` is shorter than ``total_duplicates`` (#18067)."""
        return len(self.duplicates) < self.total_duplicates

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_duplicates": self.total_duplicates,
            "total_locations": self.total_locations,
            "exact_cluster_count": self.exact_cluster_count,
            "structural_cluster_count": self.structural_cluster_count,
            "excluded_dirs": self.excluded_dirs,
            "truncated": self.truncated,
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
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith(("def ", "async def ", "class "))]
    blocks = []
    for start, stop in zip(starts, starts[1:] + [len(lines)]):
        block = make_block(file_path, start + 1, stop, "\n".join(lines[start:stop]), stop - start)
        if block:
            blocks.append(block)
    return blocks


def _js_block_end(content: str, match: "re.Match[str]") -> int:
    """Offset just past the brace that closes the function ``match`` opens."""
    brace_count = 1
    pos = match.end()
    while pos < len(content) and brace_count > 0:
        if content[pos] == "{":
            brace_count += 1
        elif content[pos] == "}":
            brace_count -= 1
        pos += 1
    return pos


def _extract_js_blocks(file_path: str, lines: List[str]) -> List[CodeBlock]:
    """Extract JavaScript/TypeScript function blocks."""
    blocks = []
    content = "\n".join(lines)

    for match in _JS_FUNC_RE.finditer(content):
        start_line = content[: match.start()].count("\n")
        pos = _js_block_end(content, match)
        end_line = content[:pos].count("\n")
        if (end_line - start_line) < MIN_DUPLICATE_LINES:
            continue
        block = make_block(
            file_path, start_line + 1, end_line + 1, content[match.start() : pos], end_line - start_line + 1
        )
        if block:
            blocks.append(block)

    return blocks


def _extract_sliding_window_blocks(file_path: str, lines: List[str], window_size: int = 10) -> List[CodeBlock]:
    """Extract blocks using sliding window for generic files."""
    blocks = []
    for i in range(0, len(lines) - window_size + 1, window_size // 2):
        block = make_block(file_path, i + 1, i + window_size, "\n".join(lines[i : i + window_size]), window_size)
        if block:
            blocks.append(block)
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
    len_ratio = min(len(s1), len(s2)) / max(len(s1), len(s2)) if max(len(s1), len(s2)) > 0 else 0
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


def _is_new_semantic_pair(block1: CodeBlock, block2: CodeBlock, seen_pairs: Set[Tuple[str, str]]) -> bool:
    """True for a cross-file, non-identical pair not seen before; records it in ``seen_pairs``."""
    if block1.file_path == block2.file_path:
        return False
    # Identical blocks are already clusters (#22157)
    if block1.content_hash == block2.content_hash:
        return False
    pair_key = tuple(sorted([f"{block1.file_path}:{block1.start_line}", f"{block2.file_path}:{block2.start_line}"]))
    if pair_key in seen_pairs:
        return False
    seen_pairs.add(pair_key)
    return True


def _cluster_totals(clusters: List[DuplicateCluster]) -> Tuple[int, int, int, int]:
    """``(clusters, locations, exact clusters, structural clusters)`` of ``clusters``."""
    return (
        len(clusters),
        sum(len(d.locations) for d in clusters),
        sum(1 for d in clusters if d.kind == KIND_EXACT),
        sum(1 for d in clusters if d.kind == KIND_STRUCTURAL),
    )


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
        project_root: str | None = None,
        min_similarity: float = LOW_SIMILARITY_THRESHOLD,
        use_semantic_analysis: bool = False,
        cancel_token: "threading.Event | None" = None,
    ):
        """
        Initialize the duplicate detector.

        Args:
            project_root: Root directory to scan (defaults to AutoBot project)
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            use_semantic_analysis: Enable LLM-based semantic duplicate detection (Issue #554)
            cancel_token: #12779 — set by the caller when it stops waiting.
                asyncio.wait_for cancels the AWAIT, but work already running in a
                ThreadPoolExecutor cannot be cancelled, so a timed-out scan kept
                walking the whole tree in a thread whose result was already
                discarded. The scan polls this token and stops cooperatively.
        """
        # Issue #554: Initialize semantic analysis infrastructure if enabled
        self.use_semantic_analysis = use_semantic_analysis and SEMANTIC_ANALYSIS_AVAILABLE

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
        self._cancel_token = cancel_token
        self.code_extensions = PYTHON_EXTENSIONS | JS_EXTENSIONS | TS_EXTENSIONS | VUE_EXTENSIONS

    def _cancelled(self) -> bool:
        """True once the caller has stopped waiting for this scan (#12779)."""
        return self._cancel_token is not None and self._cancel_token.is_set()

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped, relative to this scan's root.

        #13602: this compared SKIP_DIRS against the ABSOLUTE path, so scanning a
        root that itself sits under `.worktrees/` would have classified every
        file below it as skippable. The method had no callers, so nothing broke
        — it was a trap armed for whoever wired it in next.
        """
        return is_skipped_path(path, self.project_root)

    def _get_files_to_scan(self) -> List[Path]:
        """Get list of files to scan for duplicates.

        #12779: this used ``project_root.glob(f"**/*{ext}")`` once PER EXTENSION
        and applied the skip-list only AFTER the walk had already descended. So
        node_modules/, .git/, venv/ and .worktrees/ were fully traversed and then
        discarded — N times over, once per extension. That is what made a single
        scan expensive enough to blow the 120 s timeout.

        Now: ONE os.walk over the tree, pruning excluded directories in place via
        ``dirnames[:]`` so they are never descended at all, matching every
        extension in the same pass.

        Honours the cooperative cancel token so an abandoned scan can actually
        stop instead of running to completion in a thread nobody is waiting on.
        """
        files: List[Path] = []
        extensions = tuple(self.code_extensions)

        for dirpath, dirnames, filenames in os.walk(self.project_root):
            if self._cancelled():
                logger.info("File scan cancelled after %d files", len(files))
                return files

            # Prune BEFORE descending — this is the whole point. Mutating
            # dirnames in place is what stops os.walk entering these trees.
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for name in filenames:
                if not name.endswith(extensions):
                    continue
                files.append(Path(dirpath) / name)
                # Issue #609: MAX_FILES_TO_SCAN=0 means no limit
                if MAX_FILES_TO_SCAN > 0 and len(files) >= MAX_FILES_TO_SCAN:
                    logger.warning(
                        "Reached max files limit (%d), stopping scan",
                        MAX_FILES_TO_SCAN,
                    )
                    return files

        return files

    def _extract_all_blocks(self, files: List[Path]) -> List[CodeBlock]:
        """Extract code blocks from all files (Issue #560: extracted).

        #13602: honours the cancel token. #12779 added the token but consulted
        it only inside the os.walk loop — 0.14 s of a run whose remaining phases
        measured over six minutes on a single tree. So a scan the caller had
        abandoned still ran to completion holding one of eight executor threads,
        which is the starvation that makes unrelated endpoints hang.
        """
        all_blocks: List[CodeBlock] = []
        for index, file_path in enumerate(files):
            if index % CANCEL_CHECK_INTERVAL == 0 and self._cancelled():
                logger.info(
                    "Block extraction cancelled after %d/%d files",
                    index,
                    len(files),
                )
                return all_blocks
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                blocks = _extract_code_blocks(str(file_path), content)
                all_blocks.extend(blocks)
            except Exception as e:
                logger.debug("Failed to process %s: %s", file_path, e)
        return all_blocks

    def _to_clusters(self, all_blocks: List[CodeBlock], pairs: List[DuplicatePair]) -> List[DuplicateCluster]:
        """Clusters of identical blocks plus clustered fuzzy pairs, adjacent ones merged (#22157).

        Identical blocks are grouped by hash in O(n); a cluster lists every location
        instead of the k(k-1)/2 pairs it used to cost (#616: no O(n^2) pass is needed).
        """
        return merge_adjacent_clusters(find_identical_clusters(all_blocks) + cluster_similar_pairs(pairs))

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
        # The fuzzy pass has ONE boundary, whichever algorithm runs: blocks under
        # MIN_TOKENS_FOR_SIMILARITY distinct tokens match only by exact hash.
        eligible = [all_blocks[i] for i in eligible_indices(all_blocks)]

        # Issue #659: Use LSH for O(n) expected similarity search
        if LSH_AVAILABLE and len(eligible) > 10:
            lsh_candidates = find_lsh_candidates(
                all_blocks,
                _compute_similarity,
                self.min_similarity,
                cancelled=self._cancelled,
            )
            return self._process_lsh_candidates(all_blocks, lsh_candidates, seen_pairs)

        # Fallback: O(n²) pairwise comparison
        logger.info("Using O(n²) fallback for similarity search")

        blocks_to_compare = eligible
        if MAX_BLOCKS_FOR_SIMILARITY > 0 and len(eligible) > MAX_BLOCKS_FOR_SIMILARITY:
            sorted_blocks = sorted(eligible, key=lambda b: b.line_count, reverse=True)
            blocks_to_compare = sorted_blocks[:MAX_BLOCKS_FOR_SIMILARITY]
            logger.info(
                "Sampling %d of %d blocks for similarity comparison",
                len(blocks_to_compare),
                len(eligible),
            )

        return self._pairwise_similarity_search(blocks_to_compare, seen_pairs)

    def _calculate_statistics(
        self,
        duplicates: List[DuplicateCluster],
    ) -> Tuple[int, int, int, int]:
        """Calculate duplicate statistics (Issue #560: extracted)."""
        high_count = sum(1 for d in duplicates if d.similarity >= HIGH_SIMILARITY_THRESHOLD)
        medium_count = sum(
            1 for d in duplicates if MEDIUM_SIMILARITY_THRESHOLD <= d.similarity < HIGH_SIMILARITY_THRESHOLD
        )
        low_count = sum(1 for d in duplicates if LOW_SIMILARITY_THRESHOLD <= d.similarity < MEDIUM_SIMILARITY_THRESHOLD)
        # k copies hold k-1 redundant ones (a pair: one)
        total_lines = sum(d.line_count * (len(d.locations) - 1) for d in duplicates)
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
        if self._cancelled():
            # #13602: abandoned before the expensive similarity phases. Returning
            # an empty analysis is honest — the caller has already stopped
            # waiting — and it frees the executor thread the next request needs.
            logger.info("Duplicate detection abandoned before similarity search")
            return self._build_duplicate_analysis([], len(files))

        duplicates = self._to_clusters(all_blocks, self._find_similar_duplicates(all_blocks, set()))

        analysis = self._build_duplicate_analysis(duplicates, len(files))
        logger.info(
            "Duplicate detection complete: %d duplicates found (%d high, %d medium, %d low), %d returned",
            analysis.total_duplicates,
            analysis.high_similarity_count,
            analysis.medium_similarity_count,
            analysis.low_similarity_count,
            len(analysis.duplicates),
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
        if MAX_BLOCKS_FOR_SIMILARITY > 0 and len(all_blocks) > MAX_BLOCKS_FOR_SIMILARITY:
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
        """Find semantically similar blocks using LLM embeddings (#554, #620); extends ``seen_pairs``."""
        if not self.use_semantic_analysis:
            return []

        blocks = self._sample_blocks_for_analysis(all_blocks, "semantic")
        embeddings = await self._get_embeddings_batch([block.normalized_content for block in blocks])
        similarity_pairs = self._compute_batch_similarities(embeddings, min_similarity=self.min_similarity)
        duplicates = [
            self._create_duplicate_pair(blocks[i], blocks[j], similarity)
            for i, j, similarity in similarity_pairs
            if _is_new_semantic_pair(blocks[i], blocks[j], seen_pairs)
        ]
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
            List of all detected duplicate clusters
        """
        seen_pairs: Set[Tuple[str, str]] = set()
        pairs = self._find_similar_duplicates(all_blocks, seen_pairs)

        # Add semantic duplicates if enabled
        if self.use_semantic_analysis:
            pairs.extend(await self._find_semantic_duplicates_async(all_blocks, seen_pairs))

        return self._to_clusters(all_blocks, pairs)

    def _build_duplicate_analysis(self, duplicates: List[DuplicateCluster], files_count: int) -> DuplicateAnalysis:
        """Build DuplicateAnalysis from duplicate clusters (#665).

        Statistics describe EVERY cluster found; only the returned list is cut (#18067).
        """
        high_count, medium_count, low_count, total_lines = self._calculate_statistics(duplicates)
        total, total_locations, exact, structural = _cluster_totals(duplicates)
        duplicates.sort(key=lambda x: (x.similarity, x.line_count), reverse=True)
        if MAX_DUPLICATES_RETURNED > 0:
            duplicates = duplicates[:MAX_DUPLICATES_RETURNED]
        return DuplicateAnalysis(
            total_duplicates=total,
            high_similarity_count=high_count,
            medium_similarity_count=medium_count,
            low_similarity_count=low_count,
            total_duplicate_lines=total_lines,
            duplicates=duplicates,
            files_analyzed=files_count,
            scan_timestamp=datetime.now(tz=timezone.utc).isoformat(),
            total_locations=total_locations,
            exact_cluster_count=exact,
            structural_cluster_count=structural,
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
            cached = await self._get_cached_result(cache_key, prefix="duplicate_detector")
            if cached:
                logger.info("Returning cached duplicate analysis")
                return DuplicateAnalysis.from_dict(cached)

        files = self._get_files_to_scan()
        logger.info("Found %d files to scan", len(files))

        # Extract all code blocks
        all_blocks = self._extract_all_blocks(files)
        logger.info("Extracted %d code blocks", len(all_blocks))
        if self._cancelled():
            # #13602: abandoned before the expensive similarity phases. Returning
            # an empty analysis is honest — the caller has already stopped
            # waiting — and it frees the executor thread the next request needs.
            logger.info("Duplicate detection abandoned before similarity search")
            return self._build_duplicate_analysis([], len(files))

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


def detect_duplicates(project_root: str | None = None) -> DuplicateAnalysis:
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
    project_root: str | None = None,
    use_semantic_analysis: bool = True,
    min_similarity: float = LOW_SIMILARITY_THRESHOLD,
) -> DuplicateAnalysis:
    """
    Run duplicate code detection with semantic analysis.

    Issue #554: Async version with LLM-based semantic duplicate detection.

    Args:
        project_root: Root directory to scan
        use_semantic_analysis: Enable semantic analysis (default True)
        min_similarity: Minimum similarity threshold. The only caller passed this
            keyword before the parameter existed, so every semantic request
            raised TypeError and silently fell back to the standard scan.

    Returns:
        DuplicateAnalysis with results including semantic duplicates
    """
    detector = DuplicateCodeDetector(
        project_root=project_root,
        min_similarity=min_similarity,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await detector.run_analysis_async()
