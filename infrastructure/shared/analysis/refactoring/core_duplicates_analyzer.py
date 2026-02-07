#!/usr/bin/env python3
"""
Analyze duplicate patterns specifically in core AutoBot files
Focus on main application code, exclude archives and third-party code
"""

import json


def is_core_autobot_file(file_path: str) -> bool:
    """Check if file is part of core AutoBot application"""
    exclusions = [
        "/reports/",
        "/archives/",
        "/node_modules/",
        "/.venv/",
        "/venv/",
        "/mcp-tools/",
        "/temp/",
        "/logs/",
        "/novnc/",
        "/tests/external/",
        "/frontend/static/",
        ".git",
        "__pycache__",
    ]

    # Only include core directories
    core_patterns = ["/src/", "/backend/", "/autobot-vue/src/", "/scripts/"]

    # Exclude archived and temporary files
    for exclusion in exclusions:
        if exclusion in file_path:
            return False

    # Include only core patterns
    for pattern in core_patterns:
        if pattern in file_path:
            return True

    return False


def _filter_function_duplicates(results: dict) -> list:
    """Filter function duplicates to core files only (Issue #560: extracted)."""
    core_duplicates = []
    for dup in results["duplicate_functions"]:
        core_funcs = [f for f in dup["functions"] if is_core_autobot_file(f["file"])]
        if len(core_funcs) >= 2:
            core_duplicates.append(
                {
                    "count": len(core_funcs),
                    "functions": core_funcs,
                    "sample_code": dup["sample_code"],
                }
            )
    return core_duplicates


def _filter_class_duplicates(results: dict) -> list:
    """Filter class duplicates to core files only (Issue #560: extracted)."""
    core_duplicates = []
    for dup in results["duplicate_classes"]:
        core_classes = [c for c in dup["classes"] if is_core_autobot_file(c["file"])]
        if len(core_classes) >= 2:
            core_duplicates.append(
                {
                    "count": len(core_classes),
                    "classes": core_classes,
                    "sample_code": dup["sample_code"],
                }
            )
    return core_duplicates


def _filter_config_duplicates(results: dict) -> list:
    """Filter config duplicates to core files only (Issue #560: extracted)."""
    core_duplicates = []
    for dup in results["duplicate_config_patterns"]:
        core_configs = [p for p in dup["patterns"] if is_core_autobot_file(p["file"])]
        if len(core_configs) >= 2:
            core_duplicates.append(
                {
                    "count": len(core_configs),
                    "patterns": core_configs,
                    "sample_code": dup["sample_code"],
                }
            )
    return core_duplicates


def _filter_string_duplicates(results: dict) -> list:
    """Filter string duplicates to core files only (Issue #560: extracted)."""
    core_duplicates = []
    for dup in results["duplicate_strings"]:
        core_strings = [
            s for s in dup["occurrences"] if is_core_autobot_file(s["file"])
        ]
        if len(core_strings) >= 3:  # Higher threshold for strings
            core_duplicates.append(
                {
                    "count": len(core_strings),
                    "value": dup["value"],
                    "type": dup["type"],
                    "occurrences": core_strings,
                }
            )
    return core_duplicates


def _filter_api_duplicates(results: dict) -> list:
    """Filter API duplicates to core files only (Issue #560: extracted)."""
    core_duplicates = []
    for dup in results["duplicate_api_patterns"]:
        core_apis = [a for a in dup["patterns"] if is_core_autobot_file(a["file"])]
        if len(core_apis) >= 2:
            core_duplicates.append(
                {
                    "count": len(core_apis),
                    "patterns": core_apis,
                    "sample_code": dup["sample_code"],
                }
            )
    return core_duplicates


def _print_summary(duplicates: dict) -> None:
    """Print duplicate summary (Issue #560: extracted)."""
    print("📊 CORE DUPLICATE SUMMARY:")
    print(f"   Core function duplicates: {len(duplicates['functions'])}")
    print(f"   Core class duplicates: {len(duplicates['classes'])}")
    print(f"   Core config duplicates: {len(duplicates['configs'])}")
    print(f"   Core string duplicates: {len(duplicates['strings'])}")
    print(f"   Core API duplicates: {len(duplicates['apis'])}")


def _print_top_duplicates(
    sorted_funcs: list, sorted_configs: list, sorted_strings: list
) -> None:
    """Print top duplicates for each category (Issue #560: extracted)."""
    # Top function duplicates
    print("\n🔄 TOP CORE FUNCTION DUPLICATES:")
    for i, dup in enumerate(sorted_funcs[:10]):
        print(f"   {i+1}. {dup['count']} occurrences: {dup['functions'][0]['name']}")
        for func in dup["functions"]:
            print(f"      - {func['file']}:{func['line']}")
        print()

    # Top config duplicates
    print("\n🔧 TOP CORE CONFIG DUPLICATES:")
    for i, dup in enumerate(sorted_configs[:5]):
        pattern = (
            dup["patterns"][0]["pattern"][:60] + "..."
            if len(dup["patterns"][0]["pattern"]) > 60
            else dup["patterns"][0]["pattern"]
        )
        print(f"   {i+1}. {dup['count']} occurrences: {pattern}")
        for pat in dup["patterns"]:
            print(f"      - {pat['file']}:{pat['line']}")
        print()

    # Top string duplicates
    print("\n🌐 TOP CORE STRING DUPLICATES:")
    for i, dup in enumerate(sorted_strings[:5]):
        print(f"   {i+1}. {dup['count']} occurrences: {dup['value']} ({dup['type']})")
        for occ in dup["occurrences"][:3]:
            print(f"      - {occ['file']}:{occ['line']}")
        print()


def _print_recommendations() -> None:
    """Print refactoring recommendations (Issue #560: extracted)."""
    print("\n💡 REFACTORING RECOMMENDATIONS:")
    print("   1. Create shared utility functions for path resolution")
    print("   2. Consolidate Redis connection patterns")
    print("   3. Create configuration management utilities")
    print("   4. Extract common API endpoint patterns")
    print("   5. Centralize hardcoded URLs and IP addresses")


def _build_results(
    sorted_funcs: list,
    core_class_duplicates: list,
    sorted_configs: list,
    sorted_strings: list,
    core_api_duplicates: list,
) -> dict:
    """Build results dictionary (Issue #560: extracted)."""
    return {
        "function_duplicates": sorted_funcs,
        "class_duplicates": core_class_duplicates,
        "config_duplicates": sorted_configs,
        "string_duplicates": sorted_strings,
        "api_duplicates": core_api_duplicates,
        "summary": {
            "total_core_duplicates": (
                len(sorted_funcs)
                + len(core_class_duplicates)
                + len(sorted_configs)
                + len(sorted_strings)
                + len(core_api_duplicates)
            ),
            "function_count": len(sorted_funcs),
            "class_count": len(core_class_duplicates),
            "config_count": len(sorted_configs),
            "string_count": len(sorted_strings),
            "api_count": len(core_api_duplicates),
        },
    }


def analyze_core_duplicates():
    """Analyze duplicates in core AutoBot files only (Issue #560: decomposed)."""
    # Load the full analysis results
    with open(
        "/home/kali/Desktop/AutoBot/analysis/refactoring/duplicate_analysis_results.json",
        "r",
    ) as f:
        results = json.load(f)

    print("🎯 CORE AUTOBOT DUPLICATE ANALYSIS")
    print("=" * 60)

    # Filter duplicates to core files only
    core_function_duplicates = _filter_function_duplicates(results)
    core_class_duplicates = _filter_class_duplicates(results)
    core_config_duplicates = _filter_config_duplicates(results)
    core_string_duplicates = _filter_string_duplicates(results)
    core_api_duplicates = _filter_api_duplicates(results)

    # Print summary
    _print_summary(
        {
            "functions": core_function_duplicates,
            "classes": core_class_duplicates,
            "configs": core_config_duplicates,
            "strings": core_string_duplicates,
            "apis": core_api_duplicates,
        }
    )

    # Sort by count
    sorted_funcs = sorted(
        core_function_duplicates, key=lambda x: x["count"], reverse=True
    )
    sorted_configs = sorted(
        core_config_duplicates, key=lambda x: x["count"], reverse=True
    )
    sorted_strings = sorted(
        core_string_duplicates, key=lambda x: x["count"], reverse=True
    )

    # Print top duplicates and recommendations
    _print_top_duplicates(sorted_funcs, sorted_configs, sorted_strings)
    _print_recommendations()

    # Build and save results
    core_results = _build_results(
        sorted_funcs,
        core_class_duplicates,
        sorted_configs,
        sorted_strings,
        core_api_duplicates,
    )

    output_file = (
        "/home/kali/Desktop/AutoBot/analysis/refactoring/core_duplicates_analysis.json"
    )
    with open(output_file, "w") as f:
        json.dump(core_results, f, indent=2)

    print(f"\n💾 Core duplicates saved to: {output_file}")

    return core_results


if __name__ == "__main__":
    analyze_core_duplicates()
