#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Shared skeleton for the auto-tools CLI sanitizer/fixer scripts (Issue #12660).

``security_sanitizer.py``/``security_deep_sanitizer.py`` and
``logging_standardizer.py``/``performance_optimizer.py`` each independently
reimplemented the same ``create_backup``/``save_report``/``process_file``/
``main`` skeleton (verified byte-identical within each pair). This module
hosts those two skeletons exactly once; concrete tools subclass one of the
two bases below and only override their own vulnerability/transform logic.

This directory has no ``__init__.py`` (auto-tools is not an importable
package — the hyphen in the directory name is not a valid Python identifier,
and every tool here is invoked as a standalone script). Importers add this
directory to ``sys.path`` before importing this module; see the top of any
concrete tool for the pattern.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class SecurityFixToolBase:
    """Shared backup/report/CLI skeleton for the XSS security-fix tools.

    Verified byte-identical between ``security_sanitizer.SecurityFixAgent``
    and ``security_deep_sanitizer.SecurityFixAgent`` (module-level class name
    collision across two separate scripts — not the same class).

    Subclasses MUST set:
        - ``REPORT_FILE_PREFIX``: filename prefix for the saved report
          (e.g. ``"security_fix_report"``, ``"enhanced_security_report"``).
        - ``USAGE_PROGRAM_NAME``: program name shown in ``cli_main()`` usage
          text (e.g. ``"security_tool.py"``).

    Subclasses still own ``__init__`` (different ``xss_patterns``/
    ``safe_fixes`` dicts), the vulnerability scan/fix methods, and ``run()``
    — those are genuine per-tool specifics, not skeleton.
    """

    REPORT_FILE_PREFIX: str = "security_fix_report"
    USAGE_PROGRAM_NAME: str = "security_tool.py"

    def create_backup(self, file_path: str) -> str:
        """Create a backup of the original file."""
        try:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"{Path(file_path).name}.backup_{timestamp}"

            if not self.backup_dir:
                self.backup_dir = Path(file_path).parent / "security_backups"
                self.backup_dir.mkdir(exist_ok=True)

            backup_path = self.backup_dir / backup_name
            shutil.copy2(file_path, backup_path)

            logger.info("Backup created: %s", backup_path)
            return str(backup_path)

        except Exception as e:
            logger.error("Failed to create backup: %s", e)
            return ""

    def save_report(self, report_content: str, output_dir: str) -> str:
        """Save the security report to file."""
        try:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            report_filename = f"{self.REPORT_FILE_PREFIX}_{timestamp}.md"
            report_path = os.path.join(output_dir, report_filename)

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            # Also save JSON version for machine processing
            json_filename = f"{self.REPORT_FILE_PREFIX}_{timestamp}.json"
            json_path = os.path.join(output_dir, json_filename)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.report, f, indent=2)

            return report_path

        except Exception as e:
            logger.error("Error saving report: %s", e)
            return ""

    @classmethod
    def cli_main(cls) -> None:
        """Shared CLI entrypoint: validate args, construct the agent, run it."""
        if len(sys.argv) != 2:
            logger.info("Usage: python %s <file_or_directory_path>", cls.USAGE_PROGRAM_NAME)
            logger.info("Example: python %s /path/to/playwright-report/", cls.USAGE_PROGRAM_NAME)
            sys.exit(1)

        target_path = sys.argv[1]

        if not os.path.exists(target_path):
            logger.error("Error: Path '%s' does not exist", target_path)
            sys.exit(1)

        agent = cls()
        agent.run(target_path)


class ConsoleLogToolBase:
    """Shared backup/process/CLI skeleton for the console.log auto-tools.

    Verified byte-identical between ``logging_standardizer.DevLoggingFixer``
    and ``performance_optimizer.ConsoleLogCleaner``.

    Subclasses MUST set:
        - ``ARG_DESCRIPTION``, ``PROJECT_PATH_HELP``, ``TARGET_DIR_HELP``,
          ``REPORT_HELP``: argparse help text (kept per-tool verbatim).
        - ``REPORT_COUNT_KEY``: ``self.report`` counter key incremented by
          :meth:`process_file` on a successful transform.
        - ``ERROR_MESSAGE``: text recorded in ``self.report["errors"]`` on a
          processing failure.

    Subclasses MUST implement:
        - :meth:`_transform_content`: the actual console.log conversion/
          removal logic (returns ``(modified_content, count)``).
        - :meth:`run_project`: hook so :meth:`cli_main` can invoke either
          ``convert_project``/``clean_project`` without renaming either
          tool's existing public method.
        - :meth:`_print_cli_summary`: per-tool completion message.

    Subclasses MAY override :meth:`_extra_cli_args` to add tool-specific
    flags (e.g. ``performance_optimizer``'s ``--dry-run``/``--dev-mode``).
    """

    ARG_DESCRIPTION: str = ""
    PROJECT_PATH_HELP: str = ""
    TARGET_DIR_HELP: str = ""
    REPORT_HELP: str = ""
    REPORT_COUNT_KEY: str = ""
    ERROR_MESSAGE: str = "File processing failed"

    def create_backup(self, file_path: Path) -> Path:
        """Create backup of file before modification."""
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        relative_path = file_path.relative_to(self.project_root)
        backup_path = self.backup_dir / timestamp / relative_path

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)

        return backup_path

    def _transform_content(self, content: str, file_path: Path) -> tuple:
        """Hook: domain-specific console.log transform. Returns (content, count)."""
        raise NotImplementedError

    def process_file(self, file_path: Path) -> bool:
        """Process a single file, backing it up and rewriting it if changed."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            modified_content, count = self._transform_content(original_content, file_path)

            if count > 0:
                self.create_backup(file_path)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                self.report[self.REPORT_COUNT_KEY] += count
                return True

            return False

        except Exception:
            self.report["errors"].append(
                {
                    "file": str(file_path.relative_to(self.project_root)),
                    "error": self.ERROR_MESSAGE,
                }
            )
            return False

    def run_project(self, target_dir: str = None) -> Dict[str, Any]:
        """Hook: invoke this tool's project-wide pass (convert_project/clean_project)."""
        raise NotImplementedError

    @classmethod
    def _extra_cli_args(cls, parser: argparse.ArgumentParser) -> None:
        """Hook: tool-specific CLI flags. Default: none."""
        return

    def _print_cli_summary(self, report: Dict[str, Any]) -> None:
        """Hook: per-tool completion summary printed by cli_main()."""
        raise NotImplementedError

    @classmethod
    def cli_main(cls) -> None:
        """Shared CLI entrypoint: parse args, run the project pass, report, summarize."""
        parser = argparse.ArgumentParser(description=cls.ARG_DESCRIPTION)
        parser.add_argument("project_path", help=cls.PROJECT_PATH_HELP)
        parser.add_argument("--target-dir", help=cls.TARGET_DIR_HELP, default=None)
        parser.add_argument("--backup-dir", help="Directory to store backups", default=None)
        parser.add_argument("--report", help=cls.REPORT_HELP, default=None)
        cls._extra_cli_args(parser)

        args = parser.parse_args()

        instance = cls(args.project_path, args.backup_dir)

        if args.target_dir:
            target_path = Path(args.project_path) / args.target_dir
            report = instance.run_project(str(target_path))
        else:
            report = instance.run_project()

        instance.generate_report(args.report)
        instance._print_cli_summary(report)


__all__ = ["SecurityFixToolBase", "ConsoleLogToolBase"]
