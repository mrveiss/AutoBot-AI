# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Static request/response examples served by ``GET /api/code-search/examples`` (Issue #281).

Split out of ``api/code_search.py`` (#16375) so that router stays under its size ceiling.
"""

# Issue #281: Search examples extracted from get_search_examples for reuse
SEARCH_EXAMPLES_DATA = {
    "examples": {
        "semantic_search": {
            "description": "AI-powered semantic similarity search",
            "examples": [
                {
                    "query": "authentication middleware",
                    "type": "semantic",
                    "use_case": "Find code related to authentication, even if exact terms don't match",
                },
                {
                    "query": "database connection pool",
                    "type": "semantic",
                    "use_case": "Find database connectivity code across different implementations",
                },
            ],
        },
        "exact_search": {
            "description": "Find exact string matches",
            "examples": [
                {
                    "query": "def authenticate",
                    "type": "exact",
                    "use_case": "Find exact function definitions",
                },
                {
                    "query": "import redis",
                    "type": "exact",
                    "use_case": "Find specific imports",
                },
            ],
        },
        "regex_search": {
            "description": "Pattern-based search using regular expressions",
            "examples": [
                {
                    "query": "def\\s+\\w+_test\\s*\\(",
                    "type": "regex",
                    "use_case": "Find all test functions",
                },
                {
                    "query": "class\\s+\\w+Exception",
                    "type": "regex",
                    "use_case": "Find exception classes",
                },
            ],
        },
        "element_search": {
            "description": "Search for specific code elements by name",
            "examples": [
                {
                    "query": "authenticate",
                    "type": "element",
                    "use_case": "Find functions, classes, or variables named 'authenticate'",
                },
                {
                    "query": "UserModel",
                    "type": "element",
                    "use_case": "Find specific class definitions",
                },
            ],
        },
    },
    "language_filters": (
        "python",
        "javascript",
        "typescript",
        "java",
        "cpp",
        "c",
        "csharp",
        "ruby",
        "go",
        "rust",
        "php",
        "swift",
        "kotlin",
        "scala",
        "bash",
        "yaml",
        "json",
        "html",
        "css",
        "sql",
        "markdown",
    ),
    "usage_tips": (
        "Use semantic search for concept-based queries",
        "Use exact search for finding specific code patterns",
        "Use regex search for complex pattern matching",
        "Use element search for finding specific functions/classes by name",
        "Add language filters to narrow down results",
        "Results are cached for performance - clear cache if codebase changes",
    ),
}
