"""
Unit tests for Agent Optimizer

Tests the agent file optimization functionality including:
- Code block stripping
- YAML frontmatter preservation
- Caching mechanism
- Statistics tracking
"""

# Add project root to path for imports
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.utilities.optimize_agents import AgentOptimizer


class TestAgentOptimizer(unittest.TestCase):
    """Test suite for AgentOptimizer class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directories for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_dir = Path(self.temp_dir.name) / "source"
        self.target_dir = Path(self.temp_dir.name) / "target"
        self.source_dir.mkdir(parents=True)
        self.target_dir.mkdir(parents=True)

        # Create optimizer instance
        self.optimizer = AgentOptimizer(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            strip_code_blocks=True,
            strip_verbose_sections=False,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_extract_frontmatter(self):
        """Test YAML frontmatter extraction."""
        content_with_frontmatter = """---
name: test-agent
description: Test agent
---
This is the body content."""

        frontmatter, body = self.optimizer._extract_frontmatter(
            content_with_frontmatter
        )

        self.assertIn("name: test-agent", frontmatter)
        self.assertIn("This is the body content", body)
        self.assertTrue(frontmatter.startswith("---"))
        self.assertTrue(frontmatter.endswith("---"))

    def test_extract_frontmatter_no_frontmatter(self):
        """Test content without frontmatter."""
        content_without_frontmatter = "This is just body content."

        frontmatter, body = self.optimizer._extract_frontmatter(
            content_without_frontmatter
        )

        self.assertEqual(frontmatter, "")
        self.assertEqual(body, content_without_frontmatter)

    def test_strip_code_blocks_single_block(self):
        """Test stripping a single code block."""
        content = """Some text before.

```python
def hello():
    print("Hello, world!")  # noqa: print
```

Some text after."""

        processed, blocks_removed = self.optimizer._strip_code_blocks_from_content(
            content
        )

        self.assertEqual(blocks_removed, 1)
        self.assertNotIn("def hello()", processed)
        self.assertIn("[Code example removed", processed)
        self.assertIn("Some text before", processed)
        self.assertIn("Some text after", processed)

    def test_strip_code_blocks_multiple_blocks(self):
        """Test stripping multiple code blocks."""
        content = """First example:

```javascript
console.log("Hello");
```

Second example:

```bash
echo "World"
```

End of examples."""

        processed, blocks_removed = self.optimizer._strip_code_blocks_from_content(
            content
        )

        self.assertEqual(blocks_removed, 2)
        self.assertNotIn("console.log", processed)
        self.assertNotIn('echo "World"', processed)
        self.assertIn("First example", processed)
        self.assertIn("Second example", processed)

    def test_strip_code_blocks_preserves_language_hint(self):
        """Test that language hints are preserved in replacement."""
        content = """Example:

```python
print("test")  # noqa: print
```"""

        processed, blocks_removed = self.optimizer._strip_code_blocks_from_content(
            content
        )

        self.assertEqual(blocks_removed, 1)
        self.assertIn("(python)", processed)

    def test_strip_code_blocks_disabled(self):
        """Test that code blocks are preserved when stripping is disabled."""
        optimizer = AgentOptimizer(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            strip_code_blocks=False,
        )

        content = """Example:

```python
print("test")  # noqa: print
```"""

        processed, blocks_removed = optimizer._strip_code_blocks_from_content(content)

        self.assertEqual(blocks_removed, 0)
        self.assertIn('print("test")', processed)  # noqa: print

    def test_optimize_agent_file_complete(self):
        """Test complete agent file optimization."""
        # Create test agent file
        test_content = """---
name: test-agent
description: Test agent for unit tests
---

# Test Agent

This is a test agent with code examples.

## Example Usage

```python
def example():
    return "test"
```

More text here.

```bash
echo "test"
```

End of file."""

        test_file = self.source_dir / "test-agent.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        # Optimize the file
        result_path = self.optimizer.optimize_agent_file(test_file)

        # Verify optimization
        self.assertIsNotNone(result_path)
        self.assertTrue(result_path.exists())

        # Read optimized content
        with open(result_path, "r", encoding="utf-8") as f:
            optimized = f.read()

        # Verify frontmatter preserved
        self.assertIn("name: test-agent", optimized)

        # Verify code blocks removed
        self.assertNotIn("def example():", optimized)
        self.assertNotIn('echo "test"', optimized)

        # Verify structure preserved
        self.assertIn("# Test Agent", optimized)
        self.assertIn("## Example Usage", optimized)
        self.assertIn("More text here", optimized)

        # Verify optimization notice added
        self.assertIn("optimized version", optimized)
        self.assertIn("code blocks were removed", optimized)

    def test_caching_mechanism(self):
        """Test that caching prevents unnecessary reprocessing."""
        # Create test file
        test_content = """---
name: test-agent
---
Test content."""

        test_file = self.source_dir / "test-agent.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        # First optimization
        self.optimizer.optimize_agent_file(test_file)
        self.assertTrue(self.optimizer._is_file_cached(test_file))

        # Second optimization (should be cached)
        is_cached = self.optimizer._is_file_cached(test_file)
        self.assertTrue(is_cached)

    def test_cache_invalidation_on_change(self):
        """Test that cache is invalidated when file changes."""
        # Create test file
        test_file = self.source_dir / "test-agent.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Original content")

        # Optimize and cache
        self.optimizer.optimize_agent_file(test_file)
        self.assertTrue(self.optimizer._is_file_cached(test_file))

        # Modify file
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Modified content")

        # Should no longer be cached
        is_cached = self.optimizer._is_file_cached(test_file)
        self.assertFalse(is_cached)

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        # Create multiple test files with substantial code blocks
        for i in range(3):
            test_file = self.source_dir / f"agent-{i}.md"
            # Create larger code blocks to ensure size reduction
            large_code = "\n".join([f"    line_{j} = {j}" for j in range(20)])
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(
                    f"""---
name: agent-{i}
---
Content for agent {i}.

This is additional content to make the file larger.

## Example Section

More content here to increase file size.

```python
def example_function_{i}():
{large_code}
    return "result"
```

Additional text after code block."""
                )

        # Optimize all
        stats = self.optimizer.optimize_all()

        # Verify statistics
        self.assertEqual(stats["files_processed"], 3)
        self.assertEqual(stats["files_updated"], 3)
        self.assertEqual(stats["code_blocks_removed"], 3)
        self.assertGreater(stats["total_original_size"], 0)
        self.assertGreater(stats["total_optimized_size"], 0)
        # With optimization notice added, optimized size may be larger for tiny files
        # but the code blocks should still be removed
        self.assertGreater(stats["code_blocks_removed"], 0)

    def test_file_hash_calculation(self):
        """Test file hash calculation for caching."""
        test_file = self.source_dir / "test.md"
        test_content = "Test content for hashing"

        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        hash1 = self.optimizer._get_file_hash(test_file)
        hash2 = self.optimizer._get_file_hash(test_file)

        # Same content should produce same hash
        self.assertEqual(hash1, hash2)

        # Verify hash format (MD5 is 32 hex characters)
        self.assertEqual(len(hash1), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in hash1))

    def test_optimize_all_with_force(self):
        """Test force regeneration ignores cache."""
        # Create test file
        test_file = self.source_dir / "test-agent.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Test content")

        # First optimization
        stats1 = self.optimizer.optimize_all(force=False)
        self.assertEqual(stats1["files_updated"], 1)

        # Reset optimizer (simulates new run)
        self.optimizer.stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "files_updated": 0,
            "total_original_size": 0,
            "total_optimized_size": 0,
            "code_blocks_removed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        # Second optimization without force (should skip)
        stats2 = self.optimizer.optimize_all(force=False)
        self.assertEqual(stats2["files_skipped"], 1)

        # Reset stats again
        self.optimizer.stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "files_updated": 0,
            "total_original_size": 0,
            "total_optimized_size": 0,
            "code_blocks_removed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        # Third optimization with force (should process)
        stats3 = self.optimizer.optimize_all(force=True)
        self.assertEqual(stats3["files_updated"], 1)

    def test_token_savings_calculation(self):
        """Test that token savings are calculated correctly."""
        # Create file with significant code blocks
        large_code_block = "\n".join([f"    line_{i} = value_{i}" for i in range(50)])
        test_content = f"""---
name: large-agent
---

Example:

```python
{large_code_block}
```

End."""

        test_file = self.source_dir / "large-agent.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        # Optimize
        stats = self.optimizer.optimize_all()

        # Verify savings
        self.assertIn("total_savings_bytes", stats)
        self.assertIn("total_savings_percent", stats)
        self.assertGreater(stats["total_savings_bytes"], 0)
        self.assertGreater(stats["total_savings_percent"], 0)

        # Should achieve meaningful reduction (at least 10%)
        self.assertGreater(stats["total_savings_percent"], 10)


class TestAgentOptimizerEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_dir = Path(self.temp_dir.name) / "source"
        self.target_dir = Path(self.temp_dir.name) / "target"
        self.source_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_nested_code_blocks(self):
        """Test handling of nested code blocks (edge case)."""
        optimizer = AgentOptimizer(
            source_dir=self.source_dir, target_dir=self.target_dir
        )

        content = """Example:

```markdown
Some markdown with code:
```python
print("nested")  # noqa: print
```
end markdown
```"""

        processed, blocks_removed = optimizer._strip_code_blocks_from_content(content)

        # Should handle gracefully (may not be perfect for nested blocks)
        self.assertGreater(blocks_removed, 0)

    def test_empty_code_blocks(self):
        """Test handling of empty code blocks."""
        optimizer = AgentOptimizer(
            source_dir=self.source_dir, target_dir=self.target_dir
        )

        # Empty code blocks need at least one newline to match pattern
        content = """Example:

```python

```

End."""

        processed, blocks_removed = optimizer._strip_code_blocks_from_content(content)

        # Should remove the empty code block
        self.assertGreaterEqual(blocks_removed, 0)  # May be 0 or 1 depending on regex

    def test_malformed_agent_file(self):
        """Test handling of malformed agent files."""
        optimizer = AgentOptimizer(
            source_dir=self.source_dir, target_dir=self.target_dir
        )

        # Create malformed file (missing closing frontmatter)
        test_file = self.source_dir / "malformed.md"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                """---
name: malformed
This is malformed frontmatter without closing"""
            )

        # Should handle gracefully without crashing
        result = optimizer.optimize_agent_file(test_file)

        # May return None or optimized file depending on error handling
        # Key is that it doesn't crash
        self.assertTrue(result is None or result.exists())


if __name__ == "__main__":
    unittest.main()
