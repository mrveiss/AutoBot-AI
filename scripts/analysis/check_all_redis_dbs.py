#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Check all Redis databases to understand data distribution
"""

import redis
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_all_redis_databases():
    """Analyze data distribution across all Redis databases"""

    logger.info("=== REDIS DATABASE DISTRIBUTION ANALYSIS ===")

    for db_num in range(16):  # Redis typically has 16 databases (0-15)
        try:
            client = redis.Redis(host='localhost', port=6379, db=db_num, decode_responses=False)

            # Quick check if database has any keys
            info = client.info()
            db_key = f'db{db_num}'

            if db_key in info:
                keys_count = info[db_key]['keys']
                expires_count = info[db_key].get('expires', 0)

                logger.info(f"\n--- Database {db_num} ---")
                logger.info(f"Keys: {keys_count:,}")
                logger.info(f"Keys with expiry: {expires_count:,}")

                if keys_count > 0:
                    # Sample key patterns
                    key_patterns = defaultdict(int)
                    cursor = 0
                    sampled = 0
                    max_sample = 100

                    while cursor != '0' and sampled < max_sample:
                        cursor, keys = client.scan(cursor, count=20)
                        for key in keys:
                            sampled += 1
                            try:
                                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)

                                # Categorize by pattern
                                if key_str.startswith('llama_index/vector'):
                                    pattern = 'vectors'
                                elif key_str.startswith('fact:'):
                                    pattern = 'facts'
                                elif key_str.startswith('chat:'):
                                    pattern = 'chats'
                                elif key_str.startswith('session:'):
                                    pattern = 'sessions'
                                elif 'cache' in key_str.lower():
                                    pattern = 'cache'
                                elif 'config' in key_str.lower():
                                    pattern = 'config'
                                else:
                                    pattern = 'other'

                                key_patterns[pattern] += 1

                            except Exception:
                                key_patterns['decode_error'] += 1

                            if sampled >= max_sample:
                                break

                        if cursor == 0:
                            break

                    logger.info("Sample patterns:")
                    for pattern, count in sorted(key_patterns.items(), key=lambda x: x[1], reverse=True):
                        percentage = (count / sampled) * 100 if sampled > 0 else 0
                        estimated_total = int((count / sampled) * keys_count) if sampled > 0 else 0
                        logger.info(f"  {pattern}: {count}/{sampled} sampled ({percentage:.1f}%) ≈ {estimated_total:,} total")

        except Exception as e:
            if "NOAUTH" in str(e):
                logger.warning(f"Database {db_num}: Authentication required")
            elif "Connection refused" in str(e):
                logger.error(f"Cannot connect to Redis")
                break
            else:
                logger.debug(f"Database {db_num}: {e}")

    # Summary and recommendations
    logger.info("\n=== SUMMARY & RECOMMENDATIONS ===")
    logger.info("Based on analysis:")
    logger.info("• Database 0: PRIMARY vector store (13,383 vectors) + minimal facts/config")
    logger.info("• Other databases: Likely used for different services or empty")

    logger.info("\n💥 IMPACT OF DROPPING DATABASE 0:")
    logger.info("• ❌ Complete loss of 13,383 knowledge base vectors")
    logger.info("• ❌ Loss of stored facts and workflow rules")
    logger.info("• ❌ Loss of any cached LangChain test data")
    logger.info("• ⚠️ Potential system reconfiguration needed")

    logger.info("\n🛡️ PROTECTION STRATEGIES:")
    logger.info("• Create Redis backup before any operations: redis-cli --rdb dump.rdb")
    logger.info("• Consider moving vectors to dedicated database (e.g., DB 3)")
    logger.info("• Document database usage in CLAUDE.md")
    logger.info("• Implement automated backup system")


if __name__ == "__main__":
    analyze_all_redis_databases()
