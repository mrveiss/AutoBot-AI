#!/usr/bin/env python3
"""
Test suite for AutoBot semantic chunking functionality.
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.semantic_chunker import AutoBotSemanticChunker, SemanticChunk


class TestSemanticChunking:
    """Test cases for semantic chunking functionality."""

    def __init__(self):
        self.chunker = AutoBotSemanticChunker(
            embedding_model="all-MiniLM-L6-v2",
            percentile_threshold=95.0,
            min_chunk_size=50,
            max_chunk_size=500,
        )

    async def test_basic_chunking(self):
        """Test basic semantic chunking functionality."""
        print("Testing basic semantic chunking...")

        test_text = """
        AutoBot is an intelligent automation platform. It uses advanced AI techniques to process information.

        The system includes multiple components. First, there's the knowledge base which stores information.
        Second, the LLM interface handles language model interactions.

        Performance optimization is critical. We use semantic chunking to improve accuracy.
        Semantic chunking breaks text into contextually meaningful segments.
        This approach is better than simple sentence splitting.
        """

        chunks = await self.chunker.chunk_text(test_text)

        print(f"✓ Created {len(chunks)} semantic chunks")

        for i, chunk in enumerate(chunks):
            print(
                f"  Chunk {i+1}: {len(chunk.content)} chars, "
                f"coherence: {chunk.semantic_score:.3f}"
            )
            print(f"    Preview: {chunk.content[:100]}...")

        assert len(chunks) > 1, "Should create multiple chunks"
        assert all(
            isinstance(chunk, SemanticChunk) for chunk in chunks
        ), "All chunks should be SemanticChunk instances"

        return chunks

    async def test_small_text_handling(self):
        """Test handling of small text that shouldn't be chunked."""
        print("Testing small text handling...")

        small_text = "This is a short piece of text that should remain as one chunk."

        chunks = await self.chunker.chunk_text(small_text)

        print(f"✓ Small text created {len(chunks)} chunk(s)")
        assert len(chunks) == 1, "Small text should create only one chunk"
        assert (
            chunks[0].content.strip() == small_text.strip()
        ), "Content should be preserved"

        return chunks

    async def test_large_text_splitting(self):
        """Test handling of large text that exceeds max chunk size."""
        print("Testing large text splitting...")

        # Create text that will definitely exceed max_chunk_size (500)
        large_text = " ".join(
            [
                f"This is sentence number {i}. It contains information about topic {i}."
                for i in range(1, 100)
            ]
        )

        chunks = await self.chunker.chunk_text(large_text)

        print(f"✓ Large text created {len(chunks)} chunks")

        for chunk in chunks:
            assert (
                len(chunk.content) <= self.chunker.max_chunk_size + 100
            ), f"Chunk size {len(chunk.content)} exceeds maximum"

        return chunks

    async def test_document_format_compatibility(self):
        """Test LlamaIndex document format compatibility."""
        print("Testing document format compatibility...")

        test_content = """
        This is a test document for compatibility testing.
        It should be processed into LlamaIndex-compatible format.

        The system should preserve metadata and provide proper chunk information.
        Each chunk should have coherence scores and sentence counts.
        """

        metadata = {"title": "Test Document", "source": "test", "category": "testing"}

        documents = await self.chunker.chunk_document(test_content, metadata)

        print(f"✓ Created {len(documents)} LlamaIndex-compatible documents")

        for doc in documents:
            assert "text" in doc, "Document should have text field"
            assert "metadata" in doc, "Document should have metadata field"
            assert "semantic_score" in doc["metadata"], "Should include semantic score"
            assert "sentence_count" in doc["metadata"], "Should include sentence count"

        return documents

    async def test_chunking_coherence(self):
        """Test that semantic chunking creates coherent chunks."""
        print("Testing chunking coherence...")

        coherent_text = """
        Machine learning is a subset of artificial intelligence. It focuses on algorithms that learn from data.
        Neural networks are a type of machine learning model. They are inspired by biological neural networks.

        Python is a popular programming language. It has extensive libraries for data science.
        Libraries like NumPy and Pandas are widely used. They provide efficient data manipulation tools.

        Cloud computing has revolutionized software deployment. Services like AWS and Azure are common.
        Containerization with Docker is now standard practice. Kubernetes orchestrates container deployments.
        """

        chunks = await self.chunker.chunk_text(coherent_text)

        print(f"✓ Coherent text created {len(chunks)} chunks")

        # Check that chunks have reasonable coherence scores
        avg_coherence = sum(chunk.semantic_score for chunk in chunks) / len(chunks)
        print(f"  Average coherence score: {avg_coherence:.3f}")

        assert avg_coherence > 0.3, f"Average coherence {avg_coherence} seems too low"

        return chunks, avg_coherence

    async def test_error_handling(self):
        """Test error handling and fallback mechanisms."""
        print("Testing error handling...")

        # Test with empty text
        empty_chunks = await self.chunker.chunk_text("")
        print(f"✓ Empty text handled: {len(empty_chunks)} chunks")

        # Test with very short text
        short_chunks = await self.chunker.chunk_text("Short.")
        print(f"✓ Very short text handled: {len(short_chunks)} chunks")

        # Test with special characters
        special_text = "Text with émojis 🚀 and spëcial characters: @#$%^&*()!"
        special_chunks = await self.chunker.chunk_text(special_text)
        print(f"✓ Special characters handled: {len(special_chunks)} chunks")

        return True

    async def run_all_tests(self):
        """Run all semantic chunking tests."""
        print("=" * 60)
        print("AutoBot Semantic Chunking Test Suite")
        print("=" * 60)

        try:
            # Test basic functionality
            basic_chunks = await self.test_basic_chunking()
            print()

            # Test edge cases
            await self.test_small_text_handling()
            print()

            await self.test_large_text_splitting()
            print()

            # Test compatibility
            documents = await self.test_document_format_compatibility()
            print()

            # Test quality
            coherent_chunks, coherence = await self.test_chunking_coherence()
            print()

            # Test error handling
            error_handling = await self.test_error_handling()
            print()

            print("=" * 60)
            print("✅ All Semantic Chunking Tests Passed!")
            print("=" * 60)
            print("Summary:")
            print(f"  - Basic chunking: {len(basic_chunks)} chunks")
            print(f"  - Document compatibility: {len(documents)} documents")
            print(f"  - Average coherence: {coherence:.3f}")
            print(f"  - Error handling: {'✓' if error_handling else '✗'}")

            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestSemanticChunking()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 Semantic chunking implementation is working correctly!")
        return 0
    else:
        print("\n💥 Semantic chunking tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
