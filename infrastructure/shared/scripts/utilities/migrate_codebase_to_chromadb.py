#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migrate Codebase Analytics from Redis DB 11 to ChromaDB

This script migrates all codebase analytics data (functions, classes, problems, etc.)
from Redis DB 11 to a new ChromaDB collection 'autobot_code'.
"""

import json
import logging
import sys
from pathlib import Path

import chromadb
import redis

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from constants.network_constants import NetworkConstants

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CodebaseChromaDBMigration:
    """Migrate codebase analytics from Redis to ChromaDB"""

    def __init__(self):
        """Initialize migration tool with empty client references and stats."""
        self.redis_client = None
        self.chroma_client = None
        self.code_collection = None
        self.migration_stats = {
            "functions": 0,
            "classes": 0,
            "problems": 0,
            "stats": 0,
            "total_migrated": 0,
            "errors": 0,
        }

    def connect_redis(self):
        """Connect to Redis DB 11 (codebase analytics)"""
        try:
            self.redis_client = redis.Redis(
                host=str(NetworkConstants.REDIS_VM_IP),
                port=NetworkConstants.REDIS_PORT,
                db=11,  # Codebase analytics database
                decode_responses=True,
                socket_timeout=30,
            )
            # Test connection
            self.redis_client.ping()
            logger.info("✅ Connected to Redis DB 11")
            return True
        except Exception as e:
            logger.error("❌ Redis connection failed: %s", e)
            return False

    def connect_chromadb(self):
        """Connect to ChromaDB and create/get autobot_code collection"""
        try:
            chroma_path = project_root / "data" / "chromadb"
            chroma_path.mkdir(parents=True, exist_ok=True)

            self.chroma_client = chromadb.PersistentClient(path=str(chroma_path))

            # Create or get the code collection
            self.code_collection = self.chroma_client.get_or_create_collection(
                name="autobot_code",
                metadata={
                    "description": "Codebase analytics: functions, classes, duplicates"
                },
            )

            logger.info(
                "✅ ChromaDB collection 'autobot_code' ready (%s existing items)",
                self.code_collection.count(),
            )
            return True
        except Exception as e:
            logger.error("❌ ChromaDB connection failed: %s", e)
            return False

    def migrate_functions(self):
        """Migrate function declarations from Redis to ChromaDB"""
        try:
            logger.info("📦 Migrating functions...")

            # Get all function keys
            function_keys = list(
                self.redis_client.scan_iter(match="codebase:functions:*")
            )
            logger.info("Found %s functions", len(function_keys))

            # Prepare batch data
            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            for key in function_keys:
                try:
                    function_data = self.redis_client.hgetall(key)
                    if not function_data:
                        continue

                    function_name = key.replace("codebase:functions:", "")

                    # Create document text for vectorization
                    doc_text = """
Function: {function_name}
File: {function_data.get('file_path', 'unknown')}
Lines: {function_data.get('start_line', 'unknown')}-{function_data.get('end_line', 'unknown')}
Complexity: {function_data.get('complexity', 'unknown')}
Parameters: {function_data.get('parameters', 'unknown')}
Docstring: {function_data.get('docstring', 'No documentation')}
                    """.strip()

                    batch_ids.append(f"function_{function_name}")
                    batch_documents.append(doc_text)
                    batch_metadatas.append(
                        {
                            "type": "function",
                            "name": function_name,
                            "file_path": function_data.get("file_path", ""),
                            "start_line": function_data.get("start_line", ""),
                            "end_line": function_data.get("end_line", ""),
                            "complexity": function_data.get("complexity", ""),
                            "language": function_data.get("language", "python"),
                            "parameters": function_data.get("parameters", ""),
                        }
                    )

                except Exception as e:
                    logger.warning("Error processing %s: %s", key, e)
                    self.migration_stats["errors"] += 1

            # Add batch to ChromaDB
            if batch_ids:
                self.code_collection.add(
                    ids=batch_ids, documents=batch_documents, metadatas=batch_metadatas
                )
                self.migration_stats["functions"] = len(batch_ids)
                logger.info("✅ Migrated %s functions to ChromaDB", len(batch_ids))

        except Exception as e:
            logger.error("❌ Function migration failed: %s", e)

    def migrate_classes(self):
        """Migrate class declarations from Redis to ChromaDB"""
        try:
            logger.info("📦 Migrating classes...")

            # Get all class keys
            class_keys = list(self.redis_client.scan_iter(match="codebase:classes:*"))
            logger.info("Found %s classes", len(class_keys))

            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            for key in class_keys:
                try:
                    class_data = self.redis_client.hgetall(key)
                    if not class_data:
                        continue

                    class_name = key.replace("codebase:classes:", "")

                    doc_text = """
Class: {class_name}
File: {class_data.get('file_path', 'unknown')}
Lines: {class_data.get('start_line', 'unknown')}-{class_data.get('end_line', 'unknown')}
Methods: {class_data.get('methods', 'unknown')}
Base Classes: {class_data.get('bases', 'None')}
Docstring: {class_data.get('docstring', 'No documentation')}
                    """.strip()

                    batch_ids.append(f"class_{class_name}")
                    batch_documents.append(doc_text)
                    batch_metadatas.append(
                        {
                            "type": "class",
                            "name": class_name,
                            "file_path": class_data.get("file_path", ""),
                            "start_line": class_data.get("start_line", ""),
                            "end_line": class_data.get("end_line", ""),
                            "methods": class_data.get("methods", ""),
                            "language": class_data.get("language", "python"),
                            "bases": class_data.get("bases", ""),
                        }
                    )

                except Exception as e:
                    logger.warning("Error processing %s: %s", key, e)
                    self.migration_stats["errors"] += 1

            if batch_ids:
                self.code_collection.add(
                    ids=batch_ids, documents=batch_documents, metadatas=batch_metadatas
                )
                self.migration_stats["classes"] = len(batch_ids)
                logger.info("✅ Migrated %s classes to ChromaDB", len(batch_ids))

        except Exception as e:
            logger.error("❌ Class migration failed: %s", e)

    def migrate_problems(self):
        """Migrate code problems from Redis to ChromaDB"""
        try:
            logger.info("📦 Migrating problems...")

            # Get problems data
            problems_key = "codebase:problems"
            problems_data = self.redis_client.get(problems_key)

            if not problems_data:
                logger.info("No problems data found")
                return

            problems = json.loads(problems_data)
            logger.info("Found %s problems", len(problems))

            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            for idx, problem in enumerate(problems):
                try:
                    doc_text = """
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'unknown')}
File: {problem.get('file_path', 'unknown')}
Line: {problem.get('line_number', 'unknown')}
Description: {problem.get('description', 'No description')}
Suggestion: {problem.get('suggestion', 'No suggestion')}
                    """.strip()

                    batch_ids.append(f"problem_{idx}")
                    batch_documents.append(doc_text)
                    batch_metadatas.append(
                        {
                            "type": "problem",
                            "problem_type": problem.get("type", ""),
                            "severity": problem.get("severity", ""),
                            "file_path": problem.get("file_path", ""),
                            "line_number": str(problem.get("line_number", "")),
                            "description": problem.get("description", ""),
                            "suggestion": problem.get("suggestion", ""),
                        }
                    )

                except Exception as e:
                    logger.warning("Error processing problem %s: %s", idx, e)
                    self.migration_stats["errors"] += 1

            if batch_ids:
                self.code_collection.add(
                    ids=batch_ids, documents=batch_documents, metadatas=batch_metadatas
                )
                self.migration_stats["problems"] = len(batch_ids)
                logger.info("✅ Migrated %s problems to ChromaDB", len(batch_ids))

        except Exception as e:
            logger.error("❌ Problems migration failed: %s", e)

    def migrate_stats(self):
        """Migrate codebase statistics to ChromaDB"""
        try:
            logger.info("📦 Migrating statistics...")

            stats_key = "codebase:stats"
            stats_data = self.redis_client.get(stats_key)

            if not stats_data:
                logger.info("No stats data found")
                return

            stats = json.loads(stats_data)

            doc_text = """
Codebase Statistics:
Total Files: {stats.get('total_files', 0)}
Total Lines: {stats.get('total_lines', 0)}
Python Files: {stats.get('python_files', 0)}
JavaScript Files: {stats.get('javascript_files', 0)}
Vue Files: {stats.get('vue_files', 0)}
Total Functions: {stats.get('total_functions', 0)}
Total Classes: {stats.get('total_classes', 0)}
Last Indexed: {stats.get('last_indexed', 'unknown')}
            """.strip()

            self.code_collection.add(
                ids=["codebase_stats"],
                documents=[doc_text],
                metadatas=[{"type": "stats", **{k: str(v) for k, v in stats.items()}}],
            )

            self.migration_stats["stats"] = 1
            logger.info("✅ Migrated codebase statistics to ChromaDB")

        except Exception as e:
            logger.error("❌ Stats migration failed: %s", e)

    def run_migration(self):
        """Execute full migration"""
        logger.info("=" * 60)
        logger.info("Starting Codebase Analytics Migration: Redis → ChromaDB")
        logger.info("=" * 60)

        # Connect to both databases
        if not self.connect_redis():
            logger.error("Cannot proceed without Redis connection")
            return False

        if not self.connect_chromadb():
            logger.error("Cannot proceed without ChromaDB connection")
            return False

        # Get Redis database size
        redis_keys = self.redis_client.dbsize()
        logger.info("Redis DB 11 has %s keys", redis_keys)

        # Run migrations
        self.migrate_functions()
        self.migrate_classes()
        self.migrate_problems()
        self.migrate_stats()

        # Calculate total
        self.migration_stats["total_migrated"] = (
            self.migration_stats["functions"]
            + self.migration_stats["classes"]
            + self.migration_stats["problems"]
            + self.migration_stats["stats"]
        )

        # Print summary
        logger.info("=" * 60)
        logger.info("Migration Summary:")
        logger.info("  Functions:  %s", self.migration_stats["functions"])
        logger.info("  Classes:    %s", self.migration_stats["classes"])
        logger.info("  Problems:   %s", self.migration_stats["problems"])
        logger.info("  Stats:      %s", self.migration_stats["stats"])
        logger.info("  ---")
        logger.info("  Total:      %s", self.migration_stats["total_migrated"])
        logger.info("  Errors:     %s", self.migration_stats["errors"])
        logger.info("  ChromaDB Collection Size: %s", self.code_collection.count())
        logger.info("=" * 60)

        return True


def main():
    """Main migration entry point"""
    migrator = CodebaseChromaDBMigration()
    success = migrator.run_migration()

    if success:
        logger.info("✅ Migration completed successfully!")
        return 0
    else:
        logger.error("❌ Migration failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
