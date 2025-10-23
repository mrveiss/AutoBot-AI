#!/usr/bin/env python3
"""
Test AutoBot documentation search specifically
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.knowledge_base import KnowledgeBase
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        print("🔍 Testing AutoBot documentation search...")

        kb = KnowledgeBase()

        # Wait for initialization
        max_wait = 10
        for i in range(max_wait):
            if kb.redis_client is not None:
                print(f"✅ KB initialized after {i} seconds")
                break
            await asyncio.sleep(1)
        else:
            print("❌ KB failed to initialize")
            return

        # Check index status one more time
        try:
            info = kb.redis_client.execute_command('FT.INFO', 'llama_index')
            for i in range(0, len(info), 2):
                if info[i].decode('utf-8') in ['num_docs', 'dim', 'percent_indexed']:
                    print(f"📊 {info[i].decode('utf-8')}: {info[i+1]}")
        except Exception as e:
            print(f"⚠️ Could not get index info: {e}")

        # Search for specific AutoBot-related content
        search_terms = [
            "AutoBot",
            "autonomous Linux administration",
            "CLAUDE.md",
            "documentation root",
            "agent implementation",
            "distributed architecture"
        ]

        print("\n🔍 Testing different search terms...")

        for term in search_terms:
            try:
                print(f"\n🔎 Searching for: '{term}'")
                results = await kb.search(term, similarity_top_k=3)
                print(f"  📊 Found {len(results)} results")

                if results:
                    for i, result in enumerate(results[:2]):
                        if isinstance(result, dict):
                            text = result.get('text', '')
                            source = result.get('metadata', {}).get('source', 'Unknown')
                        else:
                            # Handle node-like objects
                            text = getattr(result, 'text', str(result)[:100])
                            source = getattr(result, 'metadata', {}).get('source', 'Unknown')

                        preview = text[:100] + "..." if len(text) > 100 else text
                        print(f"    📄 Result {i+1}: {preview}")
                        print(f"    📍 Source: {source}")
                        print()

            except Exception as e:
                print(f"  ❌ Search failed for '{term}': {e}")

        # Test manual Redis search for AutoBot content
        print("\n🔍 Manual Redis text search for AutoBot...")
        try:
            # Search using Redis directly for text containing "autobot"
            vector_keys = kb.redis_client.keys(b"llama_index/vector_*")
            print(f"📦 Checking {len(vector_keys)} vectors for AutoBot content...")

            autobot_content = []
            for i, key in enumerate(vector_keys[:100]):  # Check first 100
                try:
                    data = kb.redis_client.hgetall(key)
                    if b'text' in data:
                        text = data[b'text'].decode('utf-8', errors='ignore')
                        if 'autobot' in text.lower() or 'claude' in text.lower():
                            autobot_content.append({
                                'key': key.decode('utf-8'),
                                'text': text[:200],
                                'source': data.get(b'source_metadata', b'').decode('utf-8', errors='ignore')
                            })
                except Exception as e:
                    continue

            print(f"📄 Found {len(autobot_content)} vectors with AutoBot/Claude content")
            for content in autobot_content[:3]:
                print(f"  📄 {content['text'][:100]}...")
                print(f"  📍 Source: {content['source'][:100]}")
                print()

        except Exception as e:
            print(f"❌ Manual search failed: {e}")

        print("✅ AutoBot documentation search test completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())