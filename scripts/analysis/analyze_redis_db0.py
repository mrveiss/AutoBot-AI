#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analyze what's stored in Redis database 0 to understand the full scope
"""

import redis
import logging
import json
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_redis_db0():
    """Analyze what's in Redis database 0"""
    try:
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
        
        logger.info("=== ANALYZING REDIS DATABASE 0 ===")
        
        # Get overall info
        info = client.info()
        logger.info(f"Database 0 Keys: {info.get('db0', {}).get('keys', 'No data')}")
        logger.info(f"Total Memory Used: {info.get('used_memory_human', 'Unknown')}")
        
        # Analyze key patterns
        logger.info("\n=== KEY PATTERN ANALYSIS ===")
        key_patterns = defaultdict(int)
        key_samples = defaultdict(list)
        
        # Scan all keys (careful with large datasets)
        cursor = 0
        total_keys = 0
        max_scan = 10000  # Limit to prevent overwhelming
        
        while cursor != '0' and total_keys < max_scan:
            cursor, keys = client.scan(cursor, count=100)
            for key in keys:
                total_keys += 1
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                    
                    # Categorize by pattern
                    if key_str.startswith('llama_index/vector'):
                        pattern = 'llama_index/vector'
                    elif key_str.startswith('llama_index'):
                        pattern = 'llama_index/other'
                    elif key_str.startswith('fact:'):
                        pattern = 'fact'
                    elif key_str.startswith('chat:'):
                        pattern = 'chat'
                    elif key_str.startswith('session:'):
                        pattern = 'session'
                    elif key_str.startswith('config:'):
                        pattern = 'config'
                    elif key_str.startswith('cache:'):
                        pattern = 'cache'
                    else:
                        pattern = 'other'
                    
                    key_patterns[pattern] += 1
                    
                    # Keep samples for each pattern
                    if len(key_samples[pattern]) < 3:
                        key_samples[pattern].append(key_str)
                        
                except Exception as e:
                    key_patterns['decode_error'] += 1
                    
            if cursor == 0:
                break
        
        logger.info(f"Total keys scanned: {total_keys}")
        logger.info("\nKey patterns found:")
        for pattern, count in sorted(key_patterns.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {pattern}: {count:,} keys")
            if pattern in key_samples and key_samples[pattern]:
                logger.info(f"    Samples: {key_samples[pattern]}")
        
        # Check FT indices
        logger.info("\n=== REDIS SEARCH INDICES ===")
        try:
            indices = client.execute_command('FT._LIST')
            logger.info(f"Search indices found: {indices}")
            
            for index in indices:
                try:
                    index_name = index.decode('utf-8') if isinstance(index, bytes) else str(index)
                    ft_info = client.execute_command('FT.INFO', index_name)
                    
                    # Parse num_docs
                    num_docs = 0
                    for i in range(len(ft_info)):
                        if ft_info[i] == b'num_docs' or ft_info[i] == 'num_docs':
                            num_docs = ft_info[i + 1]
                            break
                    
                    logger.info(f"  Index '{index_name}': {num_docs} documents")
                    
                except Exception as e:
                    logger.warning(f"  Could not analyze index {index}: {e}")
                    
        except Exception as e:
            logger.warning(f"Could not list FT indices: {e}")
        
        # Sample some non-vector data to see what else is stored
        logger.info("\n=== SAMPLE NON-VECTOR DATA ===")
        for pattern, samples in key_samples.items():
            if pattern != 'llama_index/vector' and samples:
                logger.info(f"\nPattern: {pattern}")
                for sample_key in samples[:2]:  # Just first 2 samples
                    try:
                        key_type = client.type(sample_key)
                        key_type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else str(key_type)
                        logger.info(f"  Key: {sample_key} (type: {key_type_str})")
                        
                        if key_type_str == 'hash':
                            hash_data = client.hgetall(sample_key)
                            hash_fields = []
                            for field, value in hash_data.items():
                                field_str = field.decode('utf-8') if isinstance(field, bytes) else str(field)
                                value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                                hash_fields.append(f"{field_str}: {value_str}")
                            logger.info(f"    Hash fields: {hash_fields[:3]}")
                            
                        elif key_type_str == 'string':
                            value = client.get(sample_key)
                            value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                            logger.info(f"    Value: {value_str}")
                            
                    except Exception as e:
                        logger.warning(f"    Could not analyze key {sample_key}: {e}")
        
        # Impact assessment
        logger.info("\n=== IMPACT ASSESSMENT ===")
        vector_keys = key_patterns.get('llama_index/vector', 0)
        total_other_keys = sum(count for pattern, count in key_patterns.items() 
                              if pattern != 'llama_index/vector')
        
        logger.info(f"Vector keys: {vector_keys:,}")
        logger.info(f"Non-vector keys: {total_other_keys:,}")
        
        if total_other_keys == 0:
            logger.info("✅ Database 0 appears to be EXCLUSIVELY for vectors")
            logger.info("💥 DROPPING DB 0 = Complete knowledge base data loss")
        elif total_other_keys < vector_keys * 0.1:  # Less than 10% non-vector
            logger.info("⚠️ Database 0 is PRIMARILY vectors with minimal other data")
            logger.info("💥 DROPPING DB 0 = Mostly knowledge base loss + some other data")
        else:
            logger.info("🔄 Database 0 contains MIXED data - vectors + significant other data")
            logger.info("💥 DROPPING DB 0 = Knowledge base + other system data loss")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_redis_db0()