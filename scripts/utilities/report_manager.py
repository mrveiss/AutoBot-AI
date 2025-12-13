#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Report Management System for AutoBot
Manages reports with retention policy and organization by type
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ReportManager:
    """Manages reports with retention and organization policies"""

    def __init__(self, base_reports_dir: str = "reports"):
        """Initialize report manager with base directory and retention limits."""
        self.base_dir = Path(base_reports_dir)
        self.max_reports_per_type = 2

        # Report type configurations
        self.report_types = {
            "security": {
                "patterns": ["*security*", "*audit*", "*vulnerability*"],
                "description": "Security audits and vulnerability reports",
            },
            "dependency": {
                "patterns": ["*dependency*", "*package*", "*pip*"],
                "description": "Dependency and package analysis reports",
            },
            "performance": {
                "patterns": ["*performance*", "*benchmark*", "*profiling*"],
                "description": "Performance analysis and benchmarking reports",
            },
            "code-quality": {
                "patterns": ["*quality*", "*analysis*", "*lint*", "*coverage*"],
                "description": "Code quality and analysis reports",
            },
        }

    def setup_directories(self):
        """Create report directories if they don't exist"""
        self.base_dir.mkdir(exist_ok=True)

        for report_type in self.report_types:
            (self.base_dir / report_type).mkdir(exist_ok=True)

    def classify_report(self, filename: str) -> Optional[str]:
        """Classify report by filename patterns"""
        filename_lower = filename.lower()

        for report_type, config in self.report_types.items():
            for pattern in config["patterns"]:
                # Simple wildcard matching
                pattern_lower = pattern.lower().replace("*", "")
                if pattern_lower in filename_lower:
                    return report_type

        return "code-quality"  # Default category

    def add_report(self, source_path: str, report_name: Optional[str] = None) -> str:
        """Add a report with automatic retention management"""
        source_file = Path(source_path)

        if not source_file.exists():
            raise FileNotFoundError(f"Source report not found: {source_path}")

        # Generate report name with timestamp
        if not report_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = source_file.stem
            report_name = f"{base_name}_{timestamp}.json"

        # Classify report type
        report_type = self.classify_report(source_file.name)
        target_dir = self.base_dir / report_type
        target_path = target_dir / report_name

        self.setup_directories()

        # Move or copy report
        if source_file.parent.absolute() == Path.cwd().absolute():
            # Move from project root
            shutil.move(str(source_file), str(target_path))
        else:
            # Copy from other locations
            shutil.copy2(str(source_file), str(target_path))

        # Apply retention policy
        self._apply_retention_policy(report_type)

        return str(target_path)

    def _apply_retention_policy(self, report_type: str):
        """Keep only the most recent N reports per type"""
        target_dir = self.base_dir / report_type

        if not target_dir.exists():
            return

        # Get all reports in the directory, sorted by modification time
        reports = []
        for file_path in target_dir.glob("*.json"):
            if file_path.is_file():
                reports.append((file_path.stat().st_mtime, file_path))

        # Sort by modification time (newest first)
        reports.sort(reverse=True)

        # Remove oldest reports if exceeding limit
        if len(reports) > self.max_reports_per_type:
            for _, old_report in reports[self.max_reports_per_type :]:
                print(f"Removing old report: {old_report}")
                old_report.unlink()

    def list_reports(self) -> Dict[str, List[Dict]]:
        """List all reports organized by type"""
        reports_by_type = {}

        for report_type in self.report_types:
            type_dir = self.base_dir / report_type
            reports = []

            if type_dir.exists():
                for file_path in sorted(
                    type_dir.glob("*.json"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                ):
                    if file_path.is_file():
                        stat = file_path.stat()
                        reports.append(
                            {
                                "name": file_path.name,
                                "path": str(file_path),
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(
                                    stat.st_mtime
                                ).isoformat(),
                                "type": report_type,
                            }
                        )

            reports_by_type[report_type] = reports

        return reports_by_type

    def get_latest_report(self, report_type: str) -> Optional[str]:
        """Get path to the latest report of a specific type"""
        type_dir = self.base_dir / report_type

        if not type_dir.exists():
            return None

        reports = list(type_dir.glob("*.json"))
        if not reports:
            return None

        # Return the most recently modified report
        latest = max(reports, key=lambda x: x.stat().st_mtime)
        return str(latest)

    def compare_reports(self, report_type: str) -> Optional[List[str]]:
        """Get up to 2 latest reports for comparison"""
        type_dir = self.base_dir / report_type

        if not type_dir.exists():
            return None

        reports = sorted(
            type_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
        )

        return [str(report) for report in reports[:2]]

    def cleanup_project_root(self, project_root: str = "."):
        """Move any reports found in project root to organized folders"""
        root_path = Path(project_root)
        moved_files = []

        # Common report file patterns to look for in root
        report_patterns = [
            "*_report.json",
            "*-report.json",
            "*_analysis.json",
            "*analysis*.json",
            "security_audit*.json",
            "dependency*.json",
        ]

        for pattern in report_patterns:
            for file_path in root_path.glob(pattern):
                if (
                    file_path.is_file()
                    and file_path.parent.absolute() == root_path.absolute()
                ):
                    try:
                        new_path = self.add_report(str(file_path))
                        moved_files.append((str(file_path), new_path))
                    except Exception as e:
                        print(f"Error moving {file_path}: {e}")

        return moved_files


def main():
    """CLI interface for report management"""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Report Management System")
    parser.add_argument("--list", action="store_true", help="List all reports")
    parser.add_argument("--cleanup", action="store_true", help="Clean up project root")
    parser.add_argument("--add", type=str, help="Add a report file")
    parser.add_argument("--compare", type=str, help="Get comparison reports for type")

    args = parser.parse_args()

    manager = ReportManager()

    if args.list:
        reports = manager.list_reports()
        print(json.dumps(reports, indent=2))

    elif args.cleanup:
        moved = manager.cleanup_project_root()
        for old_path, new_path in moved:
            print(f"Moved: {old_path} -> {new_path}")

    elif args.add:
        try:
            new_path = manager.add_report(args.add)
            print(f"Added report: {new_path}")
        except Exception as e:
            print(f"Error: {e}")

    elif args.compare:
        reports = manager.compare_reports(args.compare)
        if reports:
            print(f"Comparison reports for {args.compare}:")
            for report in reports:
                print(f"  {report}")
        else:
            print(f"No reports found for type: {args.compare}")


if __name__ == "__main__":
    main()
