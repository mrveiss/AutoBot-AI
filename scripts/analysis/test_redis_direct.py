#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test direct Redis access to understand the field issue
"""

import redis
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_redis_direct_access():
    """Test Redis direct access"""
    try:
        client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)

        # Test FT.SEARCH with explicit RETURN
        logger.info("Testing FT.SEARCH with explicit RETURN...")
        search_result = client.execute_command(
            'FT.SEARCH', 'llama_index',
            'deployment',  # Simple query
            'RETURN', '3', 'text', 'id', 'doc_id',
            'LIMIT', '0', '2'
        )
        logger.info(f"FT.SEARCH result: {search_result}")

        # Test hash access directly
        logger.info("\nTesting direct hash access...")
        sample_keys = list(client.scan_iter(match="llama_index/vector*", count=2))
        for key in sample_keys:
            logger.info(f"\nKey: {key}")
            hash_data = client.hgetall(key)
            logger.info(f"Hash fields: {list(hash_data.keys())}")
            if 'text' in hash_data:
                logger.info(f"Text content: {hash_data['text'][:200]}...")
            if '_node_content' in hash_data:
                logger.info(f"Node content: {hash_data['_node_content'][:200]}...")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_redis_direct_access()
