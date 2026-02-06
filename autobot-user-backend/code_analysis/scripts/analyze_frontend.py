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

from frontend_analyzer import FrontendAnalyzer


def _print_analysis_summary(results: dict) -> None:
    """
    Print analysis summary statistics.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    print(f"📊 **Analysis Summary:**")
    print(f"   • Total components analyzed: {results['total_components']}")
    print(f"   • Total issues found: {results['total_issues']}")
    print(f"   • Frameworks detected: {', '.join(results['frameworks_detected'])}")
    print(f"   • Overall quality score: {results['quality_score']:.1f}/100")
    print(f"   • Analysis time: {results['analysis_time_seconds']:.2f} seconds")
    print()


def _print_framework_usage(results: dict) -> None:
    """
    Print framework usage breakdown.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results['framework_usage']:
        return

    print("🏗️ **Framework Usage:**")
    for framework, usage in results['framework_usage'].items():
        framework_name = framework.title()
        print(f"   • {framework_name}: {usage['count']} components ({usage['percentage']:.1f}%)")

        if usage.get('lifecycle_hooks'):
            hooks = ', '.join(usage['lifecycle_hooks'][:5])
            if len(usage['lifecycle_hooks']) > 5:
                hooks += f" +{len(usage['lifecycle_hooks']) - 5} more"
            print(f"     Common hooks/patterns: {hooks}")
    print()


def _print_component_analysis(results: dict) -> None:
    """
    Print component analysis details.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results['components']:
        return

    print("🧩 **Component Analysis:**")

    components_with_tests = len([c for c in results['components'] if c['has_tests']])
    test_coverage = (components_with_tests / len(results['components']) * 100) if results['components'] else 0

    print(f"   • Components with tests: {components_with_tests}/{len(results['components'])} ({test_coverage:.1f}%)")

    # Show most complex components
    complex_components = sorted(results['components'],
                              key=lambda c: len(c['methods']) + len(c['props']),
                              reverse=True)[:3]

    if complex_components:
        print("   • Most complex components:")
        for comp in complex_components:
            complexity = len(comp['methods']) + len(comp['props'])
            print(f"     - {comp['name']} ({comp['component_type']}): {complexity} methods+props")
    print()


def _print_security_analysis(results: dict) -> None:
    """
    Print security analysis details.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    security_analysis = results['security_analysis']
    print(f"🛡️ **Security Analysis:**")
    print(f"   • Total security issues: {security_analysis['total_security_issues']}")
    print(f"   • Critical issues: {security_analysis['critical_issues']}")
    print(f"   • High priority issues: {security_analysis['high_priority_issues']}")
    print(f"   • Security score: {security_analysis['security_score']:.1f}/100")

    if security_analysis['total_security_issues'] > 0:
        security_issues = [i for i in results['issues'] if i['issue_type'] == 'security']
        print("   • Top security issues:")
        for issue in security_issues[:3]:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue['severity'], "⚪")
            print(f"     {emoji} {issue['description']} ({issue['file_path']}:{issue['line_number']})")
    print()


def _print_performance_accessibility(results: dict) -> None:
    """
    Print performance and accessibility analysis.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    # Performance analysis
    performance_analysis = results['performance_analysis']
    print(f"⚡ **Performance Analysis:**")
    print(f"   • Total performance issues: {performance_analysis['total_performance_issues']}")
    print(f"   • Components with issues: {performance_analysis['components_with_issues']}")

    if performance_analysis['issues_by_type']:
        print("   • Issue breakdown:")
        for issue_desc, count in list(performance_analysis['issues_by_type'].items())[:5]:
            print(f"     - {issue_desc}: {count}")
    print()

    # Accessibility analysis
    accessibility_analysis = results['accessibility_analysis']
    print(f"♿ **Accessibility Analysis:**")
    print(f"   • Total accessibility issues: {accessibility_analysis['total_accessibility_issues']}")
    print(f"   • WCAG compliance score: {accessibility_analysis['wcag_compliance_score']:.1f}/100")

    if accessibility_analysis.get('issues_by_severity'):
        print("   • Issues by severity:")
        for severity, count in accessibility_analysis['issues_by_severity'].items():
            print(f"     - {severity.title()}: {count}")
    print()


def _print_detailed_issues(results: dict) -> None:
    """
    Print detailed issue analysis grouped by type.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    if not results['issues']:
        return

    print("🔍 **Detailed Issue Analysis:**")

    # Group issues by type
    issues_by_type = {}
    for issue in results['issues']:
        issue_type = issue['issue_type']
        if issue_type not in issues_by_type:
            issues_by_type[issue_type] = []
        issues_by_type[issue_type].append(issue)

    for issue_type, type_issues in issues_by_type.items():
        if issue_type.endswith('_specific'):
            framework = issue_type.split('_')[0].title()
            category_name = f"{framework}-Specific Issues"
        else:
            category_name = issue_type.replace('_', ' ').title()

        print(f"\n📋 **{category_name} ({len(type_issues)} issues):**")

        # Show top issues by severity
        sorted_issues = sorted(type_issues,
                             key=lambda x: {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}.get(x['severity'], 0),
                             reverse=True)

        for issue in sorted_issues[:5]:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue['severity'], "⚪")

            print(f"   {emoji} {issue['description']}")
            print(f"      📄 {issue['file_path']}:{issue['line_number']} ({issue['framework']})")
            print(f"      💡 Suggestion: {issue['suggestion']}")


def _print_framework_recommendations(results: dict) -> None:
    """
    Print framework-specific best practice recommendations.

    Issue #281: Extracted from analyze_frontend_code to reduce function length.
    """
    print(f"\n💡 **Improvement Recommendations:**")
    for i, recommendation in enumerate(results['recommendations'], 1):
        print(f"{i}. {recommendation}")

    if 'vue' in results['frameworks_detected']:
        print(f"\n🔧 **Vue.js Best Practices:**")
        print("   • Use Composition API for better code organization")
        print("   • Avoid direct DOM manipulation with $refs")
        print("   • Use proper key attributes in v-for loops")
        print("   • Sanitize content before using v-html")

    if 'react' in results['frameworks_detected']:
        print(f"\n🔧 **React Best Practices:**")
        print("   • Use React Hooks instead of class components")
        print("   • Avoid deprecated lifecycle methods")
        print("   • Sanitize content before using dangerouslySetInnerHTML")
        print("   • Use proper keys for list items")

    if 'javascript' in results['frameworks_detected']:
        print(f"\n🔧 **JavaScript Best Practices:**")
        print("   • Use const/let instead of var")
        print("   • Use strict equality (===) instead of ==")
        print("   • Handle async operations properly")
        print("   • Remove console.log statements from production")


async def analyze_frontend_code():
    """
    Run comprehensive frontend code analysis.

    Issue #281: Print sections extracted to helper functions to reduce
    function length from 186 to ~50 lines.
    """
    print("🎨 Starting frontend code analysis...")
    print("Analyzing JavaScript, TypeScript, Vue, React, Angular, and other frontend files...")
    print()

    analyzer = FrontendAnalyzer()

    # Analyze frontend code
    results = await analyzer.analyze_frontend_code(
        root_path=".",
        patterns=["**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx", "**/*.vue", "**/*.svelte", "**/*.html"]
    )

    print("=== Frontend Code Analysis Results ===\n")

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
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n📋 **Report Generated:**")
    print(f"   • Detailed analysis: {report_path}")

    # Generate fix suggestions for critical issues
    critical_issues = [i for i in results['issues'] if i['severity'] == 'critical']
    if critical_issues:
        print(f"\n🚨 **CRITICAL ISSUES - IMMEDIATE ACTION REQUIRED:**")
        print(f"Found {len(critical_issues)} critical issues that need immediate attention:")

        for issue in critical_issues:
            print(f"\n🔴 **{issue['description']}**")
            print(f"   📄 File: {issue['file_path']}:{issue['line_number']}")
            print(f"   🏗️ Framework: {issue['framework'].title()}")
            print(f"   💡 Fix: {issue['suggestion']}")

    return results


async def generate_frontend_fix_examples():
    """Generate examples of common frontend fixes"""

    print("\n=== 🛠️ Common Frontend Fix Examples ===\n")

    print("**1. XSS Prevention:**")
    print("```javascript")
    print("// ❌ Dangerous - XSS vulnerability")
    print("element.innerHTML = userInput;")
    print()
    print("// ✅ Safe - Sanitized content")
    print("element.textContent = userInput;")
    print("// or use a sanitization library")
    print("element.innerHTML = DOMPurify.sanitize(userInput);")
    print("```")
    print()

    print("**2. Performance - DOM Query Optimization:**")
    print("```javascript")
    print("// ❌ Inefficient - DOM query in loop")
    print("for (let i = 0; i < items.length; i++) {")
    print("    document.querySelector('.container').appendChild(items[i]);")
    print("}")
    print()
    print("// ✅ Efficient - Cache DOM query")
    print("const container = document.querySelector('.container');")
    print("for (let i = 0; i < items.length; i++) {")
    print("    container.appendChild(items[i]);")
    print("}")
    print("```")
    print()

    print("**3. Accessibility - Image Alt Text:**")
    print("```html")
    print("<!-- ❌ Missing alt attribute -->")
    print('<img src="chart.png">')
    print()
    print("<!-- ✅ Descriptive alt text -->")
    print('<img src="chart.png" alt="Sales chart showing 25% growth in Q3 2024">')
    print("```")
    print()

    print("**4. Vue.js - Safe v-html Usage:**")
    print("```vue")
    print("<!-- ❌ Dangerous - Direct HTML binding -->")
    print('<div v-html="userContent"></div>')
    print()
    print("<!-- ✅ Safe - Sanitized content -->")
    print('<div v-html="$sanitize(userContent)"></div>')
    print("```")
    print()

    print("**5. React - Safe dangerouslySetInnerHTML:**")
    print("```jsx")
    print("// ❌ Dangerous - Unsanitized content")
    print("function Component({ userContent }) {")
    print("    return <div dangerouslySetInnerHTML={{__html: userContent}} />;")
    print("}")
    print()
    print("// ✅ Safe - Sanitized content")
    print("import DOMPurify from 'dompurify';")
    print("function Component({ userContent }) {")
    print("    const sanitized = DOMPurify.sanitize(userContent);")
    print("    return <div dangerouslySetInnerHTML={{__html: sanitized}} />;")
    print("}")
    print("```")
    print()

    print("**6. Event Listener Cleanup:**")
    print("```javascript")
    print("// ❌ Memory leak - No cleanup")
    print("window.addEventListener('resize', handler);")
    print()
    print("// ✅ Proper cleanup")
    print("window.addEventListener('resize', handler);")
    print("// Later, when component unmounts:")
    print("window.removeEventListener('resize', handler);")
    print("```")


async def main():
    """Run frontend analysis and examples"""

    # Check if we're in the right directory
    if not Path("src").exists():
        print("❌ Please run this script from the code-analysis-suite directory")
        print("Usage: cd code-analysis-suite && python scripts/analyze_frontend.py")
        return

    # Run analysis
    results = await analyze_frontend_code()

    # Show fix examples
    await generate_frontend_fix_examples()

    print("\n=== 🎯 Frontend Analysis Complete ===")
    print("Next steps:")
    print("1. Review frontend_analysis_report.json for detailed findings")
    print("2. Address critical security issues immediately")
    print("3. Fix performance issues affecting user experience")
    print("4. Improve accessibility for better inclusion")
    print("5. Add missing tests for untested components")
    print("6. Set up ESLint and Prettier for consistent code quality")


if __name__ == "__main__":
    asyncio.run(main())
