# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import subprocess  # nosec B404  # read-only git log for co-change coupling (#13639)
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from code_intelligence.anti_pattern_detector import AntiPatternDetector

logger = get_logger(__name__)

# #13639: a commit touching more files than this is a bulk rename, a vendored-tree
# import or a reformat — not a coupling signal. Left uncapped, one 400-file commit
# contributes ~80k pair updates and drowns every real pair beneath it. Cost is
# quadratic in files-per-commit, so the cap is what keeps the walk affordable.
MAX_FILES_PER_COMMIT: int = env_int("AUTOBOT_COCHANGE_MAX_FILES_PER_COMMIT", default=50)

# Bound on the history walk; never a literal at the call site.
_GIT_TIMEOUT_SECONDS: int = env_int("AUTOBOT_COCHANGE_GIT_TIMEOUT_SECONDS", default=120)

# Paths that co-change because a tool wrote them, not because they depend on each
# other. Lockfiles are the clearest case: every dependency bump touches all of them.
_COCHANGE_SKIP_DIRS: frozenset = frozenset(
    {"node_modules", "venv", ".venv", "dist", "build", "__pycache__", ".git", "vendor", "third_party"}
)


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
        self.first_seen: datetime | None = None
        self.last_seen: datetime | None = None
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


def _run_git(repo_path: str, *args: str) -> str:
    """Run a read-only git command; empty string on any failure (#13639).

    The git binary is present wherever the repository is, which GitPython is not.
    """
    try:
        completed = subprocess.run(  # nosec B603 B607  # fixed argv, shell=False, no user-supplied option
            # -c core.quotepath=false: without it git C-quotes any non-ASCII path
            # ("lat\\303\\253le.py"), so the key depends on the reader's git config
            # and can never match a filesystem-derived path. errors="replace"
            # because a path byte that is not valid UTF-8 must not raise a
            # ValueError that the except clause below does not even catch.
            ["git", "-c", "core.quotepath=false", "-C", repo_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.warning("git %s failed in %s: %s", args, repo_path, exc)
        return ""
    if completed.returncode != 0:
        # Without this, a timeout, a non-repo path and a genuinely empty window
        # are the same empty string to the caller — the silent-computes-nothing
        # shape this method was written to get away from.
        logger.warning("git %s exited %s in %s: %s", args, completed.returncode, repo_path, completed.stderr.strip())
        return ""
    return completed.stdout


# #13832: NUL separates commits, RS separates fields. RS (0x1e) cannot appear in a
# commit message in practice, and putting the raw body last keeps a multi-line
# message from being mistaken for the numstat block that follows it.
_COMMIT_FORMAT = "--pretty=format:%x00%H%x1e%at%x1e%an%x1e%B%x1e"


def _parse_commit_block(block: str) -> "dict | None":
    """Turn one ``git log`` block into the dict shape callers already expect.

    Returns None for a block that is not a commit — notably the empty leading
    one produced by the NUL that precedes the first record.
    """
    if not block.strip():
        return None
    parts = block.split("\x1e")
    if len(parts) < 5:
        return None
    commit_hash, timestamp, author, message = parts[0], parts[1], parts[2], parts[3]
    if not commit_hash.strip() or not timestamp.strip().isdigit():
        return None
    return {
        "hash": commit_hash.strip(),
        "message": message.strip(),
        "author": author.strip(),
        # #13162: tz-aware UTC. A naive datetime here crashed calculate_trend,
        # which compares against datetime.now(tz=timezone.utc), and made month
        # bucketing depend on the server's local timezone.
        "timestamp": datetime.fromtimestamp(int(timestamp.strip()), tz=timezone.utc),
        "stats": _parse_numstat(parts[4]),
    }


def _parse_numstat(numstat: str) -> Dict[str, int]:
    """Totals from ``--numstat`` lines, matching GitPython's ``stats.total`` keys.

    A binary file is reported by git as ``-\t-\tpath``; it counts as a changed
    file with zero line changes rather than being dropped or crashing the parse.
    """
    files = insertions = deletions = 0
    for line in numstat.splitlines():
        columns = line.split("\t")
        if len(columns) < 3:
            continue
        files += 1
        added, removed = columns[0], columns[1]
        insertions += int(added) if added.isdigit() else 0
        deletions += int(removed) if removed.isdigit() else 0
    return {"files": files, "insertions": insertions, "deletions": deletions, "lines": insertions + deletions}


def _is_vendored_path(path: str) -> bool:
    """True for paths whose co-changes come from tooling rather than from design."""
    return any(part in _COCHANGE_SKIP_DIRS for part in PurePosixPath(path).parts)


class GitHistoryCrawler:
    """Crawls git history to extract code changes"""

    def __init__(self, repo_path: str):
        """#13832: reads the git binary. GitPython was imported here and nowhere
        else, and appeared in no requirements file, so ``self.repo`` was always
        ``None`` and every method returned ``[]`` in every environment since this
        class was written. The ``except ImportError`` even logged "Using fallback
        git commands" — there were none, which is how a wholly inert subsystem
        read as a handled degradation.
        """
        self.repo_path = Path(repo_path)
        self.available = _run_git(str(self.repo_path), "rev-parse", "--git-dir") != ""
        if not self.available:
            logger.warning("GitHistoryCrawler: %s is not a git repository — history is unavailable", repo_path)

    def get_commits_in_range(self, start_date: datetime | None = None, end_date: datetime | None = None) -> List[Dict]:
        """Get commits within a date range (#13832: via the git binary)."""
        if not self.available:
            return []

        args = ["log", _COMMIT_FORMAT, "--numstat"]
        if start_date:
            args.append(f"--since={start_date.isoformat()}")
        if end_date:
            args.append(f"--until={end_date.isoformat()}")
        output = _run_git(str(self.repo_path), *args)
        return [c for block in output.split("\x00") if (c := _parse_commit_block(block)) is not None]

    def get_file_history(self, file_path: str) -> List[Dict]:
        """Get commit history for a specific file (#13832: via the git binary)."""
        if not self.available:
            return []

        # `--` separates revisions from paths, so a path that looks like a flag
        # or a ref cannot be reinterpreted as one.
        output = _run_git(str(self.repo_path), "log", _COMMIT_FORMAT, "--numstat", "--", file_path)
        return [
            {"hash": c["hash"], "message": c["message"], "timestamp": c["timestamp"]}
            for block in output.split("\x00")
            if (c := _parse_commit_block(block)) is not None
        ]

    def get_commit_file_sets(self, since: "datetime | None" = None) -> "list[set[str]]":
        """Return the changed-path set for **every** commit in the window (#13639).

        Every commit, including single-file ones. That is not incidental: the
        co-change denominator is "how often did this file change", and dropping
        solo commits here would silently redefine it as "how often did it change
        alongside something else". On this repository 32% of commits touch one
        file, and excluding them inflated 44% of reported pairs past the
        threshold — the precise noise the normalised formula exists to reject.

        Deciding which commits are *too large to pair* is an analysis question,
        so it belongs to ``CoChangeAnalyzer``, not here. This method reports
        history; it does not judge it.

        Reads the git binary rather than GitPython. The rest of this class goes
        through ``self.repo``, which is **always ``None``** — GitPython appears
        in no requirements file and is imported in exactly one place, the ``try``
        block above, so every other method here returns ``[]`` in every
        environment (#13832).
        """
        args = ["log", "--no-merges", "--pretty=format:%x00%H", "--name-only"]
        if since is not None:
            args.append(f"--since={since.isoformat()}")
        output = _run_git(str(self.repo_path), *args)
        if not output:
            return []

        file_sets: list[set[str]] = []
        for block in output.split("\x00"):
            paths = {line for line in block.splitlines()[1:] if line.strip() and not _is_vendored_path(line)}
            if paths:
                file_sets.append(paths)
        return file_sets

    def get_commit_files(self, commit_hash: str) -> List[str]:
        """Paths changed by one commit (#13832).

        Replaces ``crawler.repo.commit(hash).stats.files`` — the GitPython call
        that could never run.
        """
        if not self.available:
            return []
        # `--` guards against a hash-shaped string being read as a path.
        output = _run_git(str(self.repo_path), "show", "--pretty=format:", "--name-only", commit_hash, "--")
        return [line for line in output.splitlines() if line.strip()]

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
        monthly_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

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
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=months * 30)
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
        lifecycle = self._find_lifecycle(occurrence.pattern_type, occurrence.file_path, occurrence.line_number)

        if lifecycle is None:
            lifecycle = PatternLifecycle(occurrence.pattern_type, occurrence.file_path, occurrence.line_number)
            self.lifecycles.append(lifecycle)

        lifecycle.add_occurrence(occurrence)

    def _find_lifecycle(self, pattern_type: str, file_path: str, line_number: int) -> PatternLifecycle | None:
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
        # #13832: was a bare str, and `self.repo_path / item` below is a Path
        # operation. It never raised because the guard above it short-circuited
        # on an attribute that was always None — the moment history became real,
        # every commit failed with "unsupported operand type(s) for /".
        self.repo_path = Path(repo_path)
        self.crawler = GitHistoryCrawler(repo_path)
        self.tracker = PatternEvolutionTracker()
        self.refactoring_detector = RefactoringDetector(self.crawler)
        self.anti_pattern_detector = AntiPatternDetector()

    def analyze_evolution(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
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
        # #13832: was `self.repo is None or self.crawler.repo is None` — an
        # attribute this class never had (`AttributeError` the moment the crawler
        # returned anything) guarded by one that was always None, so the guard
        # short-circuited before the broken half could raise. Now that history is
        # real, both go through the crawler's own availability flag.
        if not self.crawler.available:
            return

        try:
            changed_files = self.crawler.get_commit_files(commit["hash"])

            # Analyze each changed file
            for item in changed_files:
                # Only analyze Python files
                if not item.endswith(".py"):
                    continue

                file_path = self.repo_path / item

                # Skip if file doesn't exist (might be deleted)
                if not file_path.exists():
                    continue

                # Analyze file for anti-patterns
                try:
                    # #6757: analyze_code() never existed; use analyze_file()
                    # which returns {"anti_patterns": [dict, ...], ...}.
                    result_dict = self.anti_pattern_detector.analyze_file(str(file_path))

                    # Track each detected pattern
                    for ap in result_dict.get("anti_patterns", []):
                        occurrence = PatternOccurrence(
                            pattern_type=ap.get("pattern_type", "unknown"),
                            file_path=str(item),
                            line_number=ap.get("line_number", 0),
                            commit_hash=commit["hash"],
                            timestamp=commit["timestamp"],
                            severity=ap.get("severity", "low"),
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
                "first_seen": (min(occ.timestamp for occ in occurrences).isoformat() if occurrences else None),
                "last_seen": (max(occ.timestamp for occ in occurrences).isoformat() if occurrences else None),
            }

        return metrics
