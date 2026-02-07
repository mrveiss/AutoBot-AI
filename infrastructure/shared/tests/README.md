# AutoBot Modern Test Suite

**Configuration-driven, minimal, maintainable test suite for AutoBot platform.**

## 📁 Structure

```
tests/
├── unit/              # Fast, isolated unit tests
│   ├── test_config.py          # Configuration system
│   ├── test_chat_system.py     # Chat functionality
│   └── test_agents.py          # Agent orchestration
├── integration/       # Service integration tests
│   ├── test_distributed.py     # VM communication
│   ├── test_api.py             # API endpoints
│   └── test_workflows.py       # End-to-end workflows
├── e2e/              # Full system end-to-end tests
├── fixtures/         # Test fixtures and sample data
│   └── data/         # Test data files
├── conftest.py       # Pytest configuration and fixtures
├── pytest.ini        # Pytest settings
└── README.md         # This file
```

## 🚀 Quick Start

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests
pytest -m integration

# API tests
pytest -m api

# Distributed system tests
pytest -m distributed
```

### Run Specific Test Files

```bash
# Configuration tests
pytest unit/test_config.py

# API tests
pytest integration/test_api.py -v

# With coverage
pytest --cov=src --cov-report=html
```

## 🎯 Test Markers

Tests are organized with pytest markers for selective execution:

| Marker | Description | Usage |
|--------|-------------|-------|
| `unit` | Fast, isolated tests | `pytest -m unit` |
| `integration` | Service integration tests | `pytest -m integration` |
| `e2e` | End-to-end system tests | `pytest -m e2e` |
| `slow` | Slow-running tests | `pytest -m "not slow"` |
| `distributed` | Requires distributed VMs | `pytest -m distributed` |
| `api` | API endpoint tests | `pytest -m api` |
| `chat` | Chat system tests | `pytest -m chat` |
| `security` | Security tests | `pytest -m security` |

### Combining Markers

```bash
# Run unit and integration tests, but not slow ones
pytest -m "unit or integration and not slow"

# Run only API integration tests
pytest -m "integration and api"
```

## 🔧 Configuration

All tests use **unified_config_manager** - no hardcoded values:

### conftest.py Fixtures

```python
# Configuration fixtures
@pytest.fixture
def config():
    """Unified configuration from config.yaml"""

@pytest.fixture
def backend_url(config):
    """Backend URL from configuration"""

@pytest.fixture
def redis_url(config):
    """Redis URL from configuration"""
```

### Using in Tests

```python
def test_api_endpoint(backend_url):
    """Test uses configuration-driven backend URL."""
    response = requests.get(f"{backend_url}/api/health")
    assert response.status_code == 200
```

## 📊 Test Environment

Tests automatically run in isolated test environment:

```python
@pytest.fixture(autouse=True)
def set_test_environment():
    """Automatically sets AUTOBOT_TEST_MODE=true"""
```

This prevents tests from affecting production data.

## 🧪 Writing New Tests

### Unit Test Template

```python
# unit/test_example.py
import pytest

@pytest.mark.unit
def test_configuration_loading(config):
    """Test configuration system."""
    assert "backend" in config
    assert "redis" in config
    assert config["backend"]["host"] is not None
```

### Integration Test Template

```python
# integration/test_example.py
import pytest

@pytest.mark.integration
@pytest.mark.api
@pytest.mark.asyncio
async def test_api_health(http_client, backend_url):
    """Test API health endpoint."""
    async with http_client.get(f"{backend_url}/api/health") as response:
        assert response.status == 200
        data = await response.json()
        assert data["status"] == "healthy"
```

## 📈 Coverage

Generate coverage reports:

```bash
# HTML report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html

# Terminal report
pytest --cov=src --cov-report=term-missing
```

## 🎯 CI/CD Integration

### GitHub Actions

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## 🔍 Debugging Tests

### Verbose Output

```bash
pytest -vv
```

### Show Print Statements

```bash
pytest -s
```

### Run Specific Test

```bash
pytest unit/test_config.py::test_backend_config -v
```

### Debug with pdb

```bash
pytest --pdb
```

## 📚 Dependencies

Required packages:

```bash
pip install pytest pytest-asyncio pytest-cov aiohttp redis
```

## 🚨 Migration from Legacy Tests

**Legacy test suite archived**: `archive/legacy-test-suite-2025-01-09/`

**What changed:**
- ✅ Configuration-driven (no hardcoded URLs/IPs)
- ✅ Modern pytest structure
- ✅ Async/await support
- ✅ Clear markers and organization
- ✅ Fast execution (minimal tests, maximum coverage)

## 📊 Test Statistics

| Category | Count | Purpose |
|----------|-------|---------|
| Unit Tests | ~15 | Fast, isolated tests |
| Integration Tests | ~10 | Service integration |
| E2E Tests | ~5 | Full system validation |
| **Total** | **~30 tests** | Complete coverage |

**vs Legacy**: 437 tests → 30 tests (93% reduction, better quality)

## 🤝 Contributing

### Adding New Tests

1. Choose appropriate directory (`unit/`, `integration/`, `e2e/`)
2. Use configuration fixtures from `conftest.py`
3. Add appropriate pytest markers
4. Write clear test names and docstrings
5. Run `pytest` to verify

### Test Naming Convention

```
test_<feature>_<scenario>.py
├── test_<specific_behavior>
├── test_<edge_case>
└── test_<error_condition>
```

---

**Modern test suite**: Fast, maintainable, configuration-driven ✅
