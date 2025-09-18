#!/usr/bin/env python3
"""
Development Logging Fix Agent
Replaces console.log statements with environment-aware logging
that outputs to browser in development mode but is silent in production.
"""

import os
import re
import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Set
import argparse


class DevLoggingFixer:
    """Replaces console.log with environment-aware development logging."""

    def __init__(self, project_root: str, backup_dir: str = None):
        self.project_root = Path(project_root)
        self.backup_dir = (
            Path(backup_dir)
            if backup_dir
            else self.project_root / ".dev-logging-backups"
        )
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "files_processed": 0,
            "files_modified": 0,
            "console_logs_converted": 0,
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

    def create_dev_logger_utility(self, target_dir: Path) -> None:
        """Create the development logger utility file."""
        utils_dir = target_dir / "utils"
        utils_dir.mkdir(exist_ok=True)

        logger_file = utils_dir / "devLogger.js"

        logger_code = """/**
 * Development Logger Utility
 * Provides environment-aware logging that only outputs in development mode.
 */

// Check if we're in development mode
const isDevelopment = process.env.NODE_ENV === 'development' ||
                     process.env.NODE_ENV === 'dev' ||
                     !process.env.NODE_ENV || // Default to dev if not set
                     window.location.hostname === 'localhost' ||
                     window.location.hostname === '127.0.0.1';

/**
 * Development logger that only outputs in development environment
 */
export const devLog = {
  /**
   * Log message (only in development)
   * @param {...any} args - Arguments to log
   */
  log: (...args) => {
    if (isDevelopment) {
      console.log('[DEV]', ...args);
    }
  },

  /**
   * Log info message (only in development)
   * @param {...any} args - Arguments to log
   */
  info: (...args) => {
    if (isDevelopment) {
      console.info('[DEV-INFO]', ...args);
    }
  },

  /**
   * Log debug message (only in development)
   * @param {...any} args - Arguments to log
   */
  debug: (...args) => {
    if (isDevelopment) {
      console.debug('[DEV-DEBUG]', ...args);
    }
  },

  /**
   * Log warning (always shown - important for debugging)
   * @param {...any} args - Arguments to log
   */
  warn: (...args) => {
    console.warn('[WARN]', ...args);
  },

  /**
   * Log error (always shown - critical for debugging)
   * @param {...any} args - Arguments to log
   */
  error: (...args) => {
    console.error('[ERROR]', ...args);
  },

  /**
   * Group logging (only in development)
   * @param {string} label - Group label
   * @param {Function} fn - Function to execute within group
   */
  group: (label, fn) => {
    if (isDevelopment) {
      console.group(`[DEV-GROUP] ${label}`);
      try {
        fn();
      } finally {
        console.groupEnd();
      }
    }
  },

  /**
   * Table logging (only in development)
   * @param {any} data - Data to display as table
   */
  table: (data) => {
    if (isDevelopment) {
      console.table(data);
    }
  },

  /**
   * Time logging (only in development)
   * @param {string} label - Timer label
   */
  time: (label) => {
    if (isDevelopment) {
      console.time(`[DEV-TIME] ${label}`);
    }
  },

  /**
   * End time logging (only in development)
   * @param {string} label - Timer label
   */
  timeEnd: (label) => {
    if (isDevelopment) {
      console.timeEnd(`[DEV-TIME] ${label}`);
    }
  },

  /**
   * Check if in development mode
   * @returns {boolean} True if in development
   */
  isDev: () => isDevelopment,

  /**
   * Conditional logging - only log if condition is true and in development
   * @param {boolean} condition - Condition to check
   * @param {...any} args - Arguments to log
   */
  logIf: (condition, ...args) => {
    if (isDevelopment && condition) {
      console.log('[DEV-CONDITIONAL]', ...args);
    }
  }
};

// Export default for easier importing
export default devLog;

// Also export as a named export for convenience
export { devLog as logger };
"""

        with open(logger_file, "w") as f:
            f.write(logger_code)

        print(f"✅ Created development logger utility: {logger_file}")

    def convert_console_logs(self, content: str, file_path: Path) -> Tuple[str, int]:
        """Convert console.log statements to use devLog."""
        # Add import statement at the top if not present
        import_statement = "import { devLog } from '@/utils/devLogger.js';"

        # Check if import already exists
        has_import = "devLog" in content or "devLogger" in content

        # Find console.log statements
        console_log_pattern = r"console\.log\s*\("
        matches = list(re.finditer(console_log_pattern, content))

        if not matches:
            return content, 0

        # Sort matches by position (descending) to replace from end to start
        matches.sort(key=lambda x: x.start(), reverse=True)

        modified_content = content
        converted_count = 0
        conversion_details = []

        for match in matches:
            # Check if it's inside a comment or string
            if self.is_in_comment_or_string(content, match.start()):
                continue

            # Find the complete console.log statement
            start_pos = match.start()

            # Find matching closing parenthesis
            paren_count = 0
            search_pos = match.end() - 1  # Start at opening parenthesis

            while search_pos < len(content):
                char = content[search_pos]
                if char == "(":
                    paren_count += 1
                elif char == ")":
                    paren_count -= 1
                    if paren_count == 0:
                        break
                search_pos += 1

            if paren_count == 0:
                end_pos = search_pos + 1

                # Extract the arguments
                args_start = content.find("(", start_pos) + 1
                args_end = search_pos
                args = content[args_start:args_end].strip()

                # Replace console.log with devLog.log
                replacement = f"devLog.log({args})"
                modified_content = (
                    modified_content[:start_pos]
                    + replacement
                    + modified_content[end_pos:]
                )

                converted_count += 1
                conversion_details.append(
                    {
                        "line": content[:start_pos].count("\n") + 1,
                        "original": f"console.log({args})",
                        "converted": replacement,
                    }
                )

        # Add import statement if we made conversions and don't have import
        if converted_count > 0 and not has_import:
            # Find the best place to add import (after other imports)
            lines = modified_content.split("\n")
            import_index = 0

            # Look for existing imports or script tag
            for i, line in enumerate(lines):
                if (
                    "import " in line
                    or line.strip().startswith("<script")
                    or "from " in line
                ):
                    import_index = i + 1
                elif line.strip() == "" and import_index > 0:
                    import_index = i
                    break

            # Insert import statement
            lines.insert(import_index, import_statement)
            lines.insert(import_index + 1, "")  # Add blank line
            modified_content = "\n".join(lines)

        # Store details for report
        if converted_count > 0:
            self.report["details"].append(
                {
                    "file": str(file_path.relative_to(self.project_root)),
                    "converted_count": converted_count,
                    "conversions": conversion_details,
                }
            )

        return modified_content, converted_count

    def is_in_comment_or_string(self, content: str, position: int) -> bool:
        """Check if position is inside a comment or string (simple implementation)."""
        before = content[:position]

        # Check if in single-line comment
        last_newline = before.rfind("\n")
        line_before = before[last_newline:] if last_newline != -1 else before
        if "//" in line_before:
            return True

        # Check if in multi-line comment
        open_comment = before.count("/*")
        close_comment = before.count("*/")
        if open_comment > close_comment:
            return True

        # Basic string check
        single_quotes = before.count("'") - before.count("\\'")
        double_quotes = before.count('"') - before.count('\\"')

        return single_quotes % 2 == 1 or double_quotes % 2 == 1

    def process_file(self, file_path: Path) -> bool:
        """Process a single file to convert console.logs."""
        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            # Convert console.logs
            modified_content, converted_count = self.convert_console_logs(
                original_content, file_path
            )

            # If content changed, write back
            if converted_count > 0:
                # Create backup
                self.create_backup(file_path)

                # Write modified content
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                self.report["console_logs_converted"] += converted_count
                return True

            return False

        except Exception as e:
            self.report["errors"].append(
                {"file": str(file_path.relative_to(self.project_root)), "error": str(e)}
            )
            return False

    def convert_project(self, target_dir: str = None) -> Dict:
        """Convert console.logs in entire project or specific directory."""
        search_root = Path(target_dir) if target_dir else self.project_root

        print(f"🔧 Converting console.log to development logging in: {search_root}")
        print(f"📁 Backups will be saved to: {self.backup_dir}")

        # Create development logger utility
        self.create_dev_logger_utility(search_root)

        # Find all files to process
        files_to_process = []
        for ext in self.target_extensions:
            for file_path in search_root.rglob(f"*{ext}"):
                if self.should_process_file(file_path):
                    files_to_process.append(file_path)

        print(f"\n📊 Found {len(files_to_process)} files to analyze")

        # Process each file
        for i, file_path in enumerate(files_to_process, 1):
            print(
                f"\r⚡ Processing file {i}/{len(files_to_process)}: {file_path.name}",
                end="",
                flush=True,
            )

            self.report["files_processed"] += 1
            if self.process_file(file_path):
                self.report["files_modified"] += 1

        print("\n✅ Development logging conversion completed!")

        return self.report

    def generate_report(self, output_file: str = None) -> None:
        """Generate detailed conversion report."""
        report_content = f"""
# Development Logging Conversion Report
Generated: {self.report['timestamp']}

## Summary
- **Files Processed**: {self.report['files_processed']}
- **Files Modified**: {self.report['files_modified']}
- **Console.logs Converted**: {self.report['console_logs_converted']}
- **Errors**: {len(self.report['errors'])}

## Development Logging Benefits
- **Environment Aware**: Only logs in development, silent in production
- **Better Performance**: Zero overhead in production builds
- **Enhanced Debugging**: Prefixed logs for easy identification
- **Flexible**: Easy to toggle or modify logging behavior

## Usage
The converted code now uses `devLog.log()` instead of `console.log()`.
Import statement has been added: `import {{ devLog }} from '@/utils/devLogger.js';`

### Available Methods:
- `devLog.log()` - Development-only logging
- `devLog.info()` - Development-only info logging
- `devLog.debug()` - Development-only debug logging
- `devLog.warn()` - Always shown warnings
- `devLog.error()` - Always shown errors
- `devLog.group()` - Development-only grouped logging
- `devLog.table()` - Development-only table logging

## Files Modified
"""

        # Add details for each modified file
        for detail in sorted(
            self.report["details"], key=lambda x: x["converted_count"], reverse=True
        ):
            report_content += f"\n### {detail['file']}\n"
            report_content += (
                f"- Converted {detail['converted_count']} console.log statements\n"
            )
            report_content += "- Conversions:\n"
            for conv in detail["conversions"][:3]:  # Show first 3
                report_content += f"  - Line {conv['line']}: `{conv['original']}` → `{conv['converted']}`\n"
            if len(detail["conversions"]) > 3:
                report_content += f"  - ... and {len(detail['conversions']) - 3} more\n"

        # Add errors if any
        if self.report["errors"]:
            report_content += "\n## Errors\n"
            for error in self.report["errors"]:
                report_content += f"- **{error['file']}**: {error['error']}\n"

        # Add next steps
        report_content += """
## Next Steps
1. **Test Development Mode**: Verify logs appear in browser console during development
2. **Test Production Build**: Confirm logs are silent in production build
3. **Update Build Config**: Ensure NODE_ENV is properly set for different environments
4. **ESLint Configuration**: Add rule to prefer devLog over console.log

## Environment Setup
Make sure your build process sets NODE_ENV appropriately:
- Development: `NODE_ENV=development`
- Production: `NODE_ENV=production`

## Backup Location
All modified files have been backed up to: `{}`
""".format(
            self.backup_dir
        )

        # Save report
        if output_file:
            report_path = Path(output_file)
        else:
            report_path = self.project_root / "dev-logging-conversion-report.md"

        with open(report_path, "w") as f:
            f.write(report_content)

        print(f"\n📄 Report saved to: {report_path}")

        # Also save JSON report
        json_report_path = report_path.with_suffix(".json")
        with open(json_report_path, "w") as f:
            json.dump(self.report, f, indent=2)

        print(f"📊 JSON report saved to: {json_report_path}")


def main():
    """Main entry point for the development logging conversion tool."""
    parser = argparse.ArgumentParser(
        description="Convert console.log to environment-aware development logging"
    )
    parser.add_argument(
        "project_path", help="Path to the project root or specific directory to convert"
    )
    parser.add_argument(
        "--target-dir", help="Specific directory to convert (e.g., src/)", default=None
    )
    parser.add_argument("--backup-dir", help="Directory to store backups", default=None)
    parser.add_argument("--report", help="Path for the conversion report", default=None)

    args = parser.parse_args()

    # Create converter instance
    converter = DevLoggingFixer(args.project_path, args.backup_dir)

    # Run conversion
    if args.target_dir:
        target_path = Path(args.project_path) / args.target_dir
        report = converter.convert_project(str(target_path))
    else:
        report = converter.convert_project()

    # Generate report
    converter.generate_report(args.report)

    # Print summary
    print(f"\n🎉 Conversion Complete!")
    print(f"   - Converted {report['console_logs_converted']} console.log statements")
    print(f"   - Modified {report['files_modified']} files")
    print(f"   - Created development logger utility")
    print(f"   - Backups saved to: {converter.backup_dir}")


if __name__ == "__main__":
    # If run directly without arguments, use AutoBot defaults
    import sys

    if len(sys.argv) == 1:
        # Default to AutoBot frontend directory
        project_root = "/home/kali/Desktop/AutoBot"
        target_dir = "autobot-vue/src"

        print("🚀 AutoBot Development Logging Conversion Agent")
        print("=" * 50)

        converter = DevLoggingFixer(project_root)
        report = converter.convert_project(os.path.join(project_root, target_dir))
        converter.generate_report()
    else:
        main()
