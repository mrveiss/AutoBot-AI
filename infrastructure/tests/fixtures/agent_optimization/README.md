# Agent Optimization Test Fixtures

This directory contains test fixtures for the optimized agent loader test suite.

## Structure

```
agent_optimization/
├── README.md                    # This file
├── sample_agent_full.md        # Full agent with multiple code blocks
├── sample_agent_minimal.md     # Minimal agent without code
├── sample_agent_policy.md      # Agent with policy enforcement
└── sample_agent_nested.md      # Agent with nested structures
```

## Fixture Files

### sample_agent_full.md
Complete agent with:
- YAML frontmatter
- Multiple code blocks (Python, Bash, JavaScript)
- Markdown structure (headers, lists)
- Instructions and descriptions

### sample_agent_minimal.md
Minimal agent without code blocks for testing:
- No-op optimization (should return unchanged)
- Frontmatter preservation
- Structure validation

### sample_agent_policy.md
Agent with policy enforcement text for testing:
- MANDATORY_LOCAL_EDIT_POLICY preservation
- VM IP addresses preservation
- SSH instructions preservation
- Code block removal within policy context

### sample_agent_nested.md
Agent with complex nested structures for testing:
- Nested code blocks
- Edge case handling
- Malformed content resilience

## Usage

Test fixtures are loaded automatically by pytest fixtures in `test_optimized_agent_loader.py`.

Example:
```python
@pytest.fixture
def sample_agent_with_code_blocks() -> str:
    return Path("tests/fixtures/agent_optimization/sample_agent_full.md").read_text()
```

## Creating New Fixtures

When adding new fixtures:
1. Create markdown file in this directory
2. Add pytest fixture in test file
3. Document fixture purpose here
4. Ensure proper YAML frontmatter if applicable
