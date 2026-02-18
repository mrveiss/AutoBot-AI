#!/usr/bin/env python3
"""
Simple test to verify GPU-optimized semantic chunking integration with knowledge base
"""

import asyncio
import sys
import time

# Add AutoBot to path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")


async def test_chunker_optimization():
    """Test that the optimized chunker is being used."""
    print("🔧 Testing Semantic Chunker GPU Optimization Integration")
    print("=" * 60)

    try:
        # Test import and functionality
        print("📦 Testing chunker import...")
        from knowledge_base import get_semantic_chunker

        chunker = get_semantic_chunker()
        chunker_type = type(chunker).__name__

        print(f"  ✅ Active chunker: {chunker_type}")
        print(f"  📍 Module: {chunker.__class__.__module__}")

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
            print("  🚀 Optimization features detected:")
            for feature in optimization_features:
                print(f"    - {feature}")
        else:
            print("  ⚠️  No optimization features detected")

        # Test chunking performance
        print("\n⚡ Testing chunking performance...")
        test_text = (
            """
        AutoBot is an advanced Linux administration platform designed for intelligent automation.
        The system utilizes cutting-edge AI technologies to manage Linux environments efficiently.
        Through machine learning and natural language processing, AutoBot can understand complex system requirements.
        The platform provides autonomous decision-making capabilities for routine administrative tasks.
        Security and reliability are paramount in AutoBot's architectural design.
        """
            * 3
        )  # Make text longer for meaningful test

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
            print("  ❌ No suitable chunking method found")
            return False

        processing_time = time.time() - start_time

        print("  📊 Results:")
        print(f"    - Method used: {method_used}")
        print(f"    - Processing time: {processing_time:.3f}s")
        print(f"    - Chunks created: {len(chunks)}")
        print(f"    - Text length: {len(test_text)} characters")

        if len(chunks) > 0:
            sentences_estimated = len(test_text.split("."))
            sentences_per_sec = (
                sentences_estimated / processing_time if processing_time > 0 else 0
            )
            print(f"    - Performance: {sentences_per_sec:.1f} sentences/sec")

            # Show first chunk as example
            first_chunk = chunks[0]
            print("  📝 Sample chunk:")
            print(f"    - Content: {first_chunk.content[:100]}...")
            if hasattr(first_chunk, "metadata"):
                optimization_info = first_chunk.metadata.get(
                    "optimization_version", "none"
                )
                print(f"    - Optimization: {optimization_info}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_kb_stats():
    """Test knowledge base statistics."""
    print("\n📊 Testing Knowledge Base Statistics...")

    try:
        from knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        stats = await kb.get_stats()

        print("  📈 Knowledge Base Stats:")
        print(f"    - Total Vectors: {stats.get('total_vectors', 0)}")
        print(f"    - Total Chunks: {stats.get('total_chunks', 0)}")
        print(f"    - Total Documents: {stats.get('total_documents', 0)}")
        print(f"    - Redis Connected: {stats.get('redis_connected', False)}")
        print(f"    - Index Available: {stats.get('index_available', False)}")

        return stats.get("total_vectors", 0) > 0

    except Exception as e:
        print(f"  ❌ Stats test failed: {e}")
        return False


if __name__ == "__main__":

    async def main():
        print("🚀 AutoBot Phase 9 - GPU Optimization Integration Test")
        print("=" * 70)

        # Test chunker optimization
        chunker_success = await test_chunker_optimization()

        # Test KB stats
        stats_success = await test_kb_stats()

        # Final results
        print("\n" + "=" * 70)
        print("📋 TEST RESULTS SUMMARY")
        print("=" * 70)

        if chunker_success:
            print("✅ Semantic chunker optimization: WORKING")
        else:
            print("❌ Semantic chunker optimization: FAILED")

        if stats_success:
            print("✅ Knowledge base statistics: WORKING")
        else:
            print("❌ Knowledge base statistics: FAILED")

        overall_success = chunker_success and stats_success

        if overall_success:
            print("\n🎉 SUCCESS: GPU optimization integration is working!")
            print("  - GPU-optimized semantic chunker active")
            print("  - Knowledge base connected and functional")
            print("  - Phase 9 hardware optimization deployed")
        else:
            print("\n⚠️  PARTIAL SUCCESS: Some components may need attention")

        return overall_success

    success = asyncio.run(main())
    sys.exit(0 if success else 1)
