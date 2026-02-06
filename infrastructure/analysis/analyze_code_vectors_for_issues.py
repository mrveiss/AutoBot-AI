#!/usr/bin/env python3
"""
Analyze Code Vectors for Issues

This script analyzes the 24,803 code analytics vectors to identify:
- Duplicate code patterns
- Hardcoded values (IPs, passwords, URLs, etc.)
- Architectural issues
- Code quality problems

Focus on extracting insights rather than creating new vectors.
"""

import asyncio
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.constants.network_constants import NetworkConstants

# Use canonical Redis client utility
from src.utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeIssueAnalyzer:
    """Analyzes code vectors to identify duplicates, hardcoded values, and issues"""

    def __init__(self):
        self.analytics_redis = None
        self.analysis_results = {
            "duplicates": [],
            "hardcoded_values": {
                "ip_addresses": [],
                "urls": [],
                "passwords": [],
                "api_keys": [],
                "database_connections": [],
                "file_paths": [],
            },
            "architectural_issues": [],
            "code_quality_issues": [],
            "statistics": {},
        }

    async def initialize(self):
        """Initialize Redis connection using canonical get_redis_client()"""
        try:
            # Use canonical Redis client utility for analytics database (DB 8)
            self.analytics_redis = get_redis_client(
                async_client=False, database="analytics"
            )

            ping_result = self.analytics_redis.ping()
            logger.info(f"✅ Connected to analytics Redis: {ping_result}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            return False

    async def get_code_samples(self, limit: int = 5000) -> List[Dict[str, Any]]:
        """Get a representative sample of code vectors for analysis"""
        try:
            logger.info(f"📦 Getting {limit} code vector samples...")

            # Use SCAN to get vector keys efficiently
            vector_keys = []
            cursor = 0
            scan_count = 0

            while len(vector_keys) < limit:
                cursor, batch = self.analytics_redis.scan(
                    cursor=cursor, match="llama_index/vector_*", count=1000
                )
                vector_keys.extend(batch)
                scan_count += 1

                if cursor == 0 or scan_count > 10:  # Limit scans to prevent timeout
                    break

            # Limit to requested amount
            vector_keys = vector_keys[:limit]

            logger.info(
                f"📄 Found {len(vector_keys)} vector keys, processing in batches..."
            )

            # Process in small batches to avoid timeout
            batch_size = 100
            code_samples = []

            for i in range(0, len(vector_keys), batch_size):
                batch = vector_keys[i : i + batch_size]

                try:
                    # Get vector data for batch
                    pipe = self.analytics_redis.pipeline()
                    for key in batch:
                        pipe.hgetall(key)

                    batch_data = pipe.execute()

                    for key, data in zip(batch, batch_data):
                        if data and b"text" in data:
                            try:
                                text = data[b"text"].decode("utf-8", errors="ignore")
                                doc_id = data.get(b"doc_id", b"").decode(
                                    "utf-8", errors="ignore"
                                )

                                # Only include meaningful code samples
                                if len(text.strip()) > 20:
                                    code_samples.append(
                                        {
                                            "id": key.decode("utf-8"),
                                            "text": text,
                                            "doc_id": doc_id,
                                            "length": len(text),
                                        }
                                    )

                            except Exception as e:
                                logger.warning(
                                    f"⚠️ Failed to process vector {key}: {e}"
                                )
                                continue

                    # Progress update
                    if (i // batch_size + 1) % 10 == 0:
                        logger.info(
                            f"📊 Processed {i + batch_size}/{len(vector_keys)} vectors..."
                        )

                    # Small pause to prevent overwhelming Redis
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to process batch {i//batch_size + 1}: {e}"
                    )
                    continue

            logger.info(f"✅ Successfully extracted {len(code_samples)} code samples")
            return code_samples

        except Exception as e:
            logger.error(f"❌ Failed to get code samples: {e}")
            return []

    async def find_duplicate_code(
        self, code_samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find duplicate code patterns"""
        try:
            logger.info("🔍 Analyzing for duplicate code patterns...")

            # Group by normalized text to find duplicates
            text_groups = defaultdict(list)

            for sample in code_samples:
                # Normalize text for comparison (remove whitespace variations)
                normalized = re.sub(r"\s+", " ", sample["text"].strip().lower())

                # Only consider significant code blocks (not single lines)
                if len(normalized) > 50:
                    text_groups[normalized].append(sample)

            # Find groups with duplicates
            duplicates = []
            for normalized_text, samples in text_groups.items():
                if len(samples) > 1:
                    # This is a duplicate pattern
                    duplicate_info = {
                        "pattern": normalized_text[:200] + "..."
                        if len(normalized_text) > 200
                        else normalized_text,
                        "occurrences": len(samples),
                        "files": [sample["doc_id"] for sample in samples],
                        "severity": "high"
                        if len(samples) > 5
                        else "medium"
                        if len(samples) > 2
                        else "low",
                        "estimated_lines": samples[0]["length"] // 50,  # Rough estimate
                    }
                    duplicates.append(duplicate_info)

            # Sort by number of occurrences
            duplicates.sort(key=lambda x: x["occurrences"], reverse=True)

            logger.info(f"📊 Found {len(duplicates)} duplicate code patterns")

            # Show top 5 duplicates
            for i, dup in enumerate(duplicates[:5]):
                logger.info(
                    f"  {i+1}. {dup['occurrences']} occurrences in {len(dup['files'])} files"
                )

            return duplicates

        except Exception as e:
            logger.error(f"❌ Duplicate code analysis failed: {e}")
            return []

    async def find_hardcoded_values(
        self, code_samples: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Find hardcoded values in code"""
        try:
            logger.info("🔍 Analyzing for hardcoded values...")

            hardcoded = {
                "ip_addresses": [],
                "urls": [],
                "passwords": [],
                "api_keys": [],
                "database_connections": [],
                "file_paths": [],
            }

            # Regex patterns for different types of hardcoded values
            patterns = {
                "ip_addresses": [
                    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
                    r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b",
                ],
                "urls": [
                    r'https?://[^\s"\'<>]+',
                    r'ftp://[^\s"\'<>]+',
                    r'ws://[^\s"\'<>]+',
                    r'wss://[^\s"\'<>]+',
                ],
                "passwords": [
                    r'password\s*[:=]\s*["\']([^"\']+)["\']',
                    r'pwd\s*[:=]\s*["\']([^"\']+)["\']',
                    r'secret\s*[:=]\s*["\']([^"\']+)["\']',
                ],
                "api_keys": [
                    r'api[_-]?key\s*[:=]\s*["\']([^"\']+)["\']',
                    r'access[_-]?token\s*[:=]\s*["\']([^"\']+)["\']',
                    r"bearer\s+([a-zA-Z0-9_-]{20,})",
                ],
                "database_connections": [
                    r'mongodb://[^\s"\'<>]+',
                    r'postgresql://[^\s"\'<>]+',
                    r'mysql://[^\s"\'<>]+',
                    r'redis://[^\s"\'<>]+',
                ],
                "file_paths": [
                    r'(?:/[^/\s"\'<>]+){2,}',  # Unix paths
                    r'[C-Z]:\\[^\\s"\'<>\\]+(?:\\[^\\s"\'<>\\]+)+',  # Windows paths
                    r'~/[^\s"\'<>]+',  # Home directory paths
                ],
            }

            # Issue #506: Precompile and combine patterns per category
            # Reduces O(n⁴) to O(n²) by eliminating per-pattern loop
            compiled_patterns = {}
            for category, pattern_list in patterns.items():
                # Combine all patterns for this category into one regex
                combined = "|".join(f"({p})" for p in pattern_list)
                compiled_patterns[category] = re.compile(
                    combined, re.IGNORECASE | re.MULTILINE
                )

            # Analyze each code sample
            for sample in code_samples:
                text = sample["text"]
                doc_id = sample["doc_id"]

                # Issue #506: Single pass per category instead of per-pattern
                for category, compiled_pattern in compiled_patterns.items():
                    try:
                        matches = compiled_pattern.findall(text)

                        for match in matches:
                            # Extract the actual value (handle tuple results from groups)
                            value = (
                                match[0]
                                if isinstance(match, tuple) and len(match) > 0
                                else match
                            )

                            # Skip common false positives
                            if self.is_likely_hardcoded_value(category, value):
                                hardcoded[category].append(
                                    {
                                        "value": value,
                                        "file": doc_id,
                                        "context": text[
                                            max(0, text.find(value) - 50) : text.find(
                                                value
                                            )
                                            + 100
                                        ],
                                        "severity": self.assess_hardcode_severity(
                                            category, value
                                        ),
                                    }
                                )

                    except Exception as e:
                        logger.warning(
                            f"⚠️ Pattern matching failed for {category}: {e}"
                        )
                        continue

            # Remove duplicates and sort by severity
            for category in hardcoded:
                # Remove duplicates based on value
                seen_values = set()
                unique_items = []

                for item in hardcoded[category]:
                    if item["value"] not in seen_values:
                        seen_values.add(item["value"])
                        unique_items.append(item)

                # Sort by severity (critical first)
                severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                unique_items.sort(key=lambda x: severity_order.get(x["severity"], 3))

                hardcoded[category] = unique_items

            # Log summary
            total_hardcoded = sum(len(items) for items in hardcoded.values())
            logger.info(f"📊 Found {total_hardcoded} hardcoded values:")
            for category, items in hardcoded.items():
                if items:
                    logger.info(f"  - {category}: {len(items)}")

            return hardcoded

        except Exception as e:
            logger.error(f"❌ Hardcoded values analysis failed: {e}")
            return {}

    # Issue #626: Pre-computed lowercase frozensets for O(1) lookups
    # Moved outside method to avoid recreating on every call
    _IGNORE_PATTERNS: dict = {
        "ip_addresses": frozenset({"0.0.0.0", "255.255.255.255", "127.0.0.1"}),
        "urls": frozenset(
            {"http://example.com", "https://example.org", "http://localhost"}
        ),
        "file_paths": frozenset(
            {"/dev/null", "/tmp", "/var/log", "~/", "/etc", "/usr", "/bin"}
        ),
        "passwords": frozenset({"password", "123456", "admin", "test"}),
        "api_keys": frozenset({"your_api_key", "api_key_here", "xxx"}),
    }

    def is_likely_hardcoded_value(self, category: str, value: str) -> bool:
        """Determine if a value is likely a hardcoded value worth reporting"""

        # Check if it's in ignore list - O(1) lookup with pre-computed frozensets
        if category in self._IGNORE_PATTERNS:
            if value.lower() in self._IGNORE_PATTERNS[category]:
                return False

        # Additional filtering
        if category == "ip_addresses":
            # Skip localhost and common test IPs
            if value in NetworkConstants.LOOPBACK_IPS_V4:
                return False

        elif category == "file_paths":
            # Skip very common system paths
            if len(value) < 10 or value.startswith(("/dev", "/proc", "/sys")):
                return False

        elif category == "passwords":
            # Skip obvious placeholders
            if len(value) < 6 or value.lower() in {
                "password",
                "placeholder",
                "example",
            }:
                return False

        return True

    def assess_hardcode_severity(self, category: str, value: str) -> str:
        """Assess the severity of a hardcoded value"""

        # Critical severity
        if category == "passwords" and len(value) > 8:
            return "critical"
        if category == "api_keys" and len(value) > 20:
            return "critical"
        if category == "database_connections" and any(
            keyword in value.lower() for keyword in ["password", "secret"]
        ):
            return "critical"

        # High severity
        if category == "ip_addresses" and not value.startswith(
            ("127.", "192.168.", "10.", "172.")
        ):
            return "high"  # Public IP
        if (
            category == "urls"
            and value.startswith("https://")
            and "api" in value.lower()
        ):
            return "high"

        # Medium severity
        if category == "file_paths" and "/home/" in value:
            return "medium"
        if category == "ip_addresses":
            return "medium"

        # Low severity (default)
        return "low"

    async def analyze_architectural_issues(
        self, code_samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze for architectural issues"""
        try:
            logger.info("🔍 Analyzing for architectural issues...")

            issues = []

            # Count imports and dependencies
            import_patterns = defaultdict(int)
            dependency_files = []

            # Analyze patterns that indicate architectural issues
            for sample in code_samples:
                text = sample["text"]
                doc_id = sample["doc_id"]

                # Look for import statements
                import_matches = re.findall(
                    r"(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", text
                )
                for imp in import_matches:
                    import_patterns[imp] += 1

                # Check for architectural anti-patterns

                # Circular imports
                if "import" in text and doc_id:
                    dependency_files.append((doc_id, import_matches))

                # Large functions (rough heuristic)
                function_matches = re.findall(
                    r"def\s+\w+.*?(?=\ndef|\nclass|\n\n|\Z)", text, re.DOTALL
                )
                for func in function_matches:
                    if len(func) > 1000:  # Very large function
                        issues.append(
                            {
                                "type": "large_function",
                                "file": doc_id,
                                "severity": "medium",
                                "description": f"Large function detected ({len(func)} characters)",
                                "recommendation": "Consider breaking down into smaller functions",
                            }
                        )

                # High cyclomatic complexity (rough heuristic)
                if_count = len(re.findall(r"\bif\b", text))
                for_count = len(re.findall(r"\bfor\b", text))
                while_count = len(re.findall(r"\bwhile\b", text))
                complexity_score = if_count + for_count + while_count

                if complexity_score > 20:  # High complexity
                    issues.append(
                        {
                            "type": "high_complexity",
                            "file": doc_id,
                            "severity": "medium",
                            "description": f"High cyclomatic complexity (score: {complexity_score})",
                            "recommendation": "Refactor to reduce complexity",
                        }
                    )

                # TODO/FIXME comments
                todo_matches = re.findall(
                    r"#.*(?:TODO|FIXME|XXX|HACK).*", text, re.IGNORECASE
                )
                if len(todo_matches) > 5:
                    issues.append(
                        {
                            "type": "technical_debt",
                            "file": doc_id,
                            "severity": "low",
                            "description": f"High number of TODO/FIXME comments ({len(todo_matches)})",
                            "recommendation": "Address technical debt items",
                        }
                    )

            # Note: Circular reference detection would analyze dependency_files
            # but is not implemented in this simplified version

            logger.info(f"📊 Found {len(issues)} architectural issues")

            # Sort by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            issues.sort(key=lambda x: severity_order.get(x["severity"], 3))

            return issues

        except Exception as e:
            logger.error(f"❌ Architectural analysis failed: {e}")
            return []

    async def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report.

        Uses list accumulation + join() instead of += for O(n) performance.
        Issue #622: Fix excessive string concatenation in loops.
        """
        try:
            logger.info("📝 Generating summary report...")

            duplicates = self.analysis_results["duplicates"]
            hardcoded = self.analysis_results["hardcoded_values"]
            architectural = self.analysis_results["architectural_issues"]

            # Use list accumulation for O(n) string building instead of += (O(n²))
            report_parts = []

            report_parts.append(
                f"""
# AutoBot Codebase Analysis Report
Generated: {datetime.now().isoformat()}

## Executive Summary

This analysis examined code vectors from the AutoBot codebase to identify:
- Code duplication patterns
- Hardcoded values that should be configurable
- Architectural issues affecting maintainability

## Key Findings

### 🔄 Code Duplication
- **{len(duplicates)} duplicate patterns** identified
- **Top duplicates:**"""
            )

            # Add top 5 duplicates using list comprehension + join
            duplicate_lines = [
                f"\n  {i+1}. {dup['occurrences']} occurrences ({dup['severity']} severity)"
                for i, dup in enumerate(duplicates[:5])
            ]
            report_parts.append("".join(duplicate_lines))

            # Hardcoded values summary
            total_hardcoded = sum(len(items) for items in hardcoded.values())
            critical_hardcoded = sum(
                len([item for item in items if item.get("severity") == "critical"])
                for items in hardcoded.values()
            )

            report_parts.append(
                f"""

### 🔒 Hardcoded Values
- **{total_hardcoded} hardcoded values** found
- **{critical_hardcoded} critical security issues**
- **Breakdown by category:**"""
            )

            # Add hardcoded breakdown using list comprehension + join
            hardcoded_lines = [
                f"\n  - {category}: {len(items)} total "
                f"({len([item for item in items if item.get('severity') == 'critical'])} critical)"
                for category, items in hardcoded.items()
                if items
            ]
            report_parts.append("".join(hardcoded_lines))

            # Architectural issues
            critical_arch = len(
                [
                    issue
                    for issue in architectural
                    if issue.get("severity") == "critical"
                ]
            )
            high_arch = len(
                [issue for issue in architectural if issue.get("severity") == "high"]
            )

            report_parts.append(
                f"""

### 🏗️ Architectural Issues
- **{len(architectural)} architectural issues** identified
- **{critical_arch} critical** and **{high_arch} high** severity issues
- **Common issues:**"""
            )

            # Group architectural issues by type
            issue_types = defaultdict(int)
            for issue in architectural:
                issue_types[issue["type"]] += 1

            # Add issue types using list comprehension + join
            issue_type_lines = [
                f"\n  - {issue_type}: {count} occurrences"
                for issue_type, count in sorted(
                    issue_types.items(), key=lambda x: x[1], reverse=True
                )
            ]
            report_parts.append("".join(issue_type_lines))

            report_parts.append(
                f"""

## Recommendations

### 🎯 Priority Actions
1. **Address critical hardcoded values** - {critical_hardcoded} items need immediate attention
2. **Refactor top duplicate code** - Focus on patterns with >5 occurrences
3. **Fix high-severity architectural issues** - {high_arch} items affecting maintainability

### 📋 Next Steps
- Create configuration system for hardcoded values
- Implement code deduplication strategy
- Set up architectural guidelines and linting rules
- Schedule regular code quality reviews

## Detailed Findings

[See individual sections below for specific items and recommendations]
"""
            )

            return "".join(report_parts)

        except Exception as e:
            logger.error(f"❌ Report generation failed: {e}")
            return "Report generation failed"


async def main():
    """Main execution function"""
    try:
        print("🔍 Analyzing Code Vectors for Issues...")
        print(f"⏰ Started at: {datetime.now().isoformat()}")

        analyzer = CodeIssueAnalyzer()

        # Initialize
        if not await analyzer.initialize():
            print("❌ Failed to initialize analyzer")
            return

        # Get code samples
        print("\n📦 Step 1: Extracting code samples...")
        code_samples = await analyzer.get_code_samples(
            limit=3000
        )  # Reasonable sample size

        if not code_samples:
            print("❌ No code samples found")
            return

        print(f"✅ Extracted {len(code_samples)} code samples")

        # Find duplicates
        print("\n🔄 Step 2: Analyzing for duplicate code...")
        duplicates = await analyzer.find_duplicate_code(code_samples)
        analyzer.analysis_results["duplicates"] = duplicates

        if duplicates:
            print(f"✅ Found {len(duplicates)} duplicate patterns")
        else:
            print("ℹ️ No significant duplicates found")

        # Find hardcoded values
        print("\n🔒 Step 3: Analyzing for hardcoded values...")
        hardcoded = await analyzer.find_hardcoded_values(code_samples)
        analyzer.analysis_results["hardcoded_values"] = hardcoded

        total_hardcoded = sum(len(items) for items in hardcoded.values())
        if total_hardcoded > 0:
            print(f"✅ Found {total_hardcoded} hardcoded values")
        else:
            print("ℹ️ No significant hardcoded values found")

        # Analyze architectural issues
        print("\n🏗️ Step 4: Analyzing architectural issues...")
        architectural = await analyzer.analyze_architectural_issues(code_samples)
        analyzer.analysis_results["architectural_issues"] = architectural

        if architectural:
            print(f"✅ Found {len(architectural)} architectural issues")
        else:
            print("ℹ️ No significant architectural issues found")

        # Generate report
        print("\n📝 Step 5: Generating summary report...")
        report = await analyzer.generate_summary_report()

        # Save report - use project-relative path
        project_root = Path(__file__).parent.parent
        report_path = (
            project_root
            / "tests"
            / "results"
            / f"code_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Issue #666: Use asyncio.to_thread to avoid blocking the event loop
        def _write_report():
            with open(str(report_path), "w", encoding="utf-8") as f:
                f.write(report)

        await asyncio.to_thread(_write_report)

        print(f"✅ Report saved to: {str(report_path)}")

        # Summary
        print("\n🎉 Code Analysis Complete!")
        print("📊 Summary:")
        print(f"  - Code samples analyzed: {len(code_samples)}")
        print(f"  - Duplicate patterns: {len(duplicates)}")
        print(f"  - Hardcoded values: {total_hardcoded}")
        print(f"  - Architectural issues: {len(architectural)}")
        print(f"  - Report saved: {str(report_path)}")

        print("\n💡 This analysis will help identify:")
        print("   - Code that can be deduplicated")
        print("   - Values that should be moved to configuration")
        print("   - Architecture improvements needed")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
