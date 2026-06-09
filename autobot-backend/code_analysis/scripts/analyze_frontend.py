#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Analyze frontend code for JavaScript, TypeScript, Vue, React, Angular, and other frontend technologies
"""

import json
import sys
from pathlib import Path

# Add the parent directory to the path so we can import from src
sys.path.append(str(Path(__file__).parent.parent))

from frontend_analyzer import FrontendAnalyzer

from autobot_shared.async_compat import run_or_schedule


def _print_analysis_summary(results: dict) -> None:
    """
    Print analysis summary statistics.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    print(f"📊 **Analysis Summary:**")  # noqa: print
    print(f"   • Total components analyzed: {results['total_components']}")  # noqa: print
    print(f"   • Total issues found: {results['total_issues']}")  # noqa: print
    print(f"   • Frameworks detected: {', '.join(results['frameworks_detected'])}")  # noqa: print
    print(f"   • Overall quality score: {results['quality_score']:.1f}/100")  # noqa: print
    print(f"   • Analysis time: {results['analysis_time_seconds']:.2f} seconds")  # noqa: print
    print()  # noqa: print


def _print_framework_usage(results: dict) -> None:
    """
    Print framework usage breakdown.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results["framework_usage"]:
        return

    print("🏗️ **Framework Usage:**")  # noqa: print
    for framework, usage in results["framework_usage"].items():
        framework_name = framework.title()
        print(f"   • {framework_name}: {usage['count']} components ({usage['percentage']:.1f}%)")  # noqa: print

        if usage.get("lifecycle_hooks"):
            hooks = ", ".join(usage["lifecycle_hooks"][:5])
            if len(usage["lifecycle_hooks"]) > 5:
                hooks += f" +{len(usage['lifecycle_hooks']) - 5} more"
            print(f"     Common hooks/patterns: {hooks}")  # noqa: print
    print()  # noqa: print


def _print_component_analysis(results: dict) -> None:
    """
    Print component analysis details.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results["components"]:
        return

    print("🧩 **Component Analysis:**")  # noqa: print

    components_with_tests = len([c for c in results["components"] if c["has_tests"]])
    test_coverage = (components_with_tests / len(results["components"]) * 100) if results["components"] else 0

    print(  # noqa: print
        f"   • Components with tests: {components_with_tests}/{len(results['components'])} ({test_coverage:.1f}%)"
    )

    # Show most complex components
    complex_components = sorted(
        results["components"],
        key=lambda c: len(c["methods"]) + len(c["props"]),
        reverse=True,
    )[:3]

    if complex_components:
        print("   • Most complex components:")  # noqa: print
        for comp in complex_components:
            complexity = len(comp["methods"]) + len(comp["props"])
            print(f"     - {comp['name']} ({comp['component_type']}): {complexity} methods+props")  # noqa: print
    print()  # noqa: print


def _print_security_analysis(results: dict) -> None:
    """
    Print security analysis details.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    security_analysis = results["security_analysis"]
    print(f"🛡️ **Security Analysis:**")  # noqa: print
    print(f"   • Total security issues: {security_analysis['total_security_issues']}")  # noqa: print
    print(f"   • Critical issues: {security_analysis['critical_issues']}")  # noqa: print
    print(f"   • High priority issues: {security_analysis['high_priority_issues']}")  # noqa: print
    print(f"   • Security score: {security_analysis['security_score']:.1f}/100")  # noqa: print

    if security_analysis["total_security_issues"] > 0:
        security_issues = [i for i in results["issues"] if i["issue_type"] == "security"]
        print("   • Top security issues:")  # noqa: print
        for issue in security_issues[:3]:
            severity_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }
            emoji = severity_emoji.get(issue["severity"], "⚪")
            print(f"     {emoji} {issue['description']} ({issue['file_path']}:{issue['line_number']})")  # noqa: print
    print()  # noqa: print


def _print_performance_accessibility(results: dict) -> None:
    """
    Print performance and accessibility analysis.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    # Performance analysis
    performance_analysis = results["performance_analysis"]
    print(f"⚡ **Performance Analysis:**")  # noqa: print
    print(f"   • Total performance issues: {performance_analysis['total_performance_issues']}")  # noqa: print
    print(f"   • Components with issues: {performance_analysis['components_with_issues']}")  # noqa: print

    if performance_analysis["issues_by_type"]:
        print("   • Issue breakdown:")  # noqa: print
        for issue_desc, count in list(performance_analysis["issues_by_type"].items())[:5]:
            print(f"     - {issue_desc}: {count}")  # noqa: print
    print()  # noqa: print

    # Accessibility analysis
    accessibility_analysis = results["accessibility_analysis"]
    print(f"♿ **Accessibility Analysis:**")  # noqa: print
    print(f"   • Total accessibility issues: {accessibility_analysis['total_accessibility_issues']}")  # noqa: print
    print(f"   • WCAG compliance score: {accessibility_analysis['wcag_compliance_score']:.1f}/100")  # noqa: print

    if accessibility_analysis.get("issues_by_severity"):
        print("   • Issues by severity:")  # noqa: print
        for severity, count in accessibility_analysis["issues_by_severity"].items():
            print(f"     - {severity.title()}: {count}")  # noqa: print
    print()  # noqa: print


def _print_detailed_issues(results: dict) -> None:
    """
    Print detailed issue analysis grouped by type.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results["issues"]:
        return

    print("🔍 **Detailed Issue Analysis:**")  # noqa: print

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

        print(f"\n📋 **{category_name} ({len(type_issues)} issues):**")  # noqa: print

        # Show top issues by severity
        sorted_issues = sorted(
            type_issues,
            key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(x["severity"], 0),
            reverse=True,
        )

        for issue in sorted_issues[:5]:
            severity_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }
            emoji = severity_emoji.get(issue["severity"], "⚪")

            print(f"   {emoji} {issue['description']}")  # noqa: print
            print(f"      📄 {issue['file_path']}:{issue['line_number']} ({issue['framework']})")  # noqa: print
            print(f"      💡 Suggestion: {issue['suggestion']}")  # noqa: print


def _print_framework_recommendations(results: dict) -> None:
    """
    Print framework-specific best practice recommendations.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    print(f"\n💡 **Improvement Recommendations:**")  # noqa: print
    for i, recommendation in enumerate(results["recommendations"], 1):
        print(f"{i}. {recommendation}")  # noqa: print

    if "vue" in results["frameworks_detected"]:
        print(f"\n🔧 **Vue.js Best Practices:**")  # noqa: print
        print("   • Use Composition API for better code organization")  # noqa: print
        print("   • Avoid direct DOM manipulation with $refs")  # noqa: print
        print("   • Use proper key attributes in v-for loops")  # noqa: print
        print("   • Sanitize content before using v-html")  # noqa: print

    if "react" in results["frameworks_detected"]:
        print(f"\n🔧 **React Best Practices:**")  # noqa: print
        print("   • Use React Hooks instead of class components")  # noqa: print
        print("   • Avoid deprecated lifecycle methods")  # noqa: print
        print("   • Sanitize content before using dangerouslySetInnerHTML")  # noqa: print
        print("   • Use proper keys for list items")  # noqa: print

    if "javascript" in results["frameworks_detected"]:
        print(f"\n🔧 **JavaScript Best Practices:**")  # noqa: print
        print("   • Use const/let instead of var")  # noqa: print
        print("   • Use strict equality (===) instead of ==")  # noqa: print
        print("   • Handle async operations properly")  # noqa: print
        print("   • Remove console.log statements from production")  # noqa: print


async def analyze_frontend_code():
    """
    Run comprehensive frontend code analysis.

    Issue #281: Print sections extracted to helper functions to reduce
    function length from 186 to ~50 lines.
    """
    print("🎨 Starting frontend code analysis...")  # noqa: print
    print("Analyzing JavaScript, TypeScript, Vue, React, Angular, and other frontend files...")  # noqa: print
    print()  # noqa: print

    analyzer = FrontendAnalyzer()

    # Analyze frontend code
    results = await analyzer.analyze_frontend_code(
        root_path=".",
        patterns=[
            "**/*.js",
            "**/*.ts",
            "**/*.jsx",
            "**/*.tsx",
            "**/*.vue",
            "**/*.svelte",
            "**/*.html",
        ],
    )

    print("=== Frontend Code Analysis Results ===\n")  # noqa: print

    # Issue #281: Use extracted helpers for output sections
    _print_analysis_summary(results)
    _print_framework_usage(results)
    _print_component_analysis(results)
    _print_security_analysis(results)
    _print_performance_accessibility(results)
    _print_detailed_issues(results)
    _print_framework_recommendations(results)

    # Save detailed report
    report_path = Path("frontend_analysis_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n📋 **Report Generated:**")  # noqa: print
    print(f"   • Detailed analysis: {report_path}")  # noqa: print

    # Generate fix suggestions for critical issues
    critical_issues = [i for i in results["issues"] if i["severity"] == "critical"]
    if critical_issues:
        print(f"\n🚨 **CRITICAL ISSUES - IMMEDIATE ACTION REQUIRED:**")  # noqa: print
        print(f"Found {len(critical_issues)} critical issues that need immediate attention:")  # noqa: print

        for issue in critical_issues:
            print(f"\n🔴 **{issue['description']}**")  # noqa: print
            print(f"   📄 File: {issue['file_path']}:{issue['line_number']}")  # noqa: print
            print(f"   🏗️ Framework: {issue['framework'].title()}")  # noqa: print
            print(f"   💡 Fix: {issue['suggestion']}")  # noqa: print

    return results


def _print_examples_xss_perf_a11y() -> None:
    """Print examples 1-3: XSS, DOM performance, accessibility. Issue #1183."""
    print("**1. XSS Prevention:**")  # noqa: print
    print("```javascript")  # noqa: print
    print("// ❌ Dangerous - XSS vulnerability")  # noqa: print
    print("element.innerHTML = userInput;")  # noqa: print
    print()  # noqa: print
    print("// ✅ Safe - Sanitized content")  # noqa: print
    print("element.textContent = userInput;")  # noqa: print
    print("// or use a sanitization library")  # noqa: print
    print("element.innerHTML = DOMPurify.sanitize(userInput);")  # noqa: print
    print("```\n")  # noqa: print
    print("**2. Performance - DOM Query Optimization:**")  # noqa: print
    print("```javascript")  # noqa: print
    print("// ❌ Inefficient - DOM query in loop")  # noqa: print
    print("for (let i = 0; i < items.length; i++) {")  # noqa: print
    print("    document.querySelector('.container').appendChild(items[i]);")  # noqa: print
    print("}")  # noqa: print
    print()  # noqa: print
    print("// ✅ Efficient - Cache DOM query")  # noqa: print
    print("const container = document.querySelector('.container');")  # noqa: print
    print("for (let i = 0; i < items.length; i++) {")  # noqa: print
    print("    container.appendChild(items[i]);")  # noqa: print
    print("}")  # noqa: print
    print("```\n")  # noqa: print
    print("**3. Accessibility - Image Alt Text:**")  # noqa: print
    print("```html")  # noqa: print
    print("<!-- ❌ Missing alt attribute -->")  # noqa: print
    print('<img src="chart.png">')  # noqa: print
    print()  # noqa: print
    print("<!-- ✅ Descriptive alt text -->")  # noqa: print
    print('<img src="chart.png" alt="Sales chart showing 25% growth in Q3 2024">')  # noqa: print
    print("```\n")  # noqa: print


def _print_examples_vue_react_events() -> None:
    """Print examples 4-6: Vue v-html, React innerHTML, event cleanup. Issue #1183."""
    print("**4. Vue.js - Safe v-html Usage:**")  # noqa: print
    print("```vue")  # noqa: print
    print("<!-- ❌ Dangerous - Direct HTML binding -->")  # noqa: print
    print('<div v-html="userContent"></div>')  # noqa: print
    print()  # noqa: print
    print("<!-- ✅ Safe - Sanitized content -->")  # noqa: print
    print('<div v-html="$sanitize(userContent)"></div>')  # noqa: print
    print("```\n")  # noqa: print
    print("**5. React - Safe dangerouslySetInnerHTML:**")  # noqa: print
    print("```jsx")  # noqa: print
    print("// ❌ Dangerous - Unsanitized content")  # noqa: print
    print("function Component({ userContent }) {")  # noqa: print
    print("    return <div dangerouslySetInnerHTML={{__html: userContent}} />;")  # noqa: print
    print("}")  # noqa: print
    print()  # noqa: print
    print("// ✅ Safe - Sanitized content")  # noqa: print
    print("import DOMPurify from 'dompurify';")  # noqa: print
    print("function Component({ userContent }) {")  # noqa: print
    print("    const sanitized = DOMPurify.sanitize(userContent);")  # noqa: print
    print("    return <div dangerouslySetInnerHTML={{__html: sanitized}} />;")  # noqa: print
    print("}")  # noqa: print
    print("```\n")  # noqa: print
    print("**6. Event Listener Cleanup:**")  # noqa: print
    print("```javascript")  # noqa: print
    print("// ❌ Memory leak - No cleanup")  # noqa: print
    print("window.addEventListener('resize', handler);")  # noqa: print
    print()  # noqa: print
    print("// ✅ Proper cleanup")  # noqa: print
    print("window.addEventListener('resize', handler);")  # noqa: print
    print("// Later, when component unmounts:")  # noqa: print
    print("window.removeEventListener('resize', handler);")  # noqa: print
    print("```")  # noqa: print


async def generate_frontend_fix_examples():
    """Generate examples of common frontend fixes. Issue #1183."""
    print("\n=== 🛠️ Common Frontend Fix Examples ===\n")  # noqa: print
    _print_examples_xss_perf_a11y()
    _print_examples_vue_react_events()


async def main():
    """Run frontend analysis and examples"""

    # Check if we're in the right directory
    if not Path("src").exists():
        print("❌ Please run this script from the code-analysis-suite directory")  # noqa: print
        print("Usage: cd code-analysis-suite && python scripts/analyze_frontend.py")  # noqa: print
        return

    # Run analysis
    await analyze_frontend_code()

    # Show fix examples
    await generate_frontend_fix_examples()

    print("\n=== 🎯 Frontend Analysis Complete ===")  # noqa: print
    print("Next steps:")  # noqa: print
    print("1. Review frontend_analysis_report.json for detailed findings")  # noqa: print
    print("2. Address critical security issues immediately")  # noqa: print
    print("3. Fix performance issues affecting user experience")  # noqa: print
    print("4. Improve accessibility for better inclusion")  # noqa: print
    print("5. Add missing tests for untested components")  # noqa: print
    print("6. Set up ESLint and Prettier for consistent code quality")  # noqa: print


if __name__ == "__main__":
    run_or_schedule(main())
