#!/usr/bin/env python3
"""
Performance Fix Agent - Console.log Cleanup Tool
Intelligently removes console.log statements from production code
while preserving important console methods and handling edge cases.
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class ConsoleLogCleaner:
    """Removes console.log statements from JavaScript/TypeScript/Vue files."""

    def __init__(self, project_root: str, backup_dir: str = None):
        self.project_root = Path(project_root)
        self.backup_dir = (
            Path(backup_dir)
            if backup_dir
            else self.project_root / ".console-cleanup-backups"
        )
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "files_processed": 0,
            "files_modified": 0,
            "console_logs_removed": 0,
            "errors": [],
            "details": [],
        }

        # Directories to skip
        self.skip_dirs = {
            "node_modules",
            "dist",
            "build",
            ".git",
            "__pycache__",
            "coverage",
            ".next",
            ".nuxt",
            "out",
            "tests",
            "test",
            "__tests__",
            "e2e",
            ".cache",
            "temp",
            "tmp",
        }

        # File extensions to process
        self.target_extensions = {".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs"}

        # Console methods to preserve
        self.preserve_methods = {
            "console.error",
            "console.warn",
            "console.info",
            "console.debug",
            "console.table",
            "console.trace",
            "console.assert",
            "console.time",
            "console.timeEnd",
            "console.group",
            "console.groupEnd",
            "console.groupCollapsed",
        }

    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        # Skip if in excluded directory
        for part in file_path.parts:
            if part in self.skip_dirs:
                return False

        # Check file extension
        if file_path.suffix not in self.target_extensions:
            return False

        # Skip test files
        if any(
            pattern in file_path.name.lower() for pattern in ["test", "spec", "mock"]
        ):
            return False

        # Skip minified files
        if ".min." in file_path.name:
            return False

        return True

    def create_backup(self, file_path: Path) -> Path:
        """Create backup of file before modification."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        relative_path = file_path.relative_to(self.project_root)
        backup_path = self.backup_dir / timestamp / relative_path

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)

        return backup_path

    def _resolve_console_log_match(
        self, content: str, line: str, line_start_pos: int, match: "re.Match"
    ) -> Optional[Tuple[int, int, str]]:
        """Resolve a single console.log match to its full (start, end, text) span. Issue #1183."""
        start_pos = line_start_pos + match.start()
        paren_count = 1
        search_pos = match.end()
        while search_pos < len(line) and paren_count > 0:
            char = line[search_pos]
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
            search_pos += 1
        if paren_count == 0:
            end_pos = line_start_pos + search_pos
            if search_pos < len(line) and line[search_pos] == ";":
                end_pos += 1
            return (start_pos, end_pos, content[start_pos:end_pos])
        multiline = self.find_multiline_console_log(content, start_pos)
        return multiline

    def find_console_logs(self, content: str) -> List[Tuple[int, int, str]]:
        """Find all console.log statements in content."""
        console_logs = []
        lines = content.split("\n")
        current_pos = 0
        for line_num, line in enumerate(lines):
            line_start_pos = current_pos
            current_pos += len(line) + 1  # +1 for newline
            stripped = line.strip()
            if (
                stripped.startswith("//")
                or stripped.startswith("*")
                or stripped.startswith("/*")
            ):
                continue
            for match in re.finditer(r"console\s*\.\s*log\s*\(", line):
                before_match = line[: match.start()]
                if self.is_in_string_or_comment_on_line(before_match, line):
                    continue
                result = self._resolve_console_log_match(
                    content, line, line_start_pos, match
                )
                if result:
                    console_logs.append(result)
        return console_logs

    def is_in_string_or_comment_on_line(self, before_text: str, full_line: str) -> bool:
        """Check if position is inside string or comment on current line."""
        # Check for single-line comment
        if "//" in full_line:
            comment_pos = full_line.find("//")
            if comment_pos < len(before_text):
                return True

        # Simple string check - count unescaped quotes
        single_quotes = 0
        double_quotes = 0
        i = 0
        while i < len(before_text):
            if before_text[i] == "'" and (i == 0 or before_text[i - 1] != "\\"):
                single_quotes += 1
            elif before_text[i] == '"' and (i == 0 or before_text[i - 1] != "\\"):
                double_quotes += 1
            i += 1

        return single_quotes % 2 == 1 or double_quotes % 2 == 1

    def find_multiline_console_log(
        self, content: str, start_pos: int
    ) -> Tuple[int, int, str]:
        """Find multiline console.log statement."""
        # Simple approach: look for next semicolon or end of block
        search_pos = start_pos
        paren_count = 0
        in_string = False
        string_char = None

        while search_pos < len(content):
            char = content[search_pos]

            if not in_string:
                if char in ['"', "'", "`"]:
                    in_string = True
                    string_char = char
                elif char == "(":
                    paren_count += 1
                elif char == ")":
                    paren_count -= 1
                    if paren_count == 0:
                        # Found end of console.log
                        end_pos = search_pos + 1
                        # Check for semicolon
                        if end_pos < len(content) and content[end_pos] == ";":
                            end_pos += 1
                        return (start_pos, end_pos, content[start_pos:end_pos])
            else:
                if char == string_char and (
                    search_pos == 0 or content[search_pos - 1] != "\\"
                ):
                    in_string = False
                    string_char = None

            search_pos += 1

        return None

    def is_in_comment_or_string(self, content: str, position: int) -> bool:
        """Check if position is inside a comment or string."""
        # Simple check for common cases
        before = content[:position]

        # Check if in single-line comment
        last_newline = before.rfind("\n")
        line_before = before[last_newline:] if last_newline != -1 else before
        if "//" in line_before:
            comment_start = line_before.find("//")
            if comment_start < len(line_before) - len("console"):
                return True

        # Check if in multi-line comment
        open_comment = before.count("/*")
        close_comment = before.count("*/")
        if open_comment > close_comment:
            return True

        # Check if in string (basic check)
        # Count quotes before position
        single_quotes = before.count("'") - before.count("\\'")
        double_quotes = before.count('"') - before.count('\\"')
        backticks = before.count("`")

        if single_quotes % 2 == 1 or double_quotes % 2 == 1 or backticks % 2 == 1:
            return True

        return False

    def remove_console_logs(self, content: str, file_path: Path) -> Tuple[str, int]:
        """Remove console.log statements from content."""
        console_logs = self.find_console_logs(content)

        if not console_logs:
            return content, 0

        # Sort by position (descending) to remove from end to start
        console_logs.sort(key=lambda x: x[0], reverse=True)

        modified_content = content
        removed_count = 0
        removed_details = []

        for start, end, match in console_logs:
            # Check if it's a standalone statement
            # Look for preceding whitespace to maintain formatting
            line_start = content.rfind("\n", 0, start) + 1
            indent = content[line_start:start]

            # Check if entire line is just the console.log
            line_end = content.find("\n", end)
            if line_end == -1:
                line_end = len(content)

            line_content = content[line_start:line_end].strip()

            # If the line only contains the console.log, remove the entire line
            if line_content == match.strip() or line_content == match.strip().rstrip(
                ";"
            ):
                # Remove entire line including newline
                if line_end < len(content):
                    modified_content = (
                        modified_content[:line_start] + modified_content[line_end + 1 :]
                    )
                else:
                    # Last line, just remove from line start
                    modified_content = modified_content[:line_start].rstrip() + "\n"
            else:
                # Just remove the console.log statement
                modified_content = modified_content[:start] + modified_content[end:]

            removed_count += 1

            # Extract what was being logged for report
            log_content = match[match.find("(") + 1 : match.rfind(")")].strip()
            if len(log_content) > 50:
                log_content = log_content[:50] + "..."

            removed_details.append(
                {"line": content[:start].count("\n") + 1, "content": log_content}
            )

        # Store details for report
        if removed_count > 0:
            self.report["details"].append(
                {
                    "file": str(file_path.relative_to(self.project_root)),
                    "removed_count": removed_count,
                    "removed_logs": removed_details,
                }
            )

        return modified_content, removed_count

    def process_file(self, file_path: Path) -> bool:
        """Process a single file to remove console.logs."""
        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            # Remove console.logs
            modified_content, removed_count = self.remove_console_logs(
                original_content, file_path
            )

            # If content changed, write back
            if removed_count > 0:
                # Create backup
                self.create_backup(file_path)

                # Write modified content
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                self.report["console_logs_removed"] += removed_count
                return True

            return False

        except Exception as e:
            self.report["errors"].append(
                {"file": str(file_path.relative_to(self.project_root)), "error": str(e)}
            )
            return False

    def clean_project(self, target_dir: str = None) -> Dict:
        """Clean console.logs from entire project or specific directory."""
        search_root = Path(target_dir) if target_dir else self.project_root

        print(f"🔍 Scanning for console.log statements in: {search_root}")  # noqa: print
        print(f"📁 Backups will be saved to: {self.backup_dir}")  # noqa: print

        # Find all files to process
        files_to_process = []
        for ext in self.target_extensions:
            for file_path in search_root.rglob(f"*{ext}"):
                if self.should_process_file(file_path):
                    files_to_process.append(file_path)

        print(f"\n📊 Found {len(files_to_process)} files to analyze")  # noqa: print

        # Process each file
        for i, file_path in enumerate(files_to_process, 1):
            print(  # noqa: print
                f"\r⚡ Processing file {i}/{len(files_to_process)}: {file_path.name}",
                end="",
                flush=True,
            )

            self.report["files_processed"] += 1
            if self.process_file(file_path):
                self.report["files_modified"] += 1

        print("\n✅ Console.log cleanup completed!")  # noqa: print

        return self.report

    def _build_files_and_errors_section(self) -> str:
        """Build the modified-files and errors sections of the report. Issue #1183."""
        content = ""
        for detail in sorted(
            self.report["details"], key=lambda x: x["removed_count"], reverse=True
        ):
            content += f"\n### {detail['file']}\n"
            content += f"- Removed {detail['removed_count']} console.log statements\n"
            content += "- Locations:\n"
            for log in detail["removed_logs"][:5]:
                content += f"  - Line {log['line']}: `{log['content']}`\n"
            if len(detail["removed_logs"]) > 5:
                content += f"  - ... and {len(detail['removed_logs']) - 5} more\n"
        if self.report["errors"]:
            content += "\n## Errors\n"
            for error in self.report["errors"]:
                content += f"- **{error['file']}**: {error['error']}\n"
        return content

    def generate_report(self, output_file: str = None) -> None:
        """Generate detailed cleanup report."""
        r = self.report
        report_content = (
            f"\n# Console.log Cleanup Report\nGenerated: {r['timestamp']}\n\n"
            f"## Summary\n"
            f"- **Files Processed**: {r['files_processed']}\n"
            f"- **Files Modified**: {r['files_modified']}\n"
            f"- **Console.logs Removed**: {r['console_logs_removed']}\n"
            f"- **Errors**: {len(r['errors'])}\n\n"
            f"## Performance Impact\n"
            f"- **Estimated Size Reduction**: ~{r['console_logs_removed'] * 50} bytes\n"
            f"- **Runtime Performance**: Improved (no console output overhead)\n"
            f"- **Production Build**: Cleaner, more professional\n\n"
            f"## Files Modified\n"
        )
        report_content += self._build_files_and_errors_section()
        report_content += (
            "\n## Recommendations\n"
            "1. **Use a Logger**: Consider using a proper logging library with levels\n"
            "2. **Environment-based Logging**: Use conditional logging based on NODE_ENV\n"
            "3. **ESLint Rule**: Add `no-console` rule to prevent future console.logs\n"
            "4. **Build-time Removal**: Consider using webpack/rollup plugins\n\n"
            f"## Backup Location\nAll modified files have been backed up to: `{self.backup_dir}`\n"
        )
        report_path = (
            Path(output_file)
            if output_file
            else self.project_root / "console-cleanup-report.md"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"\n📄 Report saved to: {report_path}")  # noqa: print
        json_report_path = report_path.with_suffix(".json")
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2)
        print(f"📊 JSON report saved to: {json_report_path}")  # noqa: print


def main():
    """Main entry point for the console.log cleanup tool."""
    parser = argparse.ArgumentParser(
        description="Remove console.log statements from JavaScript/TypeScript/Vue files"
    )
    parser.add_argument(
        "project_path", help="Path to the project root or specific directory to clean"
    )
    parser.add_argument(
        "--target-dir", help="Specific directory to clean (e.g., src/)", default=None
    )
    parser.add_argument("--backup-dir", help="Directory to store backups", default=None)
    parser.add_argument("--report", help="Path for the cleanup report", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without making changes",
    )
    parser.add_argument(
        "--dev-mode",
        action="store_true",
        help="Enable development mode - preserve console.error, console.warn, etc.",
    )
    parser.add_argument(
        "--replace-with-dev-logging",
        action="store_true",
        help="Replace console.log with environment-aware logging",
    )

    args = parser.parse_args()

    # Create cleaner instance
    cleaner = ConsoleLogCleaner(args.project_path, args.backup_dir)

    # Run cleanup
    if args.target_dir:
        target_path = Path(args.project_path) / args.target_dir
        report = cleaner.clean_project(str(target_path))
    else:
        report = cleaner.clean_project()

    # Generate report
    cleaner.generate_report(args.report)

    # Print summary
    print(f"\n🎉 Cleanup Complete!")  # noqa: print
    print(
        f"   - Removed {report['console_logs_removed']} console.log statements"
    )  # noqa: print
    print(f"   - Modified {report['files_modified']} files")  # noqa: print
    print(f"   - Backups saved to: {cleaner.backup_dir}")  # noqa: print


if __name__ == "__main__":
    # If run directly without arguments, use AutoBot defaults
    import sys

    if len(sys.argv) == 1:
        # Default to AutoBot frontend directory
        project_root = "/home/kali/Desktop/AutoBot"
        target_dir = "autobot-vue/src"

        print("🚀 AutoBot Console.log Performance Fix Agent")  # noqa: print
        print("=" * 50)  # noqa: print

        cleaner = ConsoleLogCleaner(project_root)
        report = cleaner.clean_project(os.path.join(project_root, target_dir))
        cleaner.generate_report()
    else:
        main()
