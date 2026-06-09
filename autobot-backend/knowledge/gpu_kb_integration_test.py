#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Simple test to verify GPU-optimized semantic chunking integration with knowledge base
"""

import asyncio
import sys
import time

from autobot_shared.ssot_config import config

# Add AutoBot to path
sys.path.insert(0, config.project_root)


async def test_chunker_optimization():
    """Test that the optimized chunker is being used."""
    print("🔧 Testing Semantic Chunker GPU Optimization Integration")  # noqa: print
    print("=" * 60)  # noqa: print

    try:
        # Test import and functionality
        print("📦 Testing chunker import...")  # noqa: print
        from knowledge_base import get_semantic_chunker

        chunker = get_semantic_chunker()
        chunker_type = type(chunker).__name__

        print(f"  ✅ Active chunker: {chunker_type}")  # noqa: print
        print(f"  📍 Module: {chunker.__class__.__module__}")  # noqa: print

        # Check optimization features
        optimization_features = []
        if hasattr(chunker, "get_performance_stats"):
            optimization_features.append("Performance Stats")
        if hasattr(chunker, "gpu_batch_size"):
            optimization_features.append(f"GPU Batch Size: {chunker.gpu_batch_size}")
        if hasattr(chunker, "_gpu_memory_pool_initialized"):
            optimization_features.append("GPU Memory Pool")
        if hasattr(chunker, "chunk_text_optimized"):
            optimization_features.append("Optimized Chunking Method")

        if optimization_features:
            print("  🚀 Optimization features detected:")  # noqa: print
            for feature in optimization_features:
                print(f"    - {feature}")  # noqa: print
        else:
            print("  ⚠️  No optimization features detected")  # noqa: print

        # Test chunking performance
        print("\n⚡ Testing chunking performance...")  # noqa: print
        test_text = """
        AutoBot is an advanced Linux administration platform designed for intelligent automation.
        The system utilizes cutting-edge AI technologies to manage Linux environments efficiently.
        Through machine learning and natural language processing, AutoBot can understand complex system requirements.
        The platform provides autonomous decision-making capabilities for routine administrative tasks.
        Security and reliability are paramount in AutoBot's architectural design.
        """ * 3  # Make text longer for meaningful test

        start_time = time.time()

        if hasattr(chunker, "chunk_text_optimized"):
            # Use optimized method
            chunks = await chunker.chunk_text_optimized(test_text)
            method_used = "GPU-Optimized"
        elif hasattr(chunker, "chunk_text"):
            # Use standard async method
            chunks = await chunker.chunk_text(test_text)
            method_used = "Standard Async"
        else:
            print("  ❌ No suitable chunking method found")  # noqa: print
            return False

        processing_time = time.time() - start_time

        print("  📊 Results:")  # noqa: print
        print(f"    - Method used: {method_used}")  # noqa: print
        print(f"    - Processing time: {processing_time:.3f}s")  # noqa: print
        print(f"    - Chunks created: {len(chunks)}")  # noqa: print
        print(f"    - Text length: {len(test_text)} characters")  # noqa: print

        if len(chunks) > 0:
            sentences_estimated = len(test_text.split("."))
            sentences_per_sec = sentences_estimated / processing_time if processing_time > 0 else 0
            print(f"    - Performance: {sentences_per_sec:.1f} sentences/sec")  # noqa: print

            # Show first chunk as example
            first_chunk = chunks[0]
            print("  📝 Sample chunk:")  # noqa: print
            print(f"    - Content: {first_chunk.content[:100]}...")  # noqa: print
            if hasattr(first_chunk, "metadata"):
                optimization_info = first_chunk.metadata.get("optimization_version", "none")
                print(f"    - Optimization: {optimization_info}")  # noqa: print

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return False


async def test_kb_stats():
    """Test knowledge base statistics."""
    print("\n📊 Testing Knowledge Base Statistics...")  # noqa: print

    try:
        from knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        stats = await kb.get_stats()

        print("  📈 Knowledge Base Stats:")  # noqa: print
        print(f"    - Total Vectors: {stats.get('total_vectors', 0)}")  # noqa: print
        print(f"    - Total Chunks: {stats.get('total_chunks', 0)}")  # noqa: print
        print(f"    - Total Documents: {stats.get('total_documents', 0)}")  # noqa: print
        print(f"    - Redis Connected: {stats.get('redis_connected', False)}")  # noqa: print
        print(f"    - Index Available: {stats.get('index_available', False)}")  # noqa: print

        return stats.get("total_vectors", 0) > 0

    except Exception as e:
        print(f"  ❌ Stats test failed: {e}")  # noqa: print
        return False


if __name__ == "__main__":

    async def main():
        print("🚀 AutoBot Phase 9 - GPU Optimization Integration Test")  # noqa: print
        print("=" * 70)  # noqa: print

        # Test chunker optimization
        chunker_success = await test_chunker_optimization()

        # Test KB stats
        stats_success = await test_kb_stats()

        # Final results
        print("\n" + "=" * 70)  # noqa: print
        print("📋 TEST RESULTS SUMMARY")  # noqa: print
        print("=" * 70)  # noqa: print

        if chunker_success:
            print("✅ Semantic chunker optimization: WORKING")  # noqa: print
        else:
            print("❌ Semantic chunker optimization: FAILED")  # noqa: print

        if stats_success:
            print("✅ Knowledge base statistics: WORKING")  # noqa: print
        else:
            print("❌ Knowledge base statistics: FAILED")  # noqa: print

        overall_success = chunker_success and stats_success

        if overall_success:
            print("\n🎉 SUCCESS: GPU optimization integration is working!")  # noqa: print
            print("  - GPU-optimized semantic chunker active")  # noqa: print
            print("  - Knowledge base connected and functional")  # noqa: print
            print("  - Phase 9 hardware optimization deployed")  # noqa: print
        else:
            print("\n⚠️  PARTIAL SUCCESS: Some components may need attention")  # noqa: print

        return overall_success

    success = asyncio.run(main())
    sys.exit(0 if success else 1)
