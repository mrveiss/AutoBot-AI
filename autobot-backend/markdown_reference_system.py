# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Markdown Reference System for AutoBot Phase 7
Integrates markdown documents with SQLite database for enhanced knowledge management
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory import EnhancedMemoryManager

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for markdown parsing
_WORD_RE = re.compile(r"\b\w+\b")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_TAGS_RE = re.compile(r"tags:\s*\[(.*?)\]")
_INLINE_TAGS_RE = re.compile(r"#(\w+)")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_MD_FILE_MENTION_RE = re.compile(r"(?:^|[\s`])([a-zA-Z0-9_/-]+\.md)(?=$|[\s`])")


class MarkdownReferenceSystem:
    """
    Advanced markdown reference system that tracks relationships between
    markdown documents and task execution history within SQLite
    """

    def __init__(
        self,
        memory_manager: Optional[EnhancedMemoryManager] = None,
        docs_root: str = "docs",
        knowledge_root: str = "data/system_knowledge",
    ):
        """Initialize markdown reference system with document tracking tables."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.docs_root = Path(docs_root)
        self.knowledge_root = Path(knowledge_root)

        # Initialize additional tables for markdown management
        self._init_markdown_tables()

        logger.info("Markdown Reference System initialized")
        logger.info("Docs root: %s", self.docs_root)
        logger.info("Knowledge root: %s", self.knowledge_root)

    def _create_documents_table(self, conn: sqlite3.Connection) -> None:
        """Issue #665: Extracted from _init_markdown_tables to reduce function length."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markdown_documents (
                file_path TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                directory TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                word_count INTEGER,
                created_at TIMESTAMP NOT NULL,
                last_modified TIMESTAMP NOT NULL,
                last_scanned TIMESTAMP NOT NULL,
                document_type TEXT,
                tags TEXT,
                metadata_json TEXT
            )
        """
        )

    def _create_cross_references_table(self, conn: sqlite3.Connection) -> None:
        """Issue #665: Extracted from _init_markdown_tables to reduce function length."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markdown_cross_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                target_file TEXT NOT NULL,
                reference_type TEXT NOT NULL,
                context_text TEXT,
                line_number INTEGER,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (source_file) REFERENCES markdown_documents(file_path),
                FOREIGN KEY (target_file) REFERENCES markdown_documents(file_path)
            )
        """
        )

    def _create_sections_table(self, conn: sqlite3.Connection) -> None:
        """Issue #665: Extracted from _init_markdown_tables to reduce function length."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markdown_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                section_title TEXT NOT NULL,
                section_level INTEGER NOT NULL,
                content_text TEXT,
                content_hash TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (file_path) REFERENCES markdown_documents(file_path)
            )
        """
        )

    def _create_markdown_indexes(self, conn: sqlite3.Connection) -> None:
        """Issue #665: Extracted from _init_markdown_tables to reduce function length."""
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_markdown_hash ON markdown_documents(content_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_markdown_type ON markdown_documents(document_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cross_ref_source ON markdown_cross_references(source_file)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sections_file ON markdown_sections(file_path)"
        )

    def _init_markdown_tables(self) -> None:
        """Initialize additional SQLite tables for markdown management"""
        with sqlite3.connect(self.memory_manager.db_path) as conn:
            self._create_documents_table(conn)
            self._create_cross_references_table(conn)
            self._create_sections_table(conn)
            self._create_markdown_indexes(conn)
            conn.commit()

    def scan_markdown_directory(
        self, directory: Path, document_type: str = "documentation"
    ) -> Dict[str, Any]:
        """Scan directory for markdown files and update database"""
        if not directory.exists():
            logger.warning("Directory does not exist: %s", directory)
            return {"error": "Directory not found"}

        scanned_files = 0
        updated_files = 0
        new_files = 0
        errors = []

        for md_file in directory.rglob("*.md"):
            try:
                result = self._process_markdown_file(md_file, document_type)
                scanned_files += 1

                if result["is_new"]:
                    new_files += 1
                elif result["is_updated"]:
                    updated_files += 1

            except Exception as e:
                error_msg = f"Error processing {md_file}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Update cross-references
        self._update_cross_references()

        return {
            "scanned_files": scanned_files,
            "new_files": new_files,
            "updated_files": updated_files,
            "errors": errors,
            "directory": str(directory),
        }

    def _get_file_metadata(self, file_path: Path, content: str) -> Dict[str, Any]:
        """Issue #665: Extracted from _process_markdown_file to reduce function length.

        Calculate hash, stats, word count and tags for a markdown file.
        """
        stat = file_path.stat()
        return {
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            "created_at": datetime.fromtimestamp(stat.st_ctime),
            "last_modified": datetime.fromtimestamp(stat.st_mtime),
            "word_count": len(_WORD_RE.findall(content)),
            "tags": self._extract_tags(content),
        }

    def _check_document_status(
        self, conn: sqlite3.Connection, file_path: Path, content_hash: str
    ) -> tuple[bool, bool]:
        """Issue #665: Extracted from _process_markdown_file to reduce function length.

        Check if document exists and whether it has been updated.
        Returns (is_new, is_updated) tuple.
        """
        cursor = conn.execute(
            "SELECT content_hash FROM markdown_documents WHERE file_path = ?",
            (str(file_path),),
        )
        existing_record = cursor.fetchone()
        is_new = existing_record is None
        is_updated = bool(existing_record and existing_record[0] != content_hash)
        return is_new, is_updated

    def _upsert_document_record(
        self,
        conn: sqlite3.Connection,
        file_path: Path,
        document_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Issue #665: Extracted from _process_markdown_file to reduce function length.

        Insert or update the document record in the database.
        """
        conn.execute(
            """
            INSERT OR REPLACE INTO markdown_documents
            (file_path, file_name, directory, content_hash, word_count,
             created_at, last_modified, last_scanned, document_type, tags, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(file_path),
                file_path.name,
                str(file_path.parent),
                metadata["content_hash"],
                metadata["word_count"],
                metadata["created_at"],
                metadata["last_modified"],
                datetime.now(),
                document_type,
                json.dumps(metadata["tags"]),
                json.dumps({"encoding": "utf-8"}),
            ),
        )

    def _process_markdown_file(
        self, file_path: Path, document_type: str
    ) -> Dict[str, Any]:
        """Process individual markdown file and update database"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        metadata = self._get_file_metadata(file_path, content)

        with sqlite3.connect(self.memory_manager.db_path) as conn:
            is_new, is_updated = self._check_document_status(
                conn, file_path, metadata["content_hash"]
            )
            self._upsert_document_record(conn, file_path, document_type, metadata)

            if is_new or is_updated:
                self._process_markdown_sections(conn, file_path, content)
            conn.commit()

        status = "new" if is_new else "updated" if is_updated else "unchanged"
        logger.debug("Processed markdown: %s (%s)", file_path.name, status)

        return {
            "file_path": str(file_path),
            "content_hash": metadata["content_hash"],
            "is_new": is_new,
            "is_updated": is_updated,
            "word_count": metadata["word_count"],
        }

    def _extract_tags(self, content: str) -> List[str]:
        """Extract tags from markdown content using pre-compiled patterns (Issue #380)"""
        tags = set()

        # Look for YAML frontmatter tags
        frontmatter_match = _FRONTMATTER_RE.match(content)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            # Simple tag extraction from YAML
            tag_matches = _TAGS_RE.findall(frontmatter)
            for tag_list in tag_matches:
                for tag in tag_list.split(","):
                    tags.add(tag.strip().strip("\"'"))

        # Look for inline tags (e.g., #tag)
        inline_tags = _INLINE_TAGS_RE.findall(content)
        tags.update(inline_tags)

        return sorted(list(tags))

    def _finalize_section(
        self, section: Dict[str, Any], lines: List[str], end_line: int
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from _process_markdown_sections to reduce function length.

        Finalize a section by setting end_line, content_text, and content_hash.
        """
        section["end_line"] = end_line
        section["content_text"] = "\n".join(
            lines[section["start_line"] - 1 : section["end_line"]]
        )
        section["content_hash"] = hashlib.sha256(
            section["content_text"].encode()
        ).hexdigest()
        return section

    def _insert_sections_to_db(
        self, conn: sqlite3.Connection, sections: List[Dict[str, Any]]
    ) -> None:
        """Issue #665: Extracted from _process_markdown_sections to reduce function length.

        Insert all parsed sections into the database.
        """
        for section in sections:
            conn.execute(
                """
                INSERT INTO markdown_sections
                (file_path, section_title, section_level, content_text,
                 content_hash, start_line, end_line, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section["file_path"],
                    section["section_title"],
                    section["section_level"],
                    section["content_text"],
                    section["content_hash"],
                    section["start_line"],
                    section["end_line"],
                    datetime.now(),
                ),
            )

    def _process_markdown_sections(
        self, conn: sqlite3.Connection, file_path: Path, content: str
    ) -> None:
        """Extract and store markdown sections"""
        conn.execute(
            "DELETE FROM markdown_sections WHERE file_path = ?",
            (str(file_path),),
        )

        lines = content.split("\n")
        current_section = None
        sections = []

        for line_num, line in enumerate(lines, 1):
            header_match = _HEADER_RE.match(line.strip())
            if header_match:
                if current_section:
                    sections.append(
                        self._finalize_section(current_section, lines, line_num - 1)
                    )
                current_section = {
                    "file_path": str(file_path),
                    "section_title": header_match.group(2),
                    "section_level": len(header_match.group(1)),
                    "start_line": line_num,
                }

        if current_section:
            sections.append(self._finalize_section(current_section, lines, len(lines)))

        self._insert_sections_to_db(conn, sections)

    def _update_cross_references(self):
        """Update cross-references between markdown documents"""
        with sqlite3.connect(self.memory_manager.db_path) as conn:
            # Clear existing cross-references
            conn.execute("DELETE FROM markdown_cross_references")

            # Get all markdown files
            cursor = conn.execute("SELECT file_path FROM markdown_documents")
            files = [row[0] for row in cursor.fetchall()]

            for file_path in files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    self._extract_references(conn, file_path, content, files)

                except Exception as e:
                    logger.warning(
                        "Error processing references in %s: %s", file_path, e
                    )

            conn.commit()

    def _extract_references(
        self, conn, source_file: str, content: str, all_files: List[str]
    ):
        """Extract references from markdown content"""
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Find markdown links [text](url) using pre-compiled pattern (Issue #380)
            link_matches = _MARKDOWN_LINK_RE.findall(line)
            for link_text, link_url in link_matches:
                self._insert_link_reference(
                    conn, source_file, link_url, line, line_num, all_files
                )

            # Find file mentions using pre-compiled pattern (Issue #380)
            file_mentions = _MD_FILE_MENTION_RE.findall(line)
            for mentioned_file in file_mentions:
                self._insert_mention_reference(
                    conn, source_file, mentioned_file, line, line_num, all_files
                )

    def _insert_link_reference(
        self,
        conn,
        source_file: str,
        link_url: str,
        line: str,
        line_num: int,
        all_files: List[str],
    ) -> None:
        """Insert a markdown link reference into the database. Issue #620."""
        # Check if it's a reference to another markdown file
        if not (link_url.endswith(".md") or "/docs/" in link_url):
            return

        # Try to resolve the reference
        target_file = self._resolve_markdown_reference(link_url, source_file, all_files)
        if target_file:
            conn.execute(
                """
                INSERT INTO markdown_cross_references
                (source_file, target_file, reference_type, context_text,
                 line_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    source_file,
                    target_file,
                    "link",
                    line.strip(),
                    line_num,
                    datetime.now(),
                ),
            )

    def _insert_mention_reference(
        self,
        conn,
        source_file: str,
        mentioned_file: str,
        line: str,
        line_num: int,
        all_files: List[str],
    ) -> None:
        """Insert a file mention reference into the database. Issue #620."""
        target_file = self._resolve_markdown_reference(
            mentioned_file, source_file, all_files
        )
        if target_file and target_file != source_file:
            conn.execute(
                """
                INSERT INTO markdown_cross_references
                (source_file, target_file, reference_type, context_text,
                 line_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    source_file,
                    target_file,
                    "mention",
                    line.strip(),
                    line_num,
                    datetime.now(),
                ),
            )

    def _resolve_markdown_reference(
        self, reference: str, source_file: str, all_files: List[str]
    ) -> Optional[str]:
        """Resolve a markdown reference to an actual file path"""
        # Try exact match first
        if reference in all_files:
            return reference

        # Try relative path resolution
        source_dir = Path(source_file).parent
        potential_path = source_dir / reference
        if str(potential_path) in all_files:
            return str(potential_path)

        # Try filename match
        reference_name = Path(reference).name
        for file_path in all_files:
            if Path(file_path).name == reference_name:
                return file_path

        return None

    def get_document_references(
        self, file_path: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get all references for a specific document"""
        with sqlite3.connect(self.memory_manager.db_path) as conn:
            # Outgoing references
            cursor = conn.execute(
                """
                SELECT target_file, reference_type, context_text, line_number
                FROM markdown_cross_references
                WHERE source_file = ?
                ORDER BY line_number
            """,
                (file_path,),
            )

            outgoing = [
                {
                    "target_file": row[0],
                    "reference_type": row[1],
                    "context": row[2],
                    "line_number": row[3],
                }
                for row in cursor.fetchall()
            ]

            # Incoming references
            cursor = conn.execute(
                """
                SELECT source_file, reference_type, context_text, line_number
                FROM markdown_cross_references
                WHERE target_file = ?
                ORDER BY source_file, line_number
            """,
                (file_path,),
            )

            incoming = [
                {
                    "source_file": row[0],
                    "reference_type": row[1],
                    "context": row[2],
                    "line_number": row[3],
                }
                for row in cursor.fetchall()
            ]

        return {"outgoing_references": outgoing, "incoming_references": incoming}

    def _build_document_search_query(
        self,
        query: str,
        document_type: Optional[str],
        tags: Optional[List[str]],
        limit: int,
    ) -> tuple[str, List[Any]]:
        """Issue #665: Extracted from search_markdown_content to reduce function length.

        Build the SQL query and parameters for document search.
        """
        sql = """
            SELECT md.file_path, md.file_name, md.directory, md.word_count,
                   md.last_modified, md.document_type, md.tags
            FROM markdown_documents md
            WHERE (md.file_name LIKE ? OR md.directory LIKE ?)
        """
        params: List[Any] = [f"%{query}%", f"%{query}%"]

        if document_type:
            sql += " AND md.document_type = ?"
            params.append(document_type)

        if tags:
            # Issue #622: Use list + join for O(n) performance
            tag_conditions = [" AND md.tags LIKE ?" for _ in tags]
            sql += "".join(tag_conditions)
            params.extend(f"%{tag}%" for tag in tags)

        sql += " LIMIT ?"
        params.append(limit)
        return sql, params

    def _search_documents(
        self, conn: sqlite3.Connection, sql: str, params: List[Any]
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from search_markdown_content to reduce function length.

        Execute document search and format results.
        """
        cursor = conn.execute(sql, params)
        return [
            {
                "file_path": row[0],
                "file_name": row[1],
                "directory": row[2],
                "word_count": row[3],
                "last_modified": row[4],
                "document_type": row[5],
                "tags": json.loads(row[6]) if row[6] else [],
                "match_type": "document",
            }
            for row in cursor.fetchall()
        ]

    def _search_sections(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from search_markdown_content to reduce function length.

        Search markdown sections and format results.
        """
        cursor = conn.execute(
            """
            SELECT ms.file_path, ms.section_title, ms.section_level,
                   ms.start_line, ms.end_line, md.file_name
            FROM markdown_sections ms
            JOIN markdown_documents md ON ms.file_path = md.file_path
            WHERE ms.section_title LIKE ? OR ms.content_text LIKE ?
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit),
        )
        return [
            {
                "file_path": row[0],
                "section_title": row[1],
                "section_level": row[2],
                "start_line": row[3],
                "end_line": row[4],
                "file_name": row[5],
                "match_type": "section",
            }
            for row in cursor.fetchall()
        ]

    def search_markdown_content(
        self,
        query: str,
        document_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search markdown content and sections"""
        sql, params = self._build_document_search_query(
            query, document_type, tags, limit
        )

        with sqlite3.connect(self.memory_manager.db_path) as conn:
            doc_results = self._search_documents(conn, sql, params)
            section_results = self._search_sections(conn, query, limit)

        return doc_results + section_results

    def _get_document_stats_by_type(
        self, conn: sqlite3.Connection
    ) -> Dict[str, Dict[str, Any]]:
        """
        Query document statistics grouped by document type.

        Issue #620.
        """
        cursor = conn.execute(
            """
            SELECT document_type, COUNT(*), SUM(word_count), AVG(word_count)
            FROM markdown_documents
            GROUP BY document_type
        """
        )
        doc_stats = {}
        for row in cursor.fetchall():
            doc_stats[row[0]] = {
                "count": row[1],
                "total_words": row[2],
                "avg_words": round(row[3], 2) if row[3] else 0,
            }
        return doc_stats

    def _get_reference_stats(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """
        Query cross-reference statistics grouped by reference type.

        Issue #620.
        """
        cursor = conn.execute(
            """
            SELECT reference_type, COUNT(*)
            FROM markdown_cross_references
            GROUP BY reference_type
        """
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _get_section_stats(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """
        Query section statistics grouped by section level.

        Issue #620.
        """
        cursor = conn.execute(
            """
            SELECT section_level, COUNT(*)
            FROM markdown_sections
            GROUP BY section_level
            ORDER BY section_level
        """
        )
        return {f"level_{row[0]}": row[1] for row in cursor.fetchall()}

    def _get_document_totals(self, conn: sqlite3.Connection) -> tuple:
        """
        Query overall document totals.

        Issue #620.
        """
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total_documents,
                SUM(word_count) as total_words,
                COUNT(DISTINCT directory) as total_directories
            FROM markdown_documents
        """
        )
        return cursor.fetchone()

    def get_markdown_statistics(self) -> Dict[str, Any]:
        """Get comprehensive markdown statistics"""
        with sqlite3.connect(self.memory_manager.db_path) as conn:
            doc_stats = self._get_document_stats_by_type(conn)
            ref_stats = self._get_reference_stats(conn)
            section_stats = self._get_section_stats(conn)
            totals = self._get_document_totals(conn)

        return {
            "total_documents": totals[0],
            "total_words": totals[1],
            "total_directories": totals[2],
            "documents_by_type": doc_stats,
            "references_by_type": ref_stats,
            "sections_by_level": section_stats,
            "total_cross_references": sum(ref_stats.values()),
            "total_sections": sum(section_stats.values()),
        }

    def initialize_system_scan(self) -> Dict[str, Any]:
        """Initialize the markdown reference system by scanning all known directories"""
        results = {"scanned_directories": [], "total_files": 0, "total_errors": 0}

        # Scan main docs directory
        if self.docs_root.exists():
            docs_result = self.scan_markdown_directory(self.docs_root, "documentation")
            results["scanned_directories"].append(docs_result)
            results["total_files"] += docs_result["scanned_files"]
            results["total_errors"] += len(docs_result["errors"])

        # Scan system knowledge directory
        if self.knowledge_root.exists():
            knowledge_result = self.scan_markdown_directory(
                self.knowledge_root, "system_knowledge"
            )
            results["scanned_directories"].append(knowledge_result)
            results["total_files"] += knowledge_result["scanned_files"]
            results["total_errors"] += len(knowledge_result["errors"])

        # Scan for other markdown files in common locations
        other_locations = [Path("README.md"), Path("CLAUDE.md")]
        for location in other_locations:
            if location.exists():
                try:
                    self._process_markdown_file(location, "project_root")
                    results["total_files"] += 1
                except Exception as e:
                    results["total_errors"] += 1
                    logger.error("Error processing %s: %s", location, e)

        logger.info(
            f"Markdown system initialization completed: {results['total_files']} files processed"
        )

        return results
