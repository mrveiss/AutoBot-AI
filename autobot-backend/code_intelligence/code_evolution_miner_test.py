# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Code Evolution Miner
Issue #243 - Code Evolution Mining from Git History
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from code_intelligence.code_evolution_miner import (
    CodeEvolutionMiner,
    GitHistoryCrawler,
    PatternEvolutionTracker,
    PatternLifecycle,
    PatternOccurrence,
    RefactoringDetector,
    TemporalEmbedding,
)


class TestPatternOccurrence:
    """Tests for PatternOccurrence"""

    def test_create_occurrence(self):
        """Test creating a pattern occurrence"""
        timestamp = datetime.now()
        occurrence = PatternOccurrence(
            pattern_type="god_class",
            file_path="test.py",
            line_number=10,
            commit_hash="abc123",
            timestamp=timestamp,
            severity="high",
        )

        assert occurrence.pattern_type == "god_class"
        assert occurrence.file_path == "test.py"
        assert occurrence.line_number == 10
        assert occurrence.commit_hash == "abc123"
        assert occurrence.timestamp == timestamp
        assert occurrence.severity == "high"


class TestPatternLifecycle:
    """Tests for PatternLifecycle"""

    def test_create_lifecycle(self):
        """Test creating a pattern lifecycle"""
        lifecycle = PatternLifecycle("god_class", "test.py", 10)

        assert lifecycle.pattern_type == "god_class"
        assert lifecycle.file_path == "test.py"
        assert lifecycle.line_number == 10
        assert lifecycle.first_seen is None
        assert lifecycle.last_seen is None
        assert len(lifecycle.occurrences) == 0
        assert lifecycle.status == "active"

    def test_add_occurrence(self):
        """Test adding occurrences to lifecycle"""
        lifecycle = PatternLifecycle("god_class", "test.py", 10)

        now = datetime.now()
        occurrence1 = PatternOccurrence("god_class", "test.py", 10, "abc", now, "high")
        occurrence2 = PatternOccurrence(
            "god_class", "test.py", 10, "def", now + timedelta(days=1), "high"
        )

        lifecycle.add_occurrence(occurrence1)
        assert lifecycle.first_seen == now
        assert lifecycle.last_seen == now
        assert len(lifecycle.occurrences) == 1

        lifecycle.add_occurrence(occurrence2)
        assert lifecycle.first_seen == now
        assert lifecycle.last_seen == now + timedelta(days=1)
        assert len(lifecycle.occurrences) == 2

    def test_get_lifespan_days(self):
        """Test calculating lifespan in days"""
        lifecycle = PatternLifecycle("god_class", "test.py", 10)

        # No occurrences
        assert lifecycle.get_lifespan_days() == 0

        # Add occurrences
        now = datetime.now()
        lifecycle.add_occurrence(
            PatternOccurrence("god_class", "test.py", 10, "a", now, "high")
        )
        lifecycle.add_occurrence(
            PatternOccurrence(
                "god_class", "test.py", 10, "b", now + timedelta(days=30), "high"
            )
        )

        assert lifecycle.get_lifespan_days() == 30


class TestGitHistoryCrawler:
    """Tests for GitHistoryCrawler"""

    def test_init_without_git(self):
        """Test initialization without GitPython"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = GitHistoryCrawler(tmpdir)
            assert crawler.repo_path == Path(tmpdir)

    def test_classify_refactoring(self):
        """Test refactoring classification"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = GitHistoryCrawler(tmpdir)

            assert (
                crawler._classify_refactoring("extract method foo") == "extract_method"
            )
            assert crawler._classify_refactoring("rename variable") == "rename"
            assert crawler._classify_refactoring("move code to new file") == "move_code"
            assert crawler._classify_refactoring("simplify logic") == "simplification"
            assert crawler._classify_refactoring("restructure module") == "structural"
            assert (
                crawler._classify_refactoring("refactor something")
                == "general_refactoring"
            )


class TestTemporalEmbedding:
    """Tests for TemporalEmbedding"""

    def test_add_pattern(self):
        """Test adding patterns to timeline"""
        embedding = TemporalEmbedding()

        now = datetime.now()
        occurrence = PatternOccurrence("god_class", "test.py", 10, "abc", now, "high")

        embedding.add_pattern(occurrence)
        assert "god_class" in embedding.pattern_timeline
        assert len(embedding.pattern_timeline["god_class"]) == 1

    def test_get_pattern_counts_by_month(self):
        """Test monthly pattern counts"""
        embedding = TemporalEmbedding()

        now = datetime.now()
        month_key = now.strftime("%Y-%m")

        # Add multiple patterns
        embedding.add_pattern(
            PatternOccurrence("god_class", "a.py", 1, "a", now, "high")
        )
        embedding.add_pattern(
            PatternOccurrence("god_class", "b.py", 1, "b", now, "high")
        )
        embedding.add_pattern(
            PatternOccurrence("long_method", "c.py", 1, "c", now, "medium")
        )

        monthly = embedding.get_pattern_counts_by_month()

        assert month_key in monthly
        assert monthly[month_key]["god_class"] == 2
        assert monthly[month_key]["long_method"] == 1

    def test_calculate_trend_emerging(self):
        """Test trend calculation for emerging patterns"""
        embedding = TemporalEmbedding()

        old_date = datetime.now() - timedelta(days=200)
        recent_date = datetime.now()

        # Add old occurrences
        embedding.add_pattern(
            PatternOccurrence("god_class", "a.py", 1, "a", old_date, "high")
        )

        # Add many recent occurrences
        for i in range(5):
            embedding.add_pattern(
                PatternOccurrence(
                    "god_class", f"{i}.py", 1, f"h{i}", recent_date, "high"
                )
            )

        trend = embedding.calculate_trend("god_class", months=6)
        assert trend == "emerging"

    def test_calculate_trend_declining(self):
        """Test trend calculation for declining patterns"""
        embedding = TemporalEmbedding()

        old_date = datetime.now() - timedelta(days=200)
        recent_date = datetime.now()

        # Add many old occurrences
        for i in range(5):
            embedding.add_pattern(
                PatternOccurrence("god_class", f"{i}.py", 1, f"h{i}", old_date, "high")
            )

        # Add few recent occurrences
        embedding.add_pattern(
            PatternOccurrence("god_class", "a.py", 1, "a", recent_date, "high")
        )

        trend = embedding.calculate_trend("god_class", months=6)
        assert trend == "declining"

    def test_calculate_trend_stable(self):
        """Test trend calculation for stable patterns"""
        embedding = TemporalEmbedding()

        old_date = datetime.now() - timedelta(days=200)
        recent_date = datetime.now()

        # Add equal old and recent occurrences
        for i in range(3):
            embedding.add_pattern(
                PatternOccurrence(
                    "god_class", f"old{i}.py", 1, f"o{i}", old_date, "high"
                )
            )
            embedding.add_pattern(
                PatternOccurrence(
                    "god_class", f"new{i}.py", 1, f"n{i}", recent_date, "high"
                )
            )

        trend = embedding.calculate_trend("god_class", months=6)
        assert trend == "stable"


class TestPatternEvolutionTracker:
    """Tests for PatternEvolutionTracker"""

    def test_track_pattern(self):
        """Test tracking pattern occurrences"""
        tracker = PatternEvolutionTracker()

        now = datetime.now()
        occurrence = PatternOccurrence("god_class", "test.py", 10, "abc", now, "high")

        tracker.track_pattern(occurrence)

        assert len(tracker.lifecycles) == 1
        assert "god_class" in tracker.temporal_embedding.pattern_timeline

    def test_find_lifecycle(self):
        """Test finding existing lifecycle"""
        tracker = PatternEvolutionTracker()

        now = datetime.now()
        occurrence1 = PatternOccurrence("god_class", "test.py", 10, "abc", now, "high")
        occurrence2 = PatternOccurrence(
            "god_class", "test.py", 12, "def", now + timedelta(days=1), "high"
        )

        tracker.track_pattern(occurrence1)
        tracker.track_pattern(occurrence2)

        # Should reuse same lifecycle (within drift tolerance)
        assert len(tracker.lifecycles) == 1
        assert len(tracker.lifecycles[0].occurrences) == 2

    def test_get_emerging_patterns(self):
        """Test getting emerging patterns"""
        tracker = PatternEvolutionTracker()

        old_date = datetime.now() - timedelta(days=200)
        recent_date = datetime.now()

        # Add old occurrence
        tracker.track_pattern(
            PatternOccurrence("god_class", "a.py", 1, "a", old_date, "high")
        )

        # Add many recent occurrences (threshold is 5)
        for i in range(6):
            tracker.track_pattern(
                PatternOccurrence(
                    "god_class", f"{i}.py", 1, f"h{i}", recent_date, "high"
                )
            )

        emerging = tracker.get_emerging_patterns(threshold=5)

        assert len(emerging) == 1
        assert emerging[0]["pattern_type"] == "god_class"
        assert emerging[0]["trend"] == "emerging"

    def test_get_pattern_adoption_rate(self):
        """Test calculating adoption rate"""
        tracker = PatternEvolutionTracker()

        start = datetime.now() - timedelta(days=60)  # 2 months ago

        # Add occurrences over 2 months (6 total)
        for i in range(6):
            date = start + timedelta(days=i * 10)
            tracker.track_pattern(
                PatternOccurrence("god_class", f"{i}.py", 1, f"h{i}", date, "high")
            )

        rate = tracker.get_pattern_adoption_rate("god_class")

        # Should be ~3 occurrences per month (6 over 2 months)
        assert 2.0 < rate < 4.0


class TestRefactoringDetector:
    """Tests for RefactoringDetector"""

    def test_assess_refactoring_success(self):
        """Test assessing refactoring success"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = GitHistoryCrawler(tmpdir)
            detector = RefactoringDetector(crawler)

            result = detector.assess_refactoring_success("abc123")

            assert "commit" in result
            assert "success" in result
            assert "metrics" in result


class TestCodeEvolutionMiner:
    """Tests for CodeEvolutionMiner"""

    def test_init(self):
        """Test miner initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            miner = CodeEvolutionMiner(tmpdir)

            assert miner.repo_path == tmpdir
            assert miner.crawler is not None
            assert miner.tracker is not None
            assert miner.refactoring_detector is not None

    def test_generate_timeline_data(self):
        """Test timeline generation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            miner = CodeEvolutionMiner(tmpdir)

            # Add some patterns
            now = datetime.now()
            occurrence = PatternOccurrence(
                "god_class", "test.py", 10, "abc", now, "high"
            )
            miner.tracker.track_pattern(occurrence)

            timeline = miner.generate_timeline_data()

            assert "timeline" in timeline
            assert isinstance(timeline["timeline"], list)

    def test_get_pattern_metrics(self):
        """Test getting pattern metrics"""
        with tempfile.TemporaryDirectory() as tmpdir:
            miner = CodeEvolutionMiner(tmpdir)

            # Add patterns
            now = datetime.now()
            for i in range(3):
                occurrence = PatternOccurrence(
                    "god_class", f"{i}.py", 1, f"h{i}", now, "high"
                )
                miner.tracker.track_pattern(occurrence)

            metrics = miner.get_pattern_metrics()

            assert "god_class" in metrics
            assert metrics["god_class"]["total_occurrences"] == 3
            assert "trend" in metrics["god_class"]
            assert "adoption_rate" in metrics["god_class"]
