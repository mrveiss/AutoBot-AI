# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Import Tracking Model
Tracks which files have been imported into the knowledge base
"""
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


class ImportTracker:
    """Track imported files and their status"""

    def __init__(self, db_path: str = "data/knowledge_imports.db"):
        """Initialize import tracker with database path and create table."""
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """Create tracking table if it doesn't exist"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS imported_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER,
                category TEXT,
                import_status TEXT DEFAULT 'pending',
                imported_at TIMESTAMP,
                last_checked TIMESTAMP,
                error_message TEXT,
                facts_count INTEGER DEFAULT 0,
                metadata TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path ON imported_files(file_path)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_status ON imported_files(import_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category ON imported_files(category)
        """)

        conn.commit()
        conn.close()

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def mark_imported(self, file_path: str, category: str, facts_count: int = 0,
                      metadata: Optional[dict] = None):
        """Mark a file as successfully imported"""
        import json
        import sqlite3

        file_path = str(Path(file_path).absolute())
        file_hash = self.calculate_file_hash(file_path)
        file_size = Path(file_path).stat().st_size

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO imported_files
            (file_path, file_hash, file_size, category, import_status, imported_at, last_checked, facts_count, metadata)
            VALUES (?, ?, ?, ?, 'imported', ?, ?, ?, ?)
        """, (
            file_path,
            file_hash,
            file_size,
            category,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            facts_count,
            json.dumps(metadata) if metadata else None
        ))

        conn.commit()
        conn.close()

    def mark_failed(self, file_path: str, error_message: str):
        """Mark a file import as failed"""
        import sqlite3

        file_path = str(Path(file_path).absolute())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO imported_files
            (file_path, import_status, last_checked, error_message)
            VALUES (?, 'failed', ?, ?)
        """, (file_path, datetime.now().isoformat(), error_message))

        conn.commit()
        conn.close()

    def is_imported(self, file_path: str) -> bool:
        """Check if file has been imported"""
        import sqlite3

        file_path = str(Path(file_path).absolute())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT import_status FROM imported_files
            WHERE file_path = ? AND import_status = 'imported'
        """, (file_path,))

        result = cursor.fetchone()
        conn.close()

        return result is not None

    def needs_reimport(self, file_path: str) -> bool:
        """Check if file has changed and needs re-import"""
        import sqlite3

        file_path = str(Path(file_path).absolute())

        if not Path(file_path).exists():
            return False

        current_hash = self.calculate_file_hash(file_path)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT file_hash FROM imported_files
            WHERE file_path = ? AND import_status = 'imported'
        """, (file_path,))

        result = cursor.fetchone()
        conn.close()

        if not result:
            return True  # Not imported yet

        return result[0] != current_hash  # Hash changed

    def get_import_status(self, file_path: Optional[str] = None, category: Optional[str] = None):
        """Get import status for files"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if file_path:
            file_path = str(Path(file_path).absolute())
            cursor.execute("""
                SELECT file_path, file_hash, file_size, category, import_status,
                       imported_at, last_checked, error_message, facts_count
                FROM imported_files
                WHERE file_path = ?
            """, (file_path,))
        elif category:
            cursor.execute("""
                SELECT file_path, file_hash, file_size, category, import_status,
                       imported_at, last_checked, error_message, facts_count
                FROM imported_files
                WHERE category = ?
                ORDER BY imported_at DESC
            """, (category,))
        else:
            cursor.execute("""
                SELECT file_path, file_hash, file_size, category, import_status,
                       imported_at, last_checked, error_message, facts_count
                FROM imported_files
                ORDER BY imported_at DESC
            """)

        columns = ['file_path', 'file_hash', 'file_size', 'category', 'import_status',
                   'imported_at', 'last_checked', 'error_message', 'facts_count']
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_statistics(self):
        """Get import statistics"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN import_status = 'imported' THEN 1 ELSE 0 END) as imported,
                SUM(CASE WHEN import_status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN import_status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(facts_count) as total_facts,
                SUM(file_size) as total_size
            FROM imported_files
        """)

        result = cursor.fetchone()
        conn.close()

        return {
            'total_files': result[0] or 0,
            'imported': result[1] or 0,
            'failed': result[2] or 0,
            'pending': result[3] or 0,
            'total_facts': result[4] or 0,
            'total_size': result[5] or 0
        }
