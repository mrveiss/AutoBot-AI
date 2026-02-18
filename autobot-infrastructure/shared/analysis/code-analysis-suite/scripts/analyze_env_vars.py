#!/usr/bin/env python3
"""
Analyze AutoBot codebase for hardcoded environment variables and generate config recommendations
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _log_analysis_summary(results):
    """Log the analysis summary section.

    Helper for analyze_environment_variables (#825).
    """
    logger.info("\n=== Environment Variable Analysis Results ===\n")
    logger.info("Analysis Summary:")
    logger.info("   - Total hardcoded values: %s", results["total_hardcoded_values"])
    logger.info("   - High priority issues: %s", results["high_priority_count"])
    logger.info(
        "   - Configuration recommendations: %s", results["recommendations_count"]
    )
    logger.info("   - Files affected: %s", results["metrics"]["files_affected"])
    logger.info("   - Analysis time: %.2fs\n", results["analysis_time_seconds"])

    logger.info("Categories Found:")
    for category, count in results["categories"].items():
        logger.info("   - %s: %s instances", category, count)
    logger.info("")


def _log_high_priority_issues(results):
    """Log high priority hardcoded value issues.

    Helper for analyze_environment_variables (#825).
    """
    high_priority = [
        item for item in results["hardcoded_details"] if item["severity"] == "high"
    ]
    if high_priority:
        logger.info("High Priority Issues (Security/Infrastructure):")
        for item in high_priority[:10]:
            logger.info(
                "   - %s:%s - %s: '%s'",
                item["file"],
                item["line"],
                item["type"],
                item["value"],
            )
            logger.info("     Suggested env var: %s", item["suggested_env_var"])
        logger.info("")


def _log_priority_recommendations(recommendations):
    """Log high and medium priority configuration recommendations.

    Helper for analyze_environment_variables (#825).
    """
    high_priority_recs = [r for r in recommendations if r["priority"] == "high"]
    medium_priority_recs = [r for r in recommendations if r["priority"] == "medium"]

    if high_priority_recs:
        logger.info("High Priority Configuration Recommendations:")
        for rec in high_priority_recs:
            logger.info("   - %s", rec["env_var_name"])
            logger.info("     Category: %s", rec["category"])
            logger.info("     Default: '%s'", rec["default_value"])
            logger.info("     Files: %s", len(rec["affected_files"]))
        logger.info("")

    if medium_priority_recs:
        logger.info("Medium Priority Configuration Recommendations:")
        for rec in medium_priority_recs[:5]:
            logger.info("   - %s: '%s'", rec["env_var_name"], rec["default_value"])
            logger.info(
                "     Category: %s, Files: %s",
                rec["category"],
                len(rec["affected_files"]),
            )
        logger.info("")


async def analyze_environment_variables():
    """Analyze codebase for hardcoded values that should be environment variables"""

    logger.info("Starting environment variable analysis...")

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

    _log_analysis_summary(results)
    _log_high_priority_issues(results)

    recommendations = results["configuration_recommendations"]
    _log_priority_recommendations(recommendations)

    report_path = Path("env_analysis_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info("Detailed report saved to: %s", report_path)

    await generate_config_updates(recommendations)

    return results


def _group_recommendations_by_category(recommendations):
    """Group recommendations by their category field.

    Helper for generate_config_updates (#825).
    """
    by_category = {}
    for rec in recommendations:
        category = rec["category"]
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(rec)
    return by_category


def _format_config_line(env_var, default):
    """Format a single config.py line from an env var recommendation.

    Helper for generate_config_updates (#825).
    """
    if default.isdigit():
        return (
            f'        "{env_var.lower()}":' f' int(os.getenv("{env_var}", {default})),'
        )
    if default.lower() in ["true", "false"]:
        return (
            f'        "{env_var.lower()}":'
            f' os.getenv("{env_var}", "{default}").lower() == "true",'
        )
    return f'        "{env_var.lower()}":' f' os.getenv("{env_var}", "{default}"),'


def _save_env_template(by_category):
    """Save the .env template file to disk.

    Helper for generate_config_updates (#825).
    """
    env_template_path = Path("env_template.txt")
    with open(env_template_path, "w", encoding="utf-8") as f:
        f.write("# Environment variables for AutoBot configuration\n")
        for category, recs in by_category.items():
            f.write(f"\n# {category.title()} settings\n")
            for rec in recs:
                f.write(f"# {rec['description']}\n")
                f.write(f"{rec['env_var_name']}={rec['default_value']}\n")
    logger.info("Environment template saved to: %s", env_template_path)


async def generate_config_updates(recommendations):
    """Generate suggested configuration updates"""

    logger.info("\n=== Suggested Configuration Updates ===\n")

    by_category = _group_recommendations_by_category(recommendations)

    logger.info("Add to src/config.py:")
    logger.info("# Environment variable additions from analysis")

    for category, recs in by_category.items():
        logger.info("\n# %s Configuration", category.title())
        for rec in recs:
            config_line = _format_config_line(
                rec["env_var_name"],
                rec["default_value"],
            )
            logger.info("        # %s", rec["description"])
            logger.info(config_line)

    logger.info("")

    logger.info("Add to .env template:")
    logger.info("# Environment variables for AutoBot configuration")

    for category, recs in by_category.items():
        logger.info("\n# %s settings", category.title())
        for rec in recs:
            logger.info("# %s", rec["description"])
            logger.info("%s=%s", rec["env_var_name"], rec["default_value"])

    logger.info("")

    _save_env_template(by_category)


async def demonstrate_specific_fixes():
    """Demonstrate how to fix specific hardcoded values"""

    logger.info("\n=== Example Refactoring Demonstrations ===\n")

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
            "before": 'base_url = "http://localhost:8001"',
            "after": 'base_url = config.get("api.base_url")',
            "env_var": "AUTOBOT_API_BASE_URL=http://localhost:8001",
        },
        {
            "title": "File Paths",
            "before": 'log_file = "/var/log/autobot.log"',
            "after": 'log_file = config.get("logging.file_path")',
            "env_var": "AUTOBOT_LOGGING_FILE_PATH=/var/log/autobot.log",
        },
    ]

    for example in examples:
        logger.info(f"**{example['title']}:**")
        logger.info(f"   Before: `{example['before']}`")
        logger.info(f"   After:  `{example['after']}`")
        logger.info(f"   Env:    `{example['env_var']}`")
        logger.info("")


async def main():
    """Run the environment variable analysis"""

    # Analyze environment variables
    await analyze_environment_variables()

    # Show example refactorings
    await demonstrate_specific_fixes()

    logger.info("\n=== Analysis Complete ===")
    logger.info("Next steps:")
    logger.info("1. Review env_analysis_report.json for detailed findings")
    logger.info("2. Update src/config.py with high-priority environment variables")
    logger.info("3. Create/update .env file with new variables")
    logger.info("4. Refactor hardcoded values to use config system")
    logger.info("5. Test configuration changes in different environments")


if __name__ == "__main__":
    asyncio.run(main())
