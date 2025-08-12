#!/usr/bin/env python3
"""
Analyze AutoBot codebase for hardcoded environment variables and generate config recommendations
"""

import asyncio
import json
from pathlib import Path

from src.env_analyzer import EnvironmentAnalyzer


async def analyze_environment_variables():
    """Analyze codebase for hardcoded values that should be environment variables"""
    
    print("Starting environment variable analysis...")
    
    analyzer = EnvironmentAnalyzer()
    
    # Run analysis
    results = await analyzer.analyze_codebase(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py", "autobot-vue/src/**/*.js", "autobot-vue/src/**/*.vue"]
    )
    
    print("\n=== Environment Variable Analysis Results ===\n")
    
    # Summary
    print(f"📊 **Analysis Summary:**")
    print(f"   - Total hardcoded values: {results['total_hardcoded_values']}")
    print(f"   - High priority issues: {results['high_priority_count']}")
    print(f"   - Configuration recommendations: {results['recommendations_count']}")
    print(f"   - Files affected: {results['metrics']['files_affected']}")
    print(f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n")
    
    # Category breakdown
    print("🏷️  **Categories Found:**")
    for category, count in results['categories'].items():
        print(f"   - {category}: {count} instances")
    print()
    
    # High priority issues
    high_priority = [item for item in results['hardcoded_details'] if item['severity'] == 'high']
    if high_priority:
        print("🚨 **High Priority Issues (Security/Infrastructure):**")
        for item in high_priority[:10]:  # Show top 10
            print(f"   - {item['file']}:{item['line']} - {item['type']}: '{item['value']}'")
            print(f"     → Suggested env var: {item['suggested_env_var']}")
        print()
    
    # Configuration recommendations
    recommendations = results['configuration_recommendations']
    high_priority_recs = [r for r in recommendations if r['priority'] == 'high']
    medium_priority_recs = [r for r in recommendations if r['priority'] == 'medium']
    
    if high_priority_recs:
        print("🔧 **High Priority Configuration Recommendations:**")
        for rec in high_priority_recs:
            print(f"   - {rec['env_var_name']}")
            print(f"     Category: {rec['category']}")
            print(f"     Default: '{rec['default_value']}'")
            print(f"     Files: {len(rec['affected_files'])}")
        print()
    
    if medium_priority_recs:
        print("⚙️  **Medium Priority Configuration Recommendations:**")
        for rec in medium_priority_recs[:5]:  # Show top 5
            print(f"   - {rec['env_var_name']}: '{rec['default_value']}'")
            print(f"     Category: {rec['category']}, Files: {len(rec['affected_files'])}")
        print()
    
    # Save detailed report
    report_path = Path("env_analysis_report.json")
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"📋 Detailed report saved to: {report_path}")
    
    # Generate configuration updates
    await generate_config_updates(recommendations)
    
    return results


async def generate_config_updates(recommendations):
    """Generate suggested configuration updates"""
    
    print("\n=== Suggested Configuration Updates ===\n")
    
    # Group by category
    by_category = {}
    for rec in recommendations:
        category = rec['category']
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(rec)
    
    # Generate config.py additions
    config_additions = []
    
    print("🔨 **Add to src/config.py:**")
    print("```python")
    print("# Environment variable additions from analysis")
    
    for category, recs in by_category.items():
        print(f"\n# {category.title()} Configuration")
        for rec in recs:
            env_var = rec['env_var_name']
            default = rec['default_value']
            desc = rec['description']
            
            # Format for config.py
            if default.isdigit():
                config_line = f"        \"{env_var.lower()}\": int(os.getenv(\"{env_var}\", {default})),"
            elif default.lower() in ['true', 'false']:
                config_line = f"        \"{env_var.lower()}\": os.getenv(\"{env_var}\", \"{default}\").lower() == \"true\","
            else:
                config_line = f"        \"{env_var.lower()}\": os.getenv(\"{env_var}\", \"{default}\"),"
            
            config_additions.append(config_line)
            print(f"        # {desc}")
            print(config_line)
    
    print("```\n")
    
    # Generate .env template
    print("🌍 **Add to .env template:**")
    print("```bash")
    print("# Environment variables for AutoBot configuration")
    
    for category, recs in by_category.items():
        print(f"\n# {category.title()} settings")
        for rec in recs:
            env_var = rec['env_var_name']
            default = rec['default_value']
            desc = rec['description']
            print(f"# {desc}")
            print(f"{env_var}={default}")
    
    print("```\n")
    
    # Save configuration template
    env_template_path = Path("env_template.txt")
    with open(env_template_path, 'w') as f:
        f.write("# Environment variables for AutoBot configuration\n")
        for category, recs in by_category.items():
            f.write(f"\n# {category.title()} settings\n")
            for rec in recs:
                env_var = rec['env_var_name']
                default = rec['default_value']
                desc = rec['description']
                f.write(f"# {desc}\n")
                f.write(f"{env_var}={default}\n")
    
    print(f"📄 Environment template saved to: {env_template_path}")


async def demonstrate_specific_fixes():
    """Demonstrate how to fix specific hardcoded values"""
    
    print("\n=== Example Refactoring Demonstrations ===\n")
    
    examples = [
        {
            "title": "Database Connection",
            "before": 'conn = sqlite3.connect("data/knowledge_base.db")',
            "after": 'conn = sqlite3.connect(config.get("database.path", "data/knowledge_base.db"))',
            "env_var": "AUTOBOT_DATABASE_PATH=data/knowledge_base.db"
        },
        {
            "title": "Redis Host",
            "before": 'redis.Redis(host="localhost", port=6379)',
            "after": 'redis.Redis(host=config.get("redis.host"), port=config.get("redis.port"))',
            "env_var": "AUTOBOT_REDIS_HOST=localhost\nAUTOBOT_REDIS_PORT=6379"
        },
        {
            "title": "API Base URL",
            "before": 'base_url = "http://localhost:8001"',
            "after": 'base_url = config.get("api.base_url")',
            "env_var": "AUTOBOT_API_BASE_URL=http://localhost:8001"
        },
        {
            "title": "File Paths",
            "before": 'log_file = "/var/log/autobot.log"',
            "after": 'log_file = config.get("logging.file_path")',
            "env_var": "AUTOBOT_LOGGING_FILE_PATH=/var/log/autobot.log"
        }
    ]
    
    for example in examples:
        print(f"**{example['title']}:**")
        print(f"   Before: `{example['before']}`")
        print(f"   After:  `{example['after']}`")
        print(f"   Env:    `{example['env_var']}`")
        print()


async def main():
    """Run the environment variable analysis"""
    
    # Analyze environment variables
    results = await analyze_environment_variables()
    
    # Show example refactorings
    await demonstrate_specific_fixes()
    
    print("\n=== Analysis Complete ===")
    print("Next steps:")
    print("1. Review env_analysis_report.json for detailed findings")
    print("2. Update src/config.py with high-priority environment variables")
    print("3. Create/update .env file with new variables")
    print("4. Refactor hardcoded values to use config system")
    print("5. Test configuration changes in different environments")


if __name__ == "__main__":
    asyncio.run(main())