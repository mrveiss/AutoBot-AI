#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Codebase Profiler
Analyzes the entire AutoBot codebase for performance, patterns, and optimization opportunities
"""

import ast
import cProfile
import importlib
import inspect
import io
import json
import os
import pstats
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Issue #380: Module-level tuple for AST complexity checking
_COMPLEXITY_BRANCH_TYPES = (ast.If, ast.While, ast.For, ast.AsyncFor)


class CodebaseProfiler:
    """Comprehensive codebase analysis and profiling"""

    def __init__(self, project_root: str = None):
        """Initialize profiler with project root and results containers."""
        self.project_root = Path(
            project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.results = {
            "static_analysis": {},
            "runtime_profiling": {},
            "complexity_analysis": {},
            "pattern_analysis": {},
            "performance_hotspots": {},
            "recommendations": [],
        }

    def _should_skip_path(self, py_file: Path) -> bool:
        """Check if path should be skipped (Issue #315: extracted helper)."""
        skip_patterns = [
            "node_modules",
            ".git",
            "__pycache__",
            ".pytest_cache",
            "venv",
            ".env",
        ]
        return any(skip in str(py_file) for skip in skip_patterns)

    def _process_function_node(
        self, node: ast.FunctionDef, py_file: Path, patterns: Dict[str, Any]
    ) -> None:
        """Process a function definition node (Issue #315: extracted helper)."""
        patterns["function_definitions"][node.name] += 1
        patterns["duplicate_functions"][node.name].append(str(py_file))

        complexity = self._calculate_complexity(node)
        if complexity > 10:
            patterns["complexity_hotspots"].append(
                {
                    "function": node.name,
                    "file": str(py_file.relative_to(self.project_root)),
                    "complexity": complexity,
                    "line": node.lineno,
                }
            )

    def _process_ast_node(
        self, node: ast.AST, py_file: Path, patterns: Dict[str, Any]
    ) -> None:
        """Process a single AST node (Issue #315: extracted helper)."""
        if isinstance(node, ast.FunctionDef):
            self._process_function_node(node, py_file, patterns)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                patterns["import_statements"][alias.name] += 1
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                patterns["import_statements"][node.module] += 1
        elif isinstance(node, ast.ClassDef):
            patterns["class_definitions"][node.name] += 1

    def _analyze_single_file(self, py_file: Path, patterns: Dict[str, Any]) -> bool:
        """Analyze a single Python file (Issue #315: extracted helper)."""
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(py_file))

            for node in ast.walk(tree):
                self._process_ast_node(node, py_file, patterns)
            return True
        except Exception as e:
            print(f"Warning: Could not parse {py_file}: {e}")
            return False

    def analyze_static_patterns(self) -> Dict[str, Any]:
        """Analyze code patterns using AST (Issue #315: refactored)."""
        print("🔍 Analyzing code patterns with AST...")

        patterns = {
            "function_definitions": Counter(),
            "import_statements": Counter(),
            "class_definitions": Counter(),
            "common_patterns": defaultdict(int),
            "complexity_hotspots": [],
            "duplicate_functions": defaultdict(list),
        }

        python_files = [
            py_file
            for py_file in self.project_root.rglob("*.py")
            if not self._should_skip_path(py_file)
        ]

        print(f"Found {len(python_files)} Python files to analyze")

        # Limit analysis to prevent timeout
        if len(python_files) > 100:
            python_files = python_files[:100]
            print("Limited analysis to first 100 files for performance")

        for py_file in python_files:
            self._analyze_single_file(py_file, patterns)

        # Find truly duplicate functions (same name in multiple files)
        actual_duplicates = {
            name: files
            for name, files in patterns["duplicate_functions"].items()
            if len(files) > 1
        }
        patterns["duplicate_functions"] = actual_duplicates

        self.results["static_analysis"] = patterns
        return patterns

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            # Issue #380: Use module-level constant
            if isinstance(child, _COMPLEXITY_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return complexity

    def profile_runtime_performance(self) -> Dict[str, Any]:
        """Profile runtime performance of key modules"""
        print("⚡ Profiling runtime performance...")

        performance_data = {}

        # List of key modules to profile
        key_modules = [
            "src.orchestrator",
            "src.llm_interface",
            "src.knowledge_base",
            "backend.app_factory",
            "src.project_state_manager",
        ]

        for module_name in key_modules:
            try:
                print(f"  Profiling {module_name}...")

                # Profile module import time
                start_time = time.time()
                profiler = cProfile.Profile()
                profiler.enable()

                module = importlib.import_module(module_name)

                profiler.disable()
                import_time = time.time() - start_time

                # Get profiling stats
                stats_stream = io.StringIO()
                stats = pstats.Stats(profiler, stream=stats_stream)
                stats.sort_stats(pstats.SortKey.CUMULATIVE)

                performance_data[module_name] = {
                    "import_time": import_time,
                    "functions": self._get_module_functions(module),
                    "top_functions": self._extract_top_functions(stats, 10),
                }

            except Exception as e:
                print(f"  Warning: Could not profile {module_name}: {e}")
                performance_data[module_name] = {"error": str(e)}

        self.results["runtime_profiling"] = performance_data
        return performance_data

    def _get_module_functions(self, module) -> List[Dict]:
        """Extract functions from a module using inspect"""
        functions = []

        try:
            for name, obj in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    functions.append(
                        {
                            "name": name,
                            "args": len(inspect.signature(obj).parameters),
                            "docstring": bool(obj.__doc__),
                            "file": inspect.getfile(obj)
                            if hasattr(obj, "__file__")
                            else None,
                        }
                    )
        except Exception as e:
            print(f"    Could not inspect module: {e}")

        return functions

    def _extract_top_functions(self, stats: pstats.Stats, limit: int) -> List[Dict]:
        """Extract top functions from profiling stats"""
        top_functions = []

        try:
            stats_list = stats.get_stats_profile().func_profiles
            sorted_stats = sorted(
                stats_list.items(), key=lambda x: x[1].cumtime, reverse=True
            )[:limit]

            for (file, line, func), profile in sorted_stats:
                top_functions.append(
                    {
                        "function": func,
                        "file": os.path.basename(file),
                        "cumtime": profile.cumtime,
                        "calls": profile.ncalls,
                    }
                )

        except Exception as e:
            print(f"    Could not extract function stats: {e}")

        return top_functions

    def analyze_complexity_with_radon(self) -> Dict[str, Any]:
        """Analyze code complexity using radon if available"""
        print("📊 Analyzing code complexity...")

        complexity_data = {"available": False, "results": {}}

        try:
            # Check if radon is available
            result = subprocess.run(
                ["radon", "cc", str(self.project_root), "-j"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                complexity_data["available"] = True
                complexity_data["results"] = json.loads(result.stdout)
                print("  ✅ Radon analysis complete")
            else:
                print("  ⚠️ Radon not available or failed")

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            print("  ⚠️ Radon not available - install with: pip install radon")

        self.results["complexity_analysis"] = complexity_data
        return complexity_data

    def identify_performance_hotspots(self) -> Dict[str, Any]:
        """Identify performance hotspots and optimization opportunities"""
        print("🔥 Identifying performance hotspots...")

        hotspots = {
            "high_complexity_functions": [],
            "frequently_imported": [],
            "duplicate_code": [],
            "optimization_opportunities": [],
        }

        # High complexity functions from static analysis
        if "complexity_hotspots" in self.results["static_analysis"]:
            hotspots["high_complexity_functions"] = sorted(
                self.results["static_analysis"]["complexity_hotspots"],
                key=lambda x: x["complexity"],
                reverse=True,
            )[:10]

        # Most frequently imported modules
        if "import_statements" in self.results["static_analysis"]:
            hotspots["frequently_imported"] = [
                {"module": module, "count": count}
                for module, count in self.results["static_analysis"][
                    "import_statements"
                ].most_common(10)
            ]

        # Duplicate functions
        if "duplicate_functions" in self.results["static_analysis"]:
            hotspots["duplicate_code"] = [
                {"function": name, "files": files, "count": len(files)}
                for name, files in self.results["static_analysis"][
                    "duplicate_functions"
                ].items()
            ]

        self.results["performance_hotspots"] = hotspots
        return hotspots

    def generate_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on analysis"""
        print("💡 Generating optimization recommendations...")

        recommendations = []

        # Based on complexity analysis
        if self.results["performance_hotspots"]["high_complexity_functions"]:
            recommendations.append(
                "COMPLEXITY: Consider refactoring high-complexity functions (complexity > 10) "
                "to improve maintainability and testability"
            )

        # Based on duplicate code
        duplicate_count = len(self.results["performance_hotspots"]["duplicate_code"])
        if duplicate_count > 5:
            recommendations.append(
                f"DUPLICATION: Found {duplicate_count} duplicate function names. "
                "Consider consolidating similar functionality"
            )

        # Based on import patterns
        if self.results["performance_hotspots"]["frequently_imported"]:
            top_import = self.results["performance_hotspots"]["frequently_imported"][0]
            if top_import["count"] > 20:
                recommendations.append(
                    f"IMPORTS: '{top_import['module']}' is imported {top_import['count']} times. "
                    "Consider creating a centralized import or refactoring"
                )

        # Based on runtime profiling
        slow_imports = []
        for module, data in self.results["runtime_profiling"].items():
            if (
                isinstance(data, dict)
                and "import_time" in data
                and data["import_time"] > 1.0
            ):
                slow_imports.append(f"{module} ({data['import_time']:.2f}s)")

        if slow_imports:
            recommendations.append(
                f"PERFORMANCE: Slow module imports detected: {', '.join(slow_imports)}. "
                "Consider lazy loading or optimization"
            )

        self.results["recommendations"] = recommendations
        return recommendations

    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run complete codebase analysis"""
        print("🚀 Starting comprehensive codebase analysis...")
        print("=" * 60)

        # Static analysis
        self.analyze_static_patterns()

        # Runtime profiling
        self.profile_runtime_performance()

        # Complexity analysis
        self.analyze_complexity_with_radon()

        # Hotspot identification
        self.identify_performance_hotspots()

        # Generate recommendations
        self.generate_recommendations()

        print("\n" + "=" * 60)
        print("📋 ANALYSIS SUMMARY")
        print("=" * 60)

        # Print summary
        static = self.results["static_analysis"]
        print("📄 Files analyzed: Python files in codebase")
        print(f"🔧 Functions found: {len(static.get('function_definitions', {}))}")
        print(f"📦 Classes found: {len(static.get('class_definitions', {}))}")
        print(f"📥 Import statements: {len(static.get('import_statements', {}))}")
        print(
            f"🔄 Duplicate functions: {len(self.results['performance_hotspots'].get('duplicate_code', []))}"
        )
        print(
            f"🔥 High complexity functions: {len(self.results['performance_hotspots'].get('high_complexity_functions', []))}"
        )
        print(f"💡 Recommendations: {len(self.results['recommendations'])}")

        return self.results

    def save_results(self, output_file: str = None):
        """Save analysis results to file"""
        if output_file is None:
            output_file = f"reports/codebase_analysis_{int(time.time())}.json"

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\n📁 Analysis results saved to: {output_file}")


def main():
    """Main profiling execution"""
    profiler = CodebaseProfiler()
    results = profiler.run_comprehensive_analysis()

    # Save results
    profiler.save_results()

    # Print top recommendations
    print("\n" + "=" * 60)
    print("🎯 TOP RECOMMENDATIONS")
    print("=" * 60)
    for i, rec in enumerate(results["recommendations"], 1):
        print(f"{i}. {rec}")

    # Print top complexity hotspots
    hotspots = results["performance_hotspots"]["high_complexity_functions"][:5]
    if hotspots:
        print("\n🔥 TOP COMPLEXITY HOTSPOTS:")
        for spot in hotspots:
            print(
                f"  • {spot['function']} in {spot['file']} (complexity: {spot['complexity']})"
            )


if __name__ == "__main__":
    main()
