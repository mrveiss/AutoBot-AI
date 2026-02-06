#!/usr/bin/env python3
"""
Focused analysis for critical hardcoded environment variables
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List


class CriticalEnvAnalyzer:
    """Focused analyzer for critical hardcoded values"""

    def __init__(self):
        # Critical patterns that definitely should be configurable
        self.critical_patterns = {
            "database_paths": [
                r'["\']([^"\']*\.db)["\']',
                r'["\']([^"\']*\.sqlite)["\']',
                r'["\']([^"\']*data/[^"\']*)["\']',
            ],
            "network_hosts": [
                r'["\']localhost["\']',
                r'["\']127\.0\.0\.1["\']',
                r'["\']0\.0\.0\.0["\']',
            ],
            "network_ports": [
                r"\bport\s*=\s*(\d{4,5})",
                r":\s*(\d{4,5})\b",
                r"\b(8001|8000|8080|3000|5000|6379)\b",
            ],
            "api_urls": [
                r'["\']https?://[^"\']+["\']',
                r'["\']wss?://[^"\']+["\']',
            ],
            "file_paths": [
                r'["\'](/[^"\']+\.(?:log|json|yaml|yml|conf|cfg|ini))["\']',
                r'["\'](\./[^"\']+\.(?:log|json|yaml|yml|conf|cfg|ini))["\']',
            ],
            "timeouts": [
                r"timeout\s*=\s*(\d+)",
                r"TIMEOUT\s*=\s*(\d+)",
            ],
            "redis_config": [
                r'["\']redis://[^"\']*["\']',
                r'redis_[a-z_]*\s*=\s*["\']([^"\']+)["\']',
            ],
        }

    async def find_critical_hardcoded_values(self) -> Dict[str, List[Dict[str, Any]]]:
        """Find critical hardcoded values that should be configurable"""

        results = {}

        # Scan Python files
        python_files = list(Path(".").rglob("*.py"))
        python_files = [f for f in python_files if not self._should_skip_file(f)]

        for category, patterns in self.critical_patterns.items():
            results[category] = []

            for pattern in patterns:
                for file_path in python_files:
                    matches = self._find_pattern_in_file(file_path, pattern, category)
                    results[category].extend(matches)

        return results

    def _should_skip_file(self, file_path: Path) -> bool:
        """Skip test files, cache, etc."""
        skip_patterns = [
            "__pycache__",
            ".git",
            "test_",
            "_test.py",
            ".pyc",
            "env_analysis",
            "code_analysis",
            "analyze_",
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    def _find_pattern_in_file(
        self, file_path: Path, pattern: str, category: str
    ) -> List[Dict[str, Any]]:
        """Find pattern matches in a file"""
        matches = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                value = match.group(1) if match.groups() else match.group(0)

                # Get context
                context_line = lines[line_num - 1] if line_num <= len(lines) else ""

                # Skip if it's clearly not a config value
                if self._should_skip_value(value, context_line, category):
                    continue

                matches.append(
                    {
                        "file": str(file_path),
                        "line": line_num,
                        "value": value,
                        "context": context_line.strip(),
                        "category": category,
                        "suggestion": self._suggest_env_var(value, category, file_path),
                    }
                )

        except Exception as e:
            print(f"Error scanning {file_path}: {e}")

        return matches

    def _should_skip_value(self, value: str, context: str, category: str) -> bool:
        """Skip values that are clearly not configuration"""

        # Skip very common or obviously non-config values
        skip_values = {
            "database_paths": ["test.db", "temp.db"],
            "network_hosts": [],
            "network_ports": [],
            "api_urls": [],
            "file_paths": ["/dev/null", "/tmp"],
            "timeouts": ["0", "1"],
            "redis_config": [],
        }

        if value in skip_values.get(category, []):
            return True

        # Skip if in comments or docstrings
        if any(marker in context for marker in ["#", '"""', "'''"]):
            return True

        # Skip test values
        if "test" in context.lower() or "example" in context.lower():
            return True

        return False

    def _suggest_env_var(self, value: str, category: str, file_path: Path) -> str:
        """Suggest environment variable name"""

        suggestions = {
            "database_paths": "AUTOBOT_DATABASE_PATH",
            "network_hosts": "AUTOBOT_HOST",
            "network_ports": "AUTOBOT_PORT",
            "api_urls": "AUTOBOT_API_URL",
            "file_paths": "AUTOBOT_FILE_PATH",
            "timeouts": "AUTOBOT_TIMEOUT",
            "redis_config": "AUTOBOT_REDIS_URL",
        }

        base = suggestions.get(category, "AUTOBOT_CONFIG")

        # Add specificity based on file or value
        if "redis" in str(file_path).lower() or "redis" in value.lower():
            return "AUTOBOT_REDIS_URL"
        elif "database" in str(file_path).lower() or ".db" in value:
            return "AUTOBOT_DATABASE_PATH"
        elif "backend" in str(file_path) and category == "network_ports":
            return "AUTOBOT_BACKEND_PORT"
        elif "frontend" in str(file_path) and category == "network_ports":
            return "AUTOBOT_FRONTEND_PORT"

        return base


async def main():
    """Run focused critical environment variable analysis"""

    print("🔍 Analyzing critical hardcoded values...")

    analyzer = CriticalEnvAnalyzer()
    results = await analyzer.find_critical_hardcoded_values()

    print("\n=== Critical Hardcoded Values Analysis ===\n")

    total_critical = sum(len(matches) for matches in results.values())
    print(f"Found {total_critical} critical hardcoded values\n")

    # Show results by category
    for category, matches in results.items():
        if matches:
            print(
                f"🏷️  **{category.replace('_', ' ').title()} ({len(matches)} found):**"
            )

            # Group by suggested environment variable
            by_env_var = {}
            for match in matches:
                env_var = match["suggestion"]
                if env_var not in by_env_var:
                    by_env_var[env_var] = []
                by_env_var[env_var].append(match)

            for env_var, env_matches in by_env_var.items():
                print(f"   → {env_var}:")
                for match in env_matches[:5]:  # Show first 5
                    print(
                        f"     • {match['file']}:{match['line']} = '{match['value']}'"
                    )
                    print(f"       Context: {match['context']}")
                if len(env_matches) > 5:
                    print(f"     ... and {len(env_matches) - 5} more")
                print()

    # Generate practical configuration recommendations
    print("\n=== Practical Configuration Updates ===\n")

    # High priority configs to add to config.py
    high_priority = [
        ("AUTOBOT_DATABASE_PATH", "data/knowledge_base.db", "Path to main database"),
        ("AUTOBOT_REDIS_HOST", "localhost", "Redis server hostname"),
        ("AUTOBOT_REDIS_PORT", "6379", "Redis server port"),
        ("AUTOBOT_BACKEND_PORT", "8001", "Backend API port"),
        ("AUTOBOT_FRONTEND_PORT", "5173", "Frontend dev server port"),
        ("AUTOBOT_API_BASE_URL", "http://localhost:8001", "Backend API base URL"),
        ("AUTOBOT_LOG_FILE", "logs/autobot.log", "Main log file path"),
        ("AUTOBOT_TIMEOUT", "30", "Default operation timeout (seconds)"),
    ]

    print("🔧 **Add to src/config.py:**")
    print("```python")
    print("# Critical configuration from environment analysis")
    for env_var, default, description in high_priority:
        config_key = env_var.lower().replace("autobot_", "").replace("_", ".")
        print(f"# {description}")
        if default.isdigit():
            print(f'        "{config_key}": int(os.getenv("{env_var}", {default})),')
        else:
            print(f'        "{config_key}": os.getenv("{env_var}", "{default}"),')
    print("```\n")

    print("🌍 **Add to .env file:**")
    print("```bash")
    for env_var, default, description in high_priority:
        print(f"# {description}")
        print(f"{env_var}={default}")
    print("```\n")

    # Show example refactoring
    print("=== Example Refactoring ===\n")

    # Find specific examples from results
    examples = []
    for category, matches in results.items():
        for match in matches:
            if category == "database_paths" and "knowledge_base.db" in match["value"]:
                examples.append(
                    {
                        "title": "Database Path Configuration",
                        "file": match["file"],
                        "before": match["context"],
                        "after": match["context"].replace(
                            f'"{match["value"]}"', 'config.get("database.path")'
                        ),
                        "env_var": "AUTOBOT_DATABASE_PATH=data/knowledge_base.db",
                    }
                )
                break

    for category, matches in results.items():
        for match in matches:
            if category == "network_ports" and "8001" in match["value"]:
                examples.append(
                    {
                        "title": "Backend Port Configuration",
                        "file": match["file"],
                        "before": match["context"],
                        "after": match["context"].replace(
                            match["value"], 'config.get("backend.port")'
                        ),
                        "env_var": "AUTOBOT_BACKEND_PORT=8001",
                    }
                )
                break

    for example in examples:
        print(f"**{example['title']}:**")
        print(f"File: {example['file']}")
        print(f"Before: `{example['before']}`")
        print(f"After:  `{example['after']}`")
        print(f"Env:    `{example['env_var']}`")
        print()

    return results


if __name__ == "__main__":
    asyncio.run(main())
