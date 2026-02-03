#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Usage Profiler for AutoBot
Analyzes memory usage patterns and identifies optimization opportunities
"""

import gc
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    import psutil
except ImportError:
    # Use sys.stderr for early init before logger is available
    sys.stderr.write("Installing psutil for memory profiling...\n")
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import memory_profiler  # noqa: F401 - availability check

    MEMORY_PROFILER_AVAILABLE = True
except ImportError:
    # Use sys.stderr for early init before logger is available
    sys.stderr.write("memory_profiler not available - install with: pip install memory-profiler\n")
    MEMORY_PROFILER_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MemoryProfiler:
    """Comprehensive memory usage profiler for AutoBot codebase"""

    def __init__(self, project_root: Path = None):
        """Initialize memory profiler with project paths and result containers."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.reports_dir = self.project_root / "reports" / "memory"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.profile_results = {
            "timestamp": datetime.now().isoformat(),
            "system_memory": {},
            "process_memory": {},
            "object_analysis": {},
            "file_analysis": {},
            "optimization_opportunities": {},
            "recommendations": [],
        }

    def get_system_memory_info(self) -> Dict[str, Any]:
        """Get system memory information"""
        logger.info("📊 Analyzing system memory usage...")

        virtual_mem = psutil.virtual_memory()
        swap_mem = psutil.swap_memory()

        system_info = {
            "virtual_memory": {
                "total_gb": round(virtual_mem.total / (1024**3), 2),
                "available_gb": round(virtual_mem.available / (1024**3), 2),
                "used_gb": round(virtual_mem.used / (1024**3), 2),
                "percentage": virtual_mem.percent,
                "free_gb": round(virtual_mem.free / (1024**3), 2),
            },
            "swap_memory": {
                "total_gb": round(swap_mem.total / (1024**3), 2),
                "used_gb": round(swap_mem.used / (1024**3), 2),
                "free_gb": round(swap_mem.free / (1024**3), 2),
                "percentage": swap_mem.percent,
            },
        }

        logger.info(
            f"💾 System Memory: {system_info['virtual_memory']['used_gb']}GB used / {system_info['virtual_memory']['total_gb']}GB total ({system_info['virtual_memory']['percentage']:.1f}%)"
        )

        return system_info

    def get_process_memory_info(self) -> Dict[str, Any]:
        """Get current process memory information"""
        logger.info("🔍 Analyzing current process memory usage...")

        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()

        process_info = {
            "rss_mb": round(memory_info.rss / (1024**2), 2),  # Resident Set Size
            "vms_mb": round(memory_info.vms / (1024**2), 2),  # Virtual Memory Size
            "percentage": round(memory_percent, 2),
            "num_threads": process.num_threads(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections()),
        }

        logger.info(
            f"⚡ Process Memory: {process_info['rss_mb']}MB RSS, {process_info['vms_mb']}MB VMS ({process_info['percentage']:.1f}%)"
        )

        return process_info

    def analyze_python_objects(self) -> Dict[str, Any]:
        """Analyze Python objects in memory"""
        logger.info("🐍 Analyzing Python objects in memory...")

        # Force garbage collection to get accurate counts
        gc.collect()

        # Get object counts by type
        object_counts = {}
        total_objects = 0

        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            object_counts[obj_type] = object_counts.get(obj_type, 0) + 1
            total_objects += 1

        # Sort by count (most common first)
        sorted_objects = sorted(object_counts.items(), key=lambda x: x[1], reverse=True)

        # Get top 20 most common object types
        top_objects = dict(sorted_objects[:20])

        object_analysis = {
            "total_objects": total_objects,
            "unique_types": len(object_counts),
            "top_object_types": top_objects,
            "garbage_collector_stats": {
                "generation_0": gc.get_count()[0],
                "generation_1": gc.get_count()[1],
                "generation_2": gc.get_count()[2],
                "total_collections": sum(
                    gc.get_stats()[i]["collections"] for i in range(3)
                ),
            },
        }

        logger.info(
            f"🧮 Python Objects: {total_objects:,} total objects, {len(object_counts)} unique types"
        )

        return object_analysis

    def analyze_large_files(self) -> Dict[str, Any]:
        """Analyze large files that could impact memory usage"""
        logger.info("📁 Analyzing large files...")

        large_files = []
        total_size = 0
        file_count = 0

        # Analyze files in key directories
        directories_to_check = [
            "src/",
            "backend/",
            "data/",
            "reports/",
            "autobot-vue/",
            "logs/",
            "cache/",
            "temp/",
            ".git/",
        ]

        for directory in directories_to_check:
            dir_path = self.project_root / directory
            if not dir_path.exists():
                continue

            for file_path in dir_path.rglob("*"):
                if file_path.is_file():
                    try:
                        size = file_path.stat().st_size
                        total_size += size
                        file_count += 1

                        # Track files larger than 1MB
                        if size > 1024 * 1024:
                            large_files.append(
                                {
                                    "path": str(
                                        file_path.relative_to(self.project_root)
                                    ),
                                    "size_mb": round(size / (1024**2), 2),
                                    "extension": file_path.suffix.lower(),
                                }
                            )
                    except (OSError, PermissionError):
                        continue

        # Sort by size (largest first)
        large_files.sort(key=lambda x: x["size_mb"], reverse=True)

        # Group by file type
        file_types = {}
        for file_info in large_files:
            ext = file_info["extension"] or "no_extension"
            if ext not in file_types:
                file_types[ext] = {"count": 0, "total_size_mb": 0}
            file_types[ext]["count"] += 1
            file_types[ext]["total_size_mb"] += file_info["size_mb"]

        file_analysis = {
            "total_files": file_count,
            "total_size_gb": round(total_size / (1024**3), 2),
            "large_files_count": len(large_files),
            "largest_files": large_files[:20],  # Top 20 largest files
            "file_types": file_types,
        }

        logger.info(
            f"📂 Files: {file_count:,} total files, {file_analysis['total_size_gb']}GB total, {len(large_files)} files >1MB"
        )

        return file_analysis

    def identify_optimization_opportunities(self) -> Dict[str, Any]:
        """Identify memory optimization opportunities"""
        logger.info("🎯 Identifying optimization opportunities...")

        opportunities = {
            "large_files": [],
            "object_patterns": [],
            "system_recommendations": [],
            "code_recommendations": [],
        }

        # Analyze large files
        file_analysis = self.profile_results.get("file_analysis", {})
        largest_files = file_analysis.get("largest_files", [])

        for file_info in largest_files[:10]:
            if file_info["size_mb"] > 10:  # Files larger than 10MB
                opportunities["large_files"].append(
                    {
                        "file": file_info["path"],
                        "size_mb": file_info["size_mb"],
                        "recommendation": self._get_file_recommendation(file_info),
                    }
                )

        # Analyze object patterns
        object_analysis = self.profile_results.get("object_analysis", {})
        top_objects = object_analysis.get("top_object_types", {})

        for obj_type, count in list(top_objects.items())[:5]:
            if count > 1000:  # Objects with high counts
                opportunities["object_patterns"].append(
                    {
                        "type": obj_type,
                        "count": count,
                        "recommendation": self._get_object_recommendation(
                            obj_type, count
                        ),
                    }
                )

        # System-level recommendations
        system_memory = self.profile_results.get("system_memory", {})
        virtual_mem = system_memory.get("virtual_memory", {})

        if virtual_mem.get("percentage", 0) > 80:
            opportunities["system_recommendations"].append(
                "System memory usage is high (>80%) - consider adding more RAM or reducing memory usage"
            )

        process_memory = self.profile_results.get("process_memory", {})
        if process_memory.get("rss_mb", 0) > 500:
            opportunities["system_recommendations"].append(
                f"Process using {process_memory['rss_mb']}MB - consider memory optimization"
            )

        # Code-level recommendations
        opportunities["code_recommendations"].extend(
            [
                "Implement lazy loading for large data structures",
                "Use generators instead of lists for large datasets",
                "Implement caching with TTL to prevent memory leaks",
                "Consider using __slots__ for frequently instantiated classes",
                "Implement proper cleanup in context managers",
            ]
        )

        return opportunities

    def _get_file_recommendation(self, file_info: Dict[str, Any]) -> str:
        """Get recommendation for large file"""
        ext = file_info["extension"]
        size_mb = file_info["size_mb"]

        if ext in [".json", ".log"]:
            return f"Consider file rotation or compression for {size_mb}MB {ext} file"
        elif ext in [".db", ".sqlite", ".sqlite3"]:
            return f"Database file ({size_mb}MB) - consider optimization, indexing, or cleanup"
        elif ext in [".csv", ".txt"]:
            return f"Large data file ({size_mb}MB) - consider streaming or chunked processing"
        elif ext in [".py", ".js", ".ts"]:
            return f"Large code file ({size_mb}MB) - consider refactoring into smaller modules"
        else:
            return f"Large file ({size_mb}MB) - evaluate if necessary or can be compressed/archived"

    def _get_object_recommendation(self, obj_type: str, count: int) -> str:
        """Get recommendation for object type"""
        if obj_type == "dict":
            return f"High dict count ({count:,}) - consider using __slots__ or namedtuples where appropriate"
        elif obj_type == "list":
            return (
                f"High list count ({count:,}) - consider generators for large datasets"
            )
        elif obj_type == "str":
            return f"High string count ({count:,}) - consider string interning or efficient concatenation"
        elif obj_type == "function":
            return f"High function count ({count:,}) - review for unnecessary function creation"
        else:
            return f"High {obj_type} count ({count:,}) - review usage patterns"

    def generate_recommendations(self) -> List[str]:
        """Generate comprehensive optimization recommendations"""
        recommendations = []

        # Memory usage recommendations
        system_memory = self.profile_results.get("system_memory", {})
        process_memory = self.profile_results.get("process_memory", {})

        mem_usage = system_memory.get("virtual_memory", {}).get("percentage", 0)
        if mem_usage > 80:
            recommendations.append(
                "🔴 CRITICAL: System memory usage >80% - immediate action required"
            )
        elif mem_usage > 60:
            recommendations.append(
                "🟡 WARNING: System memory usage >60% - monitor closely"
            )

        # Process memory recommendations
        rss_mb = process_memory.get("rss_mb", 0)
        if rss_mb > 1000:
            recommendations.append(
                "🔴 CRITICAL: Process using >1GB memory - optimization needed"
            )
        elif rss_mb > 500:
            recommendations.append(
                "🟡 WARNING: Process using >500MB memory - consider optimization"
            )

        # Object count recommendations
        object_analysis = self.profile_results.get("object_analysis", {})
        total_objects = object_analysis.get("total_objects", 0)
        if total_objects > 100000:
            recommendations.append(
                "🟡 High Python object count - review object lifecycle management"
            )

        # File size recommendations
        file_analysis = self.profile_results.get("file_analysis", {})
        large_files_count = file_analysis.get("large_files_count", 0)
        if large_files_count > 10:
            recommendations.append(
                "📁 Multiple large files detected - review storage optimization"
            )

        # General recommendations
        recommendations.extend(
            [
                "✅ Implement object pooling for frequently created/destroyed objects",
                "✅ Use weak references where appropriate to prevent memory leaks",
                "✅ Implement proper garbage collection strategies",
                "✅ Consider memory mapping for large file operations",
                "✅ Profile memory usage in production environment",
            ]
        )

        return recommendations

    def save_reports(self):
        """Save memory profiling reports"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        json_report_path = self.reports_dir / f"memory_profile_{timestamp}.json"
        with open(json_report_path, "w") as f:
            json.dump(self.profile_results, f, indent=2)

        # Save markdown summary
        md_report_path = self.reports_dir / f"memory_summary_{timestamp}.md"
        with open(md_report_path, "w") as f:
            f.write(self.generate_markdown_report())

        logger.info("📄 Memory profiling reports saved:")
        logger.info("  JSON: %s", json_report_path)
        logger.info("  Markdown: %s", md_report_path)

    def generate_markdown_report(self) -> str:
        """Generate markdown memory profiling report"""
        system_memory = self.profile_results.get("system_memory", {})
        process_memory = self.profile_results.get("process_memory", {})
        object_analysis = self.profile_results.get("object_analysis", {})
        file_analysis = self.profile_results.get("file_analysis", {})
        recommendations = self.profile_results.get("recommendations", [])

        report = """# 💾 AutoBot Memory Usage Report

**Profile Date:** {self.profile_results["timestamp"]}

## 📊 System Memory Status

### Virtual Memory
- **Total:** {system_memory.get('virtual_memory', {}).get('total_gb', 0)}GB
- **Used:** {system_memory.get('virtual_memory', {}).get('used_gb', 0)}GB ({system_memory.get('virtual_memory', {}).get('percentage', 0):.1f}%)
- **Available:** {system_memory.get('virtual_memory', {}).get('available_gb', 0)}GB
- **Free:** {system_memory.get('virtual_memory', {}).get('free_gb', 0)}GB

### Swap Memory
- **Total:** {system_memory.get('swap_memory', {}).get('total_gb', 0)}GB
- **Used:** {system_memory.get('swap_memory', {}).get('used_gb', 0)}GB ({system_memory.get('swap_memory', {}).get('percentage', 0):.1f}%)

## ⚡ Process Memory Usage

- **RSS (Resident Set Size):** {process_memory.get('rss_mb', 0)}MB
- **VMS (Virtual Memory Size):** {process_memory.get('vms_mb', 0)}MB
- **Memory Percentage:** {process_memory.get('percentage', 0):.2f}% of system
- **Threads:** {process_memory.get('num_threads', 0)}
- **Open Files:** {process_memory.get('open_files', 0)}

## 🐍 Python Objects Analysis

- **Total Objects:** {object_analysis.get('total_objects', 0):,}
- **Unique Types:** {object_analysis.get('unique_types', 0)}

### Top Object Types
"""

        # Issue #622: Use list comprehension + join for O(n) performance
        top_objects = object_analysis.get("top_object_types", {})
        object_lines = [
            f"- **{obj_type}:** {count:,} instances"
            for obj_type, count in list(top_objects.items())[:10]
        ]
        report += "\n".join(object_lines) + "\n" if object_lines else ""

        report += """
### Garbage Collector Stats
- **Generation 0:** {object_analysis.get('garbage_collector_stats', {}).get('generation_0', 0)} objects
- **Generation 1:** {object_analysis.get('garbage_collector_stats', {}).get('generation_1', 0)} objects
- **Generation 2:** {object_analysis.get('garbage_collector_stats', {}).get('generation_2', 0)} objects
- **Total Collections:** {object_analysis.get('garbage_collector_stats', {}).get('total_collections', 0)}

## 📁 File System Analysis

- **Total Files:** {file_analysis.get('total_files', 0):,}
- **Total Size:** {file_analysis.get('total_size_gb', 0)}GB
- **Large Files (>1MB):** {file_analysis.get('large_files_count', 0)}

### Largest Files
"""

        # Issue #622: Use list comprehension + join for O(n) performance
        largest_files = file_analysis.get("largest_files", [])
        file_lines = [
            f"- **{file_info['path']}:** {file_info['size_mb']}MB"
            for file_info in largest_files[:10]
        ]
        report += "\n".join(file_lines) + "\n" if file_lines else ""

        report += "\n## 🎯 Optimization Opportunities\n\n"

        opportunities = self.profile_results.get("optimization_opportunities", {})

        # Issue #622: Use list comprehension + join for O(n) performance
        # Large files section
        large_file_opps = opportunities.get("large_files", [])
        if large_file_opps:
            report += "### Large Files\n"
            large_file_lines = [
                f"- **{opp['file']}** ({opp['size_mb']}MB): {opp['recommendation']}"
                for opp in large_file_opps[:5]
            ]
            report += "\n".join(large_file_lines) + "\n\n"

        # Object patterns section
        object_opps = opportunities.get("object_patterns", [])
        if object_opps:
            report += "### Object Patterns\n"
            object_pattern_lines = [
                f"- **{opp['type']}** ({opp['count']:,} instances): {opp['recommendation']}"
                for opp in object_opps
            ]
            report += "\n".join(object_pattern_lines) + "\n\n"

        report += "## 📋 Recommendations\n\n"
        recommendation_lines = [f"1. {rec}" for rec in recommendations]
        report += "\n".join(recommendation_lines) + "\n" if recommendation_lines else ""

        if not recommendations:
            report += "✅ No immediate memory optimization actions required\n"

        return report

    def run_full_profile(self):
        """Run complete memory profiling analysis"""
        logger.info("🚀 Starting comprehensive memory profiling...")

        self.profile_results["system_memory"] = self.get_system_memory_info()
        self.profile_results["process_memory"] = self.get_process_memory_info()
        self.profile_results["object_analysis"] = self.analyze_python_objects()
        self.profile_results["file_analysis"] = self.analyze_large_files()
        self.profile_results[
            "optimization_opportunities"
        ] = self.identify_optimization_opportunities()
        self.profile_results["recommendations"] = self.generate_recommendations()

        self.save_reports()

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("💾 MEMORY PROFILING SUMMARY")
        logger.info("=" * 60)

        system_mem = self.profile_results["system_memory"]["virtual_memory"]
        process_mem = self.profile_results["process_memory"]

        logger.info(
            f"🖥️  System Memory: {system_mem['used_gb']}GB / {system_mem['total_gb']}GB ({system_mem['percentage']:.1f}%)"
        )
        logger.info(
            f"⚡ Process Memory: {process_mem['rss_mb']}MB RSS ({process_mem['percentage']:.1f}%)"
        )
        logger.info(
            f"🐍 Python Objects: {self.profile_results['object_analysis']['total_objects']:,} total"
        )
        logger.info(
            f"📁 Large Files: {self.profile_results['file_analysis']['large_files_count']} files >1MB"
        )

        recommendations = self.profile_results["recommendations"]
        critical_recs = [r for r in recommendations if "🔴 CRITICAL" in r]
        warning_recs = [r for r in recommendations if "🟡 WARNING" in r]

        if critical_recs:
            logger.info("\n🔴 CRITICAL ISSUES: %s", len(critical_recs))
            for rec in critical_recs:
                logger.info("  - %s", rec)

        if warning_recs:
            logger.info("\n🟡 WARNINGS: %s", len(warning_recs))
            for rec in warning_recs:
                logger.info("  - %s", rec)

        logger.info("=" * 60)

        return self.profile_results


def main():
    """Main entry point"""
    profiler = MemoryProfiler()
    results = profiler.run_full_profile()

    # Exit with warning code if critical issues found
    critical_issues = [
        r for r in results.get("recommendations", []) if "🔴 CRITICAL" in r
    ]
    sys.exit(1 if critical_issues else 0)


if __name__ == "__main__":
    main()
