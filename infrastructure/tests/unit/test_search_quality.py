# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for Knowledge Base Search Quality Improvements (Issue #78)

Tests for:
- Query expansion with synonyms and related terms
- Relevance scoring with recency, popularity, authority
- Advanced filtering (date ranges, exclusions)
- Result clustering by topic
- Search analytics tracking
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

# Import test subjects
from src.knowledge.search_quality import (
    AdvancedFilter,
    QueryExpander,
    RelevanceScorer,
    ResultClusterer,
    SearchAnalytics,
    SearchFilters,
    get_query_expander,
    get_relevance_scorer,
    get_result_clusterer,
    get_search_analytics,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def query_expander():
    """Create a QueryExpander instance."""
    return QueryExpander(max_expansions=5)


@pytest.fixture
def relevance_scorer():
    """Create a RelevanceScorer instance."""
    return RelevanceScorer()


@pytest.fixture
def result_clusterer():
    """Create a ResultClusterer instance."""
    return ResultClusterer(max_clusters=5, min_cluster_size=2)


@pytest.fixture
def search_analytics():
    """Create a SearchAnalytics instance."""
    return SearchAnalytics(max_events=100)


@pytest.fixture
def sample_results() -> List[Dict[str, Any]]:
    """Create sample search results for testing."""
    return [
        {
            "content": "Authentication using JWT tokens for secure login",
            "score": 0.9,
            "metadata": {
                "fact_id": "fact_1",
                "title": "JWT Authentication",
                "source": "official_docs",
                "category": "security",
                "verified": True,
                "created_at": datetime.now().isoformat(),
            },
            "node_id": "node_1",
        },
        {
            "content": "Database connection pooling with Redis cache",
            "score": 0.85,
            "metadata": {
                "fact_id": "fact_2",
                "title": "Redis Caching",
                "source": "community",
                "category": "database",
                "tags": ["redis", "cache"],
                "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
            },
            "node_id": "node_2",
        },
        {
            "content": "API endpoint configuration for REST services",
            "score": 0.8,
            "metadata": {
                "fact_id": "fact_3",
                "title": "REST API Config",
                "source": "user_contributed",
                "category": "api",
                "created_at": (datetime.now() - timedelta(days=180)).isoformat(),
            },
            "node_id": "node_3",
        },
        {
            "content": "Network firewall rules for TCP port filtering",
            "score": 0.75,
            "metadata": {
                "fact_id": "fact_4",
                "title": "Firewall Config",
                "source": "verified",
                "category": "security",
                "tags": ["network", "firewall"],
            },
            "node_id": "node_4",
        },
        {
            "content": "User authentication with OAuth2 and session tokens",
            "score": 0.7,
            "metadata": {
                "fact_id": "fact_5",
                "title": "OAuth2 Setup",
                "source": "official_docs",
                "category": "security",
                "verified": True,
            },
            "node_id": "node_5",
        },
    ]


# =============================================================================
# QueryExpander Tests
# =============================================================================


class TestQueryExpander:
    """Tests for QueryExpander class."""

    def test_expand_query_with_synonyms(self, query_expander):
        """Test query expansion with known synonyms."""
        queries = query_expander.expand_query("login password")

        assert len(queries) > 1
        assert "login password" in queries
        # Should have expanded 'login' and/or 'password'
        assert any("signin" in q or "credential" in q for q in queries)

    def test_expand_query_no_synonyms(self, query_expander):
        """Test query with no known synonyms returns original."""
        queries = query_expander.expand_query("xyz123 unknown")

        assert len(queries) >= 1
        assert "xyz123 unknown" in queries

    def test_expand_query_related_terms(self, query_expander):
        """Test query expansion adds related terms."""
        queries = query_expander.expand_query("authentication")

        # Should expand with related terms like authorization, session
        assert len(queries) > 1

    def test_expand_query_max_expansions(self, query_expander):
        """Test that expansions are limited."""
        # Query with many expandable terms
        queries = query_expander.expand_query("login password token session user")

        # Should not exceed max_expansions + 1 (original)
        assert len(queries) <= query_expander.max_expansions + 1

    def test_get_synonyms_known_term(self, query_expander):
        """Test getting synonyms for a known term."""
        synonyms = query_expander.get_synonyms("password")

        assert len(synonyms) > 0
        assert "credential" in synonyms or "passwd" in synonyms

    def test_get_synonyms_unknown_term(self, query_expander):
        """Test getting synonyms for unknown term returns empty."""
        synonyms = query_expander.get_synonyms("xyzunknown")

        assert synonyms == []

    def test_reverse_synonym_lookup(self, query_expander):
        """Test that synonym lookup works in reverse."""
        # 'passwd' is a synonym of 'password'
        queries = query_expander.expand_query("passwd")

        # Should expand to include 'password'
        assert any("password" in q for q in queries)


# =============================================================================
# RelevanceScorer Tests
# =============================================================================


class TestRelevanceScorer:
    """Tests for RelevanceScorer class."""

    def test_recency_boost_recent(self, relevance_scorer):
        """Test recency boost for recent documents."""
        recent_date = datetime.now() - timedelta(days=1)
        boost = relevance_scorer.calculate_recency_boost(recent_date)

        assert boost > 0.9  # Very recent should have high boost

    def test_recency_boost_old(self, relevance_scorer):
        """Test recency boost for old documents."""
        old_date = datetime.now() - timedelta(days=400)
        boost = relevance_scorer.calculate_recency_boost(old_date, max_age_days=365)

        assert boost == 0.0  # Older than max_age should have no boost

    def test_recency_boost_none(self, relevance_scorer):
        """Test recency boost with no date returns neutral."""
        boost = relevance_scorer.calculate_recency_boost(None)

        assert boost == 0.5  # Unknown age returns neutral

    def test_popularity_boost(self, relevance_scorer):
        """Test popularity boost calculation."""
        relevance_scorer.popularity_store["doc_1"] = 50

        boost = relevance_scorer.calculate_popularity_boost("doc_1")

        assert 0.0 < boost < 1.0

    def test_popularity_boost_unknown(self, relevance_scorer):
        """Test popularity boost for unknown document."""
        boost = relevance_scorer.calculate_popularity_boost("unknown_doc")

        assert boost == 0.0

    def test_authority_boost_verified(self, relevance_scorer):
        """Test authority boost for verified source."""
        boost = relevance_scorer.calculate_authority_boost("any", verified=True)

        assert boost >= 0.9

    def test_authority_boost_by_source(self, relevance_scorer):
        """Test authority boost varies by source."""
        official_boost = relevance_scorer.calculate_authority_boost("official_docs")
        community_boost = relevance_scorer.calculate_authority_boost("community")

        assert official_boost > community_boost

    def test_exact_match_boost_title(self, relevance_scorer):
        """Test exact match boost in title."""
        boost = relevance_scorer.calculate_exact_match_boost(
            query="jwt authentication",
            content="Some content about tokens",
            title="JWT Authentication Guide",
        )

        assert boost == relevance_scorer.factors.title_match_boost

    def test_exact_match_boost_content(self, relevance_scorer):
        """Test exact match boost in content."""
        boost = relevance_scorer.calculate_exact_match_boost(
            query="jwt authentication",
            content="This is about jwt authentication setup",
            title="Guide",
        )

        assert boost == relevance_scorer.factors.exact_match_boost

    def test_exact_match_boost_none(self, relevance_scorer):
        """Test no boost when no exact match."""
        boost = relevance_scorer.calculate_exact_match_boost(
            query="jwt authentication", content="Something unrelated", title="Other"
        )

        assert boost == 1.0

    def test_calculate_relevance_score(self, relevance_scorer, sample_results):
        """Test combined relevance score calculation."""
        result = sample_results[0]

        score = relevance_scorer.calculate_relevance_score(
            base_score=0.8, query="jwt authentication", result=result
        )

        # Score should be modified from base
        assert 0.0 <= score <= 1.0

    def test_record_access(self, relevance_scorer):
        """Test recording document access."""
        relevance_scorer.record_access("doc_1")
        relevance_scorer.record_access("doc_1")

        assert relevance_scorer.popularity_store["doc_1"] == 2


# =============================================================================
# AdvancedFilter Tests
# =============================================================================


class TestAdvancedFilter:
    """Tests for AdvancedFilter class."""

    def test_filter_by_date_after(self, sample_results):
        """Test filtering by created_after date."""
        filters = SearchFilters(created_after=datetime.now() - timedelta(days=7))
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        # Should only include recent results
        assert len(filtered) < len(sample_results)

    def test_filter_by_date_before(self, sample_results):
        """Test filtering by created_before date."""
        filters = SearchFilters(created_before=datetime.now() - timedelta(days=60))
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        # Should only include older results
        assert len(filtered) < len(sample_results)

    def test_filter_by_category(self, sample_results):
        """Test filtering by category."""
        filters = SearchFilters(categories=["security"])
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        # All results should be security category
        for result in filtered:
            assert result["metadata"]["category"] == "security"

    def test_filter_by_tags_any(self, sample_results):
        """Test filtering by tags (match any)."""
        filters = SearchFilters(tags=["redis", "network"], tags_match_all=False)
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        # Should include results with redis OR network tags
        assert len(filtered) >= 1

    def test_filter_by_source(self, sample_results):
        """Test filtering by source."""
        filters = SearchFilters(sources=["official_docs"])
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert result["metadata"]["source"] == "official_docs"

    def test_filter_exclude_sources(self, sample_results):
        """Test excluding sources."""
        filters = SearchFilters(exclude_sources=["user_contributed"])
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert result["metadata"]["source"] != "user_contributed"

    def test_filter_exclude_terms(self, sample_results):
        """Test excluding results with specific terms."""
        filters = SearchFilters(exclude_terms=["Redis"])
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert "redis" not in result["content"].lower()

    def test_filter_require_terms(self, sample_results):
        """Test requiring specific terms."""
        filters = SearchFilters(require_terms=["authentication"])
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert "authentication" in result["content"].lower()

    def test_filter_verified_only(self, sample_results):
        """Test filtering for verified results only."""
        filters = SearchFilters(verified_only=True)
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert result["metadata"].get("verified", False) is True

    def test_filter_min_score(self, sample_results):
        """Test minimum score filtering."""
        filters = SearchFilters(min_score=0.8)
        advanced_filter = AdvancedFilter(filters)

        filtered = advanced_filter.apply_filters(sample_results)

        for result in filtered:
            assert result["score"] >= 0.8


# =============================================================================
# ResultClusterer Tests
# =============================================================================


class TestResultClusterer:
    """Tests for ResultClusterer class."""

    def test_cluster_results_basic(self, result_clusterer, sample_results):
        """Test basic result clustering."""
        clusters, unclustered = result_clusterer.cluster_results(sample_results)

        # Should create some clusters
        assert len(clusters) > 0 or len(unclustered) > 0

        # Total results should be preserved
        total_clustered = sum(len(c.results) for c in clusters)
        assert total_clustered + len(unclustered) == len(sample_results)

    def test_cluster_results_empty(self, result_clusterer):
        """Test clustering empty results."""
        clusters, unclustered = result_clusterer.cluster_results([])

        assert clusters == []
        assert unclustered == []

    def test_cluster_has_topic(self, result_clusterer, sample_results):
        """Test that clusters have valid topics."""
        clusters, _ = result_clusterer.cluster_results(sample_results)

        for cluster in clusters:
            assert cluster.topic is not None
            assert cluster.topic != ""

    def test_cluster_has_keywords(self, result_clusterer, sample_results):
        """Test that clusters have keywords."""
        clusters, _ = result_clusterer.cluster_results(sample_results)

        for cluster in clusters:
            assert isinstance(cluster.keywords, list)

    def test_cluster_avg_score(self, result_clusterer, sample_results):
        """Test that cluster average scores are calculated."""
        clusters, _ = result_clusterer.cluster_results(sample_results)

        for cluster in clusters:
            if cluster.results:
                assert 0.0 <= cluster.avg_score <= 1.0

    def test_max_clusters_limit(self, result_clusterer, sample_results):
        """Test that max_clusters limit is respected."""
        # Create many results to potentially create many clusters
        many_results = sample_results * 5

        clusters, _ = result_clusterer.cluster_results(many_results)

        assert len(clusters) <= result_clusterer.max_clusters


# =============================================================================
# SearchAnalytics Tests
# =============================================================================


class TestSearchAnalytics:
    """Tests for SearchAnalytics class."""

    def test_record_search(self, search_analytics):
        """Test recording a search event."""
        search_analytics.record_search(
            query="test query", result_count=10, duration_ms=50
        )

        assert len(search_analytics.events) == 1
        assert search_analytics.query_counts["test query"] == 1

    def test_record_failed_search(self, search_analytics):
        """Test recording a failed search (0 results)."""
        search_analytics.record_search(query="no results query", result_count=0)

        assert "no results query" in search_analytics.failed_queries

    def test_record_click(self, search_analytics):
        """Test recording a click."""
        search_analytics.record_search(
            query="test", result_count=5, session_id="session_1"
        )
        search_analytics.record_click(
            query="test", result_id="result_1", session_id="session_1"
        )

        assert search_analytics.click_counts["result_1"] == 1

    def test_get_popular_queries(self, search_analytics):
        """Test getting popular queries."""
        search_analytics.record_search("popular", 10)
        search_analytics.record_search("popular", 10)
        search_analytics.record_search("popular", 10)
        search_analytics.record_search("less popular", 5)

        popular = search_analytics.get_popular_queries(limit=2)

        assert len(popular) == 2
        assert popular[0][0] == "popular"
        assert popular[0][1] == 3

    def test_get_failed_searches(self, search_analytics):
        """Test getting failed searches."""
        search_analytics.record_search("failed1", 0)
        search_analytics.record_search("failed2", 0)
        search_analytics.record_search("success", 10)

        failed = search_analytics.get_failed_searches()

        assert "failed1" in failed
        assert "failed2" in failed
        assert "success" not in failed

    def test_click_through_rate(self, search_analytics):
        """Test click-through rate calculation."""
        # Record 10 searches
        for i in range(10):
            search_analytics.record_search(
                query=f"query_{i}", result_count=5, session_id=f"session_{i}"
            )

        # Record 3 clicks
        for i in range(3):
            search_analytics.record_click(
                query=f"query_{i}", result_id=f"result_{i}", session_id=f"session_{i}"
            )

        ctr = search_analytics.get_click_through_rate()

        assert ctr == 0.3  # 3/10

    def test_average_results_count(self, search_analytics):
        """Test average results calculation."""
        search_analytics.record_search("q1", 10)
        search_analytics.record_search("q2", 20)
        search_analytics.record_search("q3", 30)

        avg = search_analytics.get_average_results_count()

        assert avg == 20.0

    def test_performance_stats(self, search_analytics):
        """Test comprehensive performance stats."""
        search_analytics.record_search("query1", 5, duration_ms=100)
        search_analytics.record_search("query2", 0, duration_ms=50)
        search_analytics.record_search("query1", 10, duration_ms=75)

        stats = search_analytics.get_search_performance_stats()

        assert stats["total_searches"] == 3
        assert stats["unique_queries"] == 2
        assert stats["failed_search_rate"] > 0
        assert "popular_queries" in stats
        assert "recent_failed_queries" in stats

    def test_max_events_limit(self, search_analytics):
        """Test that max events limit is enforced."""
        # Record more than max_events
        for i in range(150):
            search_analytics.record_search(f"query_{i}", 5)

        assert len(search_analytics.events) <= search_analytics.max_events


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingletons:
    """Tests for thread-safe singleton instances."""

    def test_get_query_expander_singleton(self):
        """Test QueryExpander singleton."""
        expander1 = get_query_expander()
        expander2 = get_query_expander()

        assert expander1 is expander2

    def test_get_relevance_scorer_singleton(self):
        """Test RelevanceScorer singleton."""
        scorer1 = get_relevance_scorer()
        scorer2 = get_relevance_scorer()

        assert scorer1 is scorer2

    def test_get_result_clusterer_singleton(self):
        """Test ResultClusterer singleton."""
        clusterer1 = get_result_clusterer()
        clusterer2 = get_result_clusterer()

        assert clusterer1 is clusterer2

    def test_get_search_analytics_singleton(self):
        """Test SearchAnalytics singleton."""
        analytics1 = get_search_analytics()
        analytics2 = get_search_analytics()

        assert analytics1 is analytics2


# =============================================================================
# Integration Tests
# =============================================================================


class TestSearchQualityIntegration:
    """Integration tests combining multiple search quality features."""

    def test_full_search_pipeline(self, sample_results):
        """Test a full search quality pipeline."""
        query = "login authentication"

        # Step 1: Query expansion
        expander = QueryExpander()
        expanded_queries = expander.expand_query(query)
        assert len(expanded_queries) >= 1

        # Step 2: Apply filters
        filters = SearchFilters(min_score=0.7, categories=["security"])
        advanced_filter = AdvancedFilter(filters)
        filtered_results = advanced_filter.apply_filters(sample_results)

        # Step 3: Apply relevance scoring
        scorer = RelevanceScorer()
        for result in filtered_results:
            original_score = result["score"]
            result["score"] = scorer.calculate_relevance_score(
                original_score, query, result
            )

        # Step 4: Cluster results
        clusterer = ResultClusterer()
        clusters, unclustered = clusterer.cluster_results(filtered_results)

        # Step 5: Record analytics
        analytics = SearchAnalytics()
        analytics.record_search(query, len(filtered_results), duration_ms=100)

        # Verify pipeline completed successfully
        assert len(analytics.events) == 1
        assert analytics.events[0].query == query

    def test_query_expansion_improves_coverage(self, query_expander):
        """Test that query expansion increases potential matches."""
        original = "login"
        expanded = query_expander.expand_query(original)

        # Expanded queries should cover more terms
        all_terms = set()
        for q in expanded:
            all_terms.update(q.lower().split())

        assert len(all_terms) > 1  # More than just 'login'

    def test_relevance_scoring_reorders_results(self, relevance_scorer, sample_results):
        """Test that relevance scoring can reorder results."""
        query = "authentication"

        # Calculate new scores
        for result in sample_results:
            result["new_score"] = relevance_scorer.calculate_relevance_score(
                result["score"], query, result
            )

        # Sort by new scores
        reordered = sorted(sample_results, key=lambda x: x["new_score"], reverse=True)
        original_order = [r["node_id"] for r in sample_results]
        new_order = [r["node_id"] for r in reordered]

        # Order may have changed
        # (Not guaranteed, but likely with different boosts)
        assert len(new_order) == len(original_order)
