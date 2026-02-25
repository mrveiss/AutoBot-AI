#!/usr/bin/env python3
"""
Analyze AutoBot codebase for hardcoded environment variables and generate config recommendations
"""

import asyncio
import json
from pathlib import Path

from constants.network_constants import NetworkConstants
from env_analyzer import EnvironmentAnalyzer


def _print_analysis_summary(results: dict) -> None:
    """Print analysis summary and category breakdown. Issue #1183."""
    print("\n=== Environment Variable Analysis Results ===\n")  # noqa: print
    print("📊 **Analysis Summary:**")  # noqa: print
    print(
        f"   - Total hardcoded values: {results['total_hardcoded_values']}"
    )  # noqa: print
    print(f"   - High priority issues: {results['high_priority_count']}")  # noqa: print
    print(
        f"   - Configuration recommendations: {results['recommendations_count']}"
    )  # noqa: print
    print(f"   - Files affected: {results['metrics']['files_affected']}")  # noqa: print
    print(
        f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n"
    )  # noqa: print
    print("🏷️  **Categories Found:**")  # noqa: print
    for category, count in results["categories"].items():
        print(f"   - {category}: {count} instances")  # noqa: print
    print()  # noqa: print


def _print_high_priority_issues(high_priority: list) -> None:
    """Print high-priority hardcoded value issues. Issue #1183."""
    if not high_priority:
        return
    print("🚨 **High Priority Issues (Security/Infrastructure):**")  # noqa: print
    for item in high_priority[:10]:  # Show top 10
        print(
            f"   - {item['file']}:{item['line']} - {item['type']}: '{item['value']}'"
        )  # noqa: print
        print(f"     → Suggested env var: {item['suggested_env_var']}")  # noqa: print
    print()  # noqa: print


def _print_config_recs(high_priority_recs: list, medium_priority_recs: list) -> None:
    """Print configuration recommendations by priority. Issue #1183."""
    if high_priority_recs:
        print("🔧 **High Priority Configuration Recommendations:**")  # noqa: print
        for rec in high_priority_recs:
            print(f"   - {rec['env_var_name']}")  # noqa: print
            print(f"     Category: {rec['category']}")  # noqa: print
            print(f"     Default: '{rec['default_value']}'")  # noqa: print
            print(f"     Files: {len(rec['affected_files'])}")  # noqa: print
        print()  # noqa: print
    if medium_priority_recs:
        print("⚙️  **Medium Priority Configuration Recommendations:**")  # noqa: print
        for rec in medium_priority_recs[:5]:  # Show top 5
            print(
                f"   - {rec['env_var_name']}: '{rec['default_value']}'"
            )  # noqa: print
            print(
                f"     Category: {rec['category']}, Files: {len(rec['affected_files'])}"
            )  # noqa: print
        print()  # noqa: print


async def analyze_environment_variables():
    """Analyze codebase for hardcoded values that should be environment variables"""
    print("Starting environment variable analysis...")  # noqa: print
    analyzer = EnvironmentAnalyzer()
    results = await analyzer.analyze_codebase(
        root_path=".",
        patterns=[
            "src/**/*.py",
            "backend/**/*.py",
            "autobot-vue/src/**/*.js",
            "autobot-vue/src/**/*.vue",
        ],
    )
    _print_analysis_summary(results)
    high_priority = [
        item for item in results["hardcoded_details"] if item["severity"] == "high"
    ]
    _print_high_priority_issues(high_priority)
    recommendations = results["configuration_recommendations"]
    _print_config_recs(
        [r for r in recommendations if r["priority"] == "high"],
        [r for r in recommendations if r["priority"] == "medium"],
    )
    report_path = Path("env_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"📋 Detailed report saved to: {report_path}")  # noqa: print
    await generate_config_updates(recommendations)
    return results


def _print_config_py_section(by_category: dict) -> None:
    """Print config.py addition snippets. Issue #1183."""
    print("🔨 **Add to src/config.py:**")  # noqa: print
    print("```python")  # noqa: print
    print("# Environment variable additions from analysis")  # noqa: print
    for category, recs in by_category.items():
        print(f"\n# {category.title()} Configuration")  # noqa: print
        for rec in recs:
            env_var = rec["env_var_name"]
            default = rec["default_value"]
            if default.isdigit():
                config_line = f'        "{env_var.lower()}": int(os.getenv("{env_var}", {default})),'
            elif default.lower() in ["true", "false"]:
                config_line = f'        "{env_var.lower()}": os.getenv("{env_var}", "{default}").lower() == "true",'
            else:
                config_line = (
                    f'        "{env_var.lower()}": os.getenv("{env_var}", "{default}"),'
                )
            print(f"        # {rec['description']}")  # noqa: print
            print(config_line)  # noqa: print
    print("```\n")  # noqa: print


def _save_env_template(by_category: dict, path: Path) -> None:
    """Save .env template file. Issue #1183."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Environment variables for AutoBot configuration\n")
        for category, recs in by_category.items():
            f.write(f"\n# {category.title()} settings\n")
            for rec in recs:
                f.write(f"# {rec['description']}\n")
                f.write(f"{rec['env_var_name']}={rec['default_value']}\n")


async def generate_config_updates(recommendations):
    """Generate suggested configuration updates"""
    print("\n=== Suggested Configuration Updates ===\n")  # noqa: print
    by_category: dict = {}
    for rec in recommendations:
        by_category.setdefault(rec["category"], []).append(rec)
    _print_config_py_section(by_category)
    print("🌍 **Add to .env template:**")  # noqa: print
    print("```bash")  # noqa: print
    print("# Environment variables for AutoBot configuration")  # noqa: print
    for category, recs in by_category.items():
        print(f"\n# {category.title()} settings")  # noqa: print
        for rec in recs:
            print(f"# {rec['description']}")  # noqa: print
            print(f"{rec['env_var_name']}={rec['default_value']}")  # noqa: print
    print("```\n")  # noqa: print
    env_template_path = Path("env_template.txt")
    _save_env_template(by_category, env_template_path)
    print(f"📄 Environment template saved to: {env_template_path}")  # noqa: print


async def demonstrate_specific_fixes():
    """Demonstrate how to fix specific hardcoded values"""

    print("\n=== Example Refactoring Demonstrations ===\n")  # noqa: print

    examples = [
        {
            "title": "Database Connection",
            "before": 'conn = sqlite3.connect("data/knowledge_base.db")',
            "after": 'conn = sqlite3.connect(config.get("database.path", "data/knowledge_base.db"))',
            "env_var": "AUTOBOT_DATABASE_PATH=data/knowledge_base.db",
        },
        {
            "title": "Redis Host",
            "before": 'redis.Redis(host="localhost", port=6379)',
            "after": 'redis.Redis(host=config.get("redis.host"), port=config.get("redis.port"))',
            "env_var": "AUTOBOT_REDIS_HOST=localhost\nAUTOBOT_REDIS_PORT=6379",
        },
        {
            "title": "API Base URL",
            "before": f'base_url = "http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}"',
            "after": 'base_url = config.get("api.base_url")',
            "env_var": f"AUTOBOT_API_BASE_URL=http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}",
        },
        {
            "title": "File Paths",
            "before": 'log_file = "/var/log/autobot.log"',
            "after": 'log_file = config.get("logging.file_path")',
            "env_var": "AUTOBOT_LOGGING_FILE_PATH=/var/log/autobot.log",
        },
    ]

    for example in examples:
        print(f"**{example['title']}:**")  # noqa: print
        print(f"   Before: `{example['before']}`")  # noqa: print
        print(f"   After:  `{example['after']}`")  # noqa: print
        print(f"   Env:    `{example['env_var']}`")  # noqa: print
        print()  # noqa: print


async def main():
    """Run the environment variable analysis"""

    # Analyze environment variables
    await analyze_environment_variables()

    # Show example refactorings
    await demonstrate_specific_fixes()

    print("\n=== Analysis Complete ===")  # noqa: print
    print("Next steps:")  # noqa: print
    print("1. Review env_analysis_report.json for detailed findings")  # noqa: print
    print(
        "2. Update src/config.py with high-priority environment variables"
    )  # noqa: print
    print("3. Create/update .env file with new variables")  # noqa: print
    print("4. Refactor hardcoded values to use config system")  # noqa: print
    print("5. Test configuration changes in different environments")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
