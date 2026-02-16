# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Evolution Mining from Git History
Issue #243 - Parent Epic: #217 - Advanced Code Intelligence

Analyzes git history to understand how code patterns evolve, identifies emerging
patterns, and detects deprecated practices.

Features:
- Git history parsing and analysis
- Temporal pattern tracking
- Pattern lifecycle identification
- Refactoring detection
- Evolution reports and visualizations
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from code_intelligence.anti_pattern_detector import AntiPatternDetector

logger = logging.getLogger(__name__)


class PatternOccurrence:
    """Single occurrence of a pattern at a point in time"""

    def __init__(
        self,
        pattern_type: str,
        file_path: str,
        line_number: int,
        commit_hash: str,
        timestamp: datetime,
        severity: str,
    ):
        self.pattern_type = pattern_type
        self.file_path = file_path
        self.line_number = line_number
        self.commit_hash = commit_hash
        self.timestamp = timestamp
        self.severity = severity


class PatternLifecycle:
    """Lifecycle of a specific pattern instance"""

    def __init__(self, pattern_type: str, file_path: str, line_number: int):
        self.pattern_type = pattern_type
        self.file_path = file_path
        self.line_number = line_number
        self.first_seen: Optional[datetime] = None
        self.last_seen: Optional[datetime] = None
        self.occurrences: List[PatternOccurrence] = []
        self.status: str = "active"  # active, resolved, migrated

    def add_occurrence(self, occurrence: PatternOccurrence):
        """Add an occurrence to the lifecycle"""
        self.occurrences.append(occurrence)
        if self.first_seen is None or occurrence.timestamp < self.first_seen:
            self.first_seen = occurrence.timestamp
        if self.last_seen is None or occurrence.timestamp > self.last_seen:
            self.last_seen = occurrence.timestamp

    def get_lifespan_days(self) -> int:
        """Calculate lifespan in days"""
        if self.first_seen and self.last_seen:
            return (self.last_seen - self.first_seen).days
        return 0


class GitHistoryCrawler:
    """Crawls git history to extract code changes"""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        try:
            import git

            self.repo = git.Repo(repo_path)
        except ImportError:
            logger.warning("GitPython not installed. Using fallback git commands.")
            self.repo = None
        except Exception as e:
            logger.error("Failed to initialize git repository: %s", e)
            self.repo = None

    def get_commits_in_range(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get commits within a date range"""
        if self.repo is None:
            return []

        commits = []
        try:
            all_commits = list(self.repo.iter_commits("HEAD"))

            for commit in all_commits:
                commit_date = datetime.fromtimestamp(commit.committed_date)

                # Filter by date range
                if start_date and commit_date < start_date:
                    continue
                if end_date and commit_date > end_date:
                    continue

                commits.append(
                    {
                        "hash": commit.hexsha,
                        "message": commit.message.strip(),
                        "author": commit.author.name,
                        "timestamp": commit_date,
                        "stats": commit.stats.total,
                    }
                )

        except Exception as e:
            logger.error("Failed to retrieve commits: %s", e)

        return commits

    def get_file_history(self, file_path: str) -> List[Dict]:
        """Get commit history for a specific file"""
        if self.repo is None:
            return []

        commits = []
        try:
            for commit in self.repo.iter_commits(paths=file_path):
                commits.append(
                    {
                        "hash": commit.hexsha,
                        "message": commit.message.strip(),
                        "timestamp": datetime.fromtimestamp(commit.committed_date),
                    }
                )
        except Exception as e:
            logger.error("Failed to get file history for %s: %s", file_path, e)

        return commits

    def detect_refactoring_commits(self) -> List[Dict]:
        """Detect commits that likely contain refactorings"""
        refactoring_keywords = [
            "refactor",
            "restructure",
            "reorganize",
            "cleanup",
            "simplify",
            "extract method",
            "rename",
            "move",
        ]

        refactoring_commits = []
        commits = self.get_commits_in_range()

        for commit in commits:
            message_lower = commit["message"].lower()

            # Check for refactoring keywords
            if any(keyword in message_lower for keyword in refactoring_keywords):
                commit["refactoring_type"] = self._classify_refactoring(message_lower)
                refactoring_commits.append(commit)

            # Check for high churn (many files changed)
            elif commit["stats"]["files"] > 10:
                commit["refactoring_type"] = "large_scale_refactoring"
                refactoring_commits.append(commit)

        return refactoring_commits

    def _classify_refactoring(self, message: str) -> str:
        """Classify refactoring type from commit message"""
        if "extract" in message:
            return "extract_method"
        elif "rename" in message:
            return "rename"
        elif "move" in message:
            return "move_code"
        elif "simplify" in message or "cleanup" in message:
            return "simplification"
        elif "restructure" in message or "reorganize" in message:
            return "structural"
        else:
            return "general_refactoring"


class TemporalEmbedding:
    """Tracks pattern occurrences over time"""

    def __init__(self):
        self.pattern_timeline: Dict[str, List[PatternOccurrence]] = defaultdict(list)

    def add_pattern(self, occurrence: PatternOccurrence):
        """Add a pattern occurrence to the timeline"""
        self.pattern_timeline[occurrence.pattern_type].append(occurrence)

    def get_pattern_counts_by_month(self) -> Dict[str, Dict[str, int]]:
        """Get pattern counts grouped by month"""
        monthly_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        for pattern_type, occurrences in self.pattern_timeline.items():
            for occurrence in occurrences:
                month_key = occurrence.timestamp.strftime("%Y-%m")
                monthly_counts[month_key][pattern_type] += 1

        return dict(monthly_counts)

    def calculate_trend(self, pattern_type: str, months: int = 6) -> str:
        """Calculate trend (emerging/stable/declining) for a pattern"""
        if pattern_type not in self.pattern_timeline:
            return "unknown"

        occurrences = self.pattern_timeline[pattern_type]
        if len(occurrences) < 2:
            return "insufficient_data"

        # Get recent vs old occurrences
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        recent = sum(1 for occ in occurrences if occ.timestamp > cutoff_date)
        old = len(occurrences) - recent

        if old == 0:
            return "emerging"

        ratio = recent / old if old > 0 else float("inf")

        if ratio > 1.5:
            return "emerging"
        elif ratio < 0.5:
            return "declining"
        else:
            return "stable"


class PatternEvolutionTracker:
    """Tracks pattern lifecycles and evolution"""

    def __init__(self):
        self.lifecycles: List[PatternLifecycle] = []
        self.temporal_embedding = TemporalEmbedding()

    def track_pattern(self, occurrence: PatternOccurrence):
        """Track a pattern occurrence"""
        # Add to temporal embedding
        self.temporal_embedding.add_pattern(occurrence)

        # Find or create lifecycle
        lifecycle = self._find_lifecycle(
            occurrence.pattern_type, occurrence.file_path, occurrence.line_number
        )

        if lifecycle is None:
            lifecycle = PatternLifecycle(
                occurrence.pattern_type, occurrence.file_path, occurrence.line_number
            )
            self.lifecycles.append(lifecycle)

        lifecycle.add_occurrence(occurrence)

    def _find_lifecycle(
        self, pattern_type: str, file_path: str, line_number: int
    ) -> Optional[PatternLifecycle]:
        """Find existing lifecycle for a pattern"""
        for lifecycle in self.lifecycles:
            if (
                lifecycle.pattern_type == pattern_type
                and lifecycle.file_path == file_path
                and abs(lifecycle.line_number - line_number) < 10  # Allow some drift
            ):
                return lifecycle
        return None

    def get_emerging_patterns(self, threshold: int = 5) -> List[Dict]:
        """Get patterns that are emerging (increasing in frequency)"""
        emerging = []

        for pattern_type in self.temporal_embedding.pattern_timeline.keys():
            trend = self.temporal_embedding.calculate_trend(pattern_type)

            if trend == "emerging":
                occurrences = self.temporal_embedding.pattern_timeline[pattern_type]
                if len(occurrences) >= threshold:
                    emerging.append(
                        {
                            "pattern_type": pattern_type,
                            "count": len(occurrences),
                            "trend": "emerging",
                            "first_seen": min(occ.timestamp for occ in occurrences),
                            "last_seen": max(occ.timestamp for occ in occurrences),
                        }
                    )

        return emerging

    def get_declining_patterns(self) -> List[Dict]:
        """Get patterns that are declining (decreasing in frequency)"""
        declining = []

        for pattern_type in self.temporal_embedding.pattern_timeline.keys():
            trend = self.temporal_embedding.calculate_trend(pattern_type)

            if trend == "declining":
                occurrences = self.temporal_embedding.pattern_timeline[pattern_type]
                declining.append(
                    {
                        "pattern_type": pattern_type,
                        "count": len(occurrences),
                        "trend": "declining",
                        "first_seen": min(occ.timestamp for occ in occurrences),
                        "last_seen": max(occ.timestamp for occ in occurrences),
                    }
                )

        return declining

    def get_pattern_adoption_rate(self, pattern_type: str) -> float:
        """Calculate adoption rate (occurrences per month)"""
        if pattern_type not in self.temporal_embedding.pattern_timeline:
            return 0.0

        occurrences = self.temporal_embedding.pattern_timeline[pattern_type]
        if len(occurrences) < 2:
            return 0.0

        first = min(occ.timestamp for occ in occurrences)
        last = max(occ.timestamp for occ in occurrences)
        months = max(1, (last - first).days / 30)

        return len(occurrences) / months


class RefactoringDetector:
    """Detects successful refactorings in git history"""

    def __init__(self, crawler: GitHistoryCrawler):
        self.crawler = crawler

    def detect_refactorings(self) -> List[Dict]:
        """Detect refactoring events"""
        return self.crawler.detect_refactoring_commits()

    def assess_refactoring_success(self, commit_hash: str) -> Dict:
        """Assess if a refactoring was successful"""
        # Placeholder for refactoring success assessment
        # Would analyze code quality metrics before/after refactoring
        return {
            "commit": commit_hash,
            "success": True,  # Placeholder
            "metrics": {"complexity_change": 0, "pattern_count_change": 0},
        }


class CodeEvolutionMiner:
    """Main class for code evolution mining"""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.crawler = GitHistoryCrawler(repo_path)
        self.tracker = PatternEvolutionTracker()
        self.refactoring_detector = RefactoringDetector(self.crawler)
        self.anti_pattern_detector = AntiPatternDetector()

    def analyze_evolution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        """Analyze code evolution over time"""
        logger.info("Starting code evolution analysis for %s", self.repo_path)

        # Get commits in range
        commits = self.crawler.get_commits_in_range(start_date, end_date)

        # Analyze patterns in each commit
        for commit in commits[:100]:  # Limit to 100 commits for performance
            self._analyze_commit_patterns(commit)

        # Generate report
        report = {
            "repo_path": str(self.repo_path),
            "analysis_period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "commits_analyzed": len(commits),
            "emerging_patterns": self.tracker.get_emerging_patterns(),
            "declining_patterns": self.tracker.get_declining_patterns(),
            "pattern_timeline": self.tracker.temporal_embedding.get_pattern_counts_by_month(),
            "refactorings": self.refactoring_detector.detect_refactorings()[:20],
        }

        logger.info("Code evolution analysis complete")
        return report

    def _analyze_commit_patterns(self, commit: Dict):
        """Analyze patterns in a commit"""
        if self.repo is None or self.crawler.repo is None:
            return

        try:
            # Get the commit object
            commit_obj = self.crawler.repo.commit(commit["hash"])

            # Analyze each changed file
            for item in commit_obj.stats.files.keys():
                # Only analyze Python files
                if not item.endswith(".py"):
                    continue

                file_path = self.repo_path / item

                # Skip if file doesn't exist (might be deleted)
                if not file_path.exists():
                    continue

                # Analyze file for anti-patterns
                try:
                    with open(file_path, encoding="utf-8") as f:
                        code = f.read()

                    # Use anti-pattern detector
                    results = self.anti_pattern_detector.analyze_code(
                        code, str(file_path)
                    )

                    # Track each detected pattern
                    for result in results.patterns:
                        occurrence = PatternOccurrence(
                            pattern_type=result.type.value,
                            file_path=str(item),
                            line_number=result.line_number,
                            commit_hash=commit["hash"],
                            timestamp=commit["timestamp"],
                            severity=result.severity.value,
                        )
                        self.tracker.track_pattern(occurrence)

                except (IOError, OSError) as e:
                    logger.warning("Failed to analyze %s: %s", file_path, e)
                    continue

        except Exception as e:
            logger.error("Failed to analyze commit %s: %s", commit["hash"], e)

    def generate_timeline_data(self) -> Dict:
        """Generate timeline visualization data"""
        monthly_counts = self.tracker.temporal_embedding.get_pattern_counts_by_month()

        # Format for visualization
        timeline = []
        for month, patterns in sorted(monthly_counts.items()):
            timeline.append({"month": month, "patterns": patterns})

        return {"timeline": timeline}

    def get_pattern_metrics(self) -> Dict:
        """Get metrics about pattern evolution"""
        metrics = {}

        for pattern_type in self.tracker.temporal_embedding.pattern_timeline.keys():
            occurrences = self.tracker.temporal_embedding.pattern_timeline[pattern_type]

            metrics[pattern_type] = {
                "total_occurrences": len(occurrences),
                "trend": self.tracker.temporal_embedding.calculate_trend(pattern_type),
                "adoption_rate": self.tracker.get_pattern_adoption_rate(pattern_type),
                "first_seen": (
                    min(occ.timestamp for occ in occurrences).isoformat()
                    if occurrences
                    else None
                ),
                "last_seen": (
                    max(occ.timestamp for occ in occurrences).isoformat()
                    if occurrences
                    else None
                ),
            }

        return metrics
