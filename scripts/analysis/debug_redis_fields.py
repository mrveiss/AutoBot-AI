#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Debug Redis vector store fields to understand the data structure
"""

import redis
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_redis_vector_fields():
    """Debug what fields are available in Redis vector store"""
    try:
        # Connect to Redis
        client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)
        
        # Get index info
        logger.info("Getting Redis FT.INFO for llama_index...")
        ft_info = client.execute_command('FT.INFO', 'llama_index')
        
        logger.info("Index info:")
        for i in range(0, len(ft_info), 2):
            if i + 1 < len(ft_info):
                logger.info(f"  {ft_info[i]}: {ft_info[i+1]}")
        
        # Get a sample document to see actual fields
        logger.info("\nGetting sample documents...")
        search_result = client.execute_command(
            'FT.SEARCH', 'llama_index', 
            '*',  # Match all
            'LIMIT', '0', '3'
        )
        
        logger.info(f"Search returned {search_result[0]} total documents")
        
        if len(search_result) > 1:
            logger.info("\nSample document structures:")
            # Documents start at index 1, in pairs (doc_id, fields)
            for i in range(1, min(len(search_result), 7), 2):
                doc_id = search_result[i]
                if i + 1 < len(search_result):
                    fields = search_result[i + 1]
                    logger.info(f"\nDocument: {doc_id}")
                    logger.info(f"Fields: {fields}")
                    logger.info(f"Available field names: {fields[::2] if isinstance(fields, list) else 'Not a list'}")
        
        # Also check direct hash access
        logger.info("\nChecking direct hash access...")
        sample_keys = list(client.scan_iter(match="llama_index/vector*", count=3))
        for key in sample_keys[:2]:
            logger.info(f"\nKey: {key}")
            hash_data = client.hgetall(key)
            logger.info(f"Hash fields: {list(hash_data.keys())}")
            for field, value in hash_data.items():
                logger.info(f"  {field}: {value[:100] if len(str(value)) > 100 else value}...")
        
    except Exception as e:
        logger.error(f"Error debugging Redis fields: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_redis_vector_fields()