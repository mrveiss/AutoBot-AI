# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Query Processor for Knowledge Base Search

Issue #381: Extracted from search.py god class refactoring.
Contains query preprocessing and expansion functionality.
"""

import logging
import re
import threading
from typing import List

logger = logging.getLogger(__name__)


class QueryProcessor:
    """
    Handles query preprocessing and expansion for search.

    Features:
    - Whitespace normalization
    - Abbreviation expansion
    - Quoted phrase preservation
    - Query expansion with synonyms (Issue #78)
    """

    # Common abbreviations expansion (security/sysadmin context)
    ABBREVIATIONS = {
        r"\bdir\b": "directory",
        r"\bcmd\b": "command",
        r"\bpwd\b": "password",
        r"\bauth\b": "authentication",
        r"\bperm\b": "permission",
        r"\bperms\b": "permissions",
        r"\bconfig\b": "configuration",
        r"\benv\b": "environment",
        r"\bvar\b": "variable",
        r"\bvars\b": "variables",
        r"\bproc\b": "process",
        r"\bsvc\b": "service",
        r"\bpkg\b": "package",
        r"\brepo\b": "repository",
        r"\binfo\b": "information",
        r"\bdoc\b": "documentation",
        r"\bdocs\b": "documentation",
    }

    def preprocess_query(self, query: str) -> str:
        """
        Preprocess search query for better results.

        Issue #78: Query preprocessing for search quality.

        Preprocessing steps:
        1. Normalize whitespace
        2. Remove redundant punctuation
        3. Expand common abbreviations
        4. Preserve quoted phrases

        Args:
            query: Raw user query

        Returns:
            Preprocessed query string
        """
        # Normalize whitespace
        processed = " ".join(query.split())

        # Only expand if not in quotes
        if '"' not in processed and "'" not in processed:
            for abbr, expansion in self.ABBREVIATIONS.items():
                processed = re.sub(abbr, expansion, processed, flags=re.IGNORECASE)

        return processed.strip()

    def expand_query_terms(self, query: str, enable_expansion: bool) -> List[str]:
        """
        Expand query with synonyms and related terms.

        Issue #281: Extracted from enhanced_search_v2 for clarity.

        Args:
            query: Processed query string
            enable_expansion: Whether to enable query expansion

        Returns:
            List of query variations to search
        """
        if not enable_expansion:
            return [query]

        from src.knowledge.search_quality import get_query_expander

        expander = get_query_expander()
        queries = expander.expand_query(query)
        logger.debug("Query expansion: %d variations", len(queries))
        return queries


# Module-level instance for convenience (thread-safe, Issue #613)
_query_processor = None
_query_processor_lock = threading.Lock()


def get_query_processor() -> QueryProcessor:
    """Get the shared QueryProcessor instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _query_processor
    if _query_processor is None:
        with _query_processor_lock:
            # Double-check after acquiring lock
            if _query_processor is None:
                _query_processor = QueryProcessor()
    return _query_processor
