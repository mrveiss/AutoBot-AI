#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple demonstration of the AutoBot Codebase Indexing Service

This script demonstrates the key functionality without complex testing infrastructure.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def demo_indexing():
    """Demonstrate the codebase indexing functionality"""
    print("🚀 AutoBot Codebase Indexing Service Demo")
    print("=" * 50)

    try:
        # Test 1: Import the indexing service
        print("\n1️⃣  Importing indexing service...")
        from src.services.codebase_indexing_service import (
            get_indexing_service,
            index_autobot_codebase,
        )

        print("✅ Successfully imported codebase indexing service")

        # Test 2: Create indexing service instance
        print("\n2️⃣  Creating indexing service...")
        service = get_indexing_service()
        print(f"✅ Indexing service created for: {service.root_path}")
        print(f"   Include patterns: {len(service.include_patterns)} file types")
        print(f"   Category mapping: {len(service.category_mapping)} categories")

        # Test 3: Scan files
        print("\n3️⃣  Scanning codebase files...")
        files = service._scan_files()
        print(f"✅ Found {len(files)} indexable files")

        # Show file breakdown by category
        category_counts = {}
        for file_info in files[:50]:  # Show first 50 files
            category = file_info.category
            category_counts[category] = category_counts.get(category, 0) + 1

        print("   File breakdown by category:")
        for category, count in sorted(category_counts.items()):
            print(f"     {category}: {count} files")

        # Test 4: Test knowledge base connection
        print("\n4️⃣  Testing knowledge base connection...")
        try:
            from src.knowledge_base_factory import get_knowledge_base

            kb = await get_knowledge_base()
            if kb:
                print("✅ Knowledge base connection successful")

                # Get current stats
                try:
                    stats = await kb.get_stats()
                    print(f"   Current facts: {stats.get('total_facts', 0)}")
                    print(f"   Current documents: {stats.get('total_documents', 0)}")
                except Exception as e:
                    print(f"   Stats error: {e}")
            else:
                print("❌ Knowledge base connection failed")
                return False
        except Exception as e:
            print(f"❌ Knowledge base error: {e}")
            return False

        # Test 5: Quick indexing demo
        print("\n5️⃣  Running quick indexing demo (3 files)...")
        try:
            progress = await index_autobot_codebase(max_files=3, batch_size=1)

            print("✅ Quick indexing completed!")
            print(f"   Files processed: {progress.processed_files}")
            print(f"   Successful files: {progress.successful_files}")
            print(f"   Chunks created: {progress.total_chunks}")
            print(f"   Progress: {progress.progress_percentage:.1f}%")

            if progress.errors:
                print(f"   Errors: {len(progress.errors)}")

        except Exception as e:
            print(f"❌ Indexing demo failed: {e}")
            return False

        # Test 6: Verify indexing results
        print("\n6️⃣  Verifying indexing results...")
        try:
            stats_after = await kb.get_stats()
            print("✅ Updated statistics:")
            print(f"   Total facts: {stats_after.get('total_facts', 0)}")
            print(f"   Total documents: {stats_after.get('total_documents', 0)}")
            print(f"   Categories: {stats_after.get('categories', [])}")

            facts_count = stats_after.get("total_facts", 0)
            if facts_count > 0:
                print(f"✅ Knowledge base now contains {facts_count} indexed items")
            else:
                print("⚠️  No facts found in knowledge base")

        except Exception as e:
            print(f"❌ Stats verification failed: {e}")

        print("\n🎉 Demo completed successfully!")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return False


async def main():
    """Main demo function"""
    success = await demo_indexing()

    print("\n" + "=" * 50)
    if success:
        print("✅ DEMO SUCCESSFUL")
        print("\n🎯 The codebase indexing system is working correctly!")
        print("\nNext steps:")
        print("1. Start the AutoBot backend: bash run_autobot.sh --dev")
        print("2. Use API endpoint: POST /api/knowledge/quick_index")
        print("3. Check Knowledge Manager in the frontend")
        print("4. Search the indexed codebase")
    else:
        print("❌ DEMO FAILED")
        print("Please check the error messages above.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
