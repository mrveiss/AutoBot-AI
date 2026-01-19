# 🧪 Test Utilities Migration Guide

> **Addresses**: 20 duplicate `setup_method` implementations across test files
>
> **Impact**: Reduces test setup code by 70%, improves test reliability and maintenance

## 🎯 Overview

This guide shows how to migrate existing test files to use the new standardized test utilities, eliminating duplicate `setup_method` implementations identified in our codebase analysis.

## 📊 Problem Analysis

**Before Standardization:**
- 20 test files with duplicate `setup_method` patterns
- Average 15-25 lines of setup code per test class
- Inconsistent resource cleanup
- Repeated configuration mocking
- Error-prone temporary file handling

**After Standardization:**
- Single source of truth for test patterns
- 5-10 lines of setup code per test class
- Automatic resource cleanup
- Consistent test environment
- Reduced maintenance overhead

## 🛠️ Available Test Utilities

### **1. AutoBotTestCase** - Base Test Class
```python
from tests.test_utils import AutoBotTestCase

class TestMyFeature(AutoBotTestCase):
    def setup_method(self):
        super().setup_method()  # Required!
        # Your custom setup here
```

**Provides:**
- Automatic test timing
- Temp file cleanup
- Environment setup
- Standard teardown

### **2. MockConfig** - Configuration Mocking
```python
from tests.test_utils import MockConfig

# Context manager approach
with MockConfig.mock_global_config({"key": "value"}):
    instance = MyClass()

# Or in setup_method
self.with_config({"key": "value"})
```

**Standard test config includes:**
- Redis test database (DB 15)
- Disabled auth for testing
- Test environment settings
- Common file type restrictions

### **3. MockSecurityLayer** - Security Mocking
```python
from tests.test_utils import MockSecurityLayer

# Create configured mock
mock_security = MockSecurityLayer.create(
    authenticated=True,
    user_role="admin",
    session_id="test_123"
)

# Or in setup_method
self.with_security(authenticated=True, user_role="admin")
```

### **4. TempFileContext** - Temporary File Handling
```python
from tests.test_utils import TempFileContext

# Context manager approach
with TempFileContext(suffix=".log") as temp_path:
    # Use temp_path
    pass  # File auto-deleted

# Or in setup_method
temp_path = self.create_temp_file(suffix=".log", content="initial")
# Auto-cleaned in teardown
```

### **5. FastAPITestSetup** - API Testing
```python
from tests.test_utils import FastAPITestSetup

app, client = FastAPITestSetup.create_test_app(
    routers={"/api/endpoint": router},
    dependencies={"security": mock_security}
)

response = client.get("/api/endpoint/test")
```

### **6. TestDataFactory** - Test Data Creation
```python
from tests.test_utils import TestDataFactory

# Agent request
request = TestDataFactory.agent_request(
    agent_type="chat",
    action="process",
    payload={"message": "test"}
)

# WebSocket message
message = TestDataFactory.websocket_message(
    action="execute",
    data={"command": "ls"}
)
```

## 🔄 Migration Examples

### **Example 1: Simple Test Migration**

**Before:**
```python
class TestChatAgent:
    def setup_method(self):
        # Mock config - DUPLICATE
        with patch("src.agents.chat_agent.global_config_manager") as mock:
            mock.get.return_value = {"model": "test-model"}
            self.agent = ChatAgent()

        self.test_start_time = time.time()

    def teardown_method(self):
        print(f"Test took {time.time() - self.test_start_time}s")
```

**After:**
```python
from tests.test_utils import AutoBotTestCase

class TestChatAgent(AutoBotTestCase):
    def setup_method(self):
        super().setup_method()
        self.with_config({"model": "test-model"})

        from src.agents.chat_agent import ChatAgent
        self.agent = ChatAgent()
```

### **Example 2: Complex Security Test Migration**

**Before:**
```python
class TestSecureEndpoint:
    def setup_method(self):
        # Create temp file
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()

        # Mock security
        self.mock_security = MagicMock()
        self.mock_security.authenticate.return_value = True
        self.mock_security.get_user_role.return_value = "admin"

        # Mock config
        with patch("src.api.security.config") as mock_config:
            mock_config.get.return_value = {
                "audit_log": self.temp_file.name
            }

            # Create FastAPI app
            self.app = FastAPI()
            self.app.include_router(router)
            self.app.state.security = self.mock_security
            self.client = TestClient(self.app)

    def teardown_method(self):
        os.unlink(self.temp_file.name)
```

**After:**
```python
from tests.test_utils import AutoBotTestCase, FastAPITestSetup

class TestSecureEndpoint(AutoBotTestCase):
    def setup_method(self):
        super().setup_method()

        # Auto-cleaned temp file
        audit_log = self.create_temp_file(suffix=".log")

        # Standardized config
        self.with_config({"audit_log": audit_log})

        # Standardized security mock
        self.with_security(authenticated=True, user_role="admin")

        # Standardized FastAPI setup
        from backend.api.security import router
        self.app, self.client = FastAPITestSetup.create_test_app(
            routers={"/api/security": router},
            dependencies={"security": self.mock_security}
        )
```

## 📋 Migration Checklist

### **For Each Test File:**

- [ ] Import test utilities: `from tests.test_utils import ...`
- [ ] Change class to inherit from `AutoBotTestCase`
- [ ] Add `super().setup_method()` at start of setup_method
- [ ] Replace config mocking with `self.with_config()`
- [ ] Replace security mocking with `self.with_security()`
- [ ] Replace temp file creation with `self.create_temp_file()`
- [ ] Remove teardown_method if only cleaning temp files
- [ ] Use factories for test data creation
- [ ] Run tests to verify functionality

## 🧪 Pytest Integration

For projects using pytest, additional fixtures are available:

```python
def test_with_fixtures(mock_config, mock_security, temp_file, test_client):
    """All setup handled by fixtures."""
    # mock_config has standard test configuration
    # mock_security is pre-configured
    # temp_file is created and auto-cleaned
    # test_client is ready for API testing
```

## 📊 Migration Priority

Based on complexity and usage patterns:

### **Phase 1: High-Value Targets**
1. `test_enhanced_security_layer.py` - Complex setup with temp files
2. `test_secure_terminal_websocket.py` - WebSocket and security mocking
3. `test_security_api.py` - FastAPI test patterns
4. `test_performance_benchmarks.py` - Configuration heavy

### **Phase 2: Standard Patterns**
5. `test_secure_command_executor.py` - Security layer mocking
6. `test_multimodal_integration.py` - Simple instance creation
7. `test_security_edge_cases.py` - Temp file patterns
8. Other test files with `setup_method`

## 🎯 Benefits Summary

### **Code Reduction**
- **Before**: 20 files × 20 lines average = 400 lines of setup code
- **After**: 20 files × 6 lines average = 120 lines of setup code
- **Savings**: 70% reduction in setup code

### **Maintenance Benefits**
- Single source for test patterns
- Consistent behavior across tests
- Easier to update test infrastructure
- Less error-prone setup/teardown

### **Developer Experience**
- Faster test writing
- Clear patterns to follow
- Automatic resource management
- Better test isolation

## 🚀 Getting Started

1. **Import test utilities:**
   ```python
   from tests.test_utils import AutoBotTestCase, MockConfig
   ```

2. **Start with one test class:**
   - Migrate setup_method
   - Verify tests pass
   - Remove unnecessary teardown

3. **Gradually migrate file:**
   - One test class at a time
   - Run tests after each migration
   - Commit working changes

4. **Share patterns:**
   - Document any new patterns needed
   - Add to test_utils.py if widely useful
   - Update this guide with learnings

---

**Goal**: Eliminate all 20 duplicate `setup_method` implementations while improving test reliability and maintainability.
