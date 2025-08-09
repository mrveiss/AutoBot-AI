#!/usr/bin/env python3
"""
Create knowledge base index with correct dimensions using redisvl directly.
"""

import os
import sys
import redis
from redisvl.schema import IndexSchema

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_index_with_correct_dimensions():
    """Create Redis index with 768 dimensions for nomic-embed-text."""

    # Connect to Redis
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)

    # First, drop any existing indexes
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        print("Dropped existing llama_index")
    except Exception as e:
        print(f"No existing llama_index to drop: {e}")

    try:
        r.execute_command("FT.DROPINDEX", "autobot_kb_768", "DD")
        print("Dropped existing autobot_kb_768")
    except Exception as e:
        print(f"No existing autobot_kb_768 to drop: {e}")

    # Define the schema with correct dimensions
    schema_dict = {
        "index": {
            "name": "llama_index",  # Use the name that llama_index expects
            "prefix": "llama_index/vector",
            "storage_type": "hash",
        },
        "fields": [
            {"name": "id", "type": "tag"},
            {"name": "doc_id", "type": "tag"},
            {"name": "text", "type": "text"},
            {
                "name": "vector",
                "type": "vector",
                "attrs": {
                    "dims": 768,  # Correct dimension for nomic-embed-text
                    "algorithm": "flat",
                    "distance_metric": "cosine",
                },
            },
        ],
    }

    # Create the schema
    schema = IndexSchema.from_dict(schema_dict)

    print(f"Creating index with schema:")
    print(f"  Name: {schema.index.name}")
    print(f"  Vector dimensions: 768")

    # Create the index using raw Redis command
    try:
        # Build the FT.CREATE command
        create_cmd = [
            "FT.CREATE",
            "llama_index",
            "ON",
            "HASH",
            "PREFIX",
            "1",
            "llama_index/vector",
            "SCHEMA",
            "id",
            "TAG",
            "doc_id",
            "TAG",
            "text",
            "TEXT",
            "vector",
            "VECTOR",
            "FLAT",
            "6",
            "TYPE",
            "FLOAT32",
            "DIM",
            "768",
            "DISTANCE_METRIC",
            "COSINE",
        ]

        result = r.execute_command(*create_cmd)
        print(f"Index created successfully: {result}")

        # Verify the index
        info = r.execute_command("FT.INFO", "llama_index")
        print("\nIndex created with attributes:")
        for attr in info[info.index(b"attributes") + 1]:
            if b"vector" in attr and b"dim" in attr:
                dim_index = attr.index(b"dim")
                print(f"  Vector dimension: {attr[dim_index + 1]}")

    except Exception as e:
        print(f"Error creating index: {e}")
        return False

    return True


if __name__ == "__main__":
    success = create_index_with_correct_dimensions()
    if success:
        print("\nIndex created successfully with 768 dimensions!")
        print("You can now run populate_knowledge_base.py")
    else:
        print("\nFailed to create index")
