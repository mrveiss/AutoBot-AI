# LLM Interface Consolidation Migration Guide

## Overview

The AutoBot LLM interface has been consolidated from multiple fragmented implementations into a single, unified interface (`src/llm_interface_unified.py`) that provides consistent API access to all LLM providers.

## Changes Made

### Before Consolidation
- **Multiple Interfaces**: `llm_interface.py`, `llm_interface_extended.py`, multiple mock implementations
- **Inconsistent APIs**: Different method signatures and parameter formats
- **Provider Fragmentation**: Each interface handled providers differently
- **Configuration Complexity**: Multiple configuration approaches
- **Testing Issues**: Multiple mock implementations with different behaviors

### After Consolidation
- **Single Unified Interface**: `UnifiedLLMInterface` class in `llm_interface_unified.py`
- **Consistent API**: Standardized `chat_completion()` method across all providers
- **Provider Abstraction**: Clean separation between interface and providers
- **Centralized Configuration**: Unified configuration management
- **Comprehensive Testing**: Single mock provider implementation

## New Architecture

### Core Components

1. **UnifiedLLMInterface**: Main interface class
2. **LLMProvider**: Abstract base class for all providers
3. **Provider Implementations**: 
   - `OllamaProvider`
   - `OpenAIProvider` 
   - `MockProvider`
   - (Extensible for additional providers)

### Standardized Data Structures

```python
@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    llm_type: LLMType = LLMType.GENERAL
    provider: Optional[ProviderType] = None
    model_name: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    # ... additional parameters

@dataclass  
class LLMResponse:
    content: str
    provider: ProviderType
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    response_time: float = 0.0
    # ... additional metadata
```

## Migration Steps

### For Application Code

#### Old Pattern:
```python
from src.llm_interface import LLMInterface

llm = LLMInterface()
response = await llm.chat_completion(messages, llm_type="task")
content = response["choices"][0]["message"]["content"]
```

#### New Pattern:
```python
from src.llm_interface_unified import get_unified_llm_interface

llm = get_unified_llm_interface()
response = await llm.chat_completion(messages, llm_type="task")
content = response.content  # Direct access to content
```

### For Testing Code

#### Old Pattern:
```python
# Multiple different mock implementations
from tests.mock_llm_interface import MockLLMInterface
from src.intelligence.streaming_executor import MockLLMInterface as StreamingMock
```

#### New Pattern:
```python
from src.llm_interface_unified import get_unified_llm_interface
import config_manager

# Enable mock provider for testing
config_manager.set("llm.mock.enabled", True)
config_manager.set("llm.ollama.enabled", False) 
config_manager.set("llm.openai.enabled", False)

llm = get_unified_llm_interface()
# Mock provider will be used automatically
```

## Configuration Changes

### Old Configuration:
```python
# Multiple configuration sources
ollama_host = config_manager.get("llm.ollama.base_url", "http://localhost:11434")
openai_api_key = config_manager.get("llm.openai.api_key", "")
# Different configuration patterns across files
```

### New Configuration:
```yaml
# Centralized LLM configuration
llm:
  ollama:
    enabled: true
    base_url: "http://localhost:11434"
    default_model: "deepseek-r1:14b"
  openai:
    enabled: false
    api_key: ""
    default_model: "gpt-3.5-turbo"
  mock:
    enabled: true  # For testing
```

## API Reference

### Main Methods

#### chat_completion()
```python
async def chat_completion(
    messages: List[Dict[str, str]], 
    llm_type: Union[str, LLMType] = LLMType.GENERAL,
    provider: Optional[Union[str, ProviderType]] = None,
    model_name: Optional[str] = None,
    **kwargs
) -> LLMResponse
```

#### Legacy Compatibility Methods
```python
# For backward compatibility
async def generate_response(prompt: str, llm_type: str = "task", **kwargs) -> str
async def safe_query(prompt: str, **kwargs) -> Dict[str, Any]
```

#### Provider Management
```python
def get_provider_stats() -> Dict[str, Any]
async def get_available_models(provider: Optional[ProviderType] = None) -> Dict[str, List[str]]
async def health_check() -> Dict[str, Any]
```

## LLM Types

The unified interface supports different LLM usage contexts:

- `LLMType.ORCHESTRATOR`: For orchestration tasks (temperature: 0.3)
- `LLMType.TASK`: For specific task execution (temperature: 0.5)
- `LLMType.CHAT`: For conversational interactions (temperature: 0.7)
- `LLMType.RAG`: For retrieval-augmented generation (temperature: 0.2)
- `LLMType.EXTRACTION`: For data extraction tasks (temperature: 0.1, structured output)
- `LLMType.CLASSIFICATION`: For classification tasks
- `LLMType.ANALYSIS`: For analysis tasks
- `LLMType.GENERAL`: Default type

Each type has optimized defaults for temperature, max_tokens, and other parameters.

## Provider Priority & Fallback

The unified interface implements intelligent provider selection:

1. **Explicit Provider**: If specified, use that provider only
2. **Type-Based Preferences**: Each LLM type has preferred providers
3. **Automatic Fallback**: If preferred provider fails, fallback to others
4. **Health Checking**: Providers checked for availability before use

Example provider priority for different types:
```python
LLMType.ORCHESTRATOR: [OLLAMA, OPENAI, MOCK]
LLMType.CHAT: [OPENAI, OLLAMA, MOCK]  
LLMType.RAG: [OLLAMA, OPENAI, MOCK]
```

## Error Handling & Monitoring

### Enhanced Error Handling
- **Circuit Breaker**: Automatic provider isolation on failures
- **Retry Logic**: Configurable retry attempts with exponential backoff
- **Graceful Degradation**: Fallback to available providers
- **Structured Error Responses**: Consistent error format across providers

### Comprehensive Monitoring
- **Request Statistics**: Success/failure rates per provider
- **Performance Metrics**: Response times and usage tracking
- **Health Monitoring**: Real-time provider availability
- **Usage Analytics**: Token usage and cost tracking

## Files Updated

### Core Files:
- `src/llm_interface_unified.py` - New unified interface
- `src/agents/knowledge_extraction_agent.py` - Updated to use unified interface
- `tests/test_unified_llm_interface.py` - New comprehensive tests

### Configuration:
- Updated configuration management to support unified provider configs
- Centralized LLM type configurations

### Legacy Files (Deprecated):
- `src/llm_interface.py` - To be deprecated after full migration
- `src/llm_interface_extended.py` - Functionality merged into unified interface
- Various mock implementations - Replaced by single MockProvider

## Testing

### New Test Structure:
```python
class TestUnifiedLLMInterface:
    async def test_provider_selection()
    async def test_fallback_behavior() 
    async def test_llm_type_configurations()
    async def test_error_handling()
    async def test_monitoring_stats()
    async def test_backward_compatibility()
```

### Running Tests:
```bash
python tests/test_unified_llm_interface.py
```

## Benefits

### For Developers:
- **Single API**: One consistent interface for all LLM operations
- **Better Testing**: Unified mock provider for all test scenarios
- **Easier Configuration**: Centralized configuration management
- **Enhanced Debugging**: Comprehensive logging and monitoring

### For System Performance:
- **Intelligent Routing**: Automatic provider selection based on availability and performance
- **Fault Tolerance**: Graceful handling of provider failures with automatic fallback
- **Resource Management**: Connection pooling and concurrent request limiting
- **Cost Optimization**: Usage tracking and provider cost optimization

### For Maintenance:
- **Reduced Complexity**: Single codebase instead of multiple implementations
- **Easier Updates**: Provider updates isolated from interface changes
- **Better Documentation**: Centralized documentation and examples
- **Extensibility**: Easy addition of new providers without interface changes

## Rollback Plan

If issues arise during migration:

1. **Gradual Migration**: Update one component at a time
2. **Feature Flags**: Use configuration to enable/disable unified interface
3. **Legacy Support**: Old interfaces remain available during transition
4. **Quick Rollback**: Simple configuration change to revert to old interfaces

## Support

For questions or issues during migration:
- Check logs for detailed error messages
- Use health_check() method to verify provider status
- Review provider statistics with get_provider_stats()
- Enable debug logging for detailed troubleshooting