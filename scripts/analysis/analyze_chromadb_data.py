#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analyze ChromaDB data contents to determine where the 13,383 vectors actually are
"""
import sqlite3
from pathlib import Path


def analyze_chromadb(db_path):
    """Analyze ChromaDB SQLite file contents"""
    print(f"\n=== ANALYZING {db_path} ===")

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check embeddings table
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embedding_count = cursor.fetchone()[0]
        print(f"Total embeddings: {embedding_count:,}")

        # Check collections
        cursor.execute("SELECT id, name, topic FROM collections")
        collections = cursor.fetchall()
        print("Collections:")
        for coll_id, name, topic in collections:
            print(f"  {coll_id}: {name} (topic: {topic})")

            # Count embeddings per collection
            cursor.execute("SELECT COUNT(*) FROM embeddings WHERE collection_id = ?", (coll_id,))
            coll_count = cursor.fetchone()[0]
            print(f"    Embeddings: {coll_count:,}")

            # Sample some metadata
            cursor.execute("""
                SELECT e.id, em.key, em.string_value
                FROM embeddings e
                LEFT JOIN embedding_metadata em ON e.id = em.embedding_id
                WHERE e.collection_id = ?
                LIMIT 5
            """, (coll_id,))
            samples = cursor.fetchall()
            print("    Sample metadata:")
            for embedding_id, key, value in samples:
                print(f"      {embedding_id}: {key} = {value}")

        # Check segments (vector storage)
        cursor.execute("""
            SELECT s.id, s.type, s.scope, sm.key, sm.string_value
            FROM segments s
            LEFT JOIN segment_metadata sm ON s.id = sm.segment_id
        """)
        segments = cursor.fetchall()
        print(f"Segments ({len(segments)}):")
        for seg_id, seg_type, scope, key, value in segments:
            print(f"  {seg_id}: type={seg_type}, scope={scope}")
            if key:
                print(f"    {key}: {value}")

        conn.close()

    except Exception as e:
        print(f"Error analyzing {db_path}: {e}")


def analyze_hnsw_data():
    """Analyze HNSW binary data files"""
    print("\n=== ANALYZING HNSW VECTOR FILES ===")

    hnsw_dir = Path("data/chromadb_kb/f8b5c9b7-9fff-471c-b68b-17e417b4f1be")
    if not hnsw_dir.exists():
        print("No HNSW directory found")
        return

    for file in hnsw_dir.iterdir():
        if file.is_file():
            size_mb = file.stat().st_size / 1024 / 1024
            print(f"{file.name}: {size_mb:.2f} MB")

            # Estimate vector count from data_level0.bin size
            if file.name == "data_level0.bin":
                # Assuming 768-dimensional float32 vectors (768 * 4 bytes = 3072 bytes per vector)
                # Plus some HNSW overhead
                estimated_vectors = int(size_mb * 1024 * 1024 / 3200)  # ~3200 bytes per vector with overhead
                print(f"  Estimated vectors in HNSW index: ~{estimated_vectors:,}")


def main():
    print("ChromaDB Data Analysis")
    print("="*50)

    # Analyze both ChromaDB instances
    chromadb_paths = [
        Path("data/chromadb/chroma.sqlite3"),
        Path("data/chromadb_kb/chroma.sqlite3")
    ]

    for db_path in chromadb_paths:
        if db_path.exists():
            analyze_chromadb(db_path)
        else:
            print(f"\n{db_path} does not exist")

    analyze_hnsw_data()

    print("\n" + "="*50)
    print("ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
