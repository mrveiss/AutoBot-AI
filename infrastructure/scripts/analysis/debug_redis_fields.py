#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Debug Redis vector store fields to understand the data structure
"""

import logging

import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def debug_redis_vector_fields():
    """Debug what fields are available in Redis vector store"""
    try:
        # Connect to Redis
        client = redis.Redis(host="localhost", port=6379, db=2, decode_responses=True)

        # Get index info
        logger.info("Getting Redis FT.INFO for llama_index...")
        ft_info = client.execute_command("FT.INFO", "llama_index")

        logger.info("Index info:")
        for i in range(0, len(ft_info), 2):
            if i + 1 < len(ft_info):
                logger.info("  %s: %s", ft_info[i], ft_info[i + 1])

        # Get a sample document to see actual fields
        logger.info("\nGetting sample documents...")
        search_result = client.execute_command(
            "FT.SEARCH", "llama_index", "*", "LIMIT", "0", "3"  # Match all
        )

        logger.info("Search returned %s total documents", search_result[0])

        if len(search_result) > 1:
            logger.info("\nSample document structures:")
            # Documents start at index 1, in pairs (doc_id, fields)
            for i in range(1, min(len(search_result), 7), 2):
                doc_id = search_result[i]
                if i + 1 < len(search_result):
                    fields = search_result[i + 1]
                    logger.info("\nDocument: %s", doc_id)
                    logger.info("Fields: %s", fields)
                    logger.info(
                        "Available field names: %s",
                        fields[::2] if isinstance(fields, list) else "Not a list",
                    )

        # Also check direct hash access
        logger.info("\nChecking direct hash access...")
        sample_keys = list(client.scan_iter(match="llama_index/vector*", count=3))
        for key in sample_keys[:2]:
            logger.info("\nKey: %s", key)
            hash_data = client.hgetall(key)
            logger.info("Hash fields: %s", list(hash_data.keys()))
            for field, value in hash_data.items():
                logger.info(
                    "  %s: %s...",
                    field,
                    value[:100] if len(str(value)) > 100 else value,
                )

    except Exception as e:
        logger.error("Error debugging Redis fields: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_redis_vector_fields()
