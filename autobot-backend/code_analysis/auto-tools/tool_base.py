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
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import Severity
from utils.file_categorization import HTML_EXTENSIONS, SKIP_DIRS

logger = get_logger(__name__)

# Severity rungs these tools grade findings at, worst first, with the icon each
# renders as. Hosted here once because all three sanitizers had their own copy
# of the same table and the same ordering list (#14956).
#
# The rungs are canonical ``Severity`` members. The tools previously stored the
# member NAME ("HIGH") where the VALUE ("high") belongs, so anything comparing a
# finding against ``Severity.HIGH.value`` silently missed every one of them. The
# stored value is now canonical; the report text still shows the upper-case name,
# so the human-facing output is unchanged.
SEVERITY_REPORT_ICONS: Dict[Severity, str] = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🟢",
}
SEVERITY_REPORT_ORDER: tuple = tuple(SEVERITY_REPORT_ICONS)
UNRANKED_SEVERITY_ICON = "⚪"


def severity_icon(value: str) -> str:
    """Icon for a stored severity value; unranked and unknown both fall back."""
    try:
        return SEVERITY_REPORT_ICONS.get(Severity(value), UNRANKED_SEVERITY_ICON)
    except ValueError:
        return UNRANKED_SEVERITY_ICON


def severity_label(value: str) -> str:
    """Report text for a stored severity value — the member name, upper-case.

    Keeps the human-facing report identical to what it printed when the tools
    stored the name instead of the value, so #14956 changed the stored data
    without changing a single line of the rendered report.
    """
    try:
        return Severity(value).name
    except ValueError:
        return str(value)


class SecurityFixToolBase:
    """Shared backup/report/CLI skeleton for the XSS security-fix tools.

    Verified byte-identical between ``security_sanitizer.SecurityFixAgent``
    and ``security_deep_sanitizer.DeepSecurityFixAgent`` (two separate scripts that
    formerly shared a class name — not the same class).

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

    # --- Shared scan/inject core (#18557 slice 2) ---------------------------
    # Formerly cloned between security_sanitizer and security_deep_sanitizer.
    # Subclasses supply ``xss_patterns`` and the three ``_..._block`` hooks
    # (the exact text inserted, so each tool's output is byte-for-byte kept).

    _HTML_EXTENSIONS = tuple(sorted(HTML_EXTENSIONS))

    def _csp_header(self) -> str:
        """Hook: the CSP ``<meta>`` tag (without surrounding newlines)."""
        raise NotImplementedError

    def _meta_tags_block(self) -> str:
        """Hook: exact text inserted before ``</head>`` for the meta tags."""
        raise NotImplementedError

    def _dom_helper_block(self) -> str:
        """Hook: exact text inserted for the DOM sanitization helper."""
        raise NotImplementedError

    def validate_html_structure(self, content: str) -> bool:
        """HTML structure validation: doctype/html/head present, scripts balanced."""
        try:
            has_doctype = "<!DOCTYPE" in content.upper()
            has_html_tag = "<html" in content.lower()
            has_head_tag = "<head" in content.lower()
            script_opens = content.count("<script")
            script_closes = content.count("</script>")
            return has_doctype and has_html_tag and has_head_tag and script_opens == script_closes
        except Exception:
            return False

    def analyze_context_safety(self, match: str, pattern_name: str) -> bool:
        """Analyze if a potential vulnerability is actually safe in context."""
        pattern_info = self.xss_patterns.get(pattern_name, {})
        safe_contexts = pattern_info.get("context_safe", []) if isinstance(pattern_info, dict) else []
        if any(safe_context in match for safe_context in safe_contexts):
            return True
        if self.is_minified_library_code(match):
            return True
        return any(framework in match for framework in ["React", "Vue", "Angular", "__webpack"])

    def is_minified_library_code(self, code: str) -> bool:
        """Detect if code appears to be from a minified library."""
        indicators = [
            len(code) > 200,
            re.search(r"[a-zA-Z]\.[a-zA-Z]\.[a-zA-Z]", code),
            code.count(",") > 10 and "\n" not in code,
            any(lib in code.lower() for lib in ["react", "vue", "angular", "jquery", "lodash"]),
        ]
        return sum(bool(i) for i in indicators) >= 2

    def scan_directory(self, directory: str) -> List[str]:
        """Scan directory for HTML files to fix."""
        html_files = []
        try:
            for root, _dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith(self._HTML_EXTENSIONS):
                        html_files.append(os.path.join(root, file))
        except Exception as e:
            logger.error("Error scanning directory %s: %s", directory, e)
        return html_files

    def inject_security_headers(self, content: str) -> Tuple[str, List[str]]:
        """Inject CSP headers and security meta tags into HTML head."""
        enhancements: List[str] = []
        head_match = re.search(r"<head[^>]*>(.*?)</head>", content, re.DOTALL | re.IGNORECASE)
        if not head_match:
            return content, enhancements
        head_content = head_match.group(1)
        head_start, head_end = head_match.start(1), head_match.end(1)
        if not re.search(r"Content-Security-Policy", head_content, re.IGNORECASE):
            new_head = "\n" + self._csp_header() + "\n" + head_content
            content = content[:head_start] + new_head + content[head_end:]
            enhancements.append("Content Security Policy (CSP) injected")
        if not re.search(r"X-Content-Type-Options", head_content, re.IGNORECASE):
            pos = content.find("</head>")
            if pos != -1:
                content = content[:pos] + self._meta_tags_block() + content[pos:]
                enhancements.append("Security meta tags injected")
        return content, enhancements

    def inject_dom_sanitization(self, content: str) -> Tuple[str, List[str]]:
        """Inject DOM sanitization helper script."""
        enhancements: List[str] = []
        injection_point = content.find("</head>")
        if injection_point == -1:
            injection_point = content.find("<script")
        if injection_point != -1:
            content = content[:injection_point] + self._dom_helper_block() + content[injection_point:]
            enhancements.append("DOM sanitization helpers injected")
        return content, enhancements


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
    BACKUP_DIR_NAME: str = ".console-backups"

    # Class-level defaults shared by both tools (#18557 slice 2); instances get
    # their own copies in ``__init__`` so per-instance mutation stays local.
    # Canonical skip dirs plus extras: test trees and other output dirs are not
    # console.log targets.
    _SKIP_DIRS = SKIP_DIRS | {"out", "tests", "test", "__tests__", "e2e", "tmp"}
    _TARGET_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs")

    def __init__(self, project_root: str, backup_dir: str = None):
        self.project_root = Path(project_root)
        self.backup_dir = Path(backup_dir) if backup_dir else self.project_root / self.BACKUP_DIR_NAME
        self.report = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "files_processed": 0,
            "files_modified": 0,
            self.REPORT_COUNT_KEY: 0,
            "errors": [],
            "details": [],
        }
        self.skip_dirs = set(self._SKIP_DIRS)
        self.target_extensions = set(self._TARGET_EXTENSIONS)

    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        try:
            parts = file_path.relative_to(self.project_root).parts
        except ValueError:
            parts = file_path.parts
        if any(part in self.skip_dirs for part in parts):
            return False
        if file_path.suffix not in self.target_extensions:
            return False
        if any(pattern in file_path.name.lower() for pattern in ["test", "spec", "mock"]):
            return False
        return ".min." not in file_path.name

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
                # #12678: --dry-run must not touch the tree. Guarded here rather
                # than at each call site because this is the only writer, so a
                # future tool cannot bypass it by accident. The count is still
                # reported, so a dry run says what it *would* change.
                if not getattr(self, "dry_run", False):
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

    def _apply_cli_args(self, args: argparse.Namespace) -> None:
        """Receive the parsed CLI args (#12678).

        ``--dry-run`` is handled here rather than per-tool because the code that
        honours it -- :meth:`process_file` -- lives on this base. A subclass that
        forgot to wire it would otherwise silently write while reporting a dry
        run. Subclasses adding their own flags should call ``super()`` first.
        """
        self.dry_run = bool(getattr(args, "dry_run", False))

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
        # #12678: extra flags declared via _extra_cli_args were parsed and then
        # discarded here, so a tool could not read its own options.
        instance._apply_cli_args(args)

        if args.target_dir:
            target_path = Path(args.project_path) / args.target_dir
            report = instance.run_project(str(target_path))
        else:
            report = instance.run_project()

        instance.generate_report(args.report)
        instance._print_cli_summary(report)


__all__ = ["SecurityFixToolBase", "ConsoleLogToolBase"]
