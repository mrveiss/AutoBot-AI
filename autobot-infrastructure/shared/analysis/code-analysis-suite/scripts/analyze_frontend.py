#!/usr/bin/env python3
"""
Analyze frontend code for JavaScript, TypeScript, Vue, React, Angular, and other frontend technologies
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the parent directory to the path so we can import from src
sys.path.append(str(Path(__file__).parent.parent))

import logging

from src.frontend_analyzer import FrontendAnalyzer

logger = logging.getLogger(__name__)


async def _display_summary_and_framework_usage(results):
    """Display summary and framework usage breakdown.

    Helper for analyze_frontend_code (Issue #825).
    """
    logger.info("=== Frontend Code Analysis Results ===\n")

    # Summary
    logger.info(f"📊 **Analysis Summary:**")
    logger.info(f"   • Total components analyzed: {results['total_components']}")
    logger.info(f"   • Total issues found: {results['total_issues']}")
    logger.info(
        f"   • Frameworks detected: {', '.join(results['frameworks_detected'])}"
    )
    logger.info(f"   • Overall quality score: {results['quality_score']:.1f}/100")
    logger.info(f"   • Analysis time: {results['analysis_time_seconds']:.2f} seconds")
    logger.info()

    # Framework breakdown
    if results["framework_usage"]:
        logger.info("🏗️ **Framework Usage:**")
        for framework, usage in results["framework_usage"].items():
            framework_name = framework.title()
            logger.info(
                f"   • {framework_name}: {usage['count']} components ({usage['percentage']:.1f}%)"
            )

            if usage.get("lifecycle_hooks"):
                hooks = ", ".join(usage["lifecycle_hooks"][:5])
                if len(usage["lifecycle_hooks"]) > 5:
                    hooks += f" +{len(usage['lifecycle_hooks']) - 5} more"
                logger.info(f"     Common hooks/patterns: {hooks}")
        logger.info()


async def _display_component_analysis(results):
    """Display component analysis and complexity.

    Helper for analyze_frontend_code (Issue #825).
    """
    if results["components"]:
        logger.info("🧩 **Component Analysis:**")

        components_with_tests = len(
            [c for c in results["components"] if c["has_tests"]]
        )
        test_coverage = (
            (components_with_tests / len(results["components"]) * 100)
            if results["components"]
            else 0
        )

        logger.info(
            f"   • Components with tests: {components_with_tests}/{len(results['components'])} ({test_coverage:.1f}%)"
        )

        # Show most complex components
        complex_components = sorted(
            results["components"],
            key=lambda c: len(c["methods"]) + len(c["props"]),
            reverse=True,
        )[:3]

        if complex_components:
            logger.info("   • Most complex components:")
            for comp in complex_components:
                complexity = len(comp["methods"]) + len(comp["props"])
                logger.info(
                    f"     - {comp['name']} ({comp['component_type']}): {complexity} methods+props"
                )
        logger.info()


async def _display_security_performance_accessibility(results):
    """Display security, performance, and accessibility analyses.

    Helper for analyze_frontend_code (Issue #825).
    """
    # Security analysis
    security_analysis = results["security_analysis"]
    logger.info(f"🛡️ **Security Analysis:**")
    logger.info(
        f"   • Total security issues: {security_analysis['total_security_issues']}"
    )
    logger.info(f"   • Critical issues: {security_analysis['critical_issues']}")
    logger.info(
        f"   • High priority issues: {security_analysis['high_priority_issues']}"
    )
    logger.info(f"   • Security score: {security_analysis['security_score']:.1f}/100")

    if security_analysis["total_security_issues"] > 0:
        security_issues = [
            i for i in results["issues"] if i["issue_type"] == "security"
        ]
        logger.info("   • Top security issues:")
        for issue in security_issues[:3]:  # Show top 3
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue["severity"], "⚪")
            logger.info(
                f"     {emoji} {issue['description']} ({issue['file_path']}:{issue['line_number']})"
            )
    logger.info()

    # Performance analysis
    performance_analysis = results["performance_analysis"]
    logger.info(f"⚡ **Performance Analysis:**")
    logger.info(
        f"   • Total performance issues: {performance_analysis['total_performance_issues']}"
    )
    logger.info(
        f"   • Components with issues: {performance_analysis['components_with_issues']}"
    )

    if performance_analysis["issues_by_type"]:
        logger.info("   • Issue breakdown:")
        for issue_desc, count in list(performance_analysis["issues_by_type"].items())[
            :5
        ]:
            logger.info(f"     - {issue_desc}: {count}")
    logger.info()

    # Accessibility analysis
    accessibility_analysis = results["accessibility_analysis"]
    logger.info(f"♿ **Accessibility Analysis:**")
    logger.info(
        f"   • Total accessibility issues: {accessibility_analysis['total_accessibility_issues']}"
    )
    logger.info(
        f"   • WCAG compliance score: {accessibility_analysis['wcag_compliance_score']:.1f}/100"
    )

    if accessibility_analysis.get("issues_by_severity"):
        logger.info("   • Issues by severity:")
        for severity, count in accessibility_analysis["issues_by_severity"].items():
            logger.info(f"     - {severity.title()}: {count}")
    logger.info()


async def _display_detailed_issues(results):
    """Display detailed issue analysis grouped by type.

    Helper for analyze_frontend_code (Issue #825).
    """
    if results["issues"]:
        logger.info("🔍 **Detailed Issue Analysis:**")

        # Group issues by type
        issues_by_type = {}
        for issue in results["issues"]:
            issue_type = issue["issue_type"]
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)

        for issue_type, type_issues in issues_by_type.items():
            if issue_type.endswith("_specific"):
                framework = issue_type.split("_")[0].title()
                category_name = f"{framework}-Specific Issues"
            else:
                category_name = issue_type.replace("_", " ").title()

            logger.info(f"\n📋 **{category_name} ({len(type_issues)} issues):**")

            # Show top issues by severity
            sorted_issues = sorted(
                type_issues,
                key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                    x["severity"], 0
                ),
                reverse=True,
            )

            for issue in sorted_issues[:5]:  # Top 5 issues per category
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }
                emoji = severity_emoji.get(issue["severity"], "⚪")

                logger.info(f"   {emoji} {issue['description']}")
                logger.info(
                    f"      📄 {issue['file_path']}:{issue['line_number']} ({issue['framework']})"
                )
                logger.info(f"      💡 Suggestion: {issue['suggestion']}")


async def _display_recommendations_and_best_practices(results):
    """Display recommendations and framework-specific best practices.

    Helper for analyze_frontend_code (Issue #825).
    """
    # Framework-specific recommendations
    logger.info(f"\n💡 **Improvement Recommendations:**")
    for i, recommendation in enumerate(results["recommendations"], 1):
        logger.info(f"{i}. {recommendation}")

    # Best practices by framework
    if "vue" in results["frameworks_detected"]:
        logger.info(f"\n🔧 **Vue.js Best Practices:**")
        logger.info("   • Use Composition API for better code organization")
        logger.info("   • Avoid direct DOM manipulation with $refs")
        logger.info("   • Use proper key attributes in v-for loops")
        logger.info("   • Sanitize content before using v-html")

    if "react" in results["frameworks_detected"]:
        logger.info(f"\n🔧 **React Best Practices:**")
        logger.info("   • Use React Hooks instead of class components")
        logger.info("   • Avoid deprecated lifecycle methods")
        logger.info("   • Sanitize content before using dangerouslySetInnerHTML")
        logger.info("   • Use proper keys for list items")

    if "javascript" in results["frameworks_detected"]:
        logger.info(f"\n🔧 **JavaScript Best Practices:**")
        logger.info("   • Use const/let instead of var")
        logger.info("   • Use strict equality (===) instead of ==")
        logger.info("   • Handle async operations properly")
        logger.info("   • Remove console.log statements from production")


async def _display_critical_issues_report(results):
    """Display critical issues that need immediate attention.

    Helper for analyze_frontend_code (Issue #825).
    """
    # Save detailed report
    report_path = Path("frontend_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\n📋 **Report Generated:**")
    logger.info(f"   • Detailed analysis: {report_path}")

    # Generate fix suggestions for critical issues
    critical_issues = [i for i in results["issues"] if i["severity"] == "critical"]
    if critical_issues:
        logger.info(f"\n🚨 **CRITICAL ISSUES - IMMEDIATE ACTION REQUIRED:**")
        logger.info(
            f"Found {len(critical_issues)} critical issues that need immediate attention:"
        )

        for issue in critical_issues:
            logger.info(f"\n🔴 **{issue['description']}**")
            logger.info(f"   📄 File: {issue['file_path']}:{issue['line_number']}")
            logger.info(f"   🏗️ Framework: {issue['framework'].title()}")
            logger.info(f"   💡 Fix: {issue['suggestion']}")


async def analyze_frontend_code():
    """Run comprehensive frontend code analysis"""

    logger.info("🎨 Starting frontend code analysis...")
    logger.info(
        "Analyzing JavaScript, TypeScript, Vue, React, Angular, and other frontend files..."
    )
    logger.info()

    analyzer = FrontendAnalyzer()

    # Analyze frontend code
    results = await analyzer.analyze_frontend_code(
        root_path="..",
        patterns=[
            "autobot-vue/src/**/*.js",
            "autobot-vue/src/**/*.ts",
            "autobot-vue/src/**/*.jsx",
            "autobot-vue/src/**/*.tsx",
            "autobot-vue/src/**/*.vue",
            "autobot-vue/src/**/*.svelte",
            "autobot-vue/index.html",
        ],
    )

    await _display_summary_and_framework_usage(results)
    await _display_component_analysis(results)
    await _display_security_performance_accessibility(results)
    await _display_detailed_issues(results)
    await _display_recommendations_and_best_practices(results)
    await _display_critical_issues_report(results)

    return results


async def _display_xss_and_performance_examples():
    """Display XSS prevention and performance examples.

    Helper for generate_frontend_fix_examples (Issue #825).
    """
    logger.info("\n=== 🛠️ Common Frontend Fix Examples ===\n")

    logger.info("**1. XSS Prevention:**")
    logger.info("```javascript")
    logger.info("// ❌ Dangerous - XSS vulnerability")
    logger.info("element.innerHTML = userInput;")
    logger.info()
    logger.info("// ✅ Safe - Sanitized content")
    logger.info("element.textContent = userInput;")
    logger.info("// or use a sanitization library")
    logger.info("element.innerHTML = DOMPurify.sanitize(userInput);")
    logger.info("```")
    logger.info()

    logger.info("**2. Performance - DOM Query Optimization:**")
    logger.info("```javascript")
    logger.info("// ❌ Inefficient - DOM query in loop")
    logger.info("for (let i = 0; i < items.length; i++) {")
    logger.info("    document.querySelector('.container').appendChild(items[i]);")
    logger.info("}")
    logger.info()
    logger.info("// ✅ Efficient - Cache DOM query")
    logger.info("const container = document.querySelector('.container');")
    logger.info("for (let i = 0; i < items.length; i++) {")
    logger.info("    container.appendChild(items[i]);")
    logger.info("}")
    logger.info("```")
    logger.info()


async def _display_accessibility_and_vue_examples():
    """Display accessibility and Vue.js examples.

    Helper for generate_frontend_fix_examples (Issue #825).
    """
    logger.info("**3. Accessibility - Image Alt Text:**")
    logger.info("```html")
    logger.info("<!-- ❌ Missing alt attribute -->")
    logger.info('<img src="chart.png">')
    logger.info()
    logger.info("<!-- ✅ Descriptive alt text -->")
    logger.info('<img src="chart.png" alt="Sales chart showing 25% growth in Q3 2024">')
    logger.info("```")
    logger.info()

    logger.info("**4. Vue.js - Safe v-html Usage:**")
    logger.info("```vue")
    logger.info("<!-- ❌ Dangerous - Direct HTML binding -->")
    logger.info('<div v-html="userContent"></div>')
    logger.info()
    logger.info("<!-- ✅ Safe - Sanitized content -->")
    logger.info('<div v-html="$sanitize(userContent)"></div>')
    logger.info("```")
    logger.info()


async def _display_react_and_cleanup_examples():
    """Display React and event cleanup examples.

    Helper for generate_frontend_fix_examples (Issue #825).
    """
    logger.info("**5. React - Safe dangerouslySetInnerHTML:**")
    logger.info("```jsx")
    logger.info("// ❌ Dangerous - Unsanitized content")
    logger.info("function Component({ userContent }) {")
    logger.info("    return <div dangerouslySetInnerHTML={{__html: userContent}} />;")
    logger.info("}")
    logger.info()
    logger.info("// ✅ Safe - Sanitized content")
    logger.info("import DOMPurify from 'dompurify';")
    logger.info("function Component({ userContent }) {")
    logger.info("    const sanitized = DOMPurify.sanitize(userContent);")
    logger.info("    return <div dangerouslySetInnerHTML={{__html: sanitized}} />;")
    logger.info("}")
    logger.info("```")
    logger.info()

    logger.info("**6. Event Listener Cleanup:**")
    logger.info("```javascript")
    logger.info("// ❌ Memory leak - No cleanup")
    logger.info("window.addEventListener('resize', handler);")
    logger.info()
    logger.info("// ✅ Proper cleanup")
    logger.info("window.addEventListener('resize', handler);")
    logger.info("// Later, when component unmounts:")
    logger.info("window.removeEventListener('resize', handler);")
    logger.info("```")


async def generate_frontend_fix_examples():
    """Generate examples of common frontend fixes"""

    await _display_xss_and_performance_examples()
    await _display_accessibility_and_vue_examples()
    await _display_react_and_cleanup_examples()


async def main():
    """Run frontend analysis and examples"""

    # Check if we're in the right directory
    if not Path("src").exists():
        logger.info("❌ Please run this script from the code-analysis-suite directory")
        logger.info(
            "Usage: cd code-analysis-suite && python scripts/analyze_frontend.py"
        )
        return

    # Run analysis
    await analyze_frontend_code()

    # Show fix examples
    await generate_frontend_fix_examples()

    logger.info("\n=== Frontend Analysis Complete ===")
    logger.info("Next steps:")
    logger.info("1. Review frontend_analysis_report.json for detailed findings")
    logger.info("2. Address critical security issues immediately")
    logger.info("3. Fix performance issues affecting user experience")
    logger.info("4. Improve accessibility for better inclusion")
    logger.info("5. Add missing tests for untested components")
    logger.info("6. Set up ESLint and Prettier for consistent code quality")


if __name__ == "__main__":
    asyncio.run(main())
