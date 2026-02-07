#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Apply Memory Optimizations Script
Applies memory optimization improvements to the AutoBot codebase
"""

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.memory_optimization import (
    MemoryOptimizedLogging,
    get_memory_monitor,
    optimize_memory_usage,
)

logger = logging.getLogger(__name__)


class MemoryOptimizationApplier:
    """Applies memory optimizations to AutoBot codebase"""

    def __init__(self, project_root: Path = None):
        """Initialize memory optimization applier with project paths."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.logs_dir = self.project_root / "logs"
        self.backup_dir = self.project_root / "logs" / "backup"
        self.optimizations_applied = []

    def backup_large_log_files(self):
        """Backup and rotate large log files"""
        logger.info("🔄 Backing up and rotating large log files...")

        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        large_files_handled = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Check for large log files (>10MB)
        for log_file in self.logs_dir.glob("*.log"):
            if log_file.stat().st_size > 10 * 1024 * 1024:  # 10MB threshold
                size_mb = log_file.stat().st_size / (1024**2)

                # Create backup
                backup_file = self.backup_dir / f"{log_file.stem}_{timestamp}.log.bak"
                shutil.copy2(log_file, backup_file)

                # Truncate original file (keep last 1000 lines)
                self._truncate_log_file(log_file, keep_lines=1000)

                large_files_handled.append(
                    {
                        "file": str(log_file),
                        "size_mb": round(size_mb, 2),
                        "backup": str(backup_file),
                    }
                )

                logger.info(
                    f"📦 Backed up {log_file.name} ({size_mb:.1f}MB) -> {backup_file.name}"
                )

        self.optimizations_applied.append(
            {
                "type": "log_rotation",
                "description": "Backed up and rotated large log files",
                "files_handled": len(large_files_handled),
                "details": large_files_handled,
            }
        )

        return large_files_handled

    def _truncate_log_file(self, log_file: Path, keep_lines: int = 1000):
        """Truncate log file keeping only the last N lines"""
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if len(lines) > keep_lines:
                # Keep header comment if exists
                header_lines = []
                for i, line in enumerate(lines[:10]):
                    if line.strip().startswith("#") or line.strip().startswith("//"):
                        header_lines.append(line)
                        i + 1
                    else:
                        break

                # Keep header + last N lines
                truncated_lines = header_lines + lines[-keep_lines:]

                with open(log_file, "w", encoding="utf-8") as f:
                    f.writelines(truncated_lines)

                logger.info(
                    f"✂️  Truncated {log_file.name}: {len(lines)} -> {len(truncated_lines)} lines"
                )

        except Exception as e:
            logger.warning("Failed to truncate %s: %s", log_file, e)

    def setup_rotating_loggers(self):
        """Set up rotating loggers for main log files"""
        logger.info("🔄 Setting up rotating loggers...")

        rotating_loggers = []

        # Main backend logger
        backend_logger = MemoryOptimizedLogging.setup_rotating_logger(
            name="autobot_backend",
            log_file=self.logs_dir / "autobot_backend.log",
            max_bytes=20 * 1024 * 1024,  # 20MB per file
            backup_count=5,  # Keep 5 backup files
            console_output=True,
        )
        rotating_loggers.append("autobot_backend")

        # LLM usage logger
        llm_logger = MemoryOptimizedLogging.setup_rotating_logger(
            name="llm_usage",
            log_file=self.logs_dir / "llm_usage.log",
            max_bytes=10 * 1024 * 1024,  # 10MB per file
            backup_count=3,  # Keep 3 backup files
            console_output=False,  # Don't spam console with LLM logs
        )
        rotating_loggers.append("llm_usage")

        # Agent logger
        agent_logger = MemoryOptimizedLogging.setup_rotating_logger(
            name="autobot_agent",
            log_file=self.logs_dir / "autobot.log",
            max_bytes=15 * 1024 * 1024,  # 15MB per file
            backup_count=3,
            console_output=True,
        )
        rotating_loggers.append("autobot_agent")

        self.optimizations_applied.append(
            {
                "type": "rotating_loggers",
                "description": "Set up rotating file handlers for main loggers",
                "loggers_configured": len(rotating_loggers),
                "details": rotating_loggers,
            }
        )

        return rotating_loggers

    def optimize_large_data_files(self):
        """Optimize large data files in the project"""
        logger.info("🗂️  Analyzing large data files...")

        large_files_optimized = []

        # Check data directory
        data_dir = self.project_root / "data"
        if data_dir.exists():
            for data_file in data_dir.rglob("*"):
                if (
                    data_file.is_file() and data_file.stat().st_size > 5 * 1024 * 1024
                ):  # >5MB
                    size_mb = data_file.stat().st_size / (1024**2)
                    optimization_applied = False

                    # SQLite database optimization
                    if data_file.suffix.lower() in [".db", ".sqlite", ".sqlite3"]:
                        self._optimize_sqlite_database(data_file)
                        optimization_applied = True

                    # JSON file compression opportunity
                    elif data_file.suffix.lower() == ".json":
                        compressed_size = self._analyze_json_compression(data_file)
                        if (
                            compressed_size and compressed_size < size_mb * 0.7
                        ):  # >30% compression
                            large_files_optimized.append(
                                {
                                    "file": str(
                                        data_file.relative_to(self.project_root)
                                    ),
                                    "size_mb": round(size_mb, 2),
                                    "optimization": f"JSON compression could save ~{round(size_mb - compressed_size, 2)}MB",
                                    "recommendation": "Consider compressing JSON data or using binary format",
                                }
                            )
                            optimization_applied = True

                    # Binary data files
                    elif data_file.suffix.lower() in [".bin", ".dat"]:
                        large_files_optimized.append(
                            {
                                "file": str(data_file.relative_to(self.project_root)),
                                "size_mb": round(size_mb, 2),
                                "optimization": "Binary data file",
                                "recommendation": "Consider memory mapping for large binary files",
                            }
                        )
                        optimization_applied = True

                    if not optimization_applied:
                        large_files_optimized.append(
                            {
                                "file": str(data_file.relative_to(self.project_root)),
                                "size_mb": round(size_mb, 2),
                                "optimization": "Large file detected",
                                "recommendation": "Review if file is necessary or can be optimized",
                            }
                        )

        self.optimizations_applied.append(
            {
                "type": "data_file_analysis",
                "description": "Analyzed large data files for optimization",
                "files_analyzed": len(large_files_optimized),
                "details": large_files_optimized,
            }
        )

        return large_files_optimized

    def _optimize_sqlite_database(self, db_file: Path):
        """Optimize SQLite database file"""
        try:
            import sqlite3

            logger.info("🗄️  Optimizing SQLite database: %s", db_file.name)

            # Create backup first
            backup_file = db_file.with_suffix(f"{db_file.suffix}.backup")
            shutil.copy2(db_file, backup_file)

            # Optimize database
            with sqlite3.connect(db_file) as conn:
                # Vacuum to defragment and reclaim space
                conn.execute("VACUUM;")

                # Analyze to update statistics
                conn.execute("ANALYZE;")

                # Set optimal pragmas
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA cache_size=10000;")
                conn.execute("PRAGMA temp_store=MEMORY;")

                conn.commit()

            # Check size reduction
            original_size = backup_file.stat().st_size
            new_size = db_file.stat().st_size

            if new_size < original_size:
                saved_mb = (original_size - new_size) / (1024**2)
                logger.info("💾 Database optimization saved %.1fMB", saved_mb)
                # Remove backup if successful
                backup_file.unlink()
            else:
                logger.info("Database was already optimized")
                backup_file.unlink()

        except Exception as e:
            logger.warning("Failed to optimize SQLite database %s: %s", db_file, e)

    def _analyze_json_compression(self, json_file: Path) -> float:
        """Analyze potential JSON compression savings"""
        try:
            import gzip
            import json
            from io import BytesIO

            # Read and recompress JSON to estimate savings
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Compress in memory
            json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")

            buffer = BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
                gz.write(json_bytes)

            compressed_size_mb = len(buffer.getvalue()) / (1024**2)
            return compressed_size_mb

        except Exception as e:
            logger.debug("Could not analyze compression for %s: %s", json_file, e)
            return 0.0

    def apply_global_memory_optimizations(self):
        """Apply global memory optimizations"""
        logger.info("🎯 Applying global memory optimizations...")

        # Run garbage collection and optimization
        gc_results = optimize_memory_usage()

        # Set up memory monitoring
        memory_monitor = get_memory_monitor(threshold_mb=400.0)  # 400MB threshold
        current_memory = memory_monitor.check_memory()

        self.optimizations_applied.append(
            {
                "type": "global_optimization",
                "description": "Applied global memory optimizations",
                "garbage_collected": gc_results["objects_collected"],
                "current_memory_mb": current_memory["rss_mb"],
                "peak_memory_mb": current_memory["peak_mb"],
                "details": gc_results,
            }
        )

        return {"gc_results": gc_results, "memory_status": current_memory}

    def generate_optimization_report(self):
        """Generate comprehensive optimization report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "optimizations_applied": self.optimizations_applied,
            "summary": {
                "total_optimizations": len(self.optimizations_applied),
                "categories": list(
                    set(opt["type"] for opt in self.optimizations_applied)
                ),
            },
            "recommendations": [
                "Monitor memory usage regularly using the memory profiler",
                "Set up automated log rotation in production",
                "Consider implementing object pooling for frequently used objects",
                "Use memory mapping for large read-only data files",
                "Implement lazy loading for large data structures",
                "Regular database maintenance (VACUUM, ANALYZE) for SQLite files",
            ],
        }

        return report

    def save_optimization_report(self, report: dict):
        """Save optimization report"""
        reports_dir = self.project_root / "reports" / "memory"
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        import json

        json_file = reports_dir / f"memory_optimizations_applied_{timestamp}.json"
        with open(json_file, "w") as f:
            json.dump(report, f, indent=2)

        # Save markdown summary
        md_file = reports_dir / f"memory_optimizations_summary_{timestamp}.md"
        with open(md_file, "w") as f:
            f.write(self._generate_markdown_report(report))

        logger.info("📄 Optimization reports saved:")
        logger.info("  JSON: %s", json_file)
        logger.info("  Markdown: %s", md_file)

        return {"json": json_file, "markdown": md_file}

    def _generate_markdown_report(self, report: dict) -> str:
        """Generate markdown optimization report"""
        optimizations = report["optimizations_applied"]

        markdown = """# 🔧 AutoBot Memory Optimizations Applied

**Date:** {report["timestamp"]}
**Total Optimizations:** {report["summary"]["total_optimizations"]}

## 📊 Optimizations Summary

"""

        for opt in optimizations:
            markdown += """### {opt["type"].replace("_", " ").title()}

**Description:** {opt["description"]}

"""
            # Add specific details based on optimization type
            if opt["type"] == "log_rotation":
                markdown += f"- **Files handled:** {opt['files_handled']}\n"
                for file_info in opt["details"]:
                    markdown += f"  - `{file_info['file']}` ({file_info['size_mb']}MB) → `{file_info['backup']}`\n"

            elif opt["type"] == "rotating_loggers":
                markdown += f"- **Loggers configured:** {opt['loggers_configured']}\n"
                for logger_name in opt["details"]:
                    markdown += f"  - `{logger_name}` with rotation enabled\n"

            elif opt["type"] == "data_file_analysis":
                markdown += f"- **Files analyzed:** {opt['files_analyzed']}\n"
                for file_info in opt["details"][:5]:  # Show top 5
                    markdown += f"  - `{file_info['file']}` ({file_info['size_mb']}MB): {file_info['optimization']}\n"

            elif opt["type"] == "global_optimization":
                markdown += f"- **Objects collected:** {opt['garbage_collected']:,}\n"
                markdown += f"- **Current memory:** {opt['current_memory_mb']:.1f}MB\n"
                markdown += f"- **Peak memory:** {opt['peak_memory_mb']:.1f}MB\n"

            markdown += "\n"

        markdown += """## 📋 Recommendations

"""
        for i, rec in enumerate(report["recommendations"], 1):
            markdown += f"{i}. {rec}\n"

        markdown += """
## 🎯 Next Steps

1. **Monitor Performance**: Use `python scripts/memory_profiler.py` to track memory usage
2. **Production Setup**: Implement automated log rotation in production environment
3. **Regular Maintenance**: Schedule periodic database optimization and cleanup
4. **Code Optimization**: Implement memory-efficient patterns in new code

---
**Generated by AutoBot Memory Optimization System**
"""

        return markdown

    def run_all_optimizations(self):
        """Run all memory optimizations"""
        logger.info("🚀 Starting comprehensive memory optimization...")

        try:
            # 1. Backup and rotate large log files
            self.backup_large_log_files()

            # 2. Set up rotating loggers
            self.setup_rotating_loggers()

            # 3. Optimize large data files
            self.optimize_large_data_files()

            # 4. Apply global memory optimizations
            self.apply_global_memory_optimizations()

            # 5. Generate and save report
            report = self.generate_optimization_report()
            self.save_optimization_report(report)

            logger.info("✅ All memory optimizations completed successfully!")

            # Summary
            logger.info("\n" + "=" * 60)
            logger.info("🎯 MEMORY OPTIMIZATION SUMMARY")
            logger.info("=" * 60)
            logger.info(
                f"📊 Total optimizations applied: {len(self.optimizations_applied)}"
            )

            for opt in self.optimizations_applied:
                logger.info("✓ %s", opt["description"])

            logger.info("=" * 60)

            return report

        except Exception as e:
            logger.error("Memory optimization failed: %s", e)
            raise


def main():
    """Main entry point"""
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        optimizer = MemoryOptimizationApplier()
        optimizer.run_all_optimizations()

        # Exit successfully
        return 0

    except Exception as e:
        logger.error("Memory optimization failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
