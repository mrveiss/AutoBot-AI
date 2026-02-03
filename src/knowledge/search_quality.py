# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Search Quality Enhancements (Issue #78)

This module implements advanced search quality improvements including:
- Query expansion with synonyms and related terms
- Relevance scoring with recency, popularity, and authority boosting
- Advanced filtering (date ranges, exclude conditions)
- Result clustering by topic
- Search analytics tracking

Related Issues: #78 (Search Quality Improvements)
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Issue #78: Pre-compiled patterns for performance
_WORD_PATTERN = re.compile(r"\b\w+\b")


# =============================================================================
# Query Expansion (Issue #78 - Section 2)
# =============================================================================


class QueryExpander:
    """
    Expands search queries with synonyms and related terms.

    Issue #78: Query expansion improves recall by searching for
    semantically similar terms that the user might not have included.
    """

    # Security/sysadmin domain synonyms
    SYNONYMS: Dict[str, List[str]] = {
        # Authentication
        "login": ["signin", "authenticate", "logon", "sign-in"],
        "logout": ["signout", "sign-out", "logoff"],
        "password": ["passwd", "pwd", "credential", "secret"],
        "token": ["jwt", "bearer", "apikey", "api-key"],
        "session": ["cookie", "auth-state"],
        # Network
        "ip": ["address", "ipv4", "ipv6", "host"],
        "port": ["socket", "endpoint"],
        "firewall": ["iptables", "ufw", "nftables"],
        "dns": ["nameserver", "resolver", "domain"],
        "proxy": ["gateway", "relay", "forward"],
        # System
        "user": ["account", "principal", "identity"],
        "permission": ["access", "privilege", "right", "acl"],
        "process": ["pid", "daemon", "service", "task"],
        "file": ["path", "document", "resource"],
        "directory": ["folder", "dir", "path"],
        # Database
        "database": ["db", "datastore", "storage"],
        "query": ["sql", "select", "fetch"],
        "table": ["collection", "schema", "entity"],
        "cache": ["redis", "memcache", "memory"],
        # Code
        "function": ["method", "procedure", "def", "func"],
        "class": ["type", "model", "object"],
        "variable": ["var", "param", "argument"],
        "error": ["exception", "fault", "failure", "bug"],
        "log": ["logging", "trace", "debug", "audit"],
        # API
        "api": ["endpoint", "route", "rest", "interface"],
        "request": ["req", "call", "invoke"],
        "response": ["res", "reply", "result"],
        # Security
        "vulnerability": ["vuln", "cve", "weakness", "exploit"],
        "encryption": ["cipher", "encrypt", "crypto"],
        "certificate": ["cert", "ssl", "tls", "x509"],
        "scan": ["audit", "check", "analyze", "inspect"],
    }

    # Related terms (broader conceptual relationships)
    RELATED_TERMS: Dict[str, List[str]] = {
        "authentication": ["authorization", "session", "token", "oauth"],
        "security": ["encryption", "firewall", "vulnerability", "audit"],
        "network": ["tcp", "udp", "http", "dns", "ip"],
        "database": ["sql", "query", "schema", "migration"],
        "api": ["rest", "graphql", "endpoint", "webhook"],
        "testing": ["unit", "integration", "mock", "fixture"],
        "deployment": ["docker", "kubernetes", "ci", "cd"],
        "logging": ["monitoring", "metrics", "tracing", "alerting"],
        "configuration": ["settings", "environment", "yaml", "json"],
    }

    def __init__(self, max_expansions: int = 5):
        """
        Initialize query expander.

        Args:
            max_expansions: Maximum number of expansion terms to add
        """
        self.max_expansions = max_expansions
        # Build reverse lookup for faster expansion
        self._reverse_synonyms: Dict[str, str] = {}
        for canonical, synonyms in self.SYNONYMS.items():
            for syn in synonyms:
                self._reverse_synonyms[syn.lower()] = canonical

    def expand_query(self, query: str) -> List[str]:
        """
        Expand a query with synonyms and related terms.

        Issue #78: Query expansion for improved recall.

        Args:
            query: Original search query

        Returns:
            List of expanded query variations
        """
        queries = [query]
        words = _WORD_PATTERN.findall(query.lower())
        expansions_added = 0

        for word in words:
            if expansions_added >= self.max_expansions:
                break

            # Check direct synonyms
            if word in self.SYNONYMS:
                for syn in self.SYNONYMS[word][:2]:  # Limit synonyms per word
                    expanded = query.replace(word, syn)
                    if expanded not in queries:
                        queries.append(expanded)
                        expansions_added += 1
                        if expansions_added >= self.max_expansions:
                            break

            # Check reverse synonyms (synonym -> canonical)
            elif word in self._reverse_synonyms:
                canonical = self._reverse_synonyms[word]
                expanded = query.replace(word, canonical)
                if expanded not in queries:
                    queries.append(expanded)
                    expansions_added += 1

            # Check related terms
            if word in self.RELATED_TERMS and expansions_added < self.max_expansions:
                # Add first related term as additional query context
                related = self.RELATED_TERMS[word][0]
                expanded = f"{query} {related}"
                if expanded not in queries:
                    queries.append(expanded)
                    expansions_added += 1

        logger.debug("Query expansion: '%s' -> %d variations", query, len(queries))
        return queries

    def get_synonyms(self, term: str) -> List[str]:
        """Get synonyms for a specific term."""
        term_lower = term.lower()
        if term_lower in self.SYNONYMS:
            return self.SYNONYMS[term_lower]
        if term_lower in self._reverse_synonyms:
            canonical = self._reverse_synonyms[term_lower]
            return [canonical] + [s for s in self.SYNONYMS.get(canonical, []) if s != term_lower]
        return []


# =============================================================================
# Relevance Scoring (Issue #78 - Section 3)
# =============================================================================


@dataclass
class RelevanceFactors:
    """Factors used in relevance scoring."""
    recency_weight: float = 0.1
    popularity_weight: float = 0.1
    authority_weight: float = 0.1
    exact_match_boost: float = 1.2
    title_match_boost: float = 1.5


class RelevanceScorer:
    """
    Enhanced relevance scoring with multiple boosting factors.

    Issue #78: Relevance scoring considers recency, popularity, authority,
    and exact match boosting for improved search quality.
    """

    def __init__(
        self,
        factors: RelevanceFactors = None,
        popularity_store: Dict[str, int] = None,
        authority_scores: Dict[str, float] = None,
    ):
        """
        Initialize relevance scorer.

        Args:
            factors: Relevance scoring weights
            popularity_store: Dict mapping doc_id -> access_count
            authority_scores: Dict mapping source -> authority_score (0-1)
        """
        self.factors = factors or RelevanceFactors()
        self.popularity_store = popularity_store or {}
        self.authority_scores = authority_scores or self._default_authority_scores()

    def _default_authority_scores(self) -> Dict[str, float]:
        """Default authority scores by source type."""
        return {
            "official_docs": 1.0,
            "verified": 0.9,
            "community": 0.7,
            "user_contributed": 0.5,
            "auto_generated": 0.3,
            "unknown": 0.5,
        }

    def calculate_recency_boost(
        self,
        created_at: Optional[datetime],
        max_age_days: int = 365,
    ) -> float:
        """
        Calculate recency boost factor.

        Issue #78: Newer documents get higher scores.

        Args:
            created_at: Document creation timestamp
            max_age_days: Age beyond which documents get no boost

        Returns:
            Boost factor (0.0 to 1.0)
        """
        if not created_at:
            return 0.5  # Neutral for unknown age

        age = datetime.now() - created_at
        if age.days <= 0:
            return 1.0
        if age.days >= max_age_days:
            return 0.0

        # Linear decay over max_age_days
        return 1.0 - (age.days / max_age_days)

    def calculate_popularity_boost(
        self,
        doc_id: str,
        max_count: int = 100,
    ) -> float:
        """
        Calculate popularity boost based on access count.

        Issue #78: Frequently accessed documents get higher scores.

        Args:
            doc_id: Document identifier
            max_count: Access count for maximum boost

        Returns:
            Boost factor (0.0 to 1.0)
        """
        access_count = self.popularity_store.get(doc_id, 0)
        if access_count <= 0:
            return 0.0
        if access_count >= max_count:
            return 1.0

        # Logarithmic scaling for diminishing returns
        import math
        return math.log(access_count + 1) / math.log(max_count + 1)

    def calculate_authority_boost(
        self,
        source: str,
        verified: bool = False,
    ) -> float:
        """
        Calculate authority boost based on document source.

        Issue #78: Verified/official sources get higher scores.

        Args:
            source: Document source type
            verified: Whether document is verified

        Returns:
            Boost factor (0.0 to 1.0)
        """
        if verified:
            return self.authority_scores.get("verified", 0.9)
        return self.authority_scores.get(source, self.authority_scores.get("unknown", 0.5))

    def calculate_exact_match_boost(
        self,
        query: str,
        content: str,
        title: str = "",
    ) -> float:
        """
        Calculate boost for exact query matches.

        Issue #78: Exact matches in content/title get boosted.

        Args:
            query: Search query
            content: Document content
            title: Document title

        Returns:
            Boost factor (1.0 to title_match_boost)
        """
        query_lower = query.lower()
        content_lower = content.lower()
        title_lower = title.lower()

        if query_lower in title_lower:
            return self.factors.title_match_boost
        if query_lower in content_lower:
            return self.factors.exact_match_boost
        return 1.0

    def _parse_result_metadata(
        self, result: Dict[str, Any]
    ) -> Tuple[str, str, str, str, bool, Optional[datetime]]:
        """Parse metadata from result for scoring (Issue #398: extracted)."""
        metadata = result.get("metadata", {})
        content = result.get("content", "")
        title = metadata.get("title", "")
        doc_id = metadata.get("fact_id") or result.get("node_id", "")
        source = metadata.get("source", "unknown")
        verified = metadata.get("verified", False)

        created_at = None
        if "created_at" in metadata:
            try:
                created_at = datetime.fromisoformat(metadata["created_at"])
            except (ValueError, TypeError):
                pass

        return content, title, doc_id, source, verified, created_at

    def _compute_boosted_score(
        self, base_score: float, query: str, content: str, title: str,
        doc_id: str, source: str, verified: bool, created_at: Optional[datetime]
    ) -> float:
        """Compute boosted score from all factors (Issue #398: extracted)."""
        recency_boost = self.calculate_recency_boost(created_at)
        popularity_boost = self.calculate_popularity_boost(doc_id)
        authority_boost = self.calculate_authority_boost(source, verified)
        exact_boost = self.calculate_exact_match_boost(query, content, title)

        boosted_score = base_score * exact_boost
        boosted_score += self.factors.recency_weight * recency_boost
        boosted_score += self.factors.popularity_weight * popularity_boost
        boosted_score += self.factors.authority_weight * authority_boost

        max_possible = (
            1.0 * self.factors.title_match_boost
            + self.factors.recency_weight
            + self.factors.popularity_weight
            + self.factors.authority_weight
        )
        return min(boosted_score / max_possible, 1.0)

    def calculate_relevance_score(
        self, base_score: float, query: str, result: Dict[str, Any]
    ) -> float:
        """Calculate final relevance score with all factors (Issue #398: refactored)."""
        content, title, doc_id, source, verified, created_at = self._parse_result_metadata(result)
        return self._compute_boosted_score(
            base_score, query, content, title, doc_id, source, verified, created_at
        )

    def record_access(self, doc_id: str) -> None:
        """Record document access for popularity tracking."""
        self.popularity_store[doc_id] = self.popularity_store.get(doc_id, 0) + 1


# =============================================================================
# Advanced Filtering (Issue #78 - Section 4)
# =============================================================================


@dataclass
class SearchFilters:
    """Advanced search filter configuration."""
    # Date filters
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None

    # Category/tag filters
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    tags_match_all: bool = False

    # Source filters
    sources: Optional[List[str]] = None
    exclude_sources: Optional[List[str]] = None

    # Content filters
    exclude_terms: Optional[List[str]] = None
    require_terms: Optional[List[str]] = None

    # Metadata filters
    verified_only: bool = False
    min_authority: Optional[float] = None

    # Result limits
    min_score: float = 0.0
    max_results: int = 100


class AdvancedFilter:
    """
    Advanced filtering for search results.

    Issue #78: Support for date ranges, exclusions, and complex conditions.
    """

    def __init__(self, filters: SearchFilters):
        """Initialize with filter configuration."""
        self.filters = filters
        # Pre-compile exclude patterns
        self._exclude_patterns = None
        if filters.exclude_terms:
            patterns = [re.escape(term) for term in filters.exclude_terms]
            self._exclude_patterns = re.compile("|".join(patterns), re.IGNORECASE)

    def apply_filters(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply all configured filters to results.

        Issue #78: Advanced filtering pipeline.

        Args:
            results: List of search results

        Returns:
            Filtered results
        """
        filtered = results

        # Date filters
        if self.filters.created_after or self.filters.created_before:
            filtered = [r for r in filtered if self._passes_date_filter(r)]

        # Category/tag filters
        if self.filters.categories:
            filtered = [r for r in filtered if self._matches_category(r)]

        if self.filters.tags:
            filtered = [r for r in filtered if self._matches_tags(r)]

        # Source filters
        if self.filters.sources:
            filtered = [r for r in filtered if self._matches_source(r)]

        if self.filters.exclude_sources:
            filtered = [r for r in filtered if not self._matches_excluded_source(r)]

        # Content filters
        if self._exclude_patterns:
            filtered = [r for r in filtered if not self._contains_excluded_terms(r)]

        if self.filters.require_terms:
            filtered = [r for r in filtered if self._contains_required_terms(r)]

        # Metadata filters
        if self.filters.verified_only:
            filtered = [r for r in filtered if self._is_verified(r)]

        # Score filter
        if self.filters.min_score > 0:
            filtered = [r for r in filtered if r.get("score", 0) >= self.filters.min_score]

        # Limit results
        return filtered[:self.filters.max_results]

    def _passes_date_filter(self, result: Dict[str, Any]) -> bool:
        """Check if result passes date filters."""
        metadata = result.get("metadata", {})
        created_at_str = metadata.get("created_at")

        if not created_at_str:
            return True  # Allow if no date info

        try:
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            return True

        if self.filters.created_after and created_at < self.filters.created_after:
            return False
        if self.filters.created_before and created_at > self.filters.created_before:
            return False

        return True

    def _matches_category(self, result: Dict[str, Any]) -> bool:
        """Check if result matches category filter."""
        category = result.get("metadata", {}).get("category", "").lower()
        return any(c.lower() == category for c in self.filters.categories)

    def _matches_tags(self, result: Dict[str, Any]) -> bool:
        """Check if result matches tag filter."""
        result_tags = set(
            t.lower() for t in result.get("metadata", {}).get("tags", [])
        )
        filter_tags = set(t.lower() for t in self.filters.tags)

        if self.filters.tags_match_all:
            return filter_tags.issubset(result_tags)
        return bool(filter_tags.intersection(result_tags))

    def _matches_source(self, result: Dict[str, Any]) -> bool:
        """Check if result matches source filter."""
        source = result.get("metadata", {}).get("source", "").lower()
        return any(s.lower() == source for s in self.filters.sources)

    def _matches_excluded_source(self, result: Dict[str, Any]) -> bool:
        """Check if result matches excluded source."""
        source = result.get("metadata", {}).get("source", "").lower()
        return any(s.lower() == source for s in self.filters.exclude_sources)

    def _contains_excluded_terms(self, result: Dict[str, Any]) -> bool:
        """Check if result contains excluded terms."""
        content = result.get("content", "")
        return bool(self._exclude_patterns.search(content))

    def _contains_required_terms(self, result: Dict[str, Any]) -> bool:
        """Check if result contains all required terms."""
        content = result.get("content", "").lower()
        return all(term.lower() in content for term in self.filters.require_terms)

    def _is_verified(self, result: Dict[str, Any]) -> bool:
        """Check if result is from verified source."""
        return result.get("metadata", {}).get("verified", False)


# =============================================================================
# Result Clustering (Issue #78 - Section 5)
# =============================================================================


@dataclass
class ResultCluster:
    """A cluster of related search results."""
    topic: str
    results: List[Dict[str, Any]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    avg_score: float = 0.0


class ResultClusterer:
    """
    Clusters search results by topic/theme.

    Issue #78: Result clustering helps users find related information.
    """

    # Topic keywords for clustering
    TOPIC_KEYWORDS: Dict[str, List[str]] = {
        "authentication": ["auth", "login", "password", "token", "session", "oauth", "jwt"],
        "security": ["vulnerability", "exploit", "firewall", "encryption", "ssl", "tls"],
        "networking": ["network", "ip", "port", "dns", "tcp", "udp", "http"],
        "database": ["database", "sql", "query", "table", "schema", "migration"],
        "api": ["api", "endpoint", "rest", "graphql", "request", "response"],
        "configuration": ["config", "settings", "environment", "yaml", "json"],
        "logging": ["log", "trace", "debug", "monitor", "metric", "alert"],
        "testing": ["test", "unit", "integration", "mock", "fixture", "pytest"],
        "deployment": ["deploy", "docker", "kubernetes", "ci", "cd", "container"],
        "error_handling": ["error", "exception", "catch", "try", "handle", "fail"],
    }

    def __init__(self, max_clusters: int = 5, min_cluster_size: int = 2):
        """
        Initialize clusterer.

        Args:
            max_clusters: Maximum number of clusters to create
            min_cluster_size: Minimum results needed to form a cluster
        """
        self.max_clusters = max_clusters
        self.min_cluster_size = min_cluster_size

    def _match_topics_to_results(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, List[int]]:
        """Match topics to result indices (Issue #398: extracted)."""
        topic_results: Dict[str, List[int]] = defaultdict(list)
        for idx, result in enumerate(results):
            content = result.get("content", "").lower()
            title = result.get("metadata", {}).get("title", "").lower()
            text = f"{title} {content}"
            for topic, keywords in self.TOPIC_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    topic_results[topic].append(idx)
        return topic_results

    def _build_cluster(
        self, topic: str, indices: List[int], results: List[Dict]
    ) -> ResultCluster:
        """Build a cluster from topic and indices (Issue #398: extracted)."""
        cluster_results = [results[i] for i in indices]
        scores = [r.get("score", 0) for r in cluster_results]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        keywords = self.TOPIC_KEYWORDS.get(topic, [])[:5]
        return ResultCluster(
            topic=topic, results=cluster_results, keywords=keywords, avg_score=avg_score
        )

    def cluster_results(
        self, results: List[Dict[str, Any]]
    ) -> Tuple[List[ResultCluster], List[Dict[str, Any]]]:
        """Cluster results by topic (Issue #398: refactored)."""
        if not results:
            return [], []

        topic_results = self._match_topics_to_results(results)
        clusters = []
        clustered_indices: Set[int] = set()

        sorted_topics = sorted(topic_results.items(), key=lambda x: len(x[1]), reverse=True)

        for topic, indices in sorted_topics:
            if len(clusters) >= self.max_clusters:
                break
            available = [i for i in indices if i not in clustered_indices]
            if len(available) >= self.min_cluster_size:
                clusters.append(self._build_cluster(topic, available, results))
                clustered_indices.update(available)

        unclustered = [results[i] for i in range(len(results)) if i not in clustered_indices]
        clusters.sort(key=lambda c: c.avg_score, reverse=True)

        logger.debug(
            "Clustered %d results into %d clusters, %d unclustered",
            len(results), len(clusters), len(unclustered)
        )
        return clusters, unclustered


# =============================================================================
# Search Analytics (Issue #78 - Section 6)
# =============================================================================


@dataclass
class SearchEvent:
    """A single search event for analytics."""
    query: str
    timestamp: datetime
    result_count: int
    clicked_result_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    search_duration_ms: Optional[int] = None
    filters_used: Optional[Dict[str, Any]] = None


class SearchAnalytics:
    """
    Track and analyze search behavior.

    Issue #78: Search analytics for quality monitoring.
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize analytics tracker.

        Args:
            max_events: Maximum events to keep in memory
        """
        self.max_events = max_events
        self.events: List[SearchEvent] = []
        self.query_counts: Dict[str, int] = defaultdict(int)
        self.failed_queries: List[str] = []  # Queries with 0 results
        self.click_counts: Dict[str, int] = defaultdict(int)

    def record_search(
        self,
        query: str,
        result_count: int,
        duration_ms: int = 0,
        session_id: str = None,
        filters: Dict[str, Any] = None,
    ) -> None:
        """
        Record a search event.

        Issue #78: Track search queries.

        Args:
            query: Search query
            result_count: Number of results returned
            duration_ms: Search duration in milliseconds
            session_id: Optional session identifier
            filters: Filters used in search
        """
        event = SearchEvent(
            query=query,
            timestamp=datetime.now(),
            result_count=result_count,
            session_id=session_id,
            search_duration_ms=duration_ms,
            filters_used=filters,
        )

        self.events.append(event)
        self.query_counts[query.lower()] += 1

        if result_count == 0:
            self.failed_queries.append(query)

        # Trim events if over limit
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def record_click(
        self,
        query: str,
        result_id: str,
        session_id: str = None,
    ) -> None:
        """
        Record a result click (click-through).

        Issue #78: Track click-through rates.

        Args:
            query: Search query that led to click
            result_id: ID of clicked result
            session_id: Optional session identifier
        """
        self.click_counts[result_id] += 1

        # Find most recent search event and update it
        for event in reversed(self.events):
            if event.query.lower() == query.lower() and event.session_id == session_id:
                event.clicked_result_id = result_id
                break

    def get_popular_queries(self, limit: int = 10) -> List[Tuple[str, int]]:
        """
        Get most popular search queries.

        Issue #78: Popular query analysis.

        Returns:
            List of (query, count) tuples sorted by count
        """
        sorted_queries = sorted(
            self.query_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_queries[:limit]

    def get_failed_searches(self, limit: int = 10) -> List[str]:
        """
        Get recent queries with no results.

        Issue #78: Identify failed searches.

        Returns:
            List of failed queries
        """
        return self.failed_queries[-limit:]

    def get_click_through_rate(self, min_searches: int = 5) -> float:
        """
        Calculate overall click-through rate.

        Issue #78: Search performance metrics.

        Args:
            min_searches: Minimum searches to calculate rate

        Returns:
            Click-through rate (0.0 to 1.0)
        """
        if len(self.events) < min_searches:
            return 0.0

        clicks = sum(1 for e in self.events if e.clicked_result_id)
        return clicks / len(self.events)

    def get_average_results_count(self) -> float:
        """Get average number of results per search."""
        if not self.events:
            return 0.0
        return sum(e.result_count for e in self.events) / len(self.events)

    def get_search_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive search performance statistics.

        Issue #78: Search performance metrics dashboard.

        Returns:
            Dict with various performance metrics
        """
        if not self.events:
            return {
                "total_searches": 0,
                "unique_queries": 0,
                "avg_results": 0.0,
                "failed_search_rate": 0.0,
                "click_through_rate": 0.0,
                "avg_duration_ms": 0,
            }

        durations = [e.search_duration_ms for e in self.events if e.search_duration_ms]
        failed_count = len(self.failed_queries)

        return {
            "total_searches": len(self.events),
            "unique_queries": len(self.query_counts),
            "avg_results": self.get_average_results_count(),
            "failed_search_rate": failed_count / len(self.events) if self.events else 0.0,
            "click_through_rate": self.get_click_through_rate(),
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "popular_queries": self.get_popular_queries(5),
            "recent_failed_queries": self.get_failed_searches(5),
        }


# =============================================================================
# Global Instances (Thread-Safe Singletons)
# =============================================================================

import threading

_query_expander: Optional[QueryExpander] = None
_relevance_scorer: Optional[RelevanceScorer] = None
_result_clusterer: Optional[ResultClusterer] = None
_search_analytics: Optional[SearchAnalytics] = None
_instances_lock = threading.Lock()


def get_query_expander() -> QueryExpander:
    """Get global QueryExpander instance (thread-safe)."""
    global _query_expander
    if _query_expander is None:
        with _instances_lock:
            if _query_expander is None:
                _query_expander = QueryExpander()
    return _query_expander


def get_relevance_scorer() -> RelevanceScorer:
    """Get global RelevanceScorer instance (thread-safe)."""
    global _relevance_scorer
    if _relevance_scorer is None:
        with _instances_lock:
            if _relevance_scorer is None:
                _relevance_scorer = RelevanceScorer()
    return _relevance_scorer


def get_result_clusterer() -> ResultClusterer:
    """Get global ResultClusterer instance (thread-safe)."""
    global _result_clusterer
    if _result_clusterer is None:
        with _instances_lock:
            if _result_clusterer is None:
                _result_clusterer = ResultClusterer()
    return _result_clusterer


def get_search_analytics() -> SearchAnalytics:
    """Get global SearchAnalytics instance (thread-safe)."""
    global _search_analytics
    if _search_analytics is None:
        with _instances_lock:
            if _search_analytics is None:
                _search_analytics = SearchAnalytics()
    return _search_analytics
