#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Analysis Integration Script for AutoBot Analytics
Runs various code analysis tools and outputs results in JSON format
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.paths import project_root

# #14517: this module-level name was ``project_root`` while holding
# ``autobot-infrastructure/shared`` -- the script's grandparent, not the project
# root -- so it read as the canonical resolver and was not. Renamed to what it
# actually is.
_SHARED_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SHARED_DIR))

# #14543: the five sub-scripts used to be addressed under
# ``tools/code-analysis-suite/scripts/``, a directory this repo's Phase 1/4
# restructuring (#926, #781) deleted years ago, after copying its analyzers to
# ``autobot-backend/code_analysis/scripts/``. Resolved from the canonical
# project root (#13149) -- never from CWD, and never from this script's own
# directory, both of which silently point at the wrong tree when the caller's
# working directory differs.
_ANALYSIS_SCRIPTS_DIR = project_root() / "autobot-backend" / "code_analysis" / "scripts"

# Ceiling on a single sub-script's wall-clock time, in seconds.
_SUBPROCESS_TIMEOUT_SECONDS = 60

# Result keys whose value is checked for a per-analysis failure.
_ANALYSIS_RESULT_KEYS = ("code_quality", "duplicates", "performance", "architecture")


def _invoke_subprocess(
    script_path: Path, target_path: str, label: str
) -> Tuple[Optional[subprocess.CompletedProcess], Optional[str]]:
    """Run *script_path* with ``cwd=target_path``; return ``(result, error)``.

    Exactly one of the pair is ``None``. ``cwd`` is pinned to ``target_path``
    because these scripts resolve their own analysis root relative to the
    process's working directory, not from argv.
    """
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=target_path,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        return result, None
    except subprocess.TimeoutExpired:
        return None, f"{label} analysis timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s"
    except OSError as e:
        return None, f"{label} analysis could not start: {e}"


def _run_analysis_script(label: str, script_name: str, target_path: str) -> Dict[str, Any]:
    """Run one sub-script under ``_ANALYSIS_SCRIPTS_DIR`` and parse its JSON stdout.

    #14543: a missing script, a non-zero exit, and stdout that fails to parse as
    JSON are all reported as an ``error`` -- none of them may be folded into a
    fabricated "success" the way this used to synthesize placeholder metrics.
    """
    script_path = _ANALYSIS_SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_path}"}

    result, error = _invoke_subprocess(script_path, target_path, label)
    if error is not None:
        return {"error": error}

    if result.returncode != 0:
        return {"error": (result.stderr or "").strip() or f"{label} analysis exited {result.returncode}"}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"{label} analysis produced no parseable JSON output"}


def run_code_quality_analysis(target_path: str) -> Dict[str, Any]:
    """Run code quality analysis"""
    return _run_analysis_script("code quality", "analyze_code_quality.py", target_path)


def run_duplicate_analysis(target_path: str) -> Dict[str, Any]:
    """Run duplicate code analysis"""
    return _run_analysis_script("duplicate", "analyze_duplicates.py", target_path)


def run_performance_analysis(target_path: str) -> Dict[str, Any]:
    """Run performance analysis, preferring the lightweight script"""
    script_name = "analyze_performance_simple.py"
    if not (_ANALYSIS_SCRIPTS_DIR / script_name).exists():
        script_name = "analyze_performance.py"
    return _run_analysis_script("performance", script_name, target_path)


def run_architecture_analysis(target_path: str) -> Dict[str, Any]:
    """Run architecture analysis"""
    return _run_analysis_script("architecture", "analyze_architecture.py", target_path)


def _collect_failed_analyses(results: Dict[str, Any]) -> List[str]:
    """Names of the sub-analyses whose result carries an ``error`` key."""
    return [key for key in _ANALYSIS_RESULT_KEYS if isinstance(results.get(key), dict) and results[key].get("error")]


def _run_requested_analyses(results: Dict[str, Any], target_path: str, analysis_type: str) -> None:
    """Populate ``results`` in place with the analyses ``analysis_type`` selects."""
    if analysis_type in ("full", "quality"):
        results["code_quality"] = run_code_quality_analysis(target_path)

    if analysis_type in ("full", "duplicates"):
        results["duplicates"] = run_duplicate_analysis(target_path)

    if analysis_type in ("full", "performance"):
        results["performance"] = run_performance_analysis(target_path)

    if analysis_type in ("full", "communication_chains", "architecture"):
        results["architecture"] = run_architecture_analysis(target_path)
        architecture = results["architecture"]
        if isinstance(architecture, dict) and "communication_patterns" in architecture:
            results["communication_patterns"] = architecture["communication_patterns"]


def _extract_codebase_metrics(results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Roll up headline metrics from the quality analysis, when it succeeded."""
    quality = results.get("code_quality")
    if not isinstance(quality, dict) or quality.get("error"):
        return None
    return {
        "complexity": quality.get("complexity", 5),
        "maintainability": quality.get("maintainability", "good"),
        "test_coverage": quality.get("test_coverage", 70),
        "doc_coverage": quality.get("doc_coverage", 65),
    }


def run_full_analysis(target_path: str, analysis_type: str = "full") -> Dict[str, Any]:
    """Run complete code analysis suite"""
    results: Dict[str, Any] = {
        "status": "success",
        "target_path": target_path,
        "analysis_type": analysis_type,
    }

    if not Path(target_path).is_dir():
        return {"status": "error", "error": f"Target path not found: {target_path}"}

    _run_requested_analyses(results, target_path, analysis_type)

    # #14543: a failed sub-analysis must flip the overall status -- it used to
    # stay "success" no matter how many of the five analyses error'd out.
    failed = _collect_failed_analyses(results)
    if failed:
        results["status"] = "error"
        results["failed_analyses"] = failed

    metrics = _extract_codebase_metrics(results)
    if metrics is not None:
        results["codebase_metrics"] = metrics

    return results


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser for :func:`main`."""
    parser = argparse.ArgumentParser(description="Run code analysis suite")
    parser.add_argument(
        "--target",
        # #14517: the default was a shell placeholder in a plain string literal, so
        # an invocation without --target analysed a directory that cannot exist.
        default=str(project_root()),
        help="Target path to analyze",
    )
    parser.add_argument(
        "--analysis-type",
        default="full",
        choices=[
            "full",
            "quality",
            "duplicates",
            "performance",
            "communication_chains",
            "architecture",
        ],
        help="Type of analysis to run",
    )
    parser.add_argument(
        "--output-format",
        default="json",
        choices=["json", "text"],
        help="Output format",
    )
    return parser


def _print_text_report(args: argparse.Namespace, results: Dict[str, Any]) -> None:
    """Human-readable rendering of ``results`` -- CLI stdout, not logging."""
    print("Code Analysis Results")  # noqa: print -- CLI output, not application logging
    print("=" * 50)  # noqa: print
    print(f"Target: {args.target}")  # noqa: print
    print(f"Analysis Type: {args.analysis_type}")  # noqa: print
    print(f"Status: {results.get('status')}")  # noqa: print
    if results.get("failed_analyses"):
        print(f"Failed: {', '.join(results['failed_analyses'])}")  # noqa: print

    if results.get("codebase_metrics"):
        print("\nCodebase Metrics:")  # noqa: print
        for key, value in results["codebase_metrics"].items():
            print(f"  {key}: {value}")  # noqa: print


def main():
    """Main entry point"""
    args = _build_arg_parser().parse_args()

    results = run_full_analysis(args.target, args.analysis_type)

    if args.output_format == "json":
        print(json.dumps(results, indent=2))  # noqa: print -- CLI output, not application logging
    else:
        _print_text_report(args, results)

    # #14543: a run that found nothing must not exit 0 -- that is what let this
    # print a "completed" report to a caller while every sub-analysis had failed.
    if results.get("status") != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
