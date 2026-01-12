# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Ownership and Expertise Analyzer (Issue #248)

Analyzes codebase for:
- Code ownership by author/contributor
- Expertise scoring per file and directory
- Knowledge gap detection (bus factor risk)
- Team coverage analysis
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Issue #542: Handle imports for both standalone execution and backend import
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from src.utils.redis_client import get_redis_client
    from src.config import UnifiedConfig
    _REDIS_AVAILABLE = True
    _CONFIG_AVAILABLE = True
except ImportError:
    get_redis_client = None
    UnifiedConfig = None
    _REDIS_AVAILABLE = False
    _CONFIG_AVAILABLE = False


config = UnifiedConfig() if _CONFIG_AVAILABLE else None
logger = logging.getLogger(__name__)

# Directories to skip during analysis
_SKIP_DIRECTORIES = (
    '__pycache__', '.git', 'node_modules', '.venv', 'venv', 'env',
    '.pytest_cache', '.mypy_cache', '.tox', 'htmlcov',
    'dist', 'build', 'egg-info', '.eggs',
)

# File patterns to skip
_SKIP_FILE_PATTERNS = (
    '__init__.py',
    '.pyc', '.pyo',
    '.min.js', '.min.css',
    '.lock', '.sum',
)


@dataclass
class AuthorContribution:
    """Represents an author's contribution to a file or directory"""
    author_name: str
    author_email: str
    lines_count: int
    lines_percentage: float
    commits_count: int
    first_commit_date: Optional[datetime] = None
    last_commit_date: Optional[datetime] = None
    files_touched: List[str] = field(default_factory=list)


@dataclass
class FileOwnership:
    """Ownership details for a single file"""
    file_path: str
    total_lines: int
    primary_owner: Optional[str]
    ownership_percentage: float
    contributors: List[AuthorContribution] = field(default_factory=list)
    bus_factor: int = 1  # Number of people who could maintain this file
    knowledge_risk: str = "low"  # low, medium, high, critical
    last_modified: Optional[datetime] = None


@dataclass
class DirectoryOwnership:
    """Ownership details for a directory"""
    directory_path: str
    total_files: int
    total_lines: int
    primary_owner: Optional[str]
    ownership_percentage: float
    contributors: List[AuthorContribution] = field(default_factory=list)
    bus_factor: int = 1
    knowledge_risk: str = "low"


@dataclass
class ExpertiseScore:
    """Expertise score for an author"""
    author_name: str
    author_email: str
    total_lines_authored: int
    total_commits: int
    files_owned: int  # Files where they are primary owner
    directories_owned: int
    expertise_areas: List[str] = field(default_factory=list)  # Top directories
    recency_score: float = 0.0  # 0-100, based on recent activity
    impact_score: float = 0.0  # 0-100, based on lines/commits
    overall_score: float = 0.0  # Combined expertise score


@dataclass
class KnowledgeGap:
    """Represents a knowledge gap in the codebase"""
    area: str  # File or directory path
    gap_type: str  # single_contributor, inactive_owner, no_recent_changes
    risk_level: str  # low, medium, high, critical
    description: str
    recommendation: str
    affected_lines: int = 0


class OwnershipAnalyzer:
    """Analyzes code ownership, expertise, and knowledge gaps"""

    def __init__(self, redis_client=None):
        if redis_client is not None:
            self.redis_client = redis_client
        elif _REDIS_AVAILABLE and get_redis_client is not None:
            self.redis_client = get_redis_client(async_client=True)
        else:
            self.redis_client = None
            logger.info("Redis not available - caching disabled for OwnershipAnalyzer")
        self.config = config

        # Caching keys
        self.OWNERSHIP_KEY = "ownership_analysis:files"
        self.EXPERTISE_KEY = "ownership_analysis:expertise"
        self.GAPS_KEY = "ownership_analysis:gaps"

        logger.info("OwnershipAnalyzer initialized")

    async def analyze_ownership(
        self,
        root_path: str = ".",
        patterns: Optional[List[str]] = None,
        days_for_recency: int = 90
    ) -> Dict[str, Any]:
        """
        Analyze code ownership for the entire codebase.

        Args:
            root_path: Root path to analyze
            patterns: File patterns to include (default: Python, TypeScript, Vue)
            days_for_recency: Days to consider for recency scoring

        Returns:
            Dictionary with ownership analysis results
        """
        start_time = time.time()
        patterns = patterns or ["**/*.py", "**/*.ts", "**/*.vue", "**/*.js"]

        await self._clear_cache()

        logger.info(f"Analyzing code ownership in {root_path}")

        # Get git blame data for all files
        file_ownerships = await self._analyze_file_ownership(root_path, patterns)
        logger.info(f"Analyzed ownership for {len(file_ownerships)} files")

        # Aggregate to directory level
        directory_ownerships = self._aggregate_directory_ownership(file_ownerships)
        logger.info(f"Aggregated to {len(directory_ownerships)} directories")

        # Calculate expertise scores
        expertise_scores = self._calculate_expertise_scores(
            file_ownerships,
            directory_ownerships,
            days_for_recency
        )
        logger.info(f"Calculated expertise for {len(expertise_scores)} contributors")

        # Detect knowledge gaps
        knowledge_gaps = self._detect_knowledge_gaps(
            file_ownerships,
            directory_ownerships,
            days_for_recency
        )
        logger.info(f"Detected {len(knowledge_gaps)} knowledge gaps")

        # Calculate metrics
        metrics = self._calculate_metrics(
            file_ownerships,
            directory_ownerships,
            expertise_scores,
            knowledge_gaps
        )

        analysis_time = time.time() - start_time

        results = {
            "status": "success",
            "analysis_time_seconds": analysis_time,
            "summary": {
                "total_files": len(file_ownerships),
                "total_directories": len(directory_ownerships),
                "total_contributors": len(expertise_scores),
                "knowledge_gaps_count": len(knowledge_gaps),
                "critical_gaps": len([g for g in knowledge_gaps if g.risk_level == "critical"]),
                "high_risk_gaps": len([g for g in knowledge_gaps if g.risk_level == "high"]),
            },
            "file_ownership": [self._serialize_file_ownership(f) for f in file_ownerships[:100]],
            "directory_ownership": [self._serialize_directory_ownership(d) for d in directory_ownerships],
            "expertise_scores": [self._serialize_expertise(e) for e in expertise_scores],
            "knowledge_gaps": [self._serialize_gap(g) for g in knowledge_gaps],
            "metrics": metrics,
        }

        await self._cache_results(results)
        logger.info(f"Ownership analysis complete in {analysis_time:.2f}s")

        return results

    async def _analyze_file_ownership(
        self,
        root_path: str,
        patterns: List[str]
    ) -> List[FileOwnership]:
        """Analyze ownership for individual files using git blame"""
        file_ownerships = []
        root = Path(root_path).resolve()

        for pattern in patterns:
            for file_path in root.glob(pattern):
                if not file_path.is_file() or self._should_skip_file(file_path):
                    continue

                ownership = await self._get_file_ownership(file_path, root)
                if ownership:
                    file_ownerships.append(ownership)

        # Sort by total lines descending
        file_ownerships.sort(key=lambda x: x.total_lines, reverse=True)
        return file_ownerships

    async def _get_file_ownership(
        self,
        file_path: Path,
        root: Path
    ) -> Optional[FileOwnership]:
        """Get ownership data for a single file using git blame"""
        try:
            relative_path = str(file_path.relative_to(root))

            # Run git blame to get line-by-line authorship
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", str(file_path)],
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=30
            )

            if result.returncode != 0:
                return None

            # Parse git blame output
            author_lines: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"lines": 0, "email": "", "dates": []}
            )
            total_lines = 0
            current_author = ""
            current_email = ""
            current_date = None

            for line in result.stdout.splitlines():
                if line.startswith("author "):
                    current_author = line[7:].strip()
                elif line.startswith("author-mail "):
                    current_email = line[12:].strip().strip("<>")
                elif line.startswith("author-time "):
                    try:
                        timestamp = int(line[12:].strip())
                        current_date = datetime.fromtimestamp(timestamp)
                    except (ValueError, OSError):
                        current_date = None
                elif line.startswith("\t"):  # Actual code line
                    if current_author and current_author != "Not Committed Yet":
                        author_lines[current_author]["lines"] += 1
                        author_lines[current_author]["email"] = current_email
                        if current_date:
                            author_lines[current_author]["dates"].append(current_date)
                        total_lines += 1

            if total_lines == 0:
                return None

            # Build contributor list
            contributors = []
            for author_name, data in author_lines.items():
                lines_count = data["lines"]
                dates = data["dates"]

                contrib = AuthorContribution(
                    author_name=author_name,
                    author_email=data["email"],
                    lines_count=lines_count,
                    lines_percentage=round((lines_count / total_lines) * 100, 1),
                    commits_count=len(set(dates)) if dates else 1,  # Approximate
                    first_commit_date=min(dates) if dates else None,
                    last_commit_date=max(dates) if dates else None,
                    files_touched=[relative_path]
                )
                contributors.append(contrib)

            # Sort by lines authored
            contributors.sort(key=lambda x: x.lines_count, reverse=True)

            # Determine primary owner
            primary_owner = contributors[0].author_name if contributors else None
            ownership_pct = contributors[0].lines_percentage if contributors else 0.0

            # Calculate bus factor (contributors with >10% ownership)
            significant_contributors = [c for c in contributors if c.lines_percentage >= 10]
            bus_factor = max(1, len(significant_contributors))

            # Determine knowledge risk
            knowledge_risk = self._calculate_knowledge_risk(
                bus_factor,
                contributors,
                total_lines
            )

            # Get last modified date
            last_modified = None
            for contrib in contributors:
                if contrib.last_commit_date:
                    if not last_modified or contrib.last_commit_date > last_modified:
                        last_modified = contrib.last_commit_date

            return FileOwnership(
                file_path=relative_path,
                total_lines=total_lines,
                primary_owner=primary_owner,
                ownership_percentage=ownership_pct,
                contributors=contributors[:10],  # Top 10 contributors
                bus_factor=bus_factor,
                knowledge_risk=knowledge_risk,
                last_modified=last_modified
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Git blame timed out for {file_path}")
            return None
        except Exception as e:
            logger.warning(f"Failed to analyze {file_path}: {e}")
            return None

    def _aggregate_directory_ownership(
        self,
        file_ownerships: List[FileOwnership]
    ) -> List[DirectoryOwnership]:
        """Aggregate file ownership to directory level"""
        dir_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "files": 0,
                "lines": 0,
                "author_lines": defaultdict(lambda: {"lines": 0, "email": "", "files": set()})
            }
        )

        for fo in file_ownerships:
            # Get parent directory
            dir_path = str(Path(fo.file_path).parent)
            if dir_path == ".":
                dir_path = "(root)"

            dir_data[dir_path]["files"] += 1
            dir_data[dir_path]["lines"] += fo.total_lines

            for contrib in fo.contributors:
                dir_data[dir_path]["author_lines"][contrib.author_name]["lines"] += contrib.lines_count
                dir_data[dir_path]["author_lines"][contrib.author_name]["email"] = contrib.author_email
                dir_data[dir_path]["author_lines"][contrib.author_name]["files"].add(fo.file_path)

        # Build directory ownership objects
        directory_ownerships = []
        for dir_path, data in dir_data.items():
            total_lines = data["lines"]
            contributors = []

            for author_name, author_data in data["author_lines"].items():
                contrib = AuthorContribution(
                    author_name=author_name,
                    author_email=author_data["email"],
                    lines_count=author_data["lines"],
                    lines_percentage=round((author_data["lines"] / total_lines) * 100, 1) if total_lines > 0 else 0,
                    commits_count=0,
                    files_touched=list(author_data["files"])
                )
                contributors.append(contrib)

            contributors.sort(key=lambda x: x.lines_count, reverse=True)

            primary_owner = contributors[0].author_name if contributors else None
            ownership_pct = contributors[0].lines_percentage if contributors else 0.0

            significant_contributors = [c for c in contributors if c.lines_percentage >= 10]
            bus_factor = max(1, len(significant_contributors))

            knowledge_risk = self._calculate_knowledge_risk(
                bus_factor,
                contributors,
                total_lines
            )

            directory_ownerships.append(DirectoryOwnership(
                directory_path=dir_path,
                total_files=data["files"],
                total_lines=total_lines,
                primary_owner=primary_owner,
                ownership_percentage=ownership_pct,
                contributors=contributors[:10],
                bus_factor=bus_factor,
                knowledge_risk=knowledge_risk
            ))

        # Sort by total lines descending
        directory_ownerships.sort(key=lambda x: x.total_lines, reverse=True)
        return directory_ownerships

    def _calculate_expertise_scores(
        self,
        file_ownerships: List[FileOwnership],
        directory_ownerships: List[DirectoryOwnership],
        days_for_recency: int
    ) -> List[ExpertiseScore]:
        """Calculate expertise scores for all contributors"""
        author_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "email": "",
                "lines": 0,
                "commits": 0,
                "files_owned": 0,
                "dirs_owned": 0,
                "areas": set(),
                "last_activity": None
            }
        )

        # Aggregate from file ownerships
        for fo in file_ownerships:
            if fo.primary_owner:
                author_data[fo.primary_owner]["files_owned"] += 1

            for contrib in fo.contributors:
                author_data[contrib.author_name]["email"] = contrib.author_email
                author_data[contrib.author_name]["lines"] += contrib.lines_count
                author_data[contrib.author_name]["commits"] += contrib.commits_count

                if contrib.last_commit_date:
                    current = author_data[contrib.author_name]["last_activity"]
                    if not current or contrib.last_commit_date > current:
                        author_data[contrib.author_name]["last_activity"] = contrib.last_commit_date

        # Aggregate directory ownership
        for do in directory_ownerships:
            if do.primary_owner:
                author_data[do.primary_owner]["dirs_owned"] += 1
                author_data[do.primary_owner]["areas"].add(do.directory_path)

        # Calculate scores
        now = datetime.now()
        recency_cutoff = now - timedelta(days=days_for_recency)

        max_lines = max((d["lines"] for d in author_data.values()), default=1)
        max_commits = max((d["commits"] for d in author_data.values()), default=1)

        expertise_scores = []
        for author_name, data in author_data.items():
            # Recency score (0-100)
            recency_score = 0.0
            if data["last_activity"]:
                if data["last_activity"] >= recency_cutoff:
                    days_ago = (now - data["last_activity"]).days
                    recency_score = 100 * (1 - days_ago / days_for_recency)
                else:
                    recency_score = 0.0

            # Impact score (0-100) - weighted combination of lines and commits
            lines_score = (data["lines"] / max_lines) * 100 if max_lines > 0 else 0
            commits_score = (data["commits"] / max_commits) * 100 if max_commits > 0 else 0
            impact_score = (lines_score * 0.6 + commits_score * 0.4)

            # Overall score - weighted combination
            overall_score = (impact_score * 0.7 + recency_score * 0.3)

            expertise_scores.append(ExpertiseScore(
                author_name=author_name,
                author_email=data["email"],
                total_lines_authored=data["lines"],
                total_commits=data["commits"],
                files_owned=data["files_owned"],
                directories_owned=data["dirs_owned"],
                expertise_areas=sorted(data["areas"])[:5],
                recency_score=round(recency_score, 1),
                impact_score=round(impact_score, 1),
                overall_score=round(overall_score, 1)
            ))

        # Sort by overall score
        expertise_scores.sort(key=lambda x: x.overall_score, reverse=True)
        return expertise_scores

    def _detect_knowledge_gaps(
        self,
        file_ownerships: List[FileOwnership],
        directory_ownerships: List[DirectoryOwnership],
        days_for_recency: int
    ) -> List[KnowledgeGap]:
        """Detect knowledge gaps in the codebase"""
        gaps = []
        now = datetime.now()
        recency_cutoff = now - timedelta(days=days_for_recency)

        # Check file-level gaps
        for fo in file_ownerships:
            # Single contributor (bus factor = 1)
            if fo.bus_factor == 1 and fo.total_lines >= 100:
                gaps.append(KnowledgeGap(
                    area=fo.file_path,
                    gap_type="single_contributor",
                    risk_level="high" if fo.total_lines >= 500 else "medium",
                    description=f"Only {fo.primary_owner} has contributed to this file ({fo.total_lines} lines)",
                    recommendation="Cross-train team members or pair program on this file",
                    affected_lines=fo.total_lines
                ))

            # Inactive owner
            if fo.last_modified and fo.last_modified < recency_cutoff:
                days_inactive = (now - fo.last_modified).days
                if days_inactive > 180:
                    gaps.append(KnowledgeGap(
                        area=fo.file_path,
                        gap_type="inactive_owner",
                        risk_level="critical" if days_inactive > 365 else "high",
                        description=f"No changes in {days_inactive} days. Primary owner: {fo.primary_owner}",
                        recommendation="Review file for staleness and assign new maintainer if needed",
                        affected_lines=fo.total_lines
                    ))

        # Check directory-level gaps
        for do in directory_ownerships:
            # High concentration of ownership
            if do.ownership_percentage >= 80 and do.total_lines >= 1000:
                gaps.append(KnowledgeGap(
                    area=do.directory_path,
                    gap_type="ownership_concentration",
                    risk_level="high",
                    description=f"{do.primary_owner} owns {do.ownership_percentage}% of {do.directory_path} ({do.total_lines} lines)",
                    recommendation="Distribute ownership by having others contribute or review code",
                    affected_lines=do.total_lines
                ))

        # Sort by risk level and affected lines
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        gaps.sort(key=lambda x: (risk_order.get(x.risk_level, 4), -x.affected_lines))

        return gaps

    def _calculate_knowledge_risk(
        self,
        bus_factor: int,
        contributors: List[AuthorContribution],
        total_lines: int
    ) -> str:
        """Calculate knowledge risk level"""
        if bus_factor == 1:
            if total_lines >= 500:
                return "critical"
            elif total_lines >= 200:
                return "high"
            else:
                return "medium"
        elif bus_factor == 2:
            return "medium" if total_lines >= 500 else "low"
        else:
            return "low"

    def _calculate_metrics(
        self,
        file_ownerships: List[FileOwnership],
        directory_ownerships: List[DirectoryOwnership],
        expertise_scores: List[ExpertiseScore],
        knowledge_gaps: List[KnowledgeGap]
    ) -> Dict[str, Any]:
        """Calculate ownership metrics"""
        total_lines = sum(fo.total_lines for fo in file_ownerships)
        total_files = len(file_ownerships)

        # Bus factor distribution
        bus_factor_dist = defaultdict(int)
        for fo in file_ownerships:
            bus_factor_dist[fo.bus_factor] += 1

        # Knowledge risk distribution
        risk_dist = defaultdict(int)
        for fo in file_ownerships:
            risk_dist[fo.knowledge_risk] += 1

        # Top contributors by lines
        top_contributors = [
            {"name": e.author_name, "lines": e.total_lines_authored, "score": e.overall_score}
            for e in expertise_scores[:10]
        ]

        # Overall bus factor (minimum across significant files)
        significant_files = [fo for fo in file_ownerships if fo.total_lines >= 100]
        overall_bus_factor = min(
            (fo.bus_factor for fo in significant_files),
            default=1
        )

        return {
            "total_lines_analyzed": total_lines,
            "total_files_analyzed": total_files,
            "overall_bus_factor": overall_bus_factor,
            "bus_factor_distribution": dict(bus_factor_dist),
            "knowledge_risk_distribution": dict(risk_dist),
            "top_contributors": top_contributors,
            "ownership_concentration": round(
                (expertise_scores[0].total_lines_authored / total_lines * 100)
                if expertise_scores and total_lines > 0 else 0,
                1
            ),
            "team_coverage": round(
                len([e for e in expertise_scores if e.recency_score > 50]) /
                len(expertise_scores) * 100 if expertise_scores else 0,
                1
            )
        }

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        path_str = str(file_path)
        file_name = file_path.name

        for skip_dir in _SKIP_DIRECTORIES:
            if f"/{skip_dir}/" in path_str or path_str.startswith(f"{skip_dir}/"):
                return True

        for pattern in _SKIP_FILE_PATTERNS:
            if pattern in file_name:
                return True

        return False

    def _serialize_file_ownership(self, fo: FileOwnership) -> Dict[str, Any]:
        """Serialize FileOwnership to dict"""
        return {
            "file_path": fo.file_path,
            "total_lines": fo.total_lines,
            "primary_owner": fo.primary_owner,
            "ownership_percentage": fo.ownership_percentage,
            "bus_factor": fo.bus_factor,
            "knowledge_risk": fo.knowledge_risk,
            "last_modified": fo.last_modified.isoformat() if fo.last_modified else None,
            "contributors": [
                {
                    "name": c.author_name,
                    "email": c.author_email,
                    "lines": c.lines_count,
                    "percentage": c.lines_percentage
                }
                for c in fo.contributors[:5]
            ]
        }

    def _serialize_directory_ownership(self, do: DirectoryOwnership) -> Dict[str, Any]:
        """Serialize DirectoryOwnership to dict"""
        return {
            "directory_path": do.directory_path,
            "total_files": do.total_files,
            "total_lines": do.total_lines,
            "primary_owner": do.primary_owner,
            "ownership_percentage": do.ownership_percentage,
            "bus_factor": do.bus_factor,
            "knowledge_risk": do.knowledge_risk,
            "contributors": [
                {
                    "name": c.author_name,
                    "lines": c.lines_count,
                    "percentage": c.lines_percentage
                }
                for c in do.contributors[:5]
            ]
        }

    def _serialize_expertise(self, e: ExpertiseScore) -> Dict[str, Any]:
        """Serialize ExpertiseScore to dict"""
        return {
            "author_name": e.author_name,
            "author_email": e.author_email,
            "total_lines": e.total_lines_authored,
            "total_commits": e.total_commits,
            "files_owned": e.files_owned,
            "directories_owned": e.directories_owned,
            "expertise_areas": e.expertise_areas,
            "recency_score": e.recency_score,
            "impact_score": e.impact_score,
            "overall_score": e.overall_score
        }

    def _serialize_gap(self, g: KnowledgeGap) -> Dict[str, Any]:
        """Serialize KnowledgeGap to dict"""
        return {
            "area": g.area,
            "gap_type": g.gap_type,
            "risk_level": g.risk_level,
            "description": g.description,
            "recommendation": g.recommendation,
            "affected_lines": g.affected_lines
        }

    async def _cache_results(self, results: Dict[str, Any]) -> None:
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                value = json.dumps(results, default=str)
                await self.redis_client.setex(self.OWNERSHIP_KEY, 3600, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self) -> None:
        """Clear analysis cache"""
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor,
                        match="ownership_analysis:*",
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")

    async def get_cached_results(self) -> Optional[Dict[str, Any]]:
        """Get cached analysis results"""
        if self.redis_client:
            try:
                value = await self.redis_client.get(self.OWNERSHIP_KEY)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Failed to get cached results: {e}")
        return None


async def main():
    """Example usage of ownership analyzer"""
    analyzer = OwnershipAnalyzer()

    results = await analyzer.analyze_ownership(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py", "autobot-vue/src/**/*.vue"]
    )

    print("\n=== Code Ownership Analysis Results ===")
    print(f"Total files analyzed: {results['summary']['total_files']}")
    print(f"Total contributors: {results['summary']['total_contributors']}")
    print(f"Knowledge gaps detected: {results['summary']['knowledge_gaps_count']}")
    print(f"Critical gaps: {results['summary']['critical_gaps']}")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    print("\n=== Top Contributors ===")
    for i, contrib in enumerate(results['metrics']['top_contributors'][:5], 1):
        print(f"{i}. {contrib['name']}: {contrib['lines']} lines (score: {contrib['score']})")

    print("\n=== Knowledge Gaps ===")
    for gap in results['knowledge_gaps'][:5]:
        print(f"- [{gap['risk_level'].upper()}] {gap['area']}")
        print(f"  {gap['description']}")

    print("\n=== Metrics ===")
    metrics = results['metrics']
    print(f"Overall bus factor: {metrics['overall_bus_factor']}")
    print(f"Ownership concentration: {metrics['ownership_concentration']}%")
    print(f"Team coverage: {metrics['team_coverage']}%")


if __name__ == "__main__":
    asyncio.run(main())
