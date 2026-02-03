# Agent Optimization Test Suite Documentation

Comprehensive test suite for the lazy loading agent optimization system.

## Overview

This test suite validates runtime agent optimization (code stripping, caching) to reduce token usage by 20-30% without modifying agent source files.

## Test Files

- **`test_optimized_agent_loader.py`** - Main test suite (541 lines)
- **`src/utils/optimized_agent_loader.py`** - Implementation (279 lines)
- **`fixtures/agent_optimization/`** - Test fixtures directory

## Test Categories

### 1. Unit Tests - Code Block Removal

**Module:** `TestCodeBlockRemoval`

Tests code stripping functionality:

- `test_remove_python_code_blocks()` - Python code block removal
- `test_remove_bash_code_blocks()` - Bash script removal
- `test_remove_javascript_code_blocks()` - JavaScript code removal
- `test_code_block_markers_inserted()` - Marker insertion validation
- `test_no_code_blocks_unchanged()` - No-op for content without code
- `test_frontmatter_preserved()` - YAML frontmatter preservation
- `test_nested_code_blocks()` - Nested structure handling

**Expected Behavior:**
- Code blocks replaced with `[Code example omitted]` markers
- Markdown structure preserved (headers, lists, text)
- YAML frontmatter completely intact
- Agent metadata unchanged

### 2. Integration Tests - Agent Loading

**Module:** `TestAgentLoading`

Tests agent loading with optimization:

- `test_load_agent_with_optimization_enabled()` - Optimized loading
- `test_load_agent_without_optimization()` - Original content loading
- `test_cache_effectiveness()` - Cache hit/miss tracking
- `test_cache_disabled()` - Loading without caching

**Expected Behavior:**
- Optimization strips code when enabled
- Original content returned when disabled
- Cache improves load time on subsequent loads
- Cache stats accurately tracked

### 3. Validation Tests - CRITICAL

**Module:** `TestAgentRoutingValidation`

**⚠️ CRITICAL: Validates agent routing remains unchanged**

- `test_agent_routing_unchanged()` - Compare routing pre/post optimization

Test queries:
- "review my code" → code-reviewer
- "optimize backend performance" → senior-backend-engineer
- "write comprehensive tests" → testing-engineer
- "audit API security" → security-auditor
- "design system architecture" → systems-architect
- "improve database queries" → database-engineer

**Expected Behavior:**
- Identical agent selection with/without optimization
- Routing logic unaffected by code stripping

**Module:** `TestPolicyEnforcement`

**⚠️ CRITICAL: Validates policy enforcement preservation**

- `test_policy_text_preserved()` - Policy text in optimized content
- `test_load_mandatory_policy_file()` - Load actual policy file

**Required Preserved Text:**
- "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT"
- "CRITICAL: ALL code edits MUST be done locally"
- "NEVER on remote servers"
- VM IP addresses: 172.16.168.21-25
- SSH key location: `~/.ssh/autobot_key`
- "ONLY SSH key-based"
- "NON-NEGOTIABLE"

**Module:** `TestAgentFrontmatterPreservation`

**⚠️ CRITICAL: Validates agent metadata unchanged**

- `test_frontmatter_name_preserved()` - Agent name intact
- `test_frontmatter_description_preserved()` - Description intact
- `test_frontmatter_tools_preserved()` - Tools list intact
- `test_frontmatter_complete_structure()` - All fields present

### 4. Performance Tests - Benchmarks

**Module:** `TestPerformanceBenchmarks`

Measures optimization effectiveness:

- `test_token_reduction_measurement()` - Calculate token savings
- `test_loading_performance_with_cache()` - Cache speed improvement
- `test_real_agent_file_optimization()` - Test on actual agent files

**Expected Metrics:**
- Token reduction: 20-30% for agents with code blocks
- Cache load time: Faster than uncached (measurable improvement)
- Real agent optimization: Validates target reduction achieved

**Performance Reporting:**
```
=== Token Reduction Report ===
Original tokens: 450
Optimized tokens: 315
Reduction: 30.0%

=== Loading Performance Report ===
Uncached load: 2.35ms
Cached load: 0.12ms
Improvement: 94.9%

=== Real Agent File Test: testing-engineer-md.md ===
Original size: 78,965 bytes
Optimized size: 55,276 bytes
Reduction: 30.0%
```

### 5. Edge Cases & Error Handling

**Module:** `TestEdgeCases`

Tests robustness and error handling:

- `test_malformed_agent_file()` - Handle missing frontmatter
- `test_missing_agent_file()` - FileNotFoundError for missing files
- `test_concurrent_loading()` - Thread-safe cache operations
- `test_empty_agent_file()` - Handle empty files gracefully
- `test_agent_file_only_code()` - Handle files with only code blocks

**Expected Behavior:**
- Graceful handling of malformed content
- Clear error messages for missing files
- Thread-safe concurrent operations
- No crashes on edge cases

## Running Tests

### Run All Tests

```bash
cd /home/kali/Desktop/AutoBot
pytest tests/test_optimized_agent_loader.py -v --tb=short
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/test_optimized_agent_loader.py::TestCodeBlockRemoval -v

# Critical validation tests
pytest tests/test_optimized_agent_loader.py::TestAgentRoutingValidation -v
pytest tests/test_optimized_agent_loader.py::TestPolicyEnforcement -v

# Performance benchmarks
pytest tests/test_optimized_agent_loader.py::TestPerformanceBenchmarks -v -s

# Edge cases
pytest tests/test_optimized_agent_loader.py::TestEdgeCases -v
```

### Run with Coverage

```bash
pytest tests/test_optimized_agent_loader.py \
    --cov=src.utils.optimized_agent_loader \
    --cov-report=html:tests/results/agent_optimization/coverage \
    --cov-report=term-missing \
    -v
```

### Run Performance Tests with Output

```bash
pytest tests/test_optimized_agent_loader.py::TestPerformanceBenchmarks -v -s
```

## Test Fixtures

Test fixtures are defined inline in `test_optimized_agent_loader.py`:

### sample_agent_with_code_blocks
Agent with Python, Bash, and JavaScript code blocks for testing optimization.

### sample_agent_without_code
Minimal agent without code blocks for testing no-op optimization.

### sample_agent_with_policy
Agent containing MANDATORY_LOCAL_EDIT_POLICY text for validation.

### sample_agent_nested_blocks
Agent with nested code block structures for edge case testing.

## Expected Test Results

### Coverage Target
- **Target:** >90% code coverage
- **Critical paths:** All optimization and caching code paths covered

### Success Criteria

**Unit Tests:**
- ✅ All code blocks correctly removed
- ✅ Markers inserted in correct locations
- ✅ Structure and frontmatter preserved

**Integration Tests:**
- ✅ Optimization works when enabled
- ✅ Original content when disabled
- ✅ Cache improves performance

**Validation Tests (CRITICAL):**
- ✅ Agent routing produces identical results
- ✅ Policy text completely preserved
- ✅ Frontmatter unchanged

**Performance Tests:**
- ✅ 20-30% token reduction achieved
- ✅ Cache improves load time
- ✅ Real agent files optimized successfully

**Edge Cases:**
- ✅ Graceful error handling
- ✅ Thread-safe operations
- ✅ No crashes on malformed input

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/agent-optimization-tests.yml
name: Agent Optimization Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio pytest-cov
      - name: Run agent optimization tests
        run: |
          pytest tests/test_optimized_agent_loader.py \
            --cov=src.utils.optimized_agent_loader \
            --cov-report=xml \
            -v
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Troubleshooting

### Test Failures

**Import Errors:**
```bash
ModuleNotFoundError: No module named 'src.utils.optimized_agent_loader'
```
**Solution:** Ensure PYTHONPATH includes project root:
```bash
export PYTHONPATH=/home/kali/Desktop/AutoBot:$PYTHONPATH
pytest tests/test_optimized_agent_loader.py -v
```

**File Not Found:**
```bash
FileNotFoundError: Agent file not found: .claude/agents/...
```
**Solution:** Run tests from project root, not tests/ directory:
```bash
cd /home/kali/Desktop/AutoBot
pytest tests/test_optimized_agent_loader.py -v
```

**Async Test Failures:**
```bash
RuntimeError: no running event loop
```
**Solution:** Install pytest-asyncio:
```bash
pip install pytest-asyncio
```

### Performance Debugging

Enable verbose output to see performance metrics:
```bash
pytest tests/test_optimized_agent_loader.py::TestPerformanceBenchmarks -v -s
```

### Coverage Reporting

View detailed coverage report:
```bash
pytest tests/test_optimized_agent_loader.py \
    --cov=src.utils.optimized_agent_loader \
    --cov-report=html:tests/results/agent_optimization/coverage \
    -v

# Open in browser
firefox tests/results/agent_optimization/coverage/index.html
```

## Implementation Notes

### Code Stripping Algorithm

```python
def strip_code_blocks(content: str) -> str:
    """Remove code blocks with regex pattern matching."""
    code_block_pattern = re.compile(
        r"```[\w]*\n.*?\n```",
        re.DOTALL | re.MULTILINE
    )
    return code_block_pattern.sub("\n[Code example omitted]\n", content)
```

**Pattern Explanation:**
- ` ```[\w]* ` - Matches opening backticks with optional language
- `\n.*?\n` - Matches code content (non-greedy)
- ` ``` ` - Matches closing backticks
- `re.DOTALL` - Makes `.` match newlines
- `re.MULTILINE` - Makes `^` and `$` match line boundaries

### Caching Strategy

**Cache Key Generation:**
```python
cache_key = hashlib.md5(file_path.encode()).hexdigest()
```

**Cache Eviction:**
- LRU-based (Least Recently Used)
- Size limit: 100 agents (configurable)
- Thread-safe with asyncio.Lock

**Cache Statistics:**
```python
{
    "hits": 42,      # Number of cache hits
    "misses": 8,     # Number of cache misses
    "size": 15,      # Current cache size
    "limit": 100     # Maximum cache size
}
```

## Future Enhancements

1. **Advanced Code Detection**
   - Detect code examples without triple backticks
   - Preserve critical code examples (e.g., error patterns)

2. **Selective Optimization**
   - Whitelist agents that should not be optimized
   - Per-agent optimization configuration

3. **Compression**
   - Gzip compression for cached content
   - Further reduce memory usage

4. **Monitoring**
   - Prometheus metrics for cache performance
   - Token usage tracking per agent

5. **Distributed Caching**
   - Redis-based cache for multi-instance deployments
   - Cache warming on startup

## References

- **Implementation:** `src/utils/optimized_agent_loader.py`
- **Tests:** `tests/test_optimized_agent_loader.py`
- **Fixtures:** `tests/fixtures/agent_optimization/`
- **CLAUDE.md:** Project development guidelines
- **Agent Files:** `.claude/agents/*.md`

## Maintenance

### Adding New Tests

1. Add test method to appropriate test class
2. Use descriptive test name: `test_<what>_<scenario>()`
3. Include docstring explaining test purpose
4. Follow AAA pattern: Arrange, Act, Assert
5. Update this documentation

### Updating Fixtures

1. Modify fixture functions in test file
2. Document changes in fixture docstrings
3. Update fixture README if needed
4. Verify all tests still pass

### Performance Baseline

Record baseline metrics for regression detection:

```bash
# Run performance tests and save results
pytest tests/test_optimized_agent_loader.py::TestPerformanceBenchmarks \
    -v -s > tests/results/agent_optimization/performance_baseline.txt 2>&1
```

Compare future runs against baseline to detect performance regressions.

---

**Last Updated:** 2025-10-10
**Test Suite Version:** 1.0.0
**Python Version:** 3.10.13
**pytest Version:** >=7.0.0
