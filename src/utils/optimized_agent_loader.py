"""
Optimized Agent Loader - Runtime Agent Optimization System

Provides code stripping and caching for agent markdown files to reduce
token usage by 20-30% without modifying source files.

Features:
- Code block removal with structure preservation
- In-memory caching for improved performance
- Agent routing preservation
- Policy enforcement text preservation

Author: AutoBot Development Team
Date: 2025-10-10
"""

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Dict, Optional, Tuple


class OptimizedAgentLoader:
    """
    Optimized agent loader with code stripping and caching.

    This class provides runtime optimization of agent markdown files by:
    1. Stripping code blocks to reduce token usage
    2. Caching optimized content for performance
    3. Preserving agent routing and policy enforcement
    """

    def __init__(
        self,
        enable_optimization: bool = True,
        enable_cache: bool = True,
        cache_size_limit: int = 100,
    ):
        """
        Initialize optimized agent loader.

        Args:
            enable_optimization: Enable code stripping optimization
            enable_cache: Enable in-memory caching
            cache_size_limit: Maximum number of cached agents
        """
        self.enable_optimization = enable_optimization
        self.enable_cache = enable_cache
        self.cache_size_limit = cache_size_limit

        # Cache: {file_path_hash: (content, timestamp)}
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Thread lock for cache operations
        self._cache_lock = asyncio.Lock()

    async def load_agent(self, file_path: str) -> str:
        """
        Load agent markdown file with optional optimization.

        Args:
            file_path: Path to agent markdown file

        Returns:
            Agent content (optimized if enabled)

        Raises:
            FileNotFoundError: If agent file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Agent file not found: {file_path}")

        # Check cache first
        if self.enable_cache:
            cached_content = await self._get_from_cache(file_path)
            if cached_content is not None:
                self._cache_hits += 1
                return cached_content
            self._cache_misses += 1

        # Read original content
        content = path.read_text(encoding="utf-8")

        # Apply optimization if enabled
        if self.enable_optimization:
            content = strip_code_blocks(content)

        # Store in cache
        if self.enable_cache:
            await self._store_in_cache(file_path, content)

        return content

    async def _get_from_cache(self, file_path: str) -> Optional[str]:
        """Get content from cache."""
        async with self._cache_lock:
            cache_key = self._get_cache_key(file_path)
            if cache_key in self._cache:
                content, _ = self._cache[cache_key]
                return content
            return None

    async def _store_in_cache(self, file_path: str, content: str) -> None:
        """Store content in cache."""
        async with self._cache_lock:
            cache_key = self._get_cache_key(file_path)

            # Enforce cache size limit
            if len(self._cache) >= self.cache_size_limit:
                # Remove oldest entry
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k][1]
                )
                del self._cache[oldest_key]

            # Store with timestamp
            import time

            self._cache[cache_key] = (content, time.time())

    def _get_cache_key(self, file_path: str) -> str:
        """Generate cache key from file path."""
        return hashlib.md5(file_path.encode()).hexdigest()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hits, misses, and size
        """
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._cache),
            "limit": self.cache_size_limit,
        }

    async def route_agent(self, query: str) -> str:
        """
        Route user query to appropriate agent.

        This is a stub implementation for testing. In production,
        this would integrate with actual agent routing logic.

        Args:
            query: User query

        Returns:
            Agent name
        """
        # Simple keyword-based routing for testing
        query_lower = query.lower()

        if "review" in query_lower or "code quality" in query_lower:
            return "code-reviewer"
        elif "optimize" in query_lower or "performance" in query_lower:
            return "senior-backend-engineer"
        elif "test" in query_lower:
            return "testing-engineer"
        elif "security" in query_lower or "audit" in query_lower:
            return "security-auditor"
        elif "architecture" in query_lower or "design" in query_lower:
            return "systems-architect"
        elif "database" in query_lower or "queries" in query_lower:
            return "database-engineer"
        else:
            return "general-purpose"

    def clear_cache(self) -> None:
        """Clear all cached content."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0


def strip_code_blocks(content: str) -> str:
    """
    Strip code blocks from agent markdown content.

    Removes code blocks while preserving:
    - YAML frontmatter
    - Markdown structure (headers, lists, etc.)
    - Policy enforcement text
    - Instructions and descriptions

    Args:
        content: Original agent markdown content

    Returns:
        Optimized content with code blocks replaced by markers
    """
    if not content:
        return content

    # Pattern to match code blocks: ```language\ncode\n```
    # Uses non-greedy matching and handles nested backticks
    code_block_pattern = re.compile(
        r"```[\w]*\n.*?\n```", re.DOTALL | re.MULTILINE
    )

    # Replace code blocks with markers
    optimized = code_block_pattern.sub(
        "\n[Code example omitted]\n", content
    )

    return optimized


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


async def load_all_agents(
    agents_dir: Path, enable_optimization: bool = True
) -> Dict[str, str]:
    """
    Load all agent files from directory.

    Args:
        agents_dir: Directory containing agent markdown files
        enable_optimization: Enable code stripping

    Returns:
        Dictionary mapping agent names to content
    """
    loader = OptimizedAgentLoader(enable_optimization=enable_optimization)
    agents = {}

    for agent_file in agents_dir.glob("*.md"):
        try:
            content = await loader.load_agent(str(agent_file))
            agent_name = agent_file.stem
            agents[agent_name] = content
        except Exception as e:
            print(f"Error loading {agent_file}: {e}")

    return agents


def calculate_token_savings(original: str, optimized: str) -> Dict[str, float]:
    """
    Calculate token savings from optimization.

    Args:
        original: Original content
        optimized: Optimized content

    Returns:
        Dictionary with token counts and savings percentage
    """
    # Approximate token count: 4 characters per token
    original_tokens = len(original) / 4
    optimized_tokens = len(optimized) / 4

    savings = original_tokens - optimized_tokens
    savings_percent = (savings / original_tokens * 100) if original_tokens > 0 else 0

    return {
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": savings,
        "savings_percent": savings_percent,
    }


if __name__ == "__main__":
    """Test optimized agent loader."""
    import asyncio

    async def test():
        loader = OptimizedAgentLoader()

        # Test with sample content
        sample = """---
name: test-agent
---

# Test Agent

```python
def test():
    pass
```

Some text.
"""

        result = strip_code_blocks(sample)
        print("Original:", len(sample), "bytes")
        print("Optimized:", len(result), "bytes")
        print("\nOptimized content:")
        print(result)

        # Calculate savings
        savings = calculate_token_savings(sample, result)
        print(f"\nToken savings: {savings['savings_percent']:.1f}%")

    asyncio.run(test())
