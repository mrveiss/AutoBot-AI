# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Natural Language Code Search (Issue #232)

Enables developers to search the codebase using natural language queries.
Provides query intent classification, LLM-powered explanations, and suggestions.

Features:
- Natural language query understanding
- Query intent classification
- LLM-powered result explanations
- Query suggestion system
- Integration with existing semantic search
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.constants.threshold_constants import QueryDefaults

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for query parsing and code analysis
_NON_WORD_CHARS_RE = re.compile(r"[^\w\s\-_]")
_CAMEL_CASE_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", re.IGNORECASE)
_SNAKE_CASE_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
_QUOTED_STRING_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_FUNC_DEF_RE = re.compile(r"def\s+(\w+)")
_CLASS_DEF_RE = re.compile(r"class\s+(\w+)")
_ASYNC_FUNC_RE = re.compile(r"async\s+def\s+(\w+)")

# Issue #336: Keyword heuristics dispatch table for intent classification
KEYWORD_INTENT_FALLBACKS: Dict[
    Tuple[str, ...], "QueryIntent"
] = {}  # Populated after enum defined

router = APIRouter(prefix="/nl-search", tags=["natural-language-search", "code-search"])


# =============================================================================
# Enums and Data Classes
# =============================================================================


class QueryIntent(str, Enum):
    """Classified intent of a natural language query."""

    FIND_DEFINITION = "find_definition"  # "Where is X defined?"
    FIND_USAGE = "find_usage"  # "Where is X used?"
    FIND_IMPLEMENTATION = "find_implementation"  # "How is X implemented?"
    FIND_ERROR_HANDLING = "find_error_handling"  # "How are errors handled in X?"
    FIND_CONFIGURATION = "find_configuration"  # "Where is X configured?"
    FIND_TESTS = "find_tests"  # "What tests exist for X?"
    FIND_DEPENDENCIES = "find_dependencies"  # "What does X depend on?"
    FIND_PATTERN = "find_pattern"  # "Find all X patterns"
    EXPLAIN_CODE = "explain_code"  # "Explain how X works"
    COMPARE_CODE = "compare_code"  # "Compare X and Y"
    GENERAL_SEARCH = "general_search"  # General/ambiguous query


class QueryDomain(str, Enum):
    """Domain/topic area of the query."""

    AUTHENTICATION = "authentication"
    DATABASE = "database"
    API = "api"
    FRONTEND = "frontend"
    BACKEND = "backend"
    TESTING = "testing"
    CONFIGURATION = "configuration"
    LOGGING = "logging"
    CACHING = "caching"
    SECURITY = "security"
    NETWORKING = "networking"
    FILE_IO = "file_io"
    GENERAL = "general"


@dataclass
class ParsedQuery:
    """Parsed natural language query with extracted entities."""

    original_query: str
    normalized_query: str
    intent: QueryIntent
    domain: QueryDomain
    entities: List[str]  # Extracted code entities (function names, classes, etc.)
    keywords: List[str]  # Important keywords
    search_terms: List[str]  # Optimized search terms
    confidence: float  # Confidence in parsing
    question_type: str  # "what", "where", "how", "why", etc.


@dataclass
class CodeExplanation:
    """LLM-generated explanation for code."""

    code_snippet: str
    file_path: str
    line_number: int
    summary: str  # One-line summary
    detailed_explanation: str  # Full explanation
    purpose: str  # What the code does
    key_concepts: List[str]  # Important concepts used
    related_code: List[str]  # Related files/functions


@dataclass
class SearchSuggestion:
    """Suggested related or refined query."""

    suggestion: str
    reason: str
    intent: QueryIntent
    relevance_score: float


# =============================================================================
# Intent Classification Patterns
# =============================================================================

# Patterns for query intent classification
INTENT_PATTERNS = {
    QueryIntent.FIND_DEFINITION: [
        r"where\s+is\s+(\w+)\s+defined",
        r"where\s+do\s+we\s+define",
        r"show\s+me\s+the\s+definition\s+of",
        r"find\s+the\s+definition",
        r"what\s+is\s+the\s+definition",
        r"where\s+is\s+(\w+)\s+declared",
    ],
    QueryIntent.FIND_USAGE: [
        r"where\s+is\s+(\w+)\s+used",
        r"where\s+do\s+we\s+use",
        r"find\s+all\s+usages?\s+of",
        r"show\s+me\s+where\s+(\w+)\s+is\s+called",
        r"who\s+calls\s+(\w+)",
        r"what\s+uses\s+(\w+)",
    ],
    QueryIntent.FIND_IMPLEMENTATION: [
        r"how\s+is\s+(\w+)\s+implemented",
        r"show\s+me\s+the\s+implementation",
        r"how\s+does\s+(\w+)\s+work",
        r"what\s+is\s+the\s+logic\s+for",
        r"show\s+me\s+how\s+(\w+)\s+works",
    ],
    QueryIntent.FIND_ERROR_HANDLING: [
        r"how\s+are\s+errors?\s+handled",
        r"error\s+handling\s+for",
        r"exception\s+handling",
        r"what\s+happens\s+when\s+(\w+)\s+fails",
        r"how\s+do\s+we\s+handle\s+(\w+)\s+errors",
    ],
    QueryIntent.FIND_CONFIGURATION: [
        r"where\s+is\s+(\w+)\s+configured",
        r"configuration\s+for",
        r"settings?\s+for",
        r"how\s+is\s+(\w+)\s+set\s+up",
        r"environment\s+variables?\s+for",
    ],
    QueryIntent.FIND_TESTS: [
        r"tests?\s+for\s+(\w+)",
        r"test\s+cases?\s+for",
        r"how\s+is\s+(\w+)\s+tested",
        r"unit\s+tests?\s+for",
        r"testing\s+(\w+)",
    ],
    QueryIntent.FIND_DEPENDENCIES: [
        r"what\s+does\s+(\w+)\s+depend\s+on",
        r"dependencies\s+of",
        r"imports?\s+in\s+(\w+)",
        r"what\s+modules?\s+does\s+(\w+)\s+use",
    ],
    QueryIntent.FIND_PATTERN: [
        r"find\s+all\s+(\w+)\s+patterns?",
        r"show\s+me\s+all\s+(\w+)",
        r"list\s+all\s+(\w+)",
        r"where\s+do\s+we\s+have\s+(\w+)",
    ],
    QueryIntent.EXPLAIN_CODE: [
        r"explain\s+(\w+)",
        r"what\s+does\s+(\w+)\s+do",
        r"purpose\s+of\s+(\w+)",
        r"why\s+do\s+we\s+have\s+(\w+)",
    ],
    QueryIntent.COMPARE_CODE: [
        r"compare\s+(\w+)\s+and\s+(\w+)",
        r"difference\s+between\s+(\w+)\s+and",
        r"(\w+)\s+vs\s+(\w+)",
    ],
}

# Domain keyword mappings
DOMAIN_KEYWORDS = {
    QueryDomain.AUTHENTICATION: [
        "auth",
        "login",
        "logout",
        "password",
        "token",
        "jwt",
        "session",
        "user",
        "permission",
        "role",
    ],
    QueryDomain.DATABASE: [
        "database",
        "db",
        "sql",
        "query",
        "redis",
        "mongo",
        "postgres",
        "mysql",
        "orm",
        "model",
    ],
    QueryDomain.API: [
        "api",
        "endpoint",
        "route",
        "rest",
        "request",
        "response",
        "http",
        "get",
        "post",
        "put",
        "delete",
    ],
    QueryDomain.FRONTEND: [
        "frontend",
        "vue",
        "react",
        "component",
        "ui",
        "css",
        "html",
        "template",
        "style",
    ],
    QueryDomain.BACKEND: [
        "backend",
        "server",
        "fastapi",
        "flask",
        "django",
        "service",
        "handler",
    ],
    QueryDomain.TESTING: [
        "test",
        "unittest",
        "pytest",
        "mock",
        "fixture",
        "assert",
        "coverage",
    ],
    QueryDomain.CONFIGURATION: [
        "config",
        "settings",
        "environment",
        "env",
        "yaml",
        "json",
        "toml",
    ],
    QueryDomain.LOGGING: [
        "log",
        "logger",
        "logging",
        "debug",
        "info",
        "warning",
        "error",
    ],
    QueryDomain.CACHING: ["cache", "redis", "memcached", "ttl", "invalidate", "expire"],
    QueryDomain.SECURITY: [
        "security",
        "encryption",
        "decrypt",
        "hash",
        "salt",
        "secure",
        "vulnerability",
    ],
    QueryDomain.NETWORKING: [
        "network",
        "socket",
        "websocket",
        "tcp",
        "udp",
        "connection",
        "port",
    ],
    QueryDomain.FILE_IO: [
        "file",
        "read",
        "write",
        "open",
        "close",
        "path",
        "directory",
        "io",
    ],
}

# Question type indicators
QUESTION_TYPES = {
    "what": ["what", "which"],
    "where": ["where"],
    "how": ["how"],
    "why": ["why"],
    "when": ["when"],
    "who": ["who"],
    "show": ["show", "display", "list", "find", "get"],
}

# Issue #336: Keyword heuristics dispatch table for intent classification fallback
# Maps (keyword1, keyword2, ...) tuples to QueryIntent
KEYWORD_INTENT_FALLBACKS = {
    ("define", "declaration"): QueryIntent.FIND_DEFINITION,
    ("use", "call"): QueryIntent.FIND_USAGE,
    ("implement", "work"): QueryIntent.FIND_IMPLEMENTATION,
    ("error", "exception"): QueryIntent.FIND_ERROR_HANDLING,
    ("test",): QueryIntent.FIND_TESTS,
    ("config", "setting"): QueryIntent.FIND_CONFIGURATION,
}


def _match_keyword_fallback(query: str) -> Tuple[QueryIntent, float]:
    """Match query against keyword fallback patterns (Issue #336 - extracted helper)."""
    for keywords, intent in KEYWORD_INTENT_FALLBACKS.items():
        if any(kw in query for kw in keywords):
            return intent, 0.6
    return QueryIntent.GENERAL_SEARCH, 0.5


# Issue #336: Intent-based query generator dispatch table
INTENT_QUERY_TEMPLATES: Dict[QueryIntent, str] = {
    QueryIntent.FIND_USAGE: "Where is {} used?",
    QueryIntent.FIND_DEFINITION: "Where is {} defined?",
    QueryIntent.FIND_TESTS: "What tests exist for {}?",
    QueryIntent.FIND_IMPLEMENTATION: "How is {} implemented?",
    QueryIntent.FIND_ERROR_HANDLING: "How are errors handled in {}?",
}


def _generate_intent_query(intent: QueryIntent, entity: str) -> Optional[str]:
    """Generate query for intent using dispatch table (Issue #336 - extracted helper)."""
    template = INTENT_QUERY_TEMPLATES.get(intent)
    if template:
        return template.format(entity)
    return None


async def _add_explanation_to_result(
    result_dict: Dict[str, Any], code_explainer: "CodeExplainer"
) -> None:
    """Add LLM explanation to search result (Issue #315 - extracted)."""
    try:
        explanation = await code_explainer.explain_code(
            result_dict["content"],
            result_dict["file_path"],
            result_dict["line_number"],
        )
        result_dict["summary"] = explanation.summary
        result_dict["explanation"] = explanation.detailed_explanation
        result_dict["key_concepts"] = explanation.key_concepts
    except Exception as e:
        logger.warning("Explanation generation failed: %s", e)


# =============================================================================
# Query Parser
# =============================================================================


class NaturalLanguageQueryParser:
    """Parses natural language queries into structured search parameters."""

    def __init__(self):
        """Initialize parser with stopwords and pattern matchers."""
        self.stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "also",
        }

    def parse(self, query: str) -> ParsedQuery:
        """Parse a natural language query into structured components."""
        original = query
        normalized = self._normalize_query(query)

        # Classify intent
        intent, intent_confidence = self._classify_intent(normalized)

        # Detect domain
        domain = self._detect_domain(normalized)

        # Extract entities (potential code identifiers)
        entities = self._extract_entities(normalized)

        # Extract keywords
        keywords = self._extract_keywords(normalized)

        # Determine question type
        question_type = self._determine_question_type(normalized)

        # Generate optimized search terms
        search_terms = self._generate_search_terms(
            normalized, entities, keywords, intent
        )

        return ParsedQuery(
            original_query=original,
            normalized_query=normalized,
            intent=intent,
            domain=domain,
            entities=entities,
            keywords=keywords,
            search_terms=search_terms,
            confidence=intent_confidence,
            question_type=question_type,
        )

    def _normalize_query(self, query: str) -> str:
        """Normalize query for processing."""
        # Lowercase
        query = query.lower()
        # Remove extra whitespace
        query = " ".join(query.split())
        # Remove punctuation except hyphens and underscores
        query = _NON_WORD_CHARS_RE.sub(" ", query)
        return query.strip()

    def _classify_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """Classify the intent of the query."""
        best_intent = QueryIntent.GENERAL_SEARCH
        best_confidence = 0.0

        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    # Found a match
                    confidence = 0.8 + (0.1 if len(pattern) > 20 else 0)
                    if confidence > best_confidence:
                        best_intent = intent
                        best_confidence = confidence

        # Issue #336: Use dispatch table for keyword heuristics fallback
        if best_confidence < 0.5:
            return _match_keyword_fallback(query)

        return best_intent, best_confidence

    def _detect_domain(self, query: str) -> QueryDomain:
        """Detect the domain/topic of the query."""
        domain_scores = {}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query)
            if score > 0:
                domain_scores[domain] = score

        if domain_scores:
            return max(domain_scores, key=domain_scores.get)
        return QueryDomain.GENERAL

    def _extract_entities(self, query: str) -> List[str]:
        """Extract potential code entities (function names, classes, etc.)."""
        entities = []

        # Look for CamelCase words
        camel_case = _CAMEL_CASE_RE.findall(query)
        entities.extend(camel_case)

        # Look for snake_case words
        snake_case = _SNAKE_CASE_RE.findall(query)
        entities.extend(snake_case)

        # Look for quoted strings
        quoted = _QUOTED_STRING_RE.findall(query)
        for match in quoted:
            entities.extend([m for m in match if m])

        return list(set(entities))

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from the query."""
        words = query.split()
        keywords = [
            w
            for w in words
            if w not in self.stopwords and len(w) > 2 and not w.isdigit()
        ]
        return keywords

    def _determine_question_type(self, query: str) -> str:
        """Determine the type of question."""
        words = query.split()
        if words:
            first_word = words[0]
            for qtype, indicators in QUESTION_TYPES.items():
                if first_word in indicators:
                    return qtype
        return "general"

    # Issue #315: Intent to keywords dispatch table
    _INTENT_KEYWORDS = {
        QueryIntent.FIND_DEFINITION: ["def", "class", "function", "define"],
        QueryIntent.FIND_ERROR_HANDLING: [
            "try",
            "except",
            "catch",
            "error",
            "exception",
        ],
        QueryIntent.FIND_TESTS: ["test", "assert", "pytest", "unittest"],
        QueryIntent.FIND_CONFIGURATION: ["config", "settings", "env", "yaml"],
    }

    def _generate_search_terms(
        self,
        query: str,
        entities: List[str],
        keywords: List[str],
        intent: QueryIntent,
    ) -> List[str]:
        """Generate optimized search terms for the search engine."""
        terms = list(entities)  # Start with entities (most specific)

        # Add domain-specific keywords based on intent (Issue #315 - use dispatch table)
        intent_keywords = self._INTENT_KEYWORDS.get(intent)
        if intent_keywords:
            terms.extend(intent_keywords)
        elif intent == QueryIntent.FIND_USAGE:
            terms.extend(keywords)

        # Add remaining keywords not already in terms
        terms.extend(kw for kw in keywords if kw not in terms)

        return terms[:10]  # Limit to 10 most relevant terms


# =============================================================================
# Query Suggestion Generator
# =============================================================================


class QuerySuggestionGenerator:
    """Generates related and refined query suggestions."""

    def __init__(self):
        """Initialize suggestion generator with query parser."""
        self.parser = NaturalLanguageQueryParser()

    def generate_suggestions(
        self, parsed_query: ParsedQuery, search_results: List[Any]
    ) -> List[SearchSuggestion]:
        """Generate query suggestions based on parsed query and results."""
        suggestions = []

        # 1. Intent-based suggestions
        suggestions.extend(self._intent_based_suggestions(parsed_query))

        # 2. Entity-based suggestions
        suggestions.extend(self._entity_based_suggestions(parsed_query))

        # 3. Domain-based suggestions
        suggestions.extend(self._domain_based_suggestions(parsed_query))

        # 4. Refinement suggestions if few results
        if len(search_results) < 3:
            suggestions.extend(self._refinement_suggestions(parsed_query))

        # Sort by relevance and deduplicate
        seen = set()
        unique_suggestions = []
        for s in sorted(suggestions, key=lambda x: x.relevance_score, reverse=True):
            if s.suggestion not in seen:
                seen.add(s.suggestion)
                unique_suggestions.append(s)

        return unique_suggestions[:5]  # Return top 5

    def _intent_based_suggestions(self, parsed: ParsedQuery) -> List[SearchSuggestion]:
        """Generate suggestions based on query intent."""
        suggestions = []

        # Suggest related intents
        intent_relations = {
            QueryIntent.FIND_DEFINITION: [
                (QueryIntent.FIND_USAGE, "Also find where it's used"),
                (QueryIntent.FIND_TESTS, "Find tests for this"),
            ],
            QueryIntent.FIND_USAGE: [
                (QueryIntent.FIND_DEFINITION, "Find the definition"),
                (QueryIntent.FIND_IMPLEMENTATION, "See how it's implemented"),
            ],
            QueryIntent.FIND_IMPLEMENTATION: [
                (QueryIntent.FIND_TESTS, "Find related tests"),
                (QueryIntent.FIND_ERROR_HANDLING, "Check error handling"),
            ],
            QueryIntent.FIND_ERROR_HANDLING: [
                (QueryIntent.FIND_TESTS, "Find error test cases"),
            ],
        }

        if parsed.intent in intent_relations:
            for related_intent, reason in intent_relations[parsed.intent]:
                # Issue #336: Use dispatch table for query generation
                if parsed.entities:
                    entity = parsed.entities[0]
                    query = _generate_intent_query(related_intent, entity)
                    if query is None:
                        continue

                    suggestions.append(
                        SearchSuggestion(
                            suggestion=query,
                            reason=reason,
                            intent=related_intent,
                            relevance_score=0.7,
                        )
                    )

        return suggestions

    def _entity_based_suggestions(self, parsed: ParsedQuery) -> List[SearchSuggestion]:
        """Generate suggestions based on extracted entities."""
        suggestions = []

        for entity in parsed.entities[:2]:  # Top 2 entities
            # Suggest finding related entities
            suggestions.append(
                SearchSuggestion(
                    suggestion=f"Find all functions in {entity}",
                    reason=f"Explore {entity} module",
                    intent=QueryIntent.FIND_PATTERN,
                    relevance_score=0.6,
                )
            )

        return suggestions

    def _domain_based_suggestions(self, parsed: ParsedQuery) -> List[SearchSuggestion]:
        """Generate suggestions based on detected domain."""
        suggestions = []

        domain_suggestions = {
            QueryDomain.AUTHENTICATION: [
                ("Find authentication middleware", "Explore auth flow"),
                ("Show login handlers", "See login implementation"),
            ],
            QueryDomain.DATABASE: [
                ("Find database connection setup", "Check DB initialization"),
                ("Show all database models", "Explore data models"),
            ],
            QueryDomain.API: [
                ("List all API endpoints", "Explore available APIs"),
                ("Find request validation", "Check input validation"),
            ],
            QueryDomain.CACHING: [
                ("Find cache invalidation logic", "Explore cache management"),
                ("Show Redis configuration", "Check cache config"),
            ],
        }

        if parsed.domain in domain_suggestions:
            for query, reason in domain_suggestions[parsed.domain]:
                suggestions.append(
                    SearchSuggestion(
                        suggestion=query,
                        reason=reason,
                        intent=QueryIntent.FIND_PATTERN,
                        relevance_score=0.5,
                    )
                )

        return suggestions

    def _refinement_suggestions(self, parsed: ParsedQuery) -> List[SearchSuggestion]:
        """Generate refinement suggestions when results are sparse."""
        suggestions = []

        # Suggest broader search
        if parsed.entities:
            broader_query = " ".join(parsed.keywords[:3])
            suggestions.append(
                SearchSuggestion(
                    suggestion=f"Search for: {broader_query}",
                    reason="Try a broader search",
                    intent=QueryIntent.GENERAL_SEARCH,
                    relevance_score=0.4,
                )
            )

        # Suggest checking different file types
        suggestions.append(
            SearchSuggestion(
                suggestion=f"Find {parsed.keywords[0] if parsed.keywords else 'code'} in Python files",
                reason="Filter by language",
                intent=QueryIntent.FIND_PATTERN,
                relevance_score=0.4,
            )
        )

        return suggestions


# =============================================================================
# Code Explainer
# =============================================================================


def _parse_llm_explanation_response(response: str) -> dict:
    """Parse LLM explanation response into structured dict. (Issue #315 - extracted)"""
    result = {"summary": "", "explanation": "", "purpose": "", "concepts": []}
    # Line prefix to result key mapping
    prefix_map = {
        "SUMMARY:": "summary",
        "EXPLANATION:": "explanation",
        "PURPOSE:": "purpose",
    }
    for line in response.split("\n"):
        for prefix, key in prefix_map.items():
            if line.startswith(prefix):
                result[key] = line.replace(prefix, "").strip()
                break
        if line.startswith("CONCEPTS:"):
            result["concepts"] = [
                c.strip() for c in line.replace("CONCEPTS:", "").split(",")
            ]
    return result


class CodeExplainer:
    """Generates explanations for code snippets."""

    def __init__(self):
        """Initialize code explainer with LLM availability check."""
        self.llm_available = self._check_llm_availability()

    def _check_llm_availability(self) -> bool:
        """Check if LLM is available for explanations."""
        try:
            pass

            return True
        except ImportError:
            return False

    async def explain_code(
        self,
        code_snippet: str,
        file_path: str,
        line_number: int,
        context: str = "",
    ) -> CodeExplanation:
        """Generate explanation for a code snippet."""
        # Try LLM-based explanation first
        if self.llm_available:
            try:
                return await self._llm_explain(
                    code_snippet, file_path, line_number, context
                )
            except Exception as e:
                logger.warning("LLM explanation failed: %s, using heuristic", e)

        # Fall back to heuristic explanation
        return self._heuristic_explain(code_snippet, file_path, line_number)

    async def _llm_explain(
        self,
        code: str,
        file_path: str,
        line_number: int,
        context: str,
    ) -> CodeExplanation:
        """Use LLM to explain code."""
        from src.llm_manager import get_llm_manager

        llm = get_llm_manager()

        prompt = f"""Analyze this code snippet and provide a concise explanation.

File: {file_path}
Line: {line_number}

Code:
```
{code[:1000]}
```

{f'Context: {context}' if context else ''}

Provide:
1. A one-line summary (max 100 chars)
2. A detailed explanation (2-3 sentences)
3. The main purpose
4. Key concepts used (list 3-5)

Format your response as:
SUMMARY: <one-line summary>
EXPLANATION: <detailed explanation>
PURPOSE: <main purpose>
CONCEPTS: <comma-separated list>
"""

        response = await llm.generate(prompt, max_tokens=500)

        # Parse response using extracted helper (Issue #315 - reduced depth)
        parsed = _parse_llm_explanation_response(response)

        return CodeExplanation(
            code_snippet=code[:500],
            file_path=file_path,
            line_number=line_number,
            summary=parsed.get("summary") or "Code snippet",
            detailed_explanation=parsed.get("explanation")
            or "No detailed explanation available",
            purpose=parsed.get("purpose") or "Unknown purpose",
            key_concepts=parsed.get("concepts") or ["code"],
            related_code=[],
        )

    def _heuristic_explain(
        self, code: str, file_path: str, line_number: int
    ) -> CodeExplanation:
        """Generate heuristic explanation without LLM."""
        summary = "Code snippet"
        purpose = "Implementation code"
        concepts = []

        # Analyze code structure
        if "def " in code:
            match = _FUNC_DEF_RE.search(code)
            if match:
                func_name = match.group(1)
                summary = f"Function definition: {func_name}"
                purpose = f"Defines the {func_name} function"
                concepts.append("function")

        elif "class " in code:
            match = _CLASS_DEF_RE.search(code)
            if match:
                class_name = match.group(1)
                summary = f"Class definition: {class_name}"
                purpose = f"Defines the {class_name} class"
                concepts.append("class")

        elif "async def " in code:
            match = _ASYNC_FUNC_RE.search(code)
            if match:
                func_name = match.group(1)
                summary = f"Async function: {func_name}"
                purpose = f"Defines asynchronous function {func_name}"
                concepts.extend(["async", "coroutine"])

        # Detect patterns
        if "try:" in code or "except" in code:
            concepts.append("error handling")
        if "await " in code:
            concepts.append("async/await")
        if "@" in code and "def" in code:
            concepts.append("decorator")
        if "import " in code or "from " in code:
            concepts.append("imports")
        if "return " in code:
            concepts.append("return statement")

        return CodeExplanation(
            code_snippet=code[:500],
            file_path=file_path,
            line_number=line_number,
            summary=summary,
            detailed_explanation=f"This code is located in {file_path} at line {line_number}.",
            purpose=purpose,
            key_concepts=concepts or ["code"],
            related_code=[],
        )


# =============================================================================
# API Models
# =============================================================================


class NLSearchRequest(BaseModel):
    """Request model for natural language search."""

    query: str = Field(..., description="Natural language query")
    max_results: int = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        description="Maximum results to return",
    )
    include_explanations: bool = Field(
        default=True, description="Include LLM-generated explanations"
    )
    language_filter: Optional[str] = Field(
        default=None, description="Filter by programming language"
    )


class ParsedQueryResponse(BaseModel):
    """Response model for parsed query."""

    original_query: str
    normalized_query: str
    intent: str
    domain: str
    entities: List[str]
    keywords: List[str]
    search_terms: List[str]
    confidence: float
    question_type: str


class SearchResultWithExplanation(BaseModel):
    """Search result with optional explanation."""

    file_path: str
    line_number: int
    content: str
    confidence: float
    summary: Optional[str] = None
    explanation: Optional[str] = None
    key_concepts: Optional[List[str]] = None


class NLSearchResponse(BaseModel):
    """Response model for natural language search."""

    query: ParsedQueryResponse
    results: List[SearchResultWithExplanation]
    suggestions: List[Dict[str, Any]]
    total_results: int
    search_time_ms: float


class QuerySuggestionResponse(BaseModel):
    """Response model for query suggestions."""

    suggestions: List[Dict[str, Any]]


# =============================================================================
# API Endpoints
# =============================================================================


# Initialize components
_parser = NaturalLanguageQueryParser()
_suggestion_generator = QuerySuggestionGenerator()
_code_explainer = CodeExplainer()


def _convert_search_result_to_dict(result) -> dict:
    """Convert a search result to dictionary format (Issue #665: extracted helper)."""
    return {
        "file_path": (
            result.file_path
            if hasattr(result, "file_path")
            else str(result.get("file_path", ""))
        ),
        "line_number": (
            result.line_number
            if hasattr(result, "line_number")
            else result.get("line_number", 0)
        ),
        "content": (
            result.content[:500]
            if hasattr(result, "content")
            else str(result.get("content", ""))[:500]
        ),
        "confidence": (
            result.confidence
            if hasattr(result, "confidence")
            else result.get("confidence", 0.0)
        ),
    }


def _build_parsed_query_response(parsed) -> ParsedQueryResponse:
    """Build ParsedQueryResponse from parsed query (Issue #665: extracted helper)."""
    return ParsedQueryResponse(
        original_query=parsed.original_query,
        normalized_query=parsed.normalized_query,
        intent=parsed.intent.value,
        domain=parsed.domain.value,
        entities=parsed.entities,
        keywords=parsed.keywords,
        search_terms=parsed.search_terms,
        confidence=parsed.confidence,
        question_type=parsed.question_type,
    )


def _convert_suggestions_to_dicts(suggestions: list) -> list:
    """Convert suggestion objects to dictionaries (Issue #665: extracted helper)."""
    return [
        {
            "suggestion": s.suggestion,
            "reason": s.reason,
            "intent": s.intent.value,
            "relevance_score": s.relevance_score,
        }
        for s in suggestions
    ]


@router.post("/search", response_model=NLSearchResponse)
async def natural_language_search(request: NLSearchRequest):
    """
    Search codebase using natural language queries.

    Issue #665: Refactored to use extracted helper functions.

    Examples:
    - "Where do we handle user authentication?"
    - "Show me all Redis cache invalidation logic"
    """
    import time

    start_time = time.time()

    try:
        parsed = _parser.parse(request.query)

        # Perform semantic search
        try:
            from backend.api.code_search import search_codebase

            search_results = await search_codebase(
                query=" ".join(parsed.search_terms),
                search_type="semantic",
                language=request.language_filter,
                max_results=request.max_results,
            )
        except ImportError:
            search_results = []

        # Convert results and add explanations
        results_with_explanations = []
        for result in search_results:
            result_dict = _convert_search_result_to_dict(result)
            if request.include_explanations:
                await _add_explanation_to_result(result_dict, _code_explainer)
            results_with_explanations.append(SearchResultWithExplanation(**result_dict))

        suggestions = _suggestion_generator.generate_suggestions(parsed, search_results)
        search_time = (time.time() - start_time) * 1000

        return NLSearchResponse(
            query=_build_parsed_query_response(parsed),
            results=results_with_explanations,
            suggestions=_convert_suggestions_to_dicts(suggestions),
            total_results=len(results_with_explanations),
            search_time_ms=search_time,
        )

    except Exception as e:
        logger.error("Natural language search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse", response_model=ParsedQueryResponse)
async def parse_query(query: str):
    """
    Parse a natural language query without searching.

    Returns the parsed query structure including intent, domain, entities, etc.
    Useful for understanding how queries are interpreted.
    """
    try:
        parsed = _parser.parse(query)
        return ParsedQueryResponse(
            original_query=parsed.original_query,
            normalized_query=parsed.normalized_query,
            intent=parsed.intent.value,
            domain=parsed.domain.value,
            entities=parsed.entities,
            keywords=parsed.keywords,
            search_terms=parsed.search_terms,
            confidence=parsed.confidence,
            question_type=parsed.question_type,
        )
    except Exception as e:
        logger.error("Query parsing error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
async def get_query_suggestions(query: str):
    """
    Get query suggestions for a given query.

    Returns related queries and refinement suggestions.
    """
    try:
        parsed = _parser.parse(query)
        suggestions = _suggestion_generator.generate_suggestions(parsed, [])

        return {
            "original_query": query,
            "parsed_intent": parsed.intent.value,
            "suggestions": [
                {
                    "suggestion": s.suggestion,
                    "reason": s.reason,
                    "intent": s.intent.value,
                    "relevance_score": s.relevance_score,
                }
                for s in suggestions
            ],
        }
    except Exception as e:
        logger.error("Suggestion generation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain")
async def explain_code_snippet(
    code: str, file_path: str = "<unknown>", line_number: int = 0
):
    """
    Generate an explanation for a code snippet.

    Uses LLM if available, otherwise falls back to heuristic analysis.
    """
    try:
        explanation = await _code_explainer.explain_code(code, file_path, line_number)

        return {
            "code_snippet": explanation.code_snippet,
            "file_path": explanation.file_path,
            "line_number": explanation.line_number,
            "summary": explanation.summary,
            "detailed_explanation": explanation.detailed_explanation,
            "purpose": explanation.purpose,
            "key_concepts": explanation.key_concepts,
            "related_code": explanation.related_code,
        }
    except Exception as e:
        logger.error("Code explanation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intents")
async def list_supported_intents():
    """List all supported query intents with examples."""
    return {
        "intents": [
            {
                "intent": intent.value,
                "description": {
                    QueryIntent.FIND_DEFINITION: "Find where something is defined",
                    QueryIntent.FIND_USAGE: "Find where something is used",
                    QueryIntent.FIND_IMPLEMENTATION: "Find how something is implemented",
                    QueryIntent.FIND_ERROR_HANDLING: "Find error handling logic",
                    QueryIntent.FIND_CONFIGURATION: "Find configuration settings",
                    QueryIntent.FIND_TESTS: "Find test cases",
                    QueryIntent.FIND_DEPENDENCIES: "Find dependencies",
                    QueryIntent.FIND_PATTERN: "Find code patterns",
                    QueryIntent.EXPLAIN_CODE: "Get code explanation",
                    QueryIntent.COMPARE_CODE: "Compare code implementations",
                    QueryIntent.GENERAL_SEARCH: "General code search",
                }.get(intent, "Unknown intent"),
                "example_queries": {
                    QueryIntent.FIND_DEFINITION: ["Where is UserModel defined?"],
                    QueryIntent.FIND_USAGE: ["Where is authenticate() used?"],
                    QueryIntent.FIND_IMPLEMENTATION: ["How is caching implemented?"],
                    QueryIntent.FIND_ERROR_HANDLING: ["How are Redis errors handled?"],
                    QueryIntent.FIND_CONFIGURATION: ["Where is logging configured?"],
                    QueryIntent.FIND_TESTS: ["What tests exist for auth?"],
                    QueryIntent.FIND_DEPENDENCIES: [
                        "What does the API module depend on?"
                    ],
                    QueryIntent.FIND_PATTERN: ["Find all async functions"],
                    QueryIntent.EXPLAIN_CODE: ["Explain the router initialization"],
                    QueryIntent.COMPARE_CODE: ["Compare Redis and in-memory cache"],
                    QueryIntent.GENERAL_SEARCH: ["search authentication"],
                }.get(intent, []),
            }
            for intent in QueryIntent
        ]
    }


@router.get("/domains")
async def list_supported_domains():
    """List all supported query domains with keywords."""
    return {
        "domains": [
            {"domain": domain.value, "keywords": DOMAIN_KEYWORDS.get(domain, [])}
            for domain in QueryDomain
        ]
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "natural-language-search",
        "features": [
            "query_parsing",
            "intent_classification",
            "domain_detection",
            "query_suggestions",
            "code_explanations",
        ],
        "llm_available": _code_explainer.llm_available,
    }
