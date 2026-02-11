#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Timeout Configuration Standardization Script
=====================================================

This script addresses critical timeout configuration issues identified in the
comprehensive timeout audit. It standardizes Redis connection timeouts and
identifies hardcoded values that need manual review.

Usage:
    python scripts/utilities/standardize_timeout_configurations.py [--dry-run] [--fix-redis] [--scan-hardcoded]

Features:
- Standardizes Redis connection timeout configurations
- Identifies hardcoded timeout values across the codebase
- Creates unified timeout configuration module
- Validates timeout hierarchy and relationships
- Generates implementation recommendations

NOTE: generate_unified_config_module (~150 lines) is an ACCEPTABLE EXCEPTION
per Issue #490 - code generator producing configuration module. Low priority.
"""

import asyncio
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Issue #825: Module-level constant for timeout config template
_TIMEOUT_CONFIG_TEMPLATE = '''"""
AutoBot Unified Timeout Configuration
====================================

Centralized timeout configuration for all AutoBot services.
This module provides standardized timeout values that can be overridden
via environment variables.

Usage:
    from config.timeout_config import TIMEOUT_CONFIG

    redis_timeout = TIMEOUT_CONFIG.redis_socket_timeout
    api_timeout = TIMEOUT_CONFIG.api_request_timeout
"""

import os
from dataclasses import dataclass
from typing import Union


@dataclass
class TimeoutConfiguration:
    """Unified timeout configuration for AutoBot"""

    # Redis Configuration
    redis_socket_timeout: float = 5.0
    redis_connect_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_max_retries: int = 3
    redis_circuit_breaker_timeout: int = 60

    # HTTP/API Configuration
    api_request_timeout: int = 30
    health_check_timeout: int = 3
    websocket_timeout: int = 30

    # Database Configuration
    database_query_timeout: int = 10
    chromadb_timeout: int = 15
    vector_search_timeout: int = 20
    sqlite_timeout: int = 30

    # LLM Configuration
    llm_connect_timeout: float = 5.0
    llm_non_streaming_timeout: int = 30
    llm_streaming_heartbeat: int = 5

    # File Operations
    upload_timeout: int = 300
    download_timeout: int = 120

    # Background Processing
    background_processing_timeout: int = 60
    long_running_operation_timeout: int = 1800  # 30 minutes

    # Deployment Configuration
    deployment_timeout: int = 1800
    health_check_deployment_timeout: int = 300
    graceful_shutdown_timeout: int = 30

    def get_env_override(self, key: str, default: Union[int, float, bool]) -> Union[int, float, bool]:
        """Get environment variable override for timeout value"""
        env_key = f"AUTOBOT_{key.upper()}"
        env_value = os.getenv(env_key)

        if env_value is None:
            return default

        try:
            if isinstance(default, bool):
                return env_value.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(default, float):
                return float(env_value)
            elif isinstance(default, int):
                return int(env_value)
        except (ValueError, TypeError):
            return default

        return default

    def __post_init__(self):
        """Apply environment variable overrides"""
        for field_name in self.__dataclass_fields__:
            current_value = getattr(self, field_name)
            override_value = self.get_env_override(field_name, current_value)
            setattr(self, field_name, override_value)


# Global timeout configuration instance
TIMEOUT_CONFIG = TimeoutConfiguration()


def get_redis_timeout_config() -> dict:
    """Get Redis-specific timeout configuration"""
    return {
        'socket_timeout': TIMEOUT_CONFIG.redis_socket_timeout,
        'socket_connect_timeout': TIMEOUT_CONFIG.redis_connect_timeout,
        'retry_on_timeout': TIMEOUT_CONFIG.redis_retry_on_timeout,
        'max_retries': TIMEOUT_CONFIG.redis_max_retries
    }


def get_api_timeout_config() -> dict:
    """Get API-specific timeout configuration"""
    return {
        'request_timeout': TIMEOUT_CONFIG.api_request_timeout,
        'health_check_timeout': TIMEOUT_CONFIG.health_check_timeout,
        'websocket_timeout': TIMEOUT_CONFIG.websocket_timeout
    }


def get_database_timeout_config() -> dict:
    """Get database-specific timeout configuration"""
    return {
        'query_timeout': TIMEOUT_CONFIG.database_query_timeout,
        'chromadb_timeout': TIMEOUT_CONFIG.chromadb_timeout,
        'vector_search_timeout': TIMEOUT_CONFIG.vector_search_timeout,
        'sqlite_timeout': TIMEOUT_CONFIG.sqlite_timeout
    }


def validate_timeout_hierarchy():
    """Validate that timeout values maintain proper hierarchy"""
    issues = []

    # Connection timeout should be less than operation timeout
    if TIMEOUT_CONFIG.redis_connect_timeout >= TIMEOUT_CONFIG.redis_socket_timeout:
        issues.append("Redis connect timeout should be less than socket timeout")

    # Health check should be fast
    if TIMEOUT_CONFIG.health_check_timeout > TIMEOUT_CONFIG.api_request_timeout:
        issues.append("Health check timeout should be less than API request timeout")

    # WebSocket timeout should be reasonable for interactive use
    if TIMEOUT_CONFIG.websocket_timeout > 60:
        issues.append("WebSocket timeout should not exceed 60 seconds for user experience")

    return issues
'''


@dataclass
class TimeoutIssue:
    """Represents a timeout configuration issue"""

    file_path: str
    line_number: int
    issue_type: str
    current_value: str
    recommended_value: str
    severity: str  # critical, high, medium, low
    description: str
    fix_required: bool = True


@dataclass
class StandardTimeoutConfig:
    """Standard timeout configuration values"""

    # Redis timeouts
    redis_socket_timeout: float = 5.0
    redis_connect_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_max_retries: int = 3

    # HTTP/API timeouts
    api_request_timeout: int = 30
    health_check_timeout: int = 3
    websocket_timeout: int = 30

    # Database timeouts
    database_query_timeout: int = 10
    chromadb_timeout: int = 15
    vector_search_timeout: int = 20

    # LLM timeouts
    llm_connect_timeout: float = 5.0
    llm_non_streaming_timeout: int = 30

    # Upload/processing timeouts
    upload_timeout: int = 300
    background_processing_timeout: int = 60


class TimeoutConfigurationAnalyzer:
    """Analyzes and standardizes timeout configurations"""

    def __init__(self, project_root: str):
        """Initialize timeout analyzer with project root and issue tracking."""
        self.project_root = Path(project_root)
        self.issues: List[TimeoutIssue] = []
        self.standard_config = StandardTimeoutConfig()
        self.fixed_files: List[str] = []

    def scan_redis_timeout_patterns(self) -> List[TimeoutIssue]:
        """Scan for Redis timeout configuration patterns"""
        logger.info("Scanning for Redis timeout patterns...")

        redis_timeout_patterns = [
            r"socket_timeout\s*=\s*(\d+(?:\.\d+)?)",
            r"socket_connect_timeout\s*=\s*(\d+(?:\.\d+)?)",
            r"timeout\s*=\s*(\d+(?:\.\d+)?)",  # Generic timeout in Redis context
        ]

        # Files to scan for Redis patterns
        redis_files = [
            "src/redis_pool_manager.py",
            "backend/utils/async_redis_manager.py",
            "analytics_redis_timeout_corrector.py",
            "reorganize_redis_databases.py",
            "create_code_vector_knowledge.py",
            "migrate_vectors_to_db0.py",
            "index_dimensions_corrector.py",
            "analyze_code_vectors_for_issues.py",
        ]

        for file_path in redis_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                self._scan_file_for_patterns(
                    full_path, redis_timeout_patterns, "redis_timeout"
                )

        return self.issues

    def scan_hardcoded_timeouts(self) -> List[TimeoutIssue]:
        """Scan for hardcoded timeout values across the codebase"""
        logger.info("Scanning for hardcoded timeout values...")

        # Patterns for hardcoded timeouts
        timeout_patterns = [
            r"timeout\s*[=:]\s*(\d+)",
            r"setTimeout\s*\(\s*[^,]+,\s*(\d+)",
            r"setInterval\s*\(\s*[^,]+,\s*(\d+)",
            r"wait_for\s*\([^,]+,\s*timeout\s*=\s*(\d+(?:\.\d+)?)",
            r"ClientTimeout\s*\([^)]*total\s*=\s*(\d+(?:\.\d+)?)",
            r"aiohttp\.ClientTimeout\s*\([^)]*(\d+(?:\.\d+)?)",
        ]

        # Directories to scan (exclude some paths to avoid false positives)
        scan_paths = ["src/", "backend/", "autobot-vue/src/", "scripts/", "tests/"]

        exclude_patterns = [
            r"\.git/",
            r"node_modules/",
            r"__pycache__/",
            r"\.pyc$",
            r"\.log$",
            r"\.md$",
            r"\.txt$",
            r"reports/",
            r"\.console-cleanup-backups/",
        ]

        for scan_path in scan_paths:
            full_scan_path = self.project_root / scan_path
            if full_scan_path.exists():
                self._scan_directory_recursive(
                    full_scan_path,
                    timeout_patterns,
                    "hardcoded_timeout",
                    exclude_patterns,
                )

        return self.issues

    def _scan_directory_recursive(
        self,
        directory: Path,
        patterns: List[str],
        issue_type: str,
        exclude_patterns: List[str],
    ):
        """Recursively scan directory for timeout patterns"""
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                # Skip excluded files
                relative_path = str(file_path.relative_to(self.project_root))
                if any(
                    re.search(pattern, relative_path) for pattern in exclude_patterns
                ):
                    continue

                # Only scan text files
                if file_path.suffix in [
                    ".py",
                    ".js",
                    ".ts",
                    ".vue",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                ]:
                    self._scan_file_for_patterns(file_path, patterns, issue_type)

    def _scan_file_for_patterns(
        self, file_path: Path, patterns: List[str], issue_type: str
    ):
        """Scan a single file for timeout patterns.

        Issue #511: Optimized O(n³) → O(n²) by combining patterns into a single
        compiled regex. Now iterates: lines × (single combined regex) instead of
        lines × patterns × matches.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Issue #511: Combine patterns into single regex for O(1) pattern matching
            combined = "|".join(f"({p})" for p in patterns)
            compiled = re.compile(combined, re.IGNORECASE)

            for line_num, line in enumerate(lines, 1):
                for match in compiled.finditer(line):
                    self._create_timeout_issue(
                        file_path, line_num, line.strip(), match, issue_type
                    )

        except (UnicodeDecodeError, PermissionError) as e:
            logger.warning("Could not read file %s: %s", file_path, e)

    def _create_timeout_issue(
        self,
        file_path: Path,
        line_num: int,
        line: str,
        match: re.Match,
        issue_type: str,
    ):
        """Create a timeout issue from a pattern match"""
        relative_path = str(file_path.relative_to(self.project_root))
        current_value = match.group(1) if match.groups() else match.group(0)

        # Determine severity and recommendation based on context
        severity, recommended_value, description = self._analyze_timeout_context(
            relative_path, line, current_value, issue_type
        )

        issue = TimeoutIssue(
            file_path=relative_path,
            line_number=line_num,
            issue_type=issue_type,
            current_value=current_value,
            recommended_value=recommended_value,
            severity=severity,
            description=description,
            fix_required=severity in ["critical", "high"],
        )

        self.issues.append(issue)

    def _analyze_timeout_context(
        self, file_path: str, line: str, value: str, issue_type: str
    ) -> Tuple[str, str, str]:
        """Analyze timeout context to determine severity and recommendations"""
        try:
            numeric_value = float(value)
        except ValueError:
            return "low", value, "Non-numeric timeout value"

        # Redis timeout analysis
        if "redis" in issue_type.lower() or "redis" in file_path.lower():
            if numeric_value > 30:
                return "high", "5.0", f"Redis timeout too high: {value}s (recommend 5s)"
            elif numeric_value < 2:
                return (
                    "medium",
                    "5.0",
                    f"Redis timeout too low: {value}s (recommend 5s)",
                )
            elif numeric_value != 5.0:
                return (
                    "medium",
                    "5.0",
                    f"Redis timeout inconsistent: {value}s (standard: 5s)",
                )

        # HTTP/API timeout analysis
        if "api" in line.lower() or "http" in line.lower():
            if numeric_value > 60:
                return "medium", "30", f"API timeout too high: {value}s (recommend 30s)"
            elif numeric_value < 5:
                return (
                    "high",
                    "30",
                    f"API timeout too low: {value}s (may cause failures)",
                )

        # WebSocket timeout analysis
        if "websocket" in line.lower() or "ws" in line.lower():
            if numeric_value > 120:
                return "medium", "30", f"WebSocket timeout too high: {value}s"
            elif numeric_value < 10:
                return "medium", "30", f"WebSocket timeout too low: {value}s"

        # Default analysis
        if numeric_value > 300:  # 5 minutes
            return "medium", "30", f"Very high timeout: {value}s (review if necessary)"
        elif numeric_value < 1:
            return "high", "5", f"Very low timeout: {value}s (may cause failures)"

        return "low", value, "Timeout value within reasonable range"

    def generate_unified_config_module(self) -> str:
        """Generate a unified timeout configuration module.

        NOTE: This function (~50 lines) is acceptable per Issue #825 comment:
        Code generator producing configuration module. Already uses module-level
        constant for template. Low priority for further extraction.
        """
        config_content = _TIMEOUT_CONFIG_TEMPLATE

        config_file_path = self.project_root / "src" / "config" / "timeout_config.py"
        config_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        logger.info("Generated unified timeout configuration: %s", config_file_path)
        return str(config_file_path)

    def fix_redis_timeouts(self, dry_run: bool = True) -> List[str]:
        """Fix standardizable Redis timeout issues"""
        fixed_files = []

        # Group issues by file
        file_issues = {}
        for issue in self.issues:
            if issue.issue_type == "redis_timeout" and issue.fix_required:
                if issue.file_path not in file_issues:
                    file_issues[issue.file_path] = []
                file_issues[issue.file_path].append(issue)

        for file_path, issues in file_issues.items():
            if self._fix_file_redis_timeouts(file_path, issues, dry_run):
                fixed_files.append(file_path)

        return fixed_files

    def _fix_file_redis_timeouts(
        self, file_path: str, issues: List[TimeoutIssue], dry_run: bool
    ) -> bool:
        """Fix Redis timeouts in a specific file"""
        full_path = self.project_root / file_path

        try:
            with open(full_path, "r") as f:
                lines = f.readlines()

            # Apply fixes
            modified = False
            for issue in issues:
                line_idx = issue.line_number - 1
                if line_idx < len(lines):
                    original_line = lines[line_idx]

                    # Simple replacement for standard Redis timeout patterns
                    if "socket_timeout" in original_line:
                        new_line = re.sub(
                            r"socket_timeout\s*=\s*\d+(?:\.\d+)?",
                            f"socket_timeout={self.standard_config.redis_socket_timeout}",
                            original_line,
                        )
                        lines[line_idx] = new_line
                        modified = True

                    elif "socket_connect_timeout" in original_line:
                        new_line = re.sub(
                            r"socket_connect_timeout\s*=\s*\d+(?:\.\d+)?",
                            f"socket_connect_timeout={self.standard_config.redis_connect_timeout}",
                            original_line,
                        )
                        lines[line_idx] = new_line
                        modified = True

            if modified and not dry_run:
                # Backup original file
                backup_path = f"{full_path}.timeout_fix_backup"
                with open(backup_path, "w") as f:
                    f.writelines(lines)

                # Write fixed file
                with open(full_path, "w") as f:
                    f.writelines(lines)

                logger.info(
                    "Fixed Redis timeouts in %s (backup: %s)", file_path, backup_path
                )
                return True
            elif modified:
                logger.info("[DRY RUN] Would fix Redis timeouts in %s", file_path)
                return True

        except Exception as e:
            logger.error("Error fixing %s: %s", file_path, e)

        return False

    def generate_report(self) -> dict:
        """Generate comprehensive timeout audit report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_issues": len(self.issues),
            "critical_issues": len(
                [i for i in self.issues if i.severity == "critical"]
            ),
            "high_priority_issues": len(
                [i for i in self.issues if i.severity == "high"]
            ),
            "medium_priority_issues": len(
                [i for i in self.issues if i.severity == "medium"]
            ),
            "low_priority_issues": len([i for i in self.issues if i.severity == "low"]),
            "issues_by_type": {},
            "issues_by_file": {},
            "recommendations": [],
            "issues": [asdict(issue) for issue in self.issues],
        }

        # Group by type
        for issue in self.issues:
            if issue.issue_type not in report["issues_by_type"]:
                report["issues_by_type"][issue.issue_type] = 0
            report["issues_by_type"][issue.issue_type] += 1

        # Group by file
        for issue in self.issues:
            if issue.file_path not in report["issues_by_file"]:
                report["issues_by_file"][issue.file_path] = 0
            report["issues_by_file"][issue.file_path] += 1

        # Generate recommendations
        if report["critical_issues"] > 0:
            report["recommendations"].append(
                "Address critical timeout issues immediately - these may cause system failures"
            )

        if report["issues_by_type"].get("redis_timeout", 0) > 5:
            report["recommendations"].append(
                "Standardize Redis timeout configurations using unified config module"
            )

        if report["high_priority_issues"] > 10:
            report["recommendations"].append(
                "Review and standardize hardcoded timeout values across the codebase"
            )

        return report


def _run_scans(analyzer, args):
    """
    Run configured scans on the analyzer.

    Helper for main (#825).

    Args:
        analyzer: TimeoutConfigurationAnalyzer instance
        args: Parsed command line arguments
    """
    logger.info("Scanning Redis timeout patterns...")
    analyzer.scan_redis_timeout_patterns()

    if args.scan_hardcoded:
        logger.info("Scanning for hardcoded timeout values...")
        analyzer.scan_hardcoded_timeouts()

    if args.generate_config:
        logger.info("Generating unified timeout configuration module...")
        config_path = analyzer.generate_unified_config_module()
        logger.info("Generated: %s", config_path)

    if args.fix_redis:
        logger.info("Fixing Redis timeout configurations...")
        fixed_files = analyzer.fix_redis_timeouts(dry_run=args.dry_run)
        logger.info("Fixed %s files", len(fixed_files))


def _print_report_summary(report, report_path):
    """
    Print summary of timeout analysis report.

    Helper for main (#825).

    Args:
        report: Report dictionary
        report_path: Path where report was saved
    """
    logger.info("\n=== TIMEOUT CONFIGURATION ANALYSIS SUMMARY ===")
    logger.info("Total issues found: %s", report["total_issues"])
    logger.info("Critical issues: %s", report["critical_issues"])
    logger.info("High priority issues: %s", report["high_priority_issues"])
    logger.info("Medium priority issues: %s", report["medium_priority_issues"])
    logger.info("Low priority issues: %s", report["low_priority_issues"])
    logger.info("\nDetailed report saved to: %s", report_path)

    if report["recommendations"]:
        logger.info("\nRecommendations:")
        for i, rec in enumerate(report["recommendations"], 1):
            logger.info("%s. %s", i, rec)


async def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="AutoBot Timeout Configuration Standardization"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--fix-redis", action="store_true", help="Fix Redis timeout configurations"
    )
    parser.add_argument(
        "--scan-hardcoded",
        action="store_true",
        help="Scan for hardcoded timeout values",
    )
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="Generate unified timeout configuration module",
    )
    parser.add_argument("--project-root", default=".", help="Project root directory")

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = TimeoutConfigurationAnalyzer(args.project_root)
    logger.info("Starting AutoBot timeout configuration analysis...")

    # Run scans
    _run_scans(analyzer, args)

    # Generate and save report
    report = analyzer.generate_report()

    report_path = (
        Path(args.project_root)
        / "reports"
        / "performance"
        / "timeout_configuration_analysis.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    _print_report_summary(report, report_path)

    # Exit with appropriate code
    if report["critical_issues"] > 0:
        sys.exit(2)
    elif report["high_priority_issues"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
