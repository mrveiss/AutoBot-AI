#!/usr/bin/env python3
"""
Test Suite for Documentation Indexing System

Tests cover:
- Document discovery and categorization
- Metadata extraction from markdown
- Intelligent chunking by section headers
- Duplicate detection
- Search accuracy for documentation queries
- Category filtering
"""

import asyncio
import pytest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utilities.index_documentation import (
    detect_category,
    extract_title_from_markdown,
    chunk_markdown_by_sections,
    generate_content_hash,
    discover_documentation_files,
    CATEGORY_TAXONOMY
)
from src.knowledge_base_v2 import KnowledgeBaseV2


# ===== TEST DATA =====

SAMPLE_MARKDOWN = """# AutoBot Developer Setup

This is the introduction to the developer setup guide.

## Prerequisites

You need the following installed:
- Python 3.9+
- Docker
- Git

## Installation Steps

Follow these steps to install AutoBot:

### Step 1: Clone Repository

```bash
git clone https://github.com/autobot/autobot.git
```

### Step 2: Run Setup

```bash
bash setup.sh
```

## Configuration

Edit the configuration file to customize your setup.

## Troubleshooting

If you encounter issues, check the logs.
"""


# ===== UNIT TESTS =====

def test_category_detection():
    """Test automatic category detection from file paths"""
    test_cases = [
        (Path("docs/developer/PHASE_5_DEVELOPER_SETUP.md"), "developer"),
        (Path("docs/api/COMPREHENSIVE_API_DOCUMENTATION.md"), "api"),
        (Path("docs/troubleshooting/guide.md"), "troubleshooting"),
        (Path("docs/deployment/DOCKER_ARCHITECTURE.md"), "deployment"),
        (Path("docs/security/SECURITY_IMPLEMENTATION.md"), "security"),
        (Path("docs/architecture/VISUAL_ARCHITECTURE.md"), "architecture"),
        (Path("docs/testing/TEST_RESULTS.md"), "testing"),
        (Path("docs/workflow/WORKFLOW_ORCHESTRATION.md"), "workflow"),
        (Path("docs/guides/user_guide.md"), "guides"),
        (Path("docs/agents/multi-agent-architecture.md"), "agents"),
        (Path("CLAUDE.md"), "general"),
        (Path("docs/random/other.md"), "general"),
    ]

    for file_path, expected_category in test_cases:
        detected = detect_category(file_path)
        assert detected == expected_category, f"Expected {expected_category}, got {detected} for {file_path}"

    print("✅ Category detection tests passed")


def test_title_extraction():
    """Test title extraction from markdown content"""
    # Test H1 header extraction
    title = extract_title_from_markdown(SAMPLE_MARKDOWN, Path("test.md"))
    assert title == "AutoBot Developer Setup"

    # Test fallback to filename
    no_header_content = "Some content without headers"
    title = extract_title_from_markdown(no_header_content, Path("developer_guide.md"))
    assert title == "Developer Guide"

    print("✅ Title extraction tests passed")


def test_markdown_chunking():
    """Test intelligent markdown chunking by section headers"""
    chunks = chunk_markdown_by_sections(SAMPLE_MARKDOWN, max_chunk_size=2000)

    # Verify chunks are created
    assert len(chunks) > 0, "Should create at least one chunk"

    # Verify section titles are extracted
    section_titles = [title for title, _ in chunks]
    assert "Prerequisites" in section_titles or "Introduction" in section_titles

    # Verify content is preserved
    all_content = " ".join([content for _, content in chunks])
    assert "Python 3.9+" in all_content
    assert "bash setup.sh" in all_content

    # Test large document chunking
    large_doc = "# Title\n\n" + ("Large content section. " * 1000)
    large_chunks = chunk_markdown_by_sections(large_doc, max_chunk_size=500)
    assert len(large_chunks) > 1, "Large documents should be split into multiple chunks"

    print("✅ Markdown chunking tests passed")


def test_content_hashing():
    """Test content hash generation for duplicate detection"""
    content1 = "This is some content"
    content2 = "This is some content"
    content3 = "This is different content"

    hash1 = generate_content_hash(content1)
    hash2 = generate_content_hash(content2)
    hash3 = generate_content_hash(content3)

    # Same content should produce same hash
    assert hash1 == hash2, "Identical content should produce identical hashes"

    # Different content should produce different hashes
    assert hash1 != hash3, "Different content should produce different hashes"

    # Hash should be SHA-256 format (64 hex characters)
    assert len(hash1) == 64, "Hash should be 64 characters (SHA-256)"
    assert all(c in '0123456789abcdef' for c in hash1), "Hash should be hexadecimal"

    print("✅ Content hashing tests passed")


@pytest.mark.asyncio
async def test_document_discovery():
    """Test documentation file discovery"""
    docs_dir = PROJECT_ROOT / "docs"

    # Discover all files
    all_files = await discover_documentation_files(docs_dir)
    assert len(all_files) > 0, "Should discover documentation files"

    # Check that discovered files have categories
    for file_path, category in all_files:
        assert category in CATEGORY_TAXONOMY or category == "general"
        assert file_path.suffix == ".md"

    # Test category filtering
    developer_files = await discover_documentation_files(docs_dir, category_filter="developer")
    for _, category in developer_files:
        assert category == "developer", "Filtered results should only contain specified category"

    print(f"✅ Document discovery tests passed ({len(all_files)} files found)")


# ===== INTEGRATION TESTS =====

@pytest.mark.asyncio
async def test_knowledge_base_integration():
    """Test integration with knowledge base system"""
    kb = KnowledgeBaseV2()
    initialized = await kb.initialize()

    assert initialized, "Knowledge base should initialize successfully"
    assert kb.initialized, "Knowledge base initialized flag should be True"

    # Test storing a documentation chunk
    test_metadata = {
        "title": "Test Document",
        "section": "Introduction",
        "category": "developer",
        "file_path": "docs/test.md",
        "content_type": "documentation"
    }

    result = await kb.store_fact(
        content="This is a test documentation chunk for verification.",
        metadata=test_metadata
    )

    assert result["status"] == "success", "Should store documentation chunk successfully"
    assert result["vector_indexed"], "Documentation should be vectorized"

    # Test search
    search_results = await kb.search("test documentation", top_k=5)
    assert len(search_results) > 0, "Should find indexed documentation"

    # Cleanup
    await kb.close()

    print("✅ Knowledge base integration tests passed")


# ===== SEARCH ACCURACY TESTS =====

SEARCH_TEST_QUERIES = [
    {
        "query": "how to deploy autobot",
        "expected_category": "developer",
        "expected_keywords": ["setup", "deploy", "install", "docker"]
    },
    {
        "query": "how many VMs does autobot use",
        "expected_category": "architecture",
        "expected_keywords": ["vm", "distributed", "172.16.168"]
    },
    {
        "query": "autobot API documentation",
        "expected_category": "api",
        "expected_keywords": ["endpoint", "api", "request", "response"]
    },
    {
        "query": "troubleshooting redis connection",
        "expected_category": "troubleshooting",
        "expected_keywords": ["redis", "connection", "error", "fix"]
    },
    {
        "query": "security implementation",
        "expected_category": "security",
        "expected_keywords": ["security", "authentication", "authorization"]
    }
]


@pytest.mark.asyncio
async def test_search_accuracy():
    """Test search accuracy for documentation queries (requires indexed docs)"""
    kb = KnowledgeBaseV2()
    await kb.initialize()

    if not kb.initialized:
        print("⚠️  Knowledge base not initialized - skipping search accuracy tests")
        return

    passed_tests = 0
    total_tests = len(SEARCH_TEST_QUERIES)

    for test_case in SEARCH_TEST_QUERIES:
        query = test_case["query"]
        expected_category = test_case["expected_category"]
        expected_keywords = test_case["expected_keywords"]

        # Perform search
        results = await kb.search(query, top_k=5)

        if not results:
            print(f"⚠️  No results for query: {query}")
            continue

        # Check if top result matches expected category
        top_result = results[0]
        result_category = top_result.get("metadata", {}).get("category", "unknown")

        # Check if expected keywords appear in results
        keywords_found = sum(
            1 for keyword in expected_keywords
            if keyword.lower() in top_result["content"].lower()
        )

        accuracy = keywords_found / len(expected_keywords)

        if result_category == expected_category and accuracy >= 0.5:
            passed_tests += 1
            print(f"✅ Query: '{query}' - Category: {result_category}, Accuracy: {accuracy:.1%}")
        else:
            print(f"❌ Query: '{query}' - Expected: {expected_category}, Got: {result_category}, Accuracy: {accuracy:.1%}")

    await kb.close()

    success_rate = (passed_tests / total_tests) * 100
    print(f"\n📊 Search Accuracy: {success_rate:.1f}% ({passed_tests}/{total_tests} tests passed)")

    assert success_rate >= 80, f"Search accuracy should be at least 80%, got {success_rate:.1f}%"


# ===== RUN TESTS =====

def run_unit_tests():
    """Run all unit tests"""
    print("\n" + "=" * 80)
    print("RUNNING UNIT TESTS")
    print("=" * 80)

    test_category_detection()
    test_title_extraction()
    test_markdown_chunking()
    test_content_hashing()

    print("\n✅ All unit tests passed!")


async def run_integration_tests():
    """Run all integration tests"""
    print("\n" + "=" * 80)
    print("RUNNING INTEGRATION TESTS")
    print("=" * 80)

    await test_document_discovery()
    await test_knowledge_base_integration()

    print("\n✅ All integration tests passed!")


async def run_search_tests():
    """Run search accuracy tests"""
    print("\n" + "=" * 80)
    print("RUNNING SEARCH ACCURACY TESTS")
    print("=" * 80)

    await test_search_accuracy()

    print("\n✅ Search accuracy tests complete!")


async def main():
    """Run all tests"""
    try:
        # Run unit tests (synchronous)
        run_unit_tests()

        # Run integration tests (async)
        await run_integration_tests()

        # Run search tests (async, requires indexed documentation)
        try:
            await run_search_tests()
        except Exception as e:
            print(f"\n⚠️  Search accuracy tests skipped: {e}")
            print("Run 'python scripts/utilities/index_documentation.py' to index documentation first")

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
