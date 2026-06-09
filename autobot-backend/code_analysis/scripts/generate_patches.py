#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Generate Automated Code Fixes
Uses analysis results to generate specific, actionable code fixes
"""

import json
from pathlib import Path

from automated_fix_generator import AutomatedFixGenerator
from code_quality_dashboard import CodeQualityDashboard

from autobot_shared.async_compat import run_or_schedule


def _print_fix_summary_stats(fix_results: dict) -> None:
    """
    Print fix generation summary statistics.

    Issue #281: Extracted from generate_comprehensive_fixes to reduce
    function length and improve readability.
    """
    print(f"📊 **Fix Generation Summary:**")  # noqa: print
    print(f"   • Total fixes generated: {fix_results['total_fixes_generated']}")  # noqa: print
    print(f"   • High confidence fixes: {fix_results['high_confidence_fixes']}")  # noqa: print
    print(f"   • Low risk fixes: {fix_results['low_risk_fixes']}")  # noqa: print
    print(f"   • Patches generated: {len(fix_results['patches'])}")  # noqa: print
    print(f"   • Generation time: {fix_results['generation_time_seconds']:.2f} seconds")  # noqa: print
    print()  # noqa: print


def _print_fix_categories(stats: dict) -> None:
    """
    Print fix category breakdown and confidence distribution.

    Issue #281: Extracted from generate_comprehensive_fixes to reduce
    function length and improve readability.
    """
    print("🏷️ **Fix Categories:**")  # noqa: print
    for fix_type, count in stats["by_type"].items():
        fix_name = fix_type.replace("_", " ").title()
        print(f"   • {fix_name}: {count} fixes")  # noqa: print
    print()  # noqa: print

    print("🎯 **Fix Confidence Distribution:**")  # noqa: print
    conf_stats = stats["by_confidence"]
    print(f"   • High confidence (>80%): {conf_stats['high']} fixes")  # noqa: print
    print(f"   • Medium confidence (60-80%): {conf_stats['medium']} fixes")  # noqa: print
    print(f"   • Low confidence (<60%): {conf_stats['low']} fixes")  # noqa: print
    print()  # noqa: print

    print("⚠️ **Risk Assessment:**")  # noqa: print
    risk_stats = stats["by_risk"]
    print(f"   • Low risk: {risk_stats['low']} fixes (safe to auto-apply)")  # noqa: print
    print(f"   • Medium risk: {risk_stats['medium']} fixes (review recommended)")  # noqa: print
    print(f"   • High risk: {risk_stats['high']} fixes (manual review required)")  # noqa: print
    print()  # noqa: print

    print(f"🤖 **Automation Readiness:**")  # noqa: print
    print(f"   • Can be applied automatically: {stats['automated_fixes']} fixes")  # noqa: print
    print(f"   • Require manual review: {stats['manual_review_required']} fixes")  # noqa: print
    print()  # noqa: print


def _print_high_priority_fixes(fix_results: dict) -> None:
    """
    Print top priority fixes requiring immediate action.

    Issue #281: Extracted from generate_comprehensive_fixes to reduce
    function length and improve readability.
    """
    print("🚨 **Top Priority Fixes (Immediate Action):**")  # noqa: print

    high_priority_fixes = [fix for fix in fix_results["fixes"][:20] if fix["severity"] in ["critical", "high"]]

    for i, fix in enumerate(high_priority_fixes[:10], 1):
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        emoji = severity_emoji.get(fix["severity"], "⚪")
        confidence_icon = "🎯" if fix["confidence"] > 0.8 else "🤔"
        risk_icon = {"low": "✅", "medium": "⚠️", "high": "🚨"}[fix["risk_level"]]

        print(f"\n{i}. {emoji} **{fix['description']}** ({fix['severity'].upper()})")  # noqa: print
        print(f"   🏷️ Type: {fix['fix_type'].replace('_', ' ').title()}")  # noqa: print
        if fix["file_path"] != "Multiple files":
            print(f"   📄 Location: {fix['file_path']}:{fix['line_number']}")  # noqa: print
        print(f"   {confidence_icon} Confidence: {fix['confidence']:.0%}")  # noqa: print
        print(f"   {risk_icon} Risk Level: {fix['risk_level'].title()}")  # noqa: print
        print(f"   📝 Explanation: {fix['explanation']}")  # noqa: print

        if fix["original_code"] and fix["fixed_code"]:
            print(f"   \n   🔧 **Fix Preview:**")  # noqa: print
            print(f"   ```python")  # noqa: print
            print(f"   # Before:")  # noqa: print
            print(f"   {fix['original_code']}")  # noqa: print
            print(f"   # After:")  # noqa: print
            print(f"   {fix['fixed_code']}")  # noqa: print
            print(f"   ```")  # noqa: print


def _print_patches_and_security(fix_results: dict) -> None:
    """
    Print generated patches and security/performance fix sections.

    Issue #281: Extracted from generate_comprehensive_fixes to reduce
    function length and improve readability.
    """
    # Show automated patches
    if fix_results["patches"]:
        print(f"\n📋 **Generated Patches (Ready to Apply):**")  # noqa: print
        print(  # noqa: print
            f"Found {len(fix_results['patches'])} high-confidence patches that can be applied automatically.\n"
        )

        for i, patch in enumerate(fix_results["patches"][:5], 1):
            print(f"{i}. **{patch['description']}**")  # noqa: print
            print(f"   File: {patch['file_path']}:{patch['line_number']}")  # noqa: print
            print(f"   Confidence: {patch['confidence']:.0%}, Risk: {patch['risk_level']}")  # noqa: print
            print("   ```diff")  # noqa: print
            print(patch["patch_content"])  # noqa: print
            print("   ```")  # noqa: print

    # Security-specific fixes
    security_fixes = [f for f in fix_results["fixes"] if "security" in f["fix_type"] or "injection" in f["fix_type"]]
    if security_fixes:
        print(f"🛡️ **Critical Security Fixes:**")  # noqa: print
        print(f"Found {len(security_fixes)} security-related fixes that should be applied immediately:")  # noqa: print

        for fix in security_fixes[:3]:
            print(f"   • {fix['description']}")  # noqa: print
            print(f"     Location: {fix['file_path']}:{fix['line_number']}")  # noqa: print
            print(f"     Fix: {fix['explanation']}")  # noqa: print
        print()  # noqa: print

    # Performance-specific fixes
    performance_fixes = [f for f in fix_results["fixes"] if "performance" in f["fix_type"] or "memory" in f["fix_type"]]
    if performance_fixes:
        print(f"⚡ **Performance Optimization Fixes:**")  # noqa: print
        print(f"Found {len(performance_fixes)} performance-related fixes:")  # noqa: print

        for fix in performance_fixes[:3]:
            print(f"   • {fix['description']}")  # noqa: print
            print(f"     Impact: {fix['explanation']}")  # noqa: print
        print()  # noqa: print


def _print_fix_intro() -> None:
    """Print fix generation startup banner. Issue #1183: Extracted from generate_comprehensive_fixes()."""
    print("🔧 Starting automated fix generation...")  # noqa: print
    print("This will analyze the codebase and generate specific code fixes for:")  # noqa: print
    print("  • Security vulnerabilities")  # noqa: print
    print("  • Performance issues")  # noqa: print
    print("  • Code duplication")  # noqa: print
    print("  • Environment configuration")  # noqa: print
    print("  • API consistency issues")  # noqa: print
    print()  # noqa: print


async def _test_and_print_safe_application(generator, fix_results: dict) -> None:
    """Run dry-run fix application and print results. Issue #1183: Extracted from generate_comprehensive_fixes()."""
    print("🧪 **Testing Automated Fix Application (Dry Run):**")  # noqa: print
    application_results = await generator.apply_safe_fixes(fix_results, dry_run=True)
    print(f"   ✅ Can apply automatically: {application_results['total_applied']} fixes")  # noqa: print
    print("   🔍 Would require verification after application")  # noqa: print
    print()  # noqa: print
    if application_results["applied_fixes"]:
        print("   **Fixes that would be applied automatically:**")  # noqa: print
        for fix in application_results["applied_fixes"][:5]:
            print(f"   • {fix['description']} ({fix['file_path']})")  # noqa: print


def _save_fix_reports(fix_results: dict) -> None:
    """Save fixes and patches to JSON/patch files and print paths. Issue #1183: Extracted from generate_comprehensive_fixes()."""
    fixes_path = Path("automated_fixes_report.json")
    with open(fixes_path, "w", encoding="utf-8") as f:
        json.dump(fix_results, f, indent=2, default=str)
    patches_path = Path("generated_patches.patch")
    if fix_results["patches"]:
        with open(patches_path, "w", encoding="utf-8") as f:
            f.write("# Automated Code Fixes\n")
            f.write("# Generated by AutoBot Code Quality System\n\n")
            for patch in fix_results["patches"]:
                f.write(f"# Fix: {patch['description']}\n")
                f.write(f"# Confidence: {patch['confidence']:.0%}, Risk: {patch['risk_level']}\n")
                f.write(patch["patch_content"])
                f.write("\n")
    print("📋 **Generated Reports:**")  # noqa: print
    print(f"   • Detailed fixes: {fixes_path}")  # noqa: print
    if fix_results["patches"]:
        print(f"   • Patch file: {patches_path}")  # noqa: print
    print()  # noqa: print


async def generate_comprehensive_fixes():
    """
    Generate automated fixes based on comprehensive analysis.

    Issue #281: Print sections extracted to helper functions to reduce
    function length from 187 to ~60 lines.
    Issue #1183: Further extraction to _print_fix_intro, _test_and_print_safe_application,
    and _save_fix_reports.
    """
    # Issue #1183: Delegate intro to extracted helper
    _print_fix_intro()

    # First run comprehensive analysis
    dashboard = CodeQualityDashboard()

    print("📊 Running comprehensive code quality analysis...")  # noqa: print
    analysis_results = await dashboard.generate_comprehensive_report(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"], include_trends=False
    )

    # Extract detailed analysis results for fix generation
    detailed_analyses = analysis_results.get("detailed_analyses", {})

    print(f"✅ Analysis complete. Found {analysis_results['issue_summary']['total_issues']} issues.")  # noqa: print
    print()  # noqa: print

    # Generate fixes
    generator = AutomatedFixGenerator()

    print("🛠️ Generating automated fixes...")  # noqa: print
    fix_results = await generator.generate_fixes(detailed_analyses, generate_patches=True)

    print("=== Automated Fix Generation Results ===\n")  # noqa: print

    # Issue #281: Use extracted helpers for output sections
    _print_fix_summary_stats(fix_results)
    _print_fix_categories(fix_results["statistics"])
    _print_high_priority_fixes(fix_results)
    _print_patches_and_security(fix_results)

    # Show fix recommendations
    print("📋 **Fix Application Recommendations:**")  # noqa: print
    for i, recommendation in enumerate(fix_results["recommendations"], 1):
        print(f"{i}. {recommendation}")  # noqa: print
    print()  # noqa: print

    # Issue #1183: Delegate dry-run application and save-reports to extracted helpers
    await _test_and_print_safe_application(generator, fix_results)
    _save_fix_reports(fix_results)

    return fix_results


async def demonstrate_fix_application():
    """Demonstrate how to apply fixes safely"""

    print("=== Safe Fix Application Guide ===\n")  # noqa: print

    print("🔧 **How to Apply Automated Fixes Safely:**\n")  # noqa: print

    print("**1. Review High-Confidence Fixes:**")  # noqa: print
    print("   • Only apply fixes with >80% confidence and low risk")  # noqa: print
    print("   • Review the before/after code changes")  # noqa: print
    print("   • Ensure you understand what each fix does")  # noqa: print
    print()  # noqa: print

    print("**2. Apply Patches in Stages:**")  # noqa: print
    print("   ```bash")  # noqa: print
    print("   # Apply security fixes first (highest priority)")  # noqa: print
    print("   git checkout -b security-fixes")  # noqa: print
    print("   patch -p1 < security_fixes.patch")  # noqa: print
    print("   ")  # noqa: print
    print("   # Run tests after each batch")  # noqa: print
    print("   python -m pytest tests/")  # noqa: print
    print("   flake8 src/ backend/")  # noqa: print
    print("   ")  # noqa: print
    print("   # Commit and test before next batch")  # noqa: print
    print("   git add -A && git commit -m 'Apply automated security fixes'")  # noqa: print
    print("   ```")  # noqa: print
    print()  # noqa: print

    print("**3. Verification Steps:**")  # noqa: print
    print("   • Run full test suite after applying fixes")  # noqa: print
    print("   • Check for syntax errors: `python -m py_compile file.py`")  # noqa: print
    print("   • Verify application still starts correctly")  # noqa: print
    print("   • Review logs for any new errors")  # noqa: print
    print()  # noqa: print

    print("**4. Manual Review Required For:**")  # noqa: print
    print("   • High-risk fixes (may change behavior)")  # noqa: print
    print("   • Low-confidence fixes (<60%)")  # noqa: print
    print("   • Complex refactoring suggestions")  # noqa: print
    print("   • Architectural changes")  # noqa: print
    print()  # noqa: print

    print("**5. Rollback Plan:**")  # noqa: print
    print("   ```bash")  # noqa: print
    print("   # If issues arise, rollback easily")  # noqa: print
    print("   git reset --hard HEAD~1")  # noqa: print
    print("   ")  # noqa: print
    print("   # Or revert specific files")  # noqa: print
    print("   git checkout HEAD~1 -- src/problematic_file.py")  # noqa: print
    print("   ```")  # noqa: print
    print()  # noqa: print

    print("**6. Integration with CI/CD:**")  # noqa: print
    print("   • Set up pre-commit hooks for code quality")  # noqa: print
    print("   • Run automated fix generation in CI")  # noqa: print
    print("   • Create pull requests for fix review")  # noqa: print
    print("   • Automate safe fix application in staging")  # noqa: print
    print()  # noqa: print


async def main():
    """Run automated fix generation and demonstration"""

    # Generate fixes
    await generate_comprehensive_fixes()

    # Show how to apply fixes safely
    await demonstrate_fix_application()

    print("=== 🎯 Automated Fix Generation Complete ===")  # noqa: print
    print("Next steps:")  # noqa: print
    print("1. Review automated_fixes_report.json for all generated fixes")  # noqa: print
    print("2. Apply high-confidence, low-risk fixes first")  # noqa: print
    print("3. Test thoroughly after each batch of fixes")  # noqa: print
    print("4. Use generated patches for easy application")  # noqa: print
    print("5. Set up automated fix generation in your CI/CD pipeline")  # noqa: print


if __name__ == "__main__":
    run_or_schedule(main())
