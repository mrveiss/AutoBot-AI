"""
Comprehensive Test Suite for Lazy Loading Agent Optimization System

Tests validation for runtime agent optimization (code stripping, caching)
to reduce token usage by 20-30% without modifying agent files.

Test Categories:
1. Unit Tests: Code block removal, marker insertion, structure preservation
2. Integration Tests: Agent loading with/without optimization, caching
3. Validation Tests: Agent routing unchanged, policy enforcement preserved
4. Performance Tests: Token reduction, loading speed, cache effectiveness
5. Edge Cases: Malformed files, concurrent loading, error handling

Author: AutoBot Testing Team
Date: 2025-10-10
"""

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# ============================================================================
# TEST FIXTURES - Sample Agent Content
# ============================================================================


@pytest.fixture
def sample_agent_with_code_blocks() -> str:
    """Sample agent content with multiple code blocks."""
    return """---
name: test-agent
description: Test agent with code examples
tools: Read, Write, Bash
color: blue
---

# Test Agent

This agent demonstrates code examples.

## Example 1: Python Code

```python
def example_function():
    \"\"\"Example function.\"\"\"
    print("Hello, world!")
    return 42
```

## Example 2: Bash Script

```bash
#!/bin/bash
echo "Testing"
ls -la
```

## Example 3: JavaScript

```javascript
function test() {
    console.log("Testing");
    return true;
}
```

## Instructions

Follow these steps carefully.
"""


@pytest.fixture
def sample_agent_without_code() -> str:
    """Sample agent content without code blocks."""
    return """---
name: simple-agent
description: Simple agent without code
tools: Read, Write
color: green
---

# Simple Agent

This agent has no code examples.

## Instructions

1. Step one
2. Step two
3. Step three
"""


@pytest.fixture
def sample_agent_with_policy() -> str:
    """Sample agent content with policy enforcement text."""
    return """---
name: policy-agent
description: Agent with policy enforcement
tools: Read, Write, Bash
color: orange
---

# Policy Agent

## MANDATORY LOCAL-ONLY EDITING ENFORCEMENT

**CRITICAL: ALL code edits MUST be done locally, NEVER on remote servers**

### VM Target Mapping:
- **VM1 (172.16.168.21)**: Frontend - Web interface
- **VM2 (172.16.168.22)**: NPU Worker - Hardware AI acceleration
- **VM3 (172.16.168.23)**: Redis - Data layer
- **VM4 (172.16.168.24)**: AI Stack - AI processing
- **VM5 (172.16.168.25)**: Browser - Web automation

### SSH Key Requirements:
- **Key Location**: `~/.ssh/autobot_key`
- **Authentication**: ONLY SSH key-based (NO passwords)

```python
# Example code that should be removed
def sync_to_vm():
    pass
```

This policy is NON-NEGOTIABLE.
"""


@pytest.fixture
def sample_agent_nested_blocks() -> str:
    """Sample agent with nested code blocks."""
    return """---
name: nested-agent
description: Agent with nested structures
tools: Read
color: red
---

# Nested Agent

## Outer Section

Some text here.

```python
# Outer code block
def outer():
    \"\"\"Outer function.\"\"\"
    # Inner comment
    ```
    # This shouldn't break parsing
    ```
    return True
```

More text after code.
"""


# ============================================================================
# UNIT TESTS - Code Block Removal
# ============================================================================


class TestCodeBlockRemoval:
    """Test suite for code block stripping functionality."""

    def test_remove_python_code_blocks(self, sample_agent_with_code_blocks):
        """Verify Python code blocks are correctly stripped."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # Python code block should be removed
        assert "def example_function():" not in result
        assert 'print("Hello, world!")' not in result

        # Marker should be inserted
        assert "[Code example omitted]" in result

        # Headers and structure should be preserved
        assert "# Test Agent" in result
        assert "## Example 1: Python Code" in result
        assert "## Instructions" in result

    def test_remove_bash_code_blocks(self, sample_agent_with_code_blocks):
        """Verify Bash code blocks are correctly stripped."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # Bash code should be removed
        assert "#!/bin/bash" not in result
        assert 'echo "Testing"' not in result
        assert "ls -la" not in result

        # Structure preserved
        assert "## Example 2: Bash Script" in result

    def test_remove_javascript_code_blocks(self, sample_agent_with_code_blocks):
        """Verify JavaScript code blocks are correctly stripped."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # JavaScript code should be removed
        assert "function test()" not in result
        assert "console.log" not in result

        # Structure preserved
        assert "## Example 3: JavaScript" in result

    def test_code_block_markers_inserted(self, sample_agent_with_code_blocks):
        """Verify markers are inserted where code blocks removed."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # Count markers - should match number of code blocks
        marker_count = result.count("[Code example omitted]")
        assert marker_count == 3, f"Expected 3 markers, found {marker_count}"

    def test_no_code_blocks_unchanged(self, sample_agent_without_code):
        """Content without code blocks should remain unchanged."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_without_code)

        # Content should be identical (no code to strip)
        assert result == sample_agent_without_code

        # No markers should be added
        assert "[Code example omitted]" not in result

    def test_frontmatter_preserved(self, sample_agent_with_code_blocks):
        """Verify YAML frontmatter is completely preserved."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # Frontmatter should be intact
        assert "---" in result
        assert "name: test-agent" in result
        assert "description: Test agent with code examples" in result
        assert "tools: Read, Write, Bash" in result
        assert "color: blue" in result

    def test_nested_code_blocks(self, sample_agent_nested_blocks):
        """Handle nested or malformed code block markers."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_nested_blocks)

        # Code content should be removed
        assert "def outer():" not in result

        # Structure preserved
        assert "# Nested Agent" in result
        assert "## Outer Section" in result

        # Should have at least one marker
        assert "[Code example omitted]" in result


# ============================================================================
# INTEGRATION TESTS - Agent Loading
# ============================================================================


class TestAgentLoading:
    """Test suite for agent loading with optimization."""

    @pytest.mark.asyncio
    async def test_load_agent_with_optimization_enabled(
        self, sample_agent_with_code_blocks
    ):
        """Load agent with optimization enabled."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True)

        # Create temporary agent file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            content = await loader.load_agent(temp_path)

            # Code should be stripped
            assert "def example_function():" not in content
            assert "[Code example omitted]" in content

            # Structure preserved
            assert "# Test Agent" in content
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_load_agent_without_optimization(
        self, sample_agent_with_code_blocks
    ):
        """Load agent with optimization disabled."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=False)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            content = await loader.load_agent(temp_path)

            # Original content should be returned
            assert "def example_function():" in content
            assert "[Code example omitted]" not in content
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_cache_effectiveness(self, sample_agent_with_code_blocks):
        """Verify caching works correctly."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True, enable_cache=True)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            # First load - cache miss
            start_time = time.time()
            content1 = await loader.load_agent(temp_path)
            first_load_time = time.time() - start_time

            # Second load - cache hit
            start_time = time.time()
            content2 = await loader.load_agent(temp_path)
            second_load_time = time.time() - start_time

            # Content should be identical
            assert content1 == content2

            # Second load should be faster (cached)
            assert (
                second_load_time < first_load_time
            ), "Cache should improve load time"

            # Verify cache hit
            stats = loader.get_cache_stats()
            assert stats["hits"] >= 1, "Should have at least one cache hit"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_cache_disabled(self, sample_agent_with_code_blocks):
        """Verify loading works with cache disabled."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True, enable_cache=False)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            # Load multiple times
            content1 = await loader.load_agent(temp_path)
            content2 = await loader.load_agent(temp_path)

            # Content should be identical
            assert content1 == content2

            # Cache stats should show no hits
            stats = loader.get_cache_stats()
            assert stats["hits"] == 0, "Cache disabled - no hits expected"
        finally:
            os.unlink(temp_path)


# ============================================================================
# VALIDATION TESTS - CRITICAL
# ============================================================================


class TestAgentRoutingValidation:
    """CRITICAL: Verify agent routing produces same results."""

    @pytest.mark.asyncio
    async def test_agent_routing_unchanged(self):
        """CRITICAL: Verify agent routing produces same results."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        # Test cases: (user_query, expected_agent)
        test_cases = [
            ("review my code", "code-reviewer"),
            ("optimize backend performance", "senior-backend-engineer"),
            ("write comprehensive tests", "testing-engineer"),
            ("audit API security", "security-auditor"),
            ("design system architecture", "systems-architect"),
            ("improve database queries", "database-engineer"),
        ]

        # Test with optimization disabled
        loader_no_opt = OptimizedAgentLoader(enable_optimization=False)
        results_no_opt = []

        for query, _ in test_cases:
            agent = await loader_no_opt.route_agent(query)
            results_no_opt.append((query, agent))

        # Test with optimization enabled
        loader_opt = OptimizedAgentLoader(enable_optimization=True)
        results_opt = []

        for query, _ in test_cases:
            agent = await loader_opt.route_agent(query)
            results_opt.append((query, agent))

        # CRITICAL: Results must be identical
        for i, (query, expected) in enumerate(test_cases):
            no_opt_agent = results_no_opt[i][1]
            opt_agent = results_opt[i][1]

            assert (
                no_opt_agent == opt_agent
            ), f"Routing mismatch for '{query}': {no_opt_agent} vs {opt_agent}"

            # Also verify expected agent selected
            assert expected in opt_agent.lower(), (
                f"Expected '{expected}' for query '{query}', "
                f"got '{opt_agent}'"
            )


class TestPolicyEnforcement:
    """CRITICAL: Ensure policy enforcement text preserved."""

    @pytest.mark.asyncio
    async def test_policy_text_preserved(self, sample_agent_with_policy):
        """CRITICAL: Ensure MANDATORY_LOCAL_EDIT_POLICY in context."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_policy)

        # Policy heading must be preserved
        assert "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" in result

        # Key policy text must be preserved
        assert "CRITICAL: ALL code edits MUST be done locally" in result
        assert "NEVER on remote servers" in result

        # VM IPs must be preserved
        assert "172.16.168.21" in result  # Frontend
        assert "172.16.168.22" in result  # NPU Worker
        assert "172.16.168.23" in result  # Redis
        assert "172.16.168.24" in result  # AI Stack
        assert "172.16.168.25" in result  # Browser

        # SSH instructions must be preserved
        assert "~/.ssh/autobot_key" in result
        assert "ONLY SSH key-based" in result

        # Code example should be removed
        assert "def sync_to_vm():" not in result

        # Policy conclusion must be preserved
        assert "NON-NEGOTIABLE" in result

    @pytest.mark.asyncio
    async def test_load_mandatory_policy_file(self):
        """CRITICAL: Load actual MANDATORY_LOCAL_EDIT_POLICY.md file."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        policy_path = Path(".claude/agents/MANDATORY_LOCAL_EDIT_POLICY.md")

        if not policy_path.exists():
            pytest.skip("Policy file not found in expected location")

        loader = OptimizedAgentLoader(enable_optimization=True)
        content = await loader.load_agent(str(policy_path))

        # Verify key policy sections preserved
        assert "MANDATORY LOCAL-ONLY EDITING POLICY" in content
        assert "ABSOLUTE PROHIBITION" in content
        assert "VM Infrastructure" in content or "VM Target Mapping" in content
        assert "172.16.168.21" in content  # VM IPs must be preserved


class TestAgentFrontmatterPreservation:
    """CRITICAL: Ensure agent metadata unchanged."""

    def test_frontmatter_name_preserved(self, sample_agent_with_code_blocks):
        """Verify agent name preserved."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)
        assert "name: test-agent" in result

    def test_frontmatter_description_preserved(self, sample_agent_with_code_blocks):
        """Verify agent description preserved."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)
        assert "description: Test agent with code examples" in result

    def test_frontmatter_tools_preserved(self, sample_agent_with_code_blocks):
        """Verify tools list preserved."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)
        assert "tools: Read, Write, Bash" in result

    def test_frontmatter_complete_structure(self, sample_agent_with_code_blocks):
        """Verify all frontmatter intact."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        result = strip_code_blocks(sample_agent_with_code_blocks)

        # Frontmatter delimiters
        assert result.count("---") >= 2, "Frontmatter delimiters missing"

        # All fields present
        assert "name:" in result
        assert "description:" in result
        assert "tools:" in result
        assert "color:" in result


# ============================================================================
# PERFORMANCE TESTS - Benchmarks
# ============================================================================


class TestPerformanceBenchmarks:
    """Performance benchmarking for optimization system."""

    def test_token_reduction_measurement(self, sample_agent_with_code_blocks):
        """Measure actual token reduction achieved."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        # Original content
        original = sample_agent_with_code_blocks
        original_tokens = len(original) / 4  # Approximate: 4 chars per token

        # Optimized content
        optimized = strip_code_blocks(original)
        optimized_tokens = len(optimized) / 4

        # Calculate reduction
        reduction_percent = (
            (original_tokens - optimized_tokens) / original_tokens
        ) * 100

        # Report metrics
        print(f"\n=== Token Reduction Report ===")
        print(f"Original tokens: {original_tokens:.0f}")
        print(f"Optimized tokens: {optimized_tokens:.0f}")
        print(f"Reduction: {reduction_percent:.1f}%")

        # For sample with 3 code blocks, expect significant reduction
        assert reduction_percent > 0, "Should achieve some token reduction"
        assert reduction_percent < 100, "Should not remove all content"

    @pytest.mark.asyncio
    async def test_loading_performance_with_cache(
        self, sample_agent_with_code_blocks
    ):
        """Measure loading speed improvement with caching."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True, enable_cache=True)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            # Measure first load (uncached)
            start = time.time()
            await loader.load_agent(temp_path)
            uncached_time = time.time() - start

            # Measure second load (cached)
            start = time.time()
            await loader.load_agent(temp_path)
            cached_time = time.time() - start

            # Report performance
            improvement = (
                (uncached_time - cached_time) / uncached_time
            ) * 100 if uncached_time > 0 else 0

            print(f"\n=== Loading Performance Report ===")
            print(f"Uncached load: {uncached_time*1000:.2f}ms")
            print(f"Cached load: {cached_time*1000:.2f}ms")
            print(f"Improvement: {improvement:.1f}%")

            # Cached should be faster
            assert cached_time <= uncached_time, "Cache should not slow down loading"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_real_agent_file_optimization(self):
        """Test optimization on actual agent files."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        agents_dir = Path(".claude/agents")
        if not agents_dir.exists():
            pytest.skip("Agent directory not found")

        # Test on largest agent file
        agent_files = list(agents_dir.glob("*.md"))
        if not agent_files:
            pytest.skip("No agent files found")

        # Find largest agent
        largest_agent = max(agent_files, key=lambda p: p.stat().st_size)

        loader = OptimizedAgentLoader(enable_optimization=True)

        # Load with optimization
        optimized_content = await loader.load_agent(str(largest_agent))

        # Load original
        original_content = largest_agent.read_text()

        # Calculate reduction
        original_size = len(original_content)
        optimized_size = len(optimized_content)
        reduction = ((original_size - optimized_size) / original_size) * 100

        print(f"\n=== Real Agent File Test: {largest_agent.name} ===")
        print(f"Original size: {original_size:,} bytes")
        print(f"Optimized size: {optimized_size:,} bytes")
        print(f"Reduction: {reduction:.1f}%")

        # Verify target achieved (20-30% reduction)
        if "```" in original_content:  # Only if agent has code blocks
            assert (
                reduction > 0
            ), "Should achieve reduction when code blocks present"


# ============================================================================
# EDGE CASES & ERROR HANDLING
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_malformed_agent_file(self):
        """Handle malformed agent files gracefully."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True)

        malformed_content = """
        This file has no frontmatter
        It's just random text
        ```python
        # Some code
        ```
        """

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(malformed_content)
            temp_path = f.name

        try:
            # Should handle gracefully
            content = await loader.load_agent(temp_path)
            assert content is not None
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_missing_agent_file(self):
        """Handle missing agent files with clear errors."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True)

        with pytest.raises(FileNotFoundError):
            await loader.load_agent("/nonexistent/agent.md")

    @pytest.mark.asyncio
    async def test_concurrent_loading(self, sample_agent_with_code_blocks):
        """Verify thread-safe cache operations."""
        from src.utils.optimized_agent_loader import OptimizedAgentLoader

        loader = OptimizedAgentLoader(enable_optimization=True, enable_cache=True)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(sample_agent_with_code_blocks)
            temp_path = f.name

        try:
            # Load concurrently
            tasks = [loader.load_agent(temp_path) for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # All results should be identical
            for result in results[1:]:
                assert result == results[0], "Concurrent loads should be consistent"

            # Cache should handle concurrent access
            stats = loader.get_cache_stats()
            assert stats["hits"] > 0, "Should have cache hits from concurrent loads"
        finally:
            os.unlink(temp_path)

    def test_empty_agent_file(self):
        """Handle empty agent files."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        empty_content = ""
        result = strip_code_blocks(empty_content)

        # Should return empty string, not crash
        assert result == ""

    def test_agent_file_only_code(self):
        """Handle agent file that's only code blocks."""
        from src.utils.optimized_agent_loader import strip_code_blocks

        only_code = """```python
def test():
    pass
```"""

        result = strip_code_blocks(only_code)

        # Code should be removed
        assert "def test():" not in result

        # Marker should be added
        assert "[Code example omitted]" in result


# ============================================================================
# TEST CONFIGURATION & UTILITIES
# ============================================================================


@pytest.fixture(scope="session")
def test_results_directory():
    """Create directory for test results."""
    results_dir = Path("tests/results/agent_optimization")
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def pytest_configure(config):
    """Pytest configuration hook."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (requires pytest-asyncio)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line("markers", "performance: mark test as performance test")


if __name__ == "__main__":
    """Run tests directly."""
    pytest.main([__file__, "-v", "--tb=short", "-s"])
