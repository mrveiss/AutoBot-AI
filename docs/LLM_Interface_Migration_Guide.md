# LLM Interface Migration Guide

> **Note (2026-01-31):** This guide has been updated after the Issue #738 code consolidation.
> The files `llm_interface_unified.py` and `unified_llm_interface.py` have been **deleted** as orphaned code.
> The canonical LLM interface is now `src/llm_interface.py` (facade) + `src/llm_interface_pkg/` (implementation).

## Overview

The AutoBot LLM interface provides consistent API access to all LLM providers through a facade pattern:

- **`src/llm_interface.py`** - Public facade (import from here)
- **`src/llm_interface_pkg/`** - Implementation package (internal)

## Current Architecture

### Core Components

1. **LLMInterface**: Main interface class (facade)
2. **LLMProvider**: Abstract base class for all providers
3. **Provider Implementations**:
   - `OllamaProvider`
   - `OpenAIProvider`
   - `MockHandler` (for testing)
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

## Usage

### Recommended Pattern (Current)

```python
from src.llm_interface import get_llm_interface

llm = get_llm_interface()
response = await llm.chat_completion(messages, llm_type="task")
content = response.content  # Direct access to content
```

### Alternative Import

```python
from src.llm_interface import LLMInterface

llm = LLMInterface()
response = await llm.chat_completion(messages, llm_type="orchestrator")
```

### For Testing Code

```python
from src.llm_interface import get_llm_interface
import config_manager

# Enable mock provider for testing
config_manager.set("llm.mock.enabled", True)
config_manager.set("llm.ollama.enabled", False)
config_manager.set("llm.openai.enabled", False)

llm = get_llm_interface()
# Mock provider will be used automatically
```

## Configuration

### Centralized LLM Configuration

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

The interface supports different LLM usage contexts:

- `LLMType.ORCHESTRATOR`: For orchestration tasks (temperature: 0.3)
- `LLMType.TASK`: For specific task execution (temperature: 0.5)
- `LLMType.CHAT`: For conversational interactions (temperature: 0.7)
- `LLMType.RAG`: For retrieval-augmented generation (temperature: 0.2)
- `LLMType.EXTRACTION`: For data extraction tasks (temperature: 0.1, structured output)
- `LLMType.CLASSIFICATION`: For classification tasks
- `LLMType.ANALYSIS`: For analysis tasks
- `LLMType.GENERAL`: Default type

Each type has optimized defaults for temperature, max_tokens, and other parameters.

## Provider Priority and Fallback

The interface implements intelligent provider selection:

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

## Error Handling and Monitoring

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

## Files Structure

### Current (After Issue #738 Consolidation)

- `src/llm_interface.py` - Public facade (61 lines)
- `src/llm_interface_pkg/` - Implementation package (~1000 lines)
  - `__init__.py` - Package exports
  - `providers/` - Provider implementations
  - `types.py` - Type definitions

### Removed Files (Issue #738)

- ~~`src/llm_interface_unified.py`~~ - DELETED (orphaned)
- ~~`src/unified_llm_interface.py`~~ - DELETED (orphaned)

## Testing

### Running Tests

```bash
pytest tests/unit/test_llm_interface.py -v
```

## Benefits

### For Developers

- **Single API**: One consistent interface for all LLM operations
- **Better Testing**: Unified mock provider for all test scenarios
- **Easier Configuration**: Centralized configuration management
- **Enhanced Debugging**: Comprehensive logging and monitoring

### For System Performance

- **Intelligent Routing**: Automatic provider selection based on availability and performance
- **Fault Tolerance**: Graceful handling of provider failures with automatic fallback
- **Resource Management**: Connection pooling and concurrent request limiting
- **Cost Optimization**: Usage tracking and provider cost optimization

### For Maintenance

- **Reduced Complexity**: Single codebase instead of multiple implementations
- **Easier Updates**: Provider updates isolated from interface changes
- **Better Documentation**: Centralized documentation and examples
- **Extensibility**: Easy addition of new providers without interface changes

## Support

For questions or issues:

- Check logs for detailed error messages
- Use health_check() method to verify provider status
- Review provider statistics with get_provider_stats()
- Enable debug logging for detailed troubleshooting
