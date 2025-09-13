# Dependency Injection Refactoring

**Status**: ✅ **Completed** - Core components refactored to use dependency injection pattern

## Overview

The AutoBot codebase has been refactored to implement dependency injection for core components, removing their direct reliance on the global configuration manager and improving testability and maintainability.

## Problem Addressed

Previously, core components like `Orchestrator`, `KnowledgeBase`, and `Diagnostics` directly imported and used `global_config_manager`, creating tight coupling and making unit testing difficult. This pattern also made it challenging to use different configurations for different environments or test scenarios.

## Solution Implemented

### 1. Dependency Injection Module

**File**: `backend/dependencies.py`

Created a centralized dependency injection module that provides FastAPI-compatible dependency providers:

```python
from fastapi import Depends
from backend.dependencies import ConfigDep, OrchestratorDep, KnowledgeBaseDep

@router.post("/my-endpoint")
async def my_endpoint(
    config: ConfigManager = ConfigDep,
    orchestrator: Orchestrator = OrchestratorDep
):
    # Use injected dependencies
    pass
```

#### Available Dependency Providers:

- `get_config()` - Configuration manager
- `get_orchestrator()` - Orchestrator with all dependencies
- `get_knowledge_base()` - Knowledge base with config
- `get_diagnostics()` - Diagnostics with config
- `get_llm_interface()` - LLM interface
- `get_security_layer()` - Security layer (optional)

#### Cached Versions:

- `get_cached_knowledge_base()` - Cached knowledge base instance
- `get_cached_orchestrator()` - Cached orchestrator instance

### 2. Component Refactoring

#### Orchestrator Class

**Before**:
```python
class Orchestrator:
    def __init__(self):
        self.llm_interface = LLMInterface()
        self.knowledge_base = KnowledgeBase()
        self.diagnostics = Diagnostics()
        
        llm_config = global_config_manager.get_llm_config()
        # ... direct global config usage
```

**After**:
```python
class Orchestrator:
    def __init__(self, config_manager=None, llm_interface=None, knowledge_base=None, diagnostics=None):
        # Use provided dependencies or fall back to defaults for backward compatibility
        self.config_manager = config_manager or global_config_manager
        self.llm_interface = llm_interface or LLMInterface()
        self.knowledge_base = knowledge_base or KnowledgeBase()
        self.diagnostics = diagnostics or Diagnostics()
        
        llm_config = self.config_manager.get_llm_config()
        # ... use injected config
```

#### KnowledgeBase Class

**Before**:
```python
class KnowledgeBase:
    def __init__(self):
        self.network_share_path = global_config_manager.get_nested("network_share.path")
        # ... direct global config usage
```

**After**:
```python
class KnowledgeBase:
    def __init__(self, config_manager=None):
        self.config_manager = config_manager or global_config_manager
        self.network_share_path = self.config_manager.get_nested("network_share.path")
        # ... use injected config
```

#### Diagnostics Class

Similar pattern applied to `Diagnostics` class with optional config and LLM interface injection.

### 3. Backward Compatibility

All changes maintain full backward compatibility:

```python
# Old way - still works
orchestrator = Orchestrator()
kb = KnowledgeBase()
diagnostics = Diagnostics()

# New way - with dependency injection
config = get_config()
orchestrator = Orchestrator(config_manager=config)
kb = KnowledgeBase(config_manager=config)
diagnostics = Diagnostics(config_manager=config)
```

### 4. FastAPI Integration

Components can now be injected into FastAPI endpoints:

```python
from backend.dependencies import ConfigDep, OrchestratorDep

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    config: ConfigManager = ConfigDep,
    orchestrator: Orchestrator = OrchestratorDep
):
    # Use injected dependencies
    response = await orchestrator.execute_task(request.message)
    return response
```

## Benefits Achieved

### 1. **Improved Testability**

Components can now be tested with mock dependencies:

```python
def test_orchestrator_with_mock_config():
    mock_config = Mock(spec=ConfigManager)
    mock_config.get_llm_config.return_value = {"model": "test"}
    
    orchestrator = Orchestrator(config_manager=mock_config)
    
    # Test orchestrator behavior with controlled config
    mock_config.get_llm_config.assert_called_once()
```

### 2. **Reduced Coupling**

Components no longer directly import `global_config_manager`, making them more modular and easier to understand.

### 3. **Configuration Flexibility**

Different configurations can be used for different environments:

```python
# Production config
prod_orchestrator = Orchestrator(config_manager=production_config)

# Test config
test_orchestrator = Orchestrator(config_manager=test_config)
```

### 4. **FastAPI Integration**

Natural integration with FastAPI's dependency injection system for clean API endpoints.

## Testing

### Unit Tests

**File**: `tests/unit/test_dependency_injection.py`

Comprehensive test suite covering:
- Dependency injection functionality
- Backward compatibility
- Mock dependency testing
- FastAPI dependency providers

### Demo Script

**File**: `test_dependency_injection_demo.py`

Runnable demonstration script that validates:
- All components work with injected dependencies
- Backward compatibility is maintained
- Mock dependencies work correctly
- FastAPI patterns function properly

```bash
# Run demonstration
python test_dependency_injection_demo.py
```

## Usage Examples

### 1. Basic Dependency Injection

```python
from src.config import global_config_manager
from src.orchestrator import Orchestrator

# Create orchestrator with specific config
orchestrator = Orchestrator(config_manager=global_config_manager)
```

### 2. Full Dependency Chain

```python
from backend.dependencies import get_config, get_orchestrator

# Get fully configured orchestrator through dependency injection
config = get_config()
orchestrator = get_orchestrator()  # Gets config + all sub-dependencies
```

### 3. Testing with Mocks

```python
from unittest.mock import Mock
from src.orchestrator import Orchestrator

mock_config = Mock()
mock_config.get_llm_config.return_value = {"model": "test"}
mock_config.get_nested.return_value = "local"

# Test with controlled dependencies
orchestrator = Orchestrator(config_manager=mock_config)
```

### 4. FastAPI Endpoint

```python
from fastapi import APIRouter
from backend.dependencies import ConfigDep, OrchestratorDep

router = APIRouter()

@router.get("/system/status")
async def get_system_status(
    config: ConfigManager = ConfigDep,
    orchestrator: Orchestrator = OrchestratorDep
):
    return {
        "config_loaded": config is not None,
        "orchestrator_ready": orchestrator is not None,
        "model": config.get_llm_config().get("model")
    }
```

## Files Modified

### Core Components
- `src/orchestrator.py` - Added dependency injection support
- `src/knowledge_base.py` - Added config manager injection
- `src/diagnostics.py` - Added config and LLM interface injection

### Dependency Injection System
- `backend/dependencies.py` - FastAPI dependency providers
- `tests/unit/test_dependency_injection.py` - Comprehensive test suite
- `test_dependency_injection_demo.py` - Demonstration script

### Documentation
- `docs/architecture/dependency_injection.md` - This documentation

## Implementation Notes

### 1. **Lazy Imports**

Dependencies module uses lazy imports to avoid circular import issues:

```python
def get_knowledge_base(config: ConfigManager = Depends(get_config)):
    from src.knowledge_base import KnowledgeBase  # Lazy import
    return KnowledgeBase(config_manager=config)
```

### 2. **Caching Strategy**

Optional caching for expensive components:

```python
dependency_cache = DependencyCache()

def get_cached_orchestrator(config: ConfigManager = Depends(get_config)):
    return dependency_cache.get_or_create(
        "orchestrator",
        lambda: Orchestrator(config_manager=config)
    )
```

### 3. **Type Aliases**

Convenient type aliases for cleaner code:

```python
ConfigDep = Depends(get_config)
OrchestratorDep = Depends(get_orchestrator)

# Usage
def my_function(config: ConfigManager = ConfigDep): pass
```

## Future Enhancements

1. **Request-Scoped Dependencies**: Implement request-scoped caching for FastAPI
2. **Environment-Specific Configs**: Easy switching between dev/test/prod configurations
3. **Health Check Dependencies**: Dependency health monitoring and validation
4. **Additional Components**: Extend pattern to more components as needed

## Migration Guide

For existing code that directly uses components:

### Before
```python
from src.orchestrator import Orchestrator
orchestrator = Orchestrator()  # Uses global config internally
```

### After (Option 1 - Backward Compatible)
```python
from src.orchestrator import Orchestrator
orchestrator = Orchestrator()  # Still works exactly the same
```

### After (Option 2 - Explicit Dependency Injection)
```python
from src.orchestrator import Orchestrator
from src.config import global_config_manager

orchestrator = Orchestrator(config_manager=global_config_manager)
```

### After (Option 3 - FastAPI Endpoints)
```python
from backend.dependencies import OrchestratorDep

async def my_endpoint(orchestrator: Orchestrator = OrchestratorDep):
    # Use orchestrator with all dependencies injected
    pass
```

---

**Result**: Core components are now properly decoupled, more testable, and ready for advanced dependency injection patterns while maintaining full backward compatibility.