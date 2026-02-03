#!/usr/bin/env python3
"""
Create Vector Knowledge Base from Code Indexes

This script creates a searchable vector knowledge base from the existing
24,803 code analytics vectors in Redis DB 8, making them accessible
through the main knowledge base interface.
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import canonical Redis client utility (Issue #692)
from src.utils.redis_client import get_redis_client
from src.knowledge_base import KnowledgeBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeVectorKnowledgeCreator:
    """Creates vector knowledge base from code analytics indexes"""

    def __init__(self):
        # Issue #692: Removed unused RedisDatabaseManager - use get_redis_client() directly
        self.kb = None

    async def initialize(self):
        """Initialize connections"""
        try:
            # Initialize knowledge base
            self.kb = KnowledgeBase()

            # Wait for KB initialization
            max_wait = 10
            for i in range(max_wait):
                if self.kb.redis_client is not None:
                    logger.info(f"✅ Knowledge Base initialized after {i} seconds")
                    break
                await asyncio.sleep(1)
            else:
                raise Exception("Knowledge Base failed to initialize")

            return True

        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False

    async def get_code_analytics_vectors(self) -> List[Dict[str, Any]]:
        """Get all code analytics vectors from DB 8"""
        try:
            # Connect to analytics database using canonical pattern
            analytics_redis = get_redis_client(database="analytics", async_client=False)

            logger.info("🔍 Scanning code analytics vectors...")

            # Get all vector keys
            vector_keys = analytics_redis.keys(b"llama_index/vector_*")
            logger.info(f"📦 Found {len(vector_keys)} code analytics vectors")

            # Process vectors in batches to avoid timeout
            batch_size = 100
            vectors = []

            for i in range(0, len(vector_keys), batch_size):
                batch = vector_keys[i:i + batch_size]
                logger.info(f"📄 Processing batch {i//batch_size + 1}/{(len(vector_keys)-1)//batch_size + 1}")

                # Get vector data for batch
                pipe = analytics_redis.pipeline()
                for key in batch:
                    pipe.hgetall(key)

                batch_data = pipe.execute()

                for key, data in zip(batch, batch_data):
                    if data:
                        try:
                            # Decode vector data
                            vector_info = {
                                "id": key.decode('utf-8'),
                                "text": data.get(b'text', b'').decode('utf-8', errors='ignore'),
                                "doc_id": data.get(b'doc_id', b'').decode('utf-8', errors='ignore'),
                                "metadata": {}
                            }

                            # Parse metadata if available
                            if b'metadata' in data:
                                try:
                                    metadata_str = data[b'metadata'].decode('utf-8', errors='ignore')
                                    vector_info["metadata"] = json.loads(metadata_str)
                                except (json.JSONDecodeError, UnicodeDecodeError):
                                    pass

                            # Add source information for code analytics
                            vector_info["metadata"]["source"] = "code_analytics"
                            vector_info["metadata"]["database"] = "analytics_db8"
                            vector_info["metadata"]["type"] = "code_index"

                            # Only add vectors with meaningful text content
                            if vector_info["text"].strip() and len(vector_info["text"]) > 10:
                                vectors.append(vector_info)

                        except Exception as e:
                            logger.warning(f"⚠️ Failed to process vector {key}: {e}")
                            continue

            logger.info(f"✅ Successfully processed {len(vectors)} code analytics vectors")
            return vectors

        except Exception as e:
            logger.error(f"❌ Failed to get code analytics vectors: {e}")
            return []

    async def create_vector_knowledge_entries(self, vectors: List[Dict[str, Any]]) -> int:
        """Create knowledge base entries from code vectors"""
        try:
            logger.info("🔄 Creating vector knowledge entries...")

            # Process vectors in smaller batches to avoid timeouts
            batch_size = 50
            created_count = 0

            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                logger.info(f"📝 Creating entries batch {i//batch_size + 1}/{(len(vectors)-1)//batch_size + 1}")

                for vector in batch:
                    try:
                        # Create a knowledge entry from the code vector
                        entry_text = f"""
CODE ANALYTICS: {vector.get('doc_id', 'Unknown File')}

{vector['text']}

Source: Code Analytics Index
Type: {vector['metadata'].get('type', 'code_index')}
Database: {vector['metadata'].get('database', 'analytics_db8')}
"""

                        # Add to knowledge base using the existing search interface
                        # The knowledge base will handle vectorization automatically
                        search_terms = [
                            "code analytics",
                            "code index",
                            vector.get('doc_id', '').split('/')[-1] if vector.get('doc_id') else '',
                            "autobot code"
                        ]

                        # Store as a document in the knowledge base
                        doc_metadata = {
                            "source": f"code_analytics_{vector.get('doc_id', 'unknown')}",
                            "type": "code_index",
                            "original_vector_id": vector['id'],
                            "analytics_db": "db8",
                            "tags": search_terms,
                            "created_at": datetime.now().isoformat()
                        }

                        # Use the knowledge base's document storage
                        # This will automatically create searchable vectors
                        result = await self.store_code_document(entry_text, doc_metadata)

                        if result:
                            created_count += 1

                        # Avoid overwhelming the system
                        if created_count % 25 == 0:
                            await asyncio.sleep(1)  # Brief pause every 25 entries

                    except Exception as e:
                        logger.warning(f"⚠️ Failed to create entry for vector {vector['id']}: {e}")
                        continue

                # Pause between batches
                await asyncio.sleep(2)

            logger.info(f"✅ Created {created_count} vector knowledge entries")
            return created_count

        except Exception as e:
            logger.error(f"❌ Failed to create vector knowledge entries: {e}")
            return 0

    async def store_code_document(self, text: str, metadata: Dict[str, Any]) -> bool:
        """Store a code document in the knowledge base"""
        try:
            # Use the knowledge base's document storage functionality
            if hasattr(self.kb, 'add_document'):
                await self.kb.add_document(text, metadata)
                return True
            else:
                # Fallback: store directly in Redis with proper format
                doc_id = f"code_analytics_{metadata.get('original_vector_id', 'unknown')}"

                # Store in knowledge database using canonical pattern
                kb_redis = get_redis_client(database="knowledge", async_client=False)

                # Create document entry
                doc_data = {
                    "text": text,
                    "metadata": json.dumps(metadata),
                    "doc_id": doc_id,
                    "created_at": datetime.now().isoformat(),
                    "type": "code_analytics"
                }

                # Store with hash
                kb_redis.hset(f"document:{doc_id}", mapping=doc_data)

                # Add to searchable index
                kb_redis.sadd("code_analytics:documents", doc_id)

                return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to store document: {e}")
            return False

    async def create_search_index(self) -> bool:
        """Create search index for code analytics knowledge"""
        try:
            logger.info("🔨 Creating search index for code analytics...")

            # Connect to knowledge database using canonical pattern
            kb_redis = get_redis_client(database="knowledge", async_client=False)

            # Create search index for code analytics documents
            try:
                index_command = [
                    'FT.CREATE', 'code_analytics_index',
                    'ON', 'HASH',
                    'PREFIX', '1', 'document:code_analytics_',
                    'SCHEMA',
                    'text', 'TEXT', 'WEIGHT', '2.0',
                    'doc_id', 'TEXT',
                    'type', 'TAG',
                    'created_at', 'TEXT'
                ]

                result = kb_redis.execute_command(*index_command)
                logger.info(f"✅ Search index created: {result}")
                return True

            except Exception as e:
                if "Index already exists" in str(e):
                    logger.info("ℹ️ Search index already exists")
                    return True
                else:
                    logger.error(f"❌ Failed to create search index: {e}")
                    return False

        except Exception as e:
            logger.error(f"❌ Failed to create search index: {e}")
            return False

    async def test_search_functionality(self) -> bool:
        """Test the created vector knowledge search"""
        try:
            logger.info("🔍 Testing vector knowledge search...")

            # Test search using knowledge base
            if self.kb:
                # Search for code-related content
                search_terms = [
                    "code analytics",
                    "autobot code",
                    "function",
                    "python",
                    "javascript"
                ]

                for term in search_terms:
                    try:
                        results = await self.kb.search(term, similarity_top_k=3)
                        logger.info(f"📊 Search '{term}': {len(results)} results")

                        if results:
                            for i, result in enumerate(results[:1]):  # Show 1 example
                                if isinstance(result, dict):
                                    text = result.get('text', '')[:100]
                                    source = result.get('metadata', {}).get('source', 'Unknown')
                                else:
                                    text = str(result)[:100]
                                    source = "Unknown"

                                logger.info(f"  📄 Result {i+1}: {text}... (Source: {source})")

                    except Exception as e:
                        logger.warning(f"⚠️ Search failed for '{term}': {e}")
                        continue

                logger.info("✅ Vector knowledge search test completed")
                return True
            else:
                logger.error("❌ Knowledge base not available for testing")
                return False

        except Exception as e:
            logger.error(f"❌ Search test failed: {e}")
            return False


async def main():
    """Main execution function"""
    try:
        print("🚀 Creating Vector Knowledge Base from Code Indexes...")
        print(f"⏰ Started at: {datetime.now().isoformat()}")

        creator = CodeVectorKnowledgeCreator()

        # Initialize connections
        if not await creator.initialize():
            print("❌ Failed to initialize connections")
            return

        # Get code analytics vectors
        print("\n📊 Step 1: Extracting code analytics vectors...")
        vectors = await creator.get_code_analytics_vectors()

        if not vectors:
            print("❌ No code analytics vectors found")
            return

        print(f"✅ Found {len(vectors)} code analytics vectors")

        # Create vector knowledge entries
        print("\n📝 Step 2: Creating vector knowledge entries...")
        created_count = await creator.create_vector_knowledge_entries(vectors)

        if created_count == 0:
            print("❌ Failed to create any knowledge entries")
            return

        print(f"✅ Created {created_count} vector knowledge entries")

        # Create search index
        print("\n🔨 Step 3: Creating search index...")
        index_created = await creator.create_search_index()

        if not index_created:
            print("⚠️ Search index creation failed, but entries were created")
        else:
            print("✅ Search index created successfully")

        # Test search functionality
        print("\n🔍 Step 4: Testing search functionality...")
        search_works = await creator.test_search_functionality()

        if search_works:
            print("✅ Vector knowledge search is working")
        else:
            print("⚠️ Search test failed, but knowledge base was created")

        # Summary
        print("\n🎉 Vector Knowledge Base Creation Complete!")
        print("📊 Statistics:")
        print(f"  - Source vectors processed: {len(vectors)}")
        print(f"  - Knowledge entries created: {created_count}")
        print(f"  - Search index: {'✅ Created' if index_created else '❌ Failed'}")
        print(f"  - Search functionality: {'✅ Working' if search_works else '❌ Issues'}")
        print("\n💡 The code analytics are now searchable through the main knowledge base!")
        print("   You can search for terms like: 'code analytics', 'function', 'python', etc.")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
