# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Similarity Calculator Module

Calculates similarity between code fragments using multiple metrics:
- Jaccard similarity for sets
- Longest Common Subsequence for sequences
- Structural similarity for AST features

Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
import re
from typing import List, Set

from src.code_intelligence.fingerprinting.types import CodeFragment


class SimilarityCalculator:
    """
    Calculates similarity between code fragments.

    Uses multiple metrics:
    - Jaccard similarity for sets
    - Levenshtein distance for sequences
    - Structural similarity for AST features
    """

    def __init__(self):
        """Initialize similarity calculator with AST hasher for comparisons."""
        from src.code_intelligence.fingerprinting.ast_hasher import ASTHasher

        self.ast_hasher = ASTHasher()

    def calculate_similarity(
        self,
        fragment1: CodeFragment,
        fragment2: CodeFragment,
    ) -> float:
        """
        Calculate overall similarity between two code fragments.

        Returns a score between 0.0 (no similarity) and 1.0 (identical).
        """
        if fragment1.ast_node is None or fragment2.ast_node is None:
            # Fall back to text-based similarity
            return self._text_similarity(
                fragment1.source_code, fragment2.source_code
            )

        # Calculate multiple similarity metrics
        structural_sim = self._structural_similarity(
            fragment1.ast_node, fragment2.ast_node
        )
        token_sim = self._token_similarity(
            fragment1.source_code, fragment2.source_code
        )
        feature_sim = self._feature_similarity(
            fragment1.ast_node, fragment2.ast_node
        )

        # Weighted average
        weights = {"structural": 0.5, "token": 0.3, "feature": 0.2}
        similarity = (
            weights["structural"] * structural_sim
            + weights["token"] * token_sim
            + weights["feature"] * feature_sim
        )

        return min(1.0, max(0.0, similarity))

    def _structural_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Calculate similarity based on AST structure.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score between 0.0 and 1.0
        """
        features1 = self.ast_hasher.extract_features(node1)
        features2 = self.ast_hasher.extract_features(node2)

        # Compare node counts
        node_count_sim = 1.0 - abs(
            features1["node_count"] - features2["node_count"]
        ) / max(features1["node_count"], features2["node_count"], 1)

        # Compare node type sets
        types1 = set(features1["node_types"])
        types2 = set(features2["node_types"])
        node_type_sim = self._jaccard_similarity(types1, types2)

        # Compare operator types
        ops1 = set(features1["operator_types"])
        ops2 = set(features2["operator_types"])
        op_sim = self._jaccard_similarity(ops1, ops2) if ops1 or ops2 else 1.0

        return (node_count_sim + node_type_sim + op_sim) / 3

    def _token_similarity(self, code1: str, code2: str) -> float:
        """
        Calculate similarity based on token sequences.

        Args:
            code1: First code string
            code2: Second code string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        tokens1 = self._tokenize(code1)
        tokens2 = self._tokenize(code2)

        if not tokens1 or not tokens2:
            return 0.0

        # Use longest common subsequence ratio
        lcs_length = self._lcs_length(tokens1, tokens2)
        max_length = max(len(tokens1), len(tokens2))

        return lcs_length / max_length if max_length > 0 else 0.0

    def _feature_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Calculate similarity based on extracted features.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score between 0.0 and 1.0
        """
        features1 = self.ast_hasher.extract_features(node1)
        features2 = self.ast_hasher.extract_features(node2)

        # Compare numeric features
        numeric_keys = [
            "node_count",
            "depth",
            "statement_count",
            "expression_count",
            "control_flow_count",
            "loop_count",
            "function_call_count",
            "assignment_count",
        ]

        similarities = []
        for key in numeric_keys:
            val1 = features1.get(key, 0)
            val2 = features2.get(key, 0)
            max_val = max(val1, val2, 1)
            similarities.append(1.0 - abs(val1 - val2) / max_val)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text-based similarity as fallback.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Normalize whitespace and compare
        normalized1 = " ".join(text1.split())
        normalized2 = " ".join(text2.split())

        if normalized1 == normalized2:
            return 1.0

        # Use character-level LCS
        lcs_length = self._lcs_length(list(normalized1), list(normalized2))
        max_length = max(len(normalized1), len(normalized2))

        return lcs_length / max_length if max_length > 0 else 0.0

    def _tokenize(self, code: str) -> List[str]:
        """
        Tokenize code into meaningful tokens.

        Args:
            code: Source code string

        Returns:
            List of tokens
        """
        # Simple tokenization - split on whitespace and punctuation
        tokens = re.findall(r"[a-zA-Z_]\w*|\d+|[^\s\w]", code)
        return tokens

    def _jaccard_similarity(self, set1: Set, set2: Set) -> float:
        """
        Calculate Jaccard similarity between two sets.

        Args:
            set1: First set
            set2: Second set

        Returns:
            Jaccard similarity coefficient between 0.0 and 1.0
        """
        if not set1 and not set2:
            return 1.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _lcs_length(self, seq1: List, seq2: List) -> int:
        """
        Calculate length of longest common subsequence.

        Args:
            seq1: First sequence
            seq2: Second sequence

        Returns:
            Length of longest common subsequence
        """
        m, n = len(seq1), len(seq2)
        if m == 0 or n == 0:
            return 0

        # Use space-optimized LCS
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i - 1] == seq2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev

        return prev[n]
