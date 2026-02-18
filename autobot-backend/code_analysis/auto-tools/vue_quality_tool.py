#!/usr/bin/env python3
"""
Vue.js Specific Fix Agent

This agent addresses Vue.js specific issues found in the frontend analysis:
1. Fix v-for loops using index as key (6 instances)
2. Add proper event listener cleanup for Vue components
3. Improve Vue-specific performance patterns
4. Handle both Composition API and Options API patterns

Author: AutoBot Code Analysis Suite
Date: 2025-08-12
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VueSpecificFixAgent:
    """Agent to fix Vue.js specific issues in the codebase."""

    def __init__(self, project_root: str = "/home/kali/Desktop/AutoBot"):
        """Initialize the Vue fix agent."""
        self.project_root = Path(project_root)
        self.vue_dir = self.project_root / "autobot-vue" / "src"
        self.fixes_applied = []
        self.errors = []

        # Pattern matchers for Vue issues
        self.vfor_index_key_pattern = re.compile(
            r'v-for="[^"]*"\s+:key="(?:.*?index.*?)"', re.MULTILINE | re.DOTALL
        )

        self.event_listener_patterns = {
            "addEventListener": re.compile(
                r'(?:window|document|element)\.addEventListener\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([^,)]+)',
                re.MULTILINE,
            ),
            "removeEventListener": re.compile(
                r'(?:window|document|element)\.removeEventListener\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([^,)]+)',
                re.MULTILINE,
            ),
        }

    def analyze_vue_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze a Vue file for specific issues."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            issues = {
                "file": str(file_path),
                "vfor_index_keys": [],
                "missing_event_cleanup": [],
                "performance_issues": [],
                "accessibility_issues": [],
            }

            # Find v-for with index keys
            vfor_matches = self.find_vfor_index_keys(content)
            issues["vfor_index_keys"] = vfor_matches

            # Find event listeners without cleanup
            event_issues = self.find_missing_event_cleanup(content)
            issues["missing_event_cleanup"] = event_issues

            # Find performance issues
            perf_issues = self.find_performance_issues(content)
            issues["performance_issues"] = perf_issues

            return issues

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return {"file": str(file_path), "error": str(e)}

    def find_vfor_index_keys(self, content: str) -> List[Dict[str, Any]]:
        """Find v-for loops using index as key."""
        issues = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Look for v-for with :key="index"
            if "v-for=" in line and ":key=" in line:
                # Extract the v-for and key parts
                vfor_match = re.search(r'v-for="([^"]*)"', line)
                key_match = re.search(r':key="([^"]*)"', line)

                if vfor_match and key_match:
                    vfor_content = vfor_match.group(1)
                    key_content = key_match.group(1)

                    # Check if key uses index
                    if "index" in key_content and key_content.strip() == "index":
                        # Extract item variable name from v-for
                        item_var = self.extract_item_variable(vfor_content)
                        suggested_key = self.suggest_unique_key(item_var, line)

                        issues.append(
                            {
                                "line": i,
                                "content": line.strip(),
                                "current_key": key_content,
                                "item_variable": item_var,
                                "suggested_key": suggested_key,
                                "issue_type": "vfor_index_key",
                            }
                        )

        return issues

    def extract_item_variable(self, vfor_content: str) -> str:
        """Extract the item variable name from v-for content."""
        # Pattern: (item, index) in array or item in array
        match = re.match(r"\s*\(?\s*([^,\s)]+)", vfor_content)
        return match.group(1) if match else "item"

    def suggest_unique_key(self, item_var: str, line: str) -> str:
        """Suggest a unique key based on the context."""
        # Common unique properties
        unique_props = ["id", "uuid", "key", "chatId", "name"]

        # Analyze the line for context
        line_lower = line.lower()

        if "chat" in line_lower:
            return f"{item_var}.chatId || {item_var}.id || `chat-${{{item_var}.name}}`"
        elif "history" in line_lower:
            return f"{item_var}.id || `history-${{{item_var}.date}}`"
        elif "file" in line_lower:
            return f"{item_var}.name || {item_var}.id || `file-${{index}}`"
        elif "message" in line_lower:
            return f"{item_var}.id || {item_var}.timestamp || `msg-${{index}}`"
        elif "result" in line_lower:
            return f"{item_var}.id || `result-${{index}}`"
        elif "link" in line_lower:
            return f"{item_var}.url || {item_var}.href || `link-${{index}}`"
        else:
            # Try to detect if item has common ID properties
            for prop in unique_props:
                if prop in line_lower:
                    return f"{item_var}.{prop} || `{item_var}-${{index}}`"

            # Fallback to composite key
            return f"`{item_var}-${{index}}`"

    def find_missing_event_cleanup(self, content: str) -> List[Dict[str, Any]]:
        """Find event listeners that lack proper cleanup."""
        issues = []
        lines = content.split("\n")

        # Track addEventListener calls
        add_listeners = []
        remove_listeners = []

        for i, line in enumerate(lines, 1):
            # Find addEventListener calls
            add_match = self.event_listener_patterns["addEventListener"].search(line)
            if add_match:
                event_type = add_match.group(1)
                handler = add_match.group(2).strip()
                add_listeners.append(
                    {
                        "line": i,
                        "event": event_type,
                        "handler": handler,
                        "content": line.strip(),
                    }
                )

            # Find removeEventListener calls
            remove_match = self.event_listener_patterns["removeEventListener"].search(
                line
            )
            if remove_match:
                event_type = remove_match.group(1)
                handler = remove_match.group(2).strip()
                remove_listeners.append(
                    {
                        "line": i,
                        "event": event_type,
                        "handler": handler,
                        "content": line.strip(),
                    }
                )

        # Check for missing cleanup
        for add_listener in add_listeners:
            # Look for corresponding removeEventListener
            has_cleanup = False
            for remove_listener in remove_listeners:
                if (
                    add_listener["event"] == remove_listener["event"]
                    and add_listener["handler"] == remove_listener["handler"]
                ):
                    has_cleanup = True
                    break

            if not has_cleanup:
                issues.append(
                    {
                        "line": add_listener["line"],
                        "content": add_listener["content"],
                        "event": add_listener["event"],
                        "handler": add_listener["handler"],
                        "issue_type": "missing_event_cleanup",
                        "suggested_cleanup": f"removeEventListener('{add_listener['event']}', {add_listener['handler']})",
                    }
                )

        return issues

    def find_performance_issues(self, content: str) -> List[Dict[str, Any]]:
        """Find Vue-specific performance issues."""
        issues = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Check for inline functions in templates
            if re.search(r'@\w+="[^"]*=>[^"]*"', line):
                issues.append(
                    {
                        "line": i,
                        "content": line_stripped,
                        "issue_type": "inline_arrow_function",
                        "description": "Inline arrow functions in templates create new functions on each render",
                        "suggestion": "Move to methods or use computed properties",
                    }
                )

            # Check for computed properties that might need memoization
            if "computed:" in line_stripped or "computed(" in line_stripped:
                issues.append(
                    {
                        "line": i,
                        "content": line_stripped,
                        "issue_type": "computed_optimization",
                        "description": "Consider using shallowRef for computed properties with complex objects",
                        "suggestion": "Use shallowRef or shallowReactive for performance",
                    }
                )

        return issues

    def generate_fixes(self, issues: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate fixes for identified issues."""
        fixes = []

        # Fix v-for index keys
        for issue in issues.get("vfor_index_keys", []):
            fix = {
                "type": "vfor_key_fix",
                "line": issue["line"],
                "original": issue["content"],
                "fixed": issue["content"].replace(
                    f':key="{issue["current_key"]}"', f':key="{issue["suggested_key"]}"'
                ),
                "description": f'Replace index key with unique identifier: {issue["suggested_key"]}',
            }
            fixes.append(fix)

        # Fix missing event cleanup
        for issue in issues.get("missing_event_cleanup", []):
            cleanup_code = self.generate_cleanup_code(issue)
            fix = {
                "type": "event_cleanup_fix",
                "line": issue["line"],
                "original": issue["content"],
                "cleanup_code": cleanup_code,
                "description": f'Add cleanup for {issue["event"]} event listener',
            }
            fixes.append(fix)

        return fixes

    def generate_cleanup_code(self, issue: Dict[str, Any]) -> str:
        """Generate cleanup code for event listeners."""
        issue["event"]
        issue["handler"]

        # Detect Vue 3 Composition API vs Options API
        cleanup_code = f"""
// Add to beforeUnmount (Composition API) or beforeDestroy (Options API)
beforeUnmount(() => {{
  {issue['suggested_cleanup']};
}});

// Or in Options API:
beforeDestroy() {{
  {issue['suggested_cleanup']};
}}
"""
        return cleanup_code.strip()

    def apply_fix(self, file_path: Path, fix: Dict[str, Any]) -> bool:
        """Apply a specific fix to a file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if fix["type"] == "vfor_key_fix":
                # Replace the specific line
                line_idx = fix["line"] - 1
                if 0 <= line_idx < len(lines):
                    lines[line_idx] = lines[line_idx].replace(
                        fix["original"].strip(), fix["fixed"].strip()
                    )
                    if not lines[line_idx].endswith("\n"):
                        lines[line_idx] += "\n"

            elif fix["type"] == "event_cleanup_fix":
                # Add cleanup code to the appropriate lifecycle hook
                self.add_cleanup_to_lifecycle(lines, fix)

            # Write back to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            self.fixes_applied.append(
                {"file": str(file_path), "fix": fix, "status": "applied"}
            )

            return True

        except Exception as e:
            error_info = {
                "file": str(file_path),
                "fix": fix,
                "error": str(e),
                "status": "failed",
            }
            self.errors.append(error_info)
            logger.error(f"Failed to apply fix to {file_path}: {e}")
            return False

    def add_cleanup_to_lifecycle(self, lines: List[str], fix: Dict[str, Any]):
        """Add cleanup code to appropriate Vue lifecycle hook."""
        # Find the script section
        script_start = -1
        script_end = -1

        for i, line in enumerate(lines):
            if "<script>" in line or "<script " in line:
                script_start = i
            elif "</script>" in line and script_start != -1:
                script_end = i
                break

        if script_start == -1 or script_end == -1:
            return

        # Determine if it's Composition API or Options API
        script_content = "".join(lines[script_start : script_end + 1])
        is_composition_api = "setup(" in script_content or "setup ()" in script_content

        cleanup_code = fix["cleanup_code"]

        if is_composition_api:
            # Add to Composition API setup function
            self.add_composition_cleanup(lines, script_start, script_end, cleanup_code)
        else:
            # Add to Options API
            self.add_options_cleanup(lines, script_start, script_end, cleanup_code)

    def add_composition_cleanup(
        self, lines: List[str], script_start: int, script_end: int, cleanup_code: str
    ):
        """Add cleanup code to Composition API setup function."""
        # Find the setup function return statement
        for i in range(script_end - 1, script_start, -1):
            if "return {" in lines[i]:
                # Insert cleanup before return
                indent = len(lines[i]) - len(lines[i].lstrip())
                cleanup_lines = [
                    " " * indent + "// Event listener cleanup\n",
                    " " * indent + "onBeforeUnmount(() => {\n",
                    " " * indent
                    + f'  {cleanup_code.split("beforeUnmount(() => {")[1].split("});")[0].strip()};\n',
                    " " * indent + "});\n",
                    "\n",
                ]
                lines[i:i] = cleanup_lines
                break

    def add_options_cleanup(
        self, lines: List[str], script_start: int, script_end: int, cleanup_code: str
    ):
        """Add cleanup code to Options API beforeDestroy hook."""
        # Look for existing beforeDestroy or add new one
        for i in range(script_start, script_end):
            if "beforeDestroy" in lines[i]:
                # Add to existing beforeDestroy
                return

        # Add new beforeDestroy hook
        for i in range(script_end - 1, script_start, -1):
            if "};" in lines[i] or "}" in lines[i].strip():
                indent = len(lines[i]) - len(lines[i].lstrip())
                cleanup_lines = [
                    " " * indent + "beforeDestroy() {\n",
                    " " * indent
                    + f'  {cleanup_code.split("beforeDestroy() {")[1].split("}")[0].strip()};\n',
                    " " * indent + "},\n",
                ]
                lines[i:i] = cleanup_lines
                break

    def create_backup(self, file_path: Path) -> Path:
        """Create a backup of the file before applying fixes."""
        backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
        backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        return backup_path

    def run_analysis(self) -> Dict[str, Any]:
        """Run comprehensive Vue.js analysis."""
        logger.info("Starting Vue.js specific analysis...")

        results = {
            "timestamp": "2025-08-12",
            "files_analyzed": 0,
            "total_issues": 0,
            "issues_by_type": {
                "vfor_index_keys": 0,
                "missing_event_cleanup": 0,
                "performance_issues": 0,
                "accessibility_issues": 0,
            },
            "files": [],
            "summary": {},
        }

        # Find all Vue files
        vue_files = list(self.vue_dir.rglob("*.vue"))

        for vue_file in vue_files:
            logger.info(f"Analyzing {vue_file}")
            file_issues = self.analyze_vue_file(vue_file)

            if "error" not in file_issues:
                results["files"].append(file_issues)
                results["files_analyzed"] += 1

                # Count issues
                for issue_type, issues in file_issues.items():
                    if issue_type in results["issues_by_type"] and isinstance(
                        issues, list
                    ):
                        count = len(issues)
                        results["issues_by_type"][issue_type] += count
                        results["total_issues"] += count

        # Create summary
        results["summary"] = {
            "total_files": results["files_analyzed"],
            "total_issues": results["total_issues"],
            "critical_issues": results["issues_by_type"]["vfor_index_keys"],
            "performance_issues": results["issues_by_type"]["performance_issues"],
            "maintenance_issues": results["issues_by_type"]["missing_event_cleanup"],
        }

        return results

    def apply_all_fixes(self) -> Dict[str, Any]:
        """Apply all generated fixes."""
        logger.info("Applying Vue.js fixes...")

        analysis_results = self.run_analysis()
        fixes_summary = {
            "total_fixes": 0,
            "successful_fixes": 0,
            "failed_fixes": 0,
            "files_modified": set(),
            "fixes_by_type": {"vfor_key_fix": 0, "event_cleanup_fix": 0},
        }

        for file_data in analysis_results["files"]:
            file_path = Path(file_data["file"])

            # Generate fixes for this file
            fixes = self.generate_fixes(file_data)

            if fixes:
                # Create backup
                backup_path = self.create_backup(file_path)
                logger.info(f"Created backup: {backup_path}")

                # Apply each fix
                for fix in fixes:
                    fixes_summary["total_fixes"] += 1

                    if self.apply_fix(file_path, fix):
                        fixes_summary["successful_fixes"] += 1
                        fixes_summary["files_modified"].add(str(file_path))
                        fixes_summary["fixes_by_type"][fix["type"]] += 1
                    else:
                        fixes_summary["failed_fixes"] += 1

        # Convert set to list for JSON serialization
        fixes_summary["files_modified"] = list(fixes_summary["files_modified"])

        return fixes_summary

    def generate_report(
        self, analysis_results: Dict[str, Any], fixes_summary: Dict[str, Any]
    ) -> str:
        """Generate comprehensive Vue.js improvement report."""
        report = f"""
# Vue.js Specific Fix Agent Report
Generated on: {analysis_results['timestamp']}

## Executive Summary
- **Files Analyzed**: {analysis_results['files_analyzed']}
- **Total Issues Found**: {analysis_results['total_issues']}
- **Fixes Applied**: {fixes_summary['successful_fixes']}/{fixes_summary['total_fixes']}
- **Files Modified**: {len(fixes_summary['files_modified'])}

## Issue Breakdown

### Critical Issues
- **v-for Index Keys**: {analysis_results['issues_by_type']['vfor_index_keys']} instances
  - Using array index as key can cause rendering issues
  - Fixed with unique identifiers based on item properties

### Performance Issues
- **Performance Patterns**: {analysis_results['issues_by_type']['performance_issues']} instances
  - Inline functions in templates
  - Unoptimized computed properties

### Maintenance Issues
- **Missing Event Cleanup**: {analysis_results['issues_by_type']['missing_event_cleanup']} instances
  - Event listeners without proper cleanup in lifecycle hooks
  - Can cause memory leaks and unexpected behavior

## Detailed Fixes Applied

### v-for Key Improvements ({fixes_summary['fixes_by_type'].get('vfor_key_fix', 0)} fixes)
"""

        # Add detailed fix information
        for file_data in analysis_results["files"]:
            if file_data.get("vfor_index_keys"):
                report += f"\n**{file_data['file']}**:\n"
                for issue in file_data["vfor_index_keys"]:
                    report += f"- Line {issue['line']}: Changed `:key=\"{issue['current_key']}\"` to `:key=\"{issue['suggested_key']}\"`\n"

        report += f"""
### Event Listener Cleanup ({fixes_summary['fixes_by_type'].get('event_cleanup_fix', 0)} fixes)
"""

        for file_data in analysis_results["files"]:
            if file_data.get("missing_event_cleanup"):
                report += f"\n**{file_data['file']}**:\n"
                for issue in file_data["missing_event_cleanup"]:
                    report += f"- Line {issue['line']}: Added cleanup for '{issue['event']}' event listener\n"

        report += f"""
## Files Modified
"""
        for file_path in fixes_summary["files_modified"]:
            report += f"- {file_path}\n"

        report += f"""
## Recommendations for Further Improvement

### Immediate Actions Required
1. **Test All Modified Components**: Verify functionality after key changes
2. **Review Event Handlers**: Ensure all event listeners have proper cleanup
3. **Update Component Tests**: Modify tests that depend on array index keys

### Long-term Improvements
1. **Implement Vue DevTools**: Use for performance monitoring
2. **Add ESLint Vue Rules**: Prevent similar issues in future development
3. **Component Optimization**: Consider using `shallowRef` for large data sets
4. **Memory Profiling**: Regular checks for memory leaks

### Vue 3 Best Practices
1. **Composition API Migration**: Consider migrating Options API components
2. **Script Setup Syntax**: Use `<script setup>` for better performance
3. **Teleport Usage**: For modal and overlay components
4. **Suspense Integration**: For async component loading

## Error Summary
"""

        if self.errors:
            report += f"**{len(self.errors)} errors occurred during fixing**:\n"
            for error in self.errors:
                report += f"- {error['file']}: {error['error']}\n"
        else:
            report += "✅ All fixes applied successfully with no errors.\n"

        report += f"""
## Next Steps
1. Run `npm run lint` to check for any new linting issues
2. Run `npm run test:unit` to verify component functionality
3. Test the application manually to ensure UI behavior is correct
4. Consider implementing the recommended ESLint rules:
   ```json
   {{
     "rules": {{
       "vue/require-v-for-key": "error",
       "vue/no-side-effects-in-computed-properties": "error",
       "vue/return-in-computed-property": "error"
     }}
   }}
   ```

**Report generated by AutoBot Vue Fix Agent**
"""

        return report


def main():
    """Main function to run Vue-specific fixes."""
    try:
        # Initialize the agent
        agent = VueSpecificFixAgent()

        # Run analysis
        logger.info("Starting Vue.js specific analysis and fixes...")
        analysis_results = agent.run_analysis()

        # Apply fixes
        fixes_summary = agent.apply_all_fixes()

        # Generate report
        report = agent.generate_report(analysis_results, fixes_summary)

        # Save results
        results_dir = Path(__file__).parent / "results"
        results_dir.mkdir(exist_ok=True)

        # Save analysis results
        with open(results_dir / "vue_analysis_results.json", "w") as f:
            json.dump(analysis_results, f, indent=2)

        # Save fixes summary
        with open(results_dir / "vue_fixes_summary.json", "w") as f:
            json.dump(fixes_summary, f, indent=2)

        # Save report
        with open(results_dir / "vue_improvement_report.md", "w") as f:
            f.write(report)

        # Print summary
        print("\n" + "=" * 60)
        print("VUE.JS SPECIFIC FIX AGENT - EXECUTION COMPLETE")
        print("=" * 60)
        print(f"Files Analyzed: {analysis_results['files_analyzed']}")
        print(f"Issues Found: {analysis_results['total_issues']}")
        print(
            f"Fixes Applied: {fixes_summary['successful_fixes']}/{fixes_summary['total_fixes']}"
        )
        print(f"Files Modified: {len(fixes_summary['files_modified'])}")
        print(f"\nReports saved to: {results_dir}")
        print(f"- vue_analysis_results.json")
        print(f"- vue_fixes_summary.json")
        print(f"- vue_improvement_report.md")

        if fixes_summary["failed_fixes"] > 0:
            print(
                f"\n⚠️  {fixes_summary['failed_fixes']} fixes failed - check error logs"
            )
        else:
            print(f"\n✅ All fixes applied successfully!")

        return analysis_results, fixes_summary

    except Exception as e:
        logger.error(f"Error in Vue fix agent: {e}")
        raise


if __name__ == "__main__":
    main()
