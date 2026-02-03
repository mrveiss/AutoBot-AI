# Knowledge Manager Test Suite - Quick Start Guide
**GitHub Issue**: #163 (Task 4.2)
**Author**: mrveiss
**Date**: 2025-11-28

---

## Quick Validation

```bash
# Validate all test files exist
./tests/validate_test_suite.sh
```

**Expected Output**: ✓ All test files validated successfully!

---

## Running Tests

### Option 1: Run All Knowledge Manager Tests

```bash
# Backend tests (unit + integration)
pytest tests/unit/test_knowledge_*.py tests/integration/test_knowledge_*.py -v

# Frontend tests
cd autobot-vue && npm run test:unit -- useKnowledgeVectorization
```

### Option 2: Run Tests by Type

#### Backend Unit Tests
```bash
# Category filtering tests (36 tests)
pytest tests/unit/test_knowledge_categories.py -v

# Vectorization status tests (42 tests)
pytest tests/unit/test_knowledge_vectorization.py -v

# Both
pytest tests/unit/test_knowledge_*.py -v
```

#### Frontend Unit Tests
```bash
cd autobot-vue

# Vectorization composable tests (38 tests)
npm run test:unit -- useKnowledgeVectorization.test.ts
```

#### Integration Tests
```bash
# API integration tests (15 tests)
pytest tests/integration/test_knowledge_api_integration.py -v -m requires_backend
```

### Option 3: Run with Coverage

#### Backend Coverage
```bash
# Generate HTML coverage report
pytest tests/unit/test_knowledge_*.py \
  --cov=src.unified_knowledge_manager \
  --cov=src.agents.system_knowledge_manager \
  --cov-report=html \
  --cov-report=term

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

#### Frontend Coverage
```bash
cd autobot-vue

# Generate coverage report
npm run test:unit -- --coverage useKnowledgeVectorization.test.ts

# View report
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux
```

---

## Test Discovery

### Verify Tests Are Discoverable

```bash
# List all tests without running
pytest tests/unit/test_knowledge_*.py --collect-only

# Count total tests
pytest tests/unit/test_knowledge_*.py tests/integration/test_knowledge_*.py --collect-only | grep "test session starts" -A 1
```

**Expected**: ~66 tests collected (backend unit + integration)

---

## Test Filtering

### Run Specific Test Classes

```bash
# Run only category filtering tests
pytest tests/unit/test_knowledge_categories.py::TestCategoryFiltering -v

# Run only vectorization polling tests
pytest tests/unit/test_knowledge_vectorization.py::TestJobStatusPolling -v
```

### Run Specific Test Functions

```bash
# Run single test
pytest tests/unit/test_knowledge_categories.py::TestCategoryListRetrieval::test_get_categories_success -v

# Run tests matching pattern
pytest tests/unit/test_knowledge_*.py -k "cache" -v
```

### Run Tests by Marker

```bash
# Integration tests only (requires backend running)
pytest tests/integration/test_knowledge_*.py -v -m requires_backend

# Async tests only
pytest tests/unit/test_knowledge_*.py -v -m asyncio
```

---

## Debugging Failed Tests

### Verbose Output
```bash
# Show print statements and full tracebacks
pytest tests/unit/test_knowledge_categories.py -vv -s
```

### Stop on First Failure
```bash
# Exit immediately on first failure
pytest tests/unit/test_knowledge_*.py -x
```

### Run Last Failed Tests
```bash
# Re-run only tests that failed last time
pytest tests/unit/test_knowledge_*.py --lf
```

### Show Locals on Failure
```bash
# Show local variables in traceback
pytest tests/unit/test_knowledge_*.py -l
```

---

## Performance Testing

### Run Tests with Timing
```bash
# Show slowest 10 tests
pytest tests/unit/test_knowledge_*.py --durations=10
```

### Run Tests in Parallel
```bash
# Install pytest-xdist
pip install pytest-xdist

# Run with 4 workers
pytest tests/unit/test_knowledge_*.py -n 4
```

---

## Continuous Integration

### GitHub Actions Workflow

Add to `.github/workflows/tests.yml`:

```yaml
name: Knowledge Manager Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run backend tests
        run: |
          pytest tests/unit/test_knowledge_*.py \
            --cov=src \
            --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: cd autobot-vue && npm ci
      - name: Run frontend tests
        run: |
          cd autobot-vue
          npm run test:unit -- --coverage
```

---

## Test Maintenance

### Adding New Tests

1. **Backend tests**: Add to `tests/unit/test_knowledge_*.py`
2. **Frontend tests**: Add to `autobot-vue/src/composables/__tests__/*.test.ts`
3. **Integration tests**: Add to `tests/integration/test_knowledge_*.py`

### Test Naming Conventions

- **Files**: `test_knowledge_<feature>.py` or `<feature>.test.ts`
- **Classes**: `Test<Feature><Aspect>` (e.g., `TestCategoryFiltering`)
- **Functions**: `test_<what>_<scenario>` (e.g., `test_filter_by_single_category`)

### Fixture Best Practices

```python
# Good: Reusable fixture
@pytest.fixture
def sample_categories():
    return [{"name": "tools", "count": 15}]

# Good: Async fixture
@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield session

# Good: Scoped fixture (runs once per session)
@pytest.fixture(scope="session")
def config():
    return load_config()
```

---

## Troubleshooting

### Import Errors

```bash
# Ensure project root in PYTHONPATH
export PYTHONPATH=/home/kali/Desktop/AutoBot:$PYTHONPATH

# Or use pytest from project root
cd /home/kali/Desktop/AutoBot
pytest tests/unit/test_knowledge_*.py
```

### Async Test Errors

```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Verify asyncio mode in pytest.ini
cat tests/pytest.ini  # Should have: asyncio_mode = auto
```

### Mock Issues

```python
# Use AsyncMock for async functions
from unittest.mock import AsyncMock

mock_func = AsyncMock(return_value={"status": "success"})
```

### Redis Connection Errors (Integration Tests)

```bash
# Ensure Redis is running
redis-cli -h 172.16.168.23 ping

# Or use mock Redis client for unit tests
@pytest.fixture
def mock_redis_client():
    return AsyncMock()
```

---

## Test Coverage Goals

| Component | Target | Current* |
|-----------|--------|----------|
| Category Filtering | 80% | TBD |
| Vectorization Status | 80% | TBD |
| Integration Workflows | 80% | TBD |
| Error Handling | 90% | TBD |

*Run with `--cov` to measure actual coverage

---

## Next Steps After Tests Pass

1. ✅ Run code review (Task 4.1): Use `code-reviewer` agent
2. ⏳ Run performance tests (Task 4.3): Use `performance-engineer` agent
3. ⏳ Generate coverage report: `pytest --cov-report=html`
4. ⏳ Add to CI/CD: GitHub Actions workflow
5. ⏳ Document coverage gaps: Create follow-up issues if needed

---

## Support

**Issue Tracker**: https://github.com/mrveiss/AutoBot-AI/issues/163
**Test Summary**: `/home/kali/Desktop/AutoBot/tests/TEST_SUITE_SUMMARY.md`
**Project Docs**: `/home/kali/Desktop/AutoBot/docs/`

---

**Happy Testing! 🧪**
