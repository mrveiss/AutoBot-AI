# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Clone Detector Module

Main clone detection engine that detects all four types of code clones:
- Type 1: Exact clones
- Type 2: Renamed clones
- Type 3: Near-miss clones
- Type 4: Semantic clones

Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
import hashlib
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.code_intelligence.fingerprinting.ast_hasher import ASTHasher
from src.code_intelligence.fingerprinting.semantic_hasher import SemanticHasher
from src.code_intelligence.fingerprinting.similarity import SimilarityCalculator
from src.code_intelligence.fingerprinting.types import (
    CloneDetectionReport,
    CloneGroup,
    CloneInstance,
    CloneSeverity,
    CloneType,
    CodeFragment,
    Fingerprint,
    FingerprintType,
)

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for function definition types
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


class CloneDetector:
    """
    Main clone detection engine.

    Detects all four types of code clones:
    - Type 1: Exact clones
    - Type 2: Renamed clones
    - Type 3: Near-miss clones
    - Type 4: Semantic clones
    """

    # Minimum fragment size for detection (in lines)
    MIN_FRAGMENT_LINES = 5

    # Similarity thresholds
    TYPE_3_SIMILARITY_THRESHOLD = 0.7  # Minimum for Type 3 clones
    TYPE_4_SIMILARITY_THRESHOLD = 0.6  # Minimum for Type 4 clones

    def __init__(
        self,
        min_fragment_lines: int = 5,
        exclude_dirs: Optional[List[str]] = None,
        use_shared_cache: bool = True,
    ):
        """
        Initialize the clone detector.

        Args:
            min_fragment_lines: Minimum lines for a fragment to be considered
            exclude_dirs: Directories to exclude from analysis
            use_shared_cache: Whether to use shared ASTCache (Issue #607)
        """
        self.min_fragment_lines = min_fragment_lines
        self.exclude_dirs = exclude_dirs or [
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            "archive",
            ".mypy_cache",
        ]
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        self.ast_hasher = ASTHasher()
        self.semantic_hasher = SemanticHasher()
        self.similarity_calc = SimilarityCalculator()

        # Storage for fingerprints
        self._structural_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)
        self._normalized_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)
        self._semantic_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)

    def _collect_fragments(self, directory: str) -> tuple:
        """Collect all code fragments from directory (Issue #398: extracted).

        Returns:
            Tuple of (fragments list, total_files, total_lines)
        """
        fragments: List[CodeFragment] = []
        total_files = 0
        total_lines = 0

        for py_file in self._get_python_files(directory):
            try:
                file_fragments = self._extract_fragments(py_file)
                fragments.extend(file_fragments)
                total_files += 1

                with open(py_file, "r", encoding="utf-8") as f:
                    total_lines += len(f.readlines())
            except Exception as e:
                logger.warning("Failed to process %s: %s", py_file, e)

        return fragments, total_files, total_lines

    def _detect_all_clone_types(
        self, fragments: List[CodeFragment]
    ) -> List[CloneGroup]:
        """Detect clones of all types (Issue #398: extracted).

        Returns:
            List of all detected clone groups
        """
        clone_groups: List[CloneGroup] = []

        # Type 1: Exact clones (from structural fingerprints)
        type1_groups = self._detect_type1_clones()
        clone_groups.extend(type1_groups)

        # Type 2: Renamed clones (from normalized fingerprints)
        type2_groups = self._detect_type2_clones(type1_groups)
        clone_groups.extend(type2_groups)

        # Type 3: Near-miss clones (fuzzy matching)
        type3_groups = self._detect_type3_clones(fragments, type1_groups, type2_groups)
        clone_groups.extend(type3_groups)

        # Type 4: Semantic clones (from semantic fingerprints)
        type4_groups = self._detect_type4_clones(
            fragments, type1_groups, type2_groups, type3_groups
        )
        clone_groups.extend(type4_groups)

        return clone_groups

    def _build_clone_report(
        self,
        directory: str,
        fragments: List[CodeFragment],
        clone_groups: List[CloneGroup],
        total_files: int,
        total_lines: int,
    ) -> CloneDetectionReport:
        """Build the final clone detection report (Issue #398: extracted).

        Returns:
            Complete CloneDetectionReport
        """
        # Add refactoring suggestions
        for group in clone_groups:
            group.refactoring_suggestion = self._generate_refactoring_suggestion(group)
            group.estimated_effort = self._estimate_refactoring_effort(group)

        # Calculate statistics
        total_duplicated_lines = sum(g.total_duplicated_lines for g in clone_groups)
        duplication_percentage = (
            (total_duplicated_lines / total_lines * 100) if total_lines > 0 else 0
        )

        return CloneDetectionReport(
            scan_path=directory,
            total_files=total_files,
            total_fragments=len(fragments),
            clone_groups=clone_groups,
            clone_type_distribution=self._calculate_type_distribution(clone_groups),
            severity_distribution=self._calculate_severity_distribution(clone_groups),
            total_duplicated_lines=total_duplicated_lines,
            duplication_percentage=duplication_percentage,
            top_cloned_files=self._find_top_cloned_files(clone_groups),
            refactoring_priorities=self._prioritize_refactoring(clone_groups),
        )

    def detect_clones(self, directory: str) -> CloneDetectionReport:
        """Detect all clones in a directory (Issue #398: refactored to use helpers).

        Args:
            directory: Path to the directory to analyze

        Returns:
            CloneDetectionReport with all findings
        """
        logger.info("Starting clone detection in: %s", directory)

        # Reset fingerprint storage
        self._structural_fingerprints.clear()
        self._normalized_fingerprints.clear()
        self._semantic_fingerprints.clear()

        # Issue #398: Use extracted helpers for phases
        fragments, total_files, total_lines = self._collect_fragments(directory)
        logger.info("Extracted %d fragments from %d files", len(fragments), total_files)

        # Generate fingerprints for all fragments
        for fragment in fragments:
            self._generate_fingerprints(fragment)

        # Detect all clone types
        clone_groups = self._detect_all_clone_types(fragments)

        # Build and return report
        report = self._build_clone_report(
            directory, fragments, clone_groups, total_files, total_lines
        )

        logger.info(
            "Clone detection complete: %d groups, %.1f%% duplication",
            len(clone_groups),
            report.duplication_percentage,
        )

        return report

    def _get_python_files(self, directory: str) -> List[str]:
        """
        Get all Python files in directory, excluding specified patterns.

        Args:
            directory: Root directory to search

        Returns:
            Sorted list of Python file paths
        """
        python_files = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            # Check if in excluded directory
            should_exclude = False
            for exclude_dir in self.exclude_dirs:
                if exclude_dir in py_file.parts:
                    should_exclude = True
                    break

            if not should_exclude:
                python_files.append(str(py_file))

        return sorted(python_files)

    def _create_fragment_from_node(
        self, node: ast.AST, file_path: str, lines: List[str], fragment_type: str
    ) -> Optional[CodeFragment]:
        """
        Create a CodeFragment from an AST node.

        Args:
            node: AST node (FunctionDef, AsyncFunctionDef, or ClassDef)
            file_path: Path to source file
            lines: Source code lines
            fragment_type: Type of fragment (function or class)

        Returns:
            CodeFragment if fragment meets size threshold, None otherwise
        """
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", start_line)
        line_count = end_line - start_line + 1

        if line_count < self.min_fragment_lines:
            return None

        fragment_source = "\n".join(lines[start_line - 1 : end_line])
        return CodeFragment(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source_code=fragment_source,
            ast_node=node,
            fragment_type=fragment_type,
            entity_name=node.name,
        )

    def _extract_fragments(self, file_path: str) -> List[CodeFragment]:
        """
        Extract code fragments (functions, classes) from a file.

        Args:
            file_path: Path to Python source file

        Returns:
            List of CodeFragment objects
        """
        try:
            return self._extract_fragments_from_file(file_path)
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", file_path, e)
            return []
        except Exception as e:
            logger.error("Error extracting fragments from %s: %s", file_path, e)
            return []

    def _extract_fragments_from_file(self, file_path: str) -> List[CodeFragment]:
        """
        Parse file and extract code fragments.

        Issue #607: Uses shared ASTCache when available for performance.

        Args:
            file_path: Path to Python source file

        Returns:
            List of CodeFragment objects
        """
        # Issue #607: Use shared AST cache if available
        if self.use_shared_cache:
            tree, source = get_ast_with_content(file_path)
            if tree is None or not source:
                return []
            lines = source.split("\n")
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            lines = source.split("\n")
            tree = ast.parse(source, filename=file_path)

        fragments: List[CodeFragment] = []
        for node in ast.walk(tree):
            fragment = self._maybe_create_fragment(node, file_path, lines)
            if fragment:
                fragments.append(fragment)
        return fragments

    def _maybe_create_fragment(
        self, node: ast.AST, file_path: str, lines: List[str]
    ) -> Optional[CodeFragment]:
        """
        Create a fragment from node if it's a function or class.

        Args:
            node: AST node to check
            file_path: Path to source file
            lines: Source code lines

        Returns:
            CodeFragment if node is function/class and meets threshold, None otherwise
        """
        if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
            return self._create_fragment_from_node(node, file_path, lines, "function")
        if isinstance(node, ast.ClassDef):
            return self._create_fragment_from_node(node, file_path, lines, "class")
        return None

    def _generate_fingerprints(self, fragment: CodeFragment) -> None:
        """
        Generate all types of fingerprints for a fragment.

        Args:
            fragment: CodeFragment to fingerprint
        """
        if fragment.ast_node is None:
            return

        # Structural fingerprint (Type 1)
        structural_hash = self.ast_hasher.hash_structural(fragment.ast_node)
        structural_features = self.ast_hasher.extract_features(fragment.ast_node)
        structural_fp = Fingerprint(
            hash_value=structural_hash,
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._structural_fingerprints[structural_hash].append(structural_fp)

        # Normalized fingerprint (Type 2)
        normalized_hash = self.ast_hasher.hash_normalized(fragment.ast_node)
        normalized_fp = Fingerprint(
            hash_value=normalized_hash,
            fingerprint_type=FingerprintType.AST_NORMALIZED,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._normalized_fingerprints[normalized_hash].append(normalized_fp)

        # Semantic fingerprint (Type 4)
        semantic_hash = self.semantic_hasher.hash_semantic(fragment.ast_node)
        semantic_fp = Fingerprint(
            hash_value=semantic_hash,
            fingerprint_type=FingerprintType.SEMANTIC,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._semantic_fingerprints[semantic_hash].append(semantic_fp)

    def _detect_type1_clones(self) -> List[CloneGroup]:
        """
        Detect Type 1 (exact) clones.

        Returns:
            List of CloneGroup objects for Type 1 clones
        """
        clone_groups: List[CloneGroup] = []

        for hash_value, fingerprints in self._structural_fingerprints.items():
            if len(fingerprints) >= 2:
                instances = [
                    CloneInstance(
                        fragment=fp.fragment,
                        fingerprint=fp,
                        similarity_score=1.0,
                    )
                    for fp in fingerprints
                ]

                total_lines = sum(i.fragment.line_count for i in instances)
                severity = self._calculate_severity(len(instances), total_lines)

                group = CloneGroup(
                    clone_type=CloneType.TYPE_1,
                    severity=severity,
                    instances=instances,
                    canonical_fingerprint=hash_value,
                    similarity_range=(1.0, 1.0),
                    total_duplicated_lines=total_lines,
                )
                clone_groups.append(group)

        return clone_groups

    def _collect_type1_fragment_keys(
        self, type1_groups: List[CloneGroup]
    ) -> Set[Tuple[str, int, int]]:
        """Collect fragment keys from Type 1 groups for exclusion (Issue #665: extracted helper)."""
        type1_fragments: Set[Tuple[str, int, int]] = set()
        for group in type1_groups:
            for instance in group.instances:
                type1_fragments.add(
                    (
                        instance.fragment.file_path,
                        instance.fragment.start_line,
                        instance.fragment.end_line,
                    )
                )
        return type1_fragments

    def _create_type2_clone_group(
        self, hash_value: str, valid_fps: List[Fingerprint]
    ) -> CloneGroup:
        """Create a Type 2 clone group from fingerprints (Issue #665: extracted helper)."""
        instances = [
            CloneInstance(
                fragment=fp.fragment,
                fingerprint=fp,
                similarity_score=1.0,
            )
            for fp in valid_fps
        ]
        total_lines = sum(i.fragment.line_count for i in instances)
        severity = self._calculate_severity(len(instances), total_lines)

        return CloneGroup(
            clone_type=CloneType.TYPE_2,
            severity=severity,
            instances=instances,
            canonical_fingerprint=hash_value,
            similarity_range=(1.0, 1.0),
            total_duplicated_lines=total_lines,
        )

    def _detect_type2_clones(self, type1_groups: List[CloneGroup]) -> List[CloneGroup]:
        """
        Detect Type 2 (renamed) clones, excluding Type 1 clones.

        Args:
            type1_groups: Previously detected Type 1 clone groups

        Returns:
            List of CloneGroup objects for Type 2 clones
        """
        type1_fragments = self._collect_type1_fragment_keys(type1_groups)
        clone_groups: List[CloneGroup] = []

        for hash_value, fingerprints in self._normalized_fingerprints.items():
            if len(fingerprints) < 2:
                continue

            # Filter out fragments already in Type 1 groups
            valid_fps = [
                fp
                for fp in fingerprints
                if (fp.fragment.file_path, fp.fragment.start_line, fp.fragment.end_line)
                not in type1_fragments
            ]

            # Check if all fragments are already in Type 1
            all_in_type1 = all(
                (fp.fragment.file_path, fp.fragment.start_line, fp.fragment.end_line)
                in type1_fragments
                for fp in fingerprints
            )

            if all_in_type1:
                continue  # Skip, this is already captured as Type 1

            # Create group if we have enough valid fingerprints
            if len(valid_fps) >= 2:
                clone_groups.append(
                    self._create_type2_clone_group(hash_value, valid_fps)
                )

        return clone_groups

    def _create_type3_clone_group(
        self,
        frag1: CodeFragment,
        similar_fragments: List[Tuple[CodeFragment, float]],
    ) -> CloneGroup:
        """
        Create a Type 3 clone group from a fragment and its similar matches.

        Issue #281: Extracted from _detect_type3_clones to reduce nesting.

        Args:
            frag1: Primary fragment
            similar_fragments: List of (fragment, similarity) tuples

        Returns:
            CloneGroup for the similar fragments
        """
        instances = [
            CloneInstance(
                fragment=frag1,
                fingerprint=Fingerprint(
                    hash_value="",
                    fingerprint_type=FingerprintType.AST_STRUCTURAL,
                    fragment=frag1,
                ),
                similarity_score=1.0,
            )
        ]

        similarities = [1.0]
        for frag, sim in similar_fragments:
            instances.append(
                CloneInstance(
                    fragment=frag,
                    fingerprint=Fingerprint(
                        hash_value="",
                        fingerprint_type=FingerprintType.AST_STRUCTURAL,
                        fragment=frag,
                    ),
                    similarity_score=sim,
                )
            )
            similarities.append(sim)

        total_lines = sum(i.fragment.line_count for i in instances)
        severity = self._calculate_severity(len(instances), total_lines)

        # Generate a hash for this group
        group_hash = hashlib.sha256(
            f"{frag1.file_path}:{frag1.start_line}".encode()
        ).hexdigest()[:16]

        return CloneGroup(
            clone_type=CloneType.TYPE_3,
            severity=severity,
            instances=instances,
            canonical_fingerprint=group_hash,
            similarity_range=(min(similarities), max(similarities)),
            total_duplicated_lines=total_lines,
        )

    def _find_similar_fragments(
        self,
        frag1: CodeFragment,
        candidates: List[CodeFragment],
        start_idx: int,
        processed: Set[Tuple[str, int, int]],
    ) -> List[Tuple[CodeFragment, float]]:
        """
        Find fragments similar to frag1 from candidates.

        Args:
            frag1: Fragment to find matches for
            candidates: List of candidate fragments
            start_idx: Index to start searching from
            processed: Set of already processed fragment keys

        Returns:
            List of (fragment, similarity) tuples meeting threshold

        Issue #620.
        """
        similar: List[Tuple[CodeFragment, float]] = []
        for j, frag2 in enumerate(candidates):
            if start_idx >= j:
                continue
            if (frag2.file_path, frag2.start_line, frag2.end_line) in processed:
                continue
            similarity = self.similarity_calc.calculate_similarity(frag1, frag2)
            if similarity >= self.TYPE_3_SIMILARITY_THRESHOLD:
                similar.append((frag2, similarity))
        return similar

    def _detect_type3_clones(
        self,
        fragments: List[CodeFragment],
        type1_groups: List[CloneGroup],
        type2_groups: List[CloneGroup],
    ) -> List[CloneGroup]:
        """
        Detect Type 3 (near-miss) clones using fuzzy matching.

        Args:
            fragments: All code fragments
            type1_groups: Previously detected Type 1 clone groups
            type2_groups: Previously detected Type 2 clone groups

        Returns:
            List of CloneGroup objects for Type 3 clones
        """
        existing_fragments = self._collect_existing_fragments(
            type1_groups + type2_groups
        )

        unclassified = [
            f
            for f in fragments
            if (f.file_path, f.start_line, f.end_line) not in existing_fragments
        ]

        clone_groups: List[CloneGroup] = []
        processed: Set[Tuple[str, int, int]] = set()

        for i, frag1 in enumerate(unclassified):
            if (frag1.file_path, frag1.start_line, frag1.end_line) in processed:
                continue

            similar_fragments = self._find_similar_fragments(
                frag1, unclassified, i, processed
            )

            if similar_fragments:
                group = self._create_type3_clone_group(frag1, similar_fragments)
                clone_groups.append(group)

                processed.add((frag1.file_path, frag1.start_line, frag1.end_line))
                for frag, _ in similar_fragments:
                    processed.add((frag.file_path, frag.start_line, frag.end_line))

        return clone_groups

    def _detect_type4_clones(
        self,
        fragments: List[CodeFragment],
        type1_groups: List[CloneGroup],
        type2_groups: List[CloneGroup],
        type3_groups: List[CloneGroup],
    ) -> List[CloneGroup]:
        """
        Detect Type 4 (semantic) clones.

        Args:
            fragments: All code fragments
            type1_groups: Previously detected Type 1 clone groups
            type2_groups: Previously detected Type 2 clone groups
            type3_groups: Previously detected Type 3 clone groups

        Returns:
            List of CloneGroup objects for Type 4 clones
        """
        existing_fragments = self._collect_existing_fragments(
            type1_groups + type2_groups + type3_groups
        )

        clone_groups: List[CloneGroup] = []
        for hash_value, fingerprints in self._semantic_fingerprints.items():
            group = self._maybe_create_type4_group(
                hash_value, fingerprints, existing_fragments
            )
            if group:
                clone_groups.append(group)
        return clone_groups

    def _collect_existing_fragments(
        self, groups: List[CloneGroup]
    ) -> Set[Tuple[str, int, int]]:
        """
        Collect fragment identifiers from existing groups.

        Args:
            groups: List of clone groups

        Returns:
            Set of (file_path, start_line, end_line) tuples
        """
        existing: Set[Tuple[str, int, int]] = set()
        for group in groups:
            for instance in group.instances:
                existing.add(
                    (
                        instance.fragment.file_path,
                        instance.fragment.start_line,
                        instance.fragment.end_line,
                    )
                )
        return existing

    def _maybe_create_type4_group(
        self,
        hash_value: str,
        fingerprints: List,
        existing_fragments: Set[Tuple[str, int, int]],
    ) -> Optional[CloneGroup]:
        """
        Create a Type 4 clone group if valid.

        Args:
            hash_value: Semantic hash value
            fingerprints: List of fingerprints with same semantic hash
            existing_fragments: Set of already classified fragments

        Returns:
            CloneGroup if valid Type 4 group, None otherwise
        """
        if len(fingerprints) < 2:
            return None
        if self._should_skip_type4_group(fingerprints, existing_fragments):
            return None

        instances = [
            CloneInstance(
                fragment=fp.fragment,
                fingerprint=fp,
                similarity_score=0.8,  # Semantic similarity placeholder
            )
            for fp in fingerprints
        ]
        total_lines = sum(i.fragment.line_count for i in instances)
        severity = self._calculate_severity(len(instances), total_lines)

        return CloneGroup(
            clone_type=CloneType.TYPE_4,
            severity=severity,
            instances=instances,
            canonical_fingerprint=hash_value,
            similarity_range=(0.6, 0.9),
            total_duplicated_lines=total_lines,
        )

    def _should_skip_type4_group(
        self, fingerprints: List, existing_fragments: Set[Tuple[str, int, int]]
    ) -> bool:
        """
        Check if this semantic group should be skipped.

        Args:
            fingerprints: List of fingerprints
            existing_fragments: Set of already classified fragments

        Returns:
            True if group should be skipped, False otherwise
        """
        # Check if all are from same structural group
        structural_hashes = {
            self.ast_hasher.hash_structural(fp.fragment.ast_node)
            for fp in fingerprints
            if fp.fragment.ast_node
        }
        if len(structural_hashes) == 1:
            return True  # Already caught by structural detection

        # Check if all fragments are already classified
        return all(
            (fp.fragment.file_path, fp.fragment.start_line, fp.fragment.end_line)
            in existing_fragments
            for fp in fingerprints
        )

    def _calculate_severity(
        self, instance_count: int, total_lines: int
    ) -> CloneSeverity:
        """
        Calculate severity based on clone metrics.

        Args:
            instance_count: Number of clone instances
            total_lines: Total duplicated lines across all instances

        Returns:
            CloneSeverity level
        """
        if instance_count >= 7 or total_lines >= 200:
            return CloneSeverity.CRITICAL
        if instance_count >= 5 or total_lines >= 100:
            return CloneSeverity.HIGH
        if instance_count >= 3 or total_lines >= 50:
            return CloneSeverity.MEDIUM
        if instance_count >= 2:
            return CloneSeverity.LOW
        return CloneSeverity.INFO

    def _calculate_type_distribution(self, groups: List[CloneGroup]) -> Dict[str, int]:
        """
        Calculate distribution of clone types.

        Args:
            groups: List of clone groups

        Returns:
            Dictionary mapping clone type to count
        """
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.clone_type.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _calculate_severity_distribution(
        self, groups: List[CloneGroup]
    ) -> Dict[str, int]:
        """
        Calculate distribution of severities.

        Args:
            groups: List of clone groups

        Returns:
            Dictionary mapping severity level to count
        """
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _find_top_cloned_files(
        self, groups: List[CloneGroup], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find files with the most clones.

        Args:
            groups: List of clone groups
            top_n: Number of top files to return

        Returns:
            List of dictionaries with file statistics
        """
        file_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"clone_count": 0, "duplicated_lines": 0}
        )

        for group in groups:
            for instance in group.instances:
                file_path = instance.fragment.file_path
                file_stats[file_path]["clone_count"] += 1
                file_stats[file_path][
                    "duplicated_lines"
                ] += instance.fragment.line_count

        # Sort by clone count
        sorted_files = sorted(
            file_stats.items(),
            key=lambda x: (x[1]["clone_count"], x[1]["duplicated_lines"]),
            reverse=True,
        )[:top_n]

        return [
            {
                "file_path": path,
                "clone_count": stats["clone_count"],
                "duplicated_lines": stats["duplicated_lines"],
            }
            for path, stats in sorted_files
        ]

    def _prioritize_refactoring(
        self, groups: List[CloneGroup], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Prioritize clone groups for refactoring.

        Args:
            groups: List of clone groups
            top_n: Number of top priorities to return

        Returns:
            List of dictionaries with refactoring priorities
        """
        # Score based on severity, instance count, and total lines
        scored_groups = []
        for group in groups:
            severity_scores = {
                CloneSeverity.CRITICAL: 100,
                CloneSeverity.HIGH: 75,
                CloneSeverity.MEDIUM: 50,
                CloneSeverity.LOW: 25,
                CloneSeverity.INFO: 10,
            }
            score = (
                severity_scores[group.severity]
                + len(group.instances) * 10
                + group.total_duplicated_lines
            )
            scored_groups.append((group, score))

        # Sort by score (descending)
        sorted_groups = sorted(scored_groups, key=lambda x: x[1], reverse=True)[:top_n]

        return [
            {
                "clone_type": group.clone_type.value,
                "severity": group.severity.value,
                "instance_count": len(group.instances),
                "total_duplicated_lines": group.total_duplicated_lines,
                "priority_score": score,
                "refactoring_suggestion": group.refactoring_suggestion,
                "estimated_effort": group.estimated_effort,
                "files_affected": list(
                    set(i.fragment.file_path for i in group.instances)
                ),
            }
            for group, score in sorted_groups
        ]

    # Suggestion templates for each clone type
    _REFACTORING_TEMPLATES = {
        CloneType.TYPE_1: (
            "Extract duplicated {fragment_type} into a shared utility function "
            "or module. All {count} copies are identical and can be "
            "replaced with a single implementation."
        ),
        CloneType.TYPE_2: (
            "The {count} {fragment_type} copies differ only in variable "
            "names. Create a parameterized function or use generics to eliminate "
            "duplication while preserving the different naming contexts."
        ),
        CloneType.TYPE_3: (
            "These {count} similar {fragment_type}s share significant "
            "logic. Consider extracting common parts into a base function, "
            "then use composition or inheritance for variations."
        ),
        CloneType.TYPE_4: (
            "These {count} {fragment_type}s achieve the same result "
            "differently. Evaluate which implementation is best and consolidate, "
            "or document why different approaches are needed."
        ),
    }

    def _generate_refactoring_suggestion(self, group: CloneGroup) -> str:
        """
        Generate a refactoring suggestion for a clone group.

        Args:
            group: CloneGroup to generate suggestion for

        Returns:
            Human-readable refactoring suggestion
        """
        template = self._REFACTORING_TEMPLATES.get(group.clone_type)
        if not template:
            return "Review and consider consolidating duplicated code."

        fragment_type = (
            group.instances[0].fragment.fragment_type if group.instances else "code"
        )
        return template.format(count=len(group.instances), fragment_type=fragment_type)

    def _estimate_refactoring_effort(self, group: CloneGroup) -> str:
        """
        Estimate the effort required to refactor a clone group.

        Args:
            group: CloneGroup to estimate effort for

        Returns:
            Effort estimation string
        """
        total_lines = group.total_duplicated_lines
        instance_count = len(group.instances)
        files_affected = len(set(i.fragment.file_path for i in group.instances))

        # Simple effort estimation based on metrics
        if total_lines < 50 and files_affected <= 2:
            effort = "Low (< 1 hour)"
        elif total_lines < 150 and files_affected <= 5:
            effort = "Medium (1-4 hours)"
        elif total_lines < 300 or files_affected <= 10:
            effort = "High (4-8 hours)"
        else:
            effort = "Very High (> 8 hours)"

        return f"{effort} - {instance_count} instances across {files_affected} files"
