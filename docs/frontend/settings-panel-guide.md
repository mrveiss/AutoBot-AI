# AutoBot Settings Panel Guide

## Overview

The SettingsPanel component (`autobot-vue/src/components/SettingsPanel.vue`) is the central configuration interface for AutoBot, providing comprehensive access to all system settings through a tabbed interface. This component handles both frontend UI settings and backend system configuration.

## Architecture

### Component Structure
- **Template**: Multi-tab interface with dynamic content sections
- **Script**: Vue 3 Composition API with reactive state management
- **Styling**: Responsive design with mobile-friendly adaptations

### Key Features
- **Real-time Health Monitoring**: Live status updates for LLM and embedding models
- **Dynamic Model Loading**: Automatic detection and loading of available models
- **Bi-directional Sync**: Settings sync between frontend, backend, and local storage
- **Error Handling**: Comprehensive error handling with user feedback
- **Auto-save**: Local storage persistence with manual backend saves

## Settings Categories

### 1. Chat Settings (`chat` tab)
Configuration for chat interface behavior.

```javascript
chat: {
  auto_scroll: true,           // Auto-scroll to bottom of chat
  max_messages: 100,           // Maximum messages to keep in memory
  message_retention_days: 30   // Days to retain chat history
}
```

### 2. Backend Settings (`backend` tab)
Multi-sub-tab configuration for backend services.

#### General Sub-tab
Basic backend connectivity and file paths:
- API endpoint configuration
- Server host and port settings
- Data directory paths (chat history, knowledge base, audit logs)
- CORS origins configuration

#### LLM Sub-tab
Language model configuration with provider support:

**Local Providers:**
- **Ollama**: Model selection, endpoint configuration
- **LM Studio**: Model selection, endpoint configuration

**Cloud Providers:**
- **OpenAI**: API key, endpoint, model selection
- **Anthropic**: API key, endpoint, model selection

**Settings:**
```javascript
backend: {
  llm: {
    provider_type: 'local|cloud',
    local: {
      provider: 'ollama|lmstudio',
      providers: {
        ollama: {
          endpoint: 'http://localhost:11434/api/generate',
          models: ['model1', 'model2'],
          selected_model: 'selected_model_name'
        }
      }
    }
  }
}
```

#### Embedding Sub-tab
Embedding model configuration for knowledge base operations:
- Provider selection (Ollama, OpenAI)
- Model-specific endpoints and API keys
- Real-time embedding model status

#### Memory Sub-tab
Memory and storage configuration:
- Long-term memory settings (retention period)
- Short-term memory settings (duration)
- Vector storage configuration
- ChromaDB settings (path, collection name)
- Redis configuration for chat history

### 3. UI Settings (`ui` tab)
Frontend interface customization:

```javascript
ui: {
  theme: 'light|dark',
  font_size: 'small|medium|large',
  language: 'en|es|fr|de',
  animations: true|false,
  developer_mode: true|false
}
```

### 4. Security Settings (`security` tab)
Security and access control:

```javascript
security: {
  enable_encryption: true|false,
  session_timeout_minutes: 30
}
```

### 5. Logging Settings (`logging` tab)
System logging configuration:

```javascript
logging: {
  log_level: 'debug|info|warning|error',
  log_to_file: true|false,
  log_file_path: 'path/to/log/file.log'
}
```

### 6. Knowledge Base Settings (`knowledgeBase` tab)
Knowledge base behavior:

```javascript
knowledge_base: {
  enabled: true|false,
  update_frequency_days: 7
}
```

### 7. Voice Interface Settings (`voiceInterface` tab)
Voice interaction configuration:

```javascript
voice_interface: {
  enabled: true|false,
  voice: 'default|male1|female1',
  speech_rate: 1.0  // 0.5 to 2.0
}
```

### 8. System Prompts Settings (`prompts` tab)
System prompt management interface:
- Prompt listing with categories
- In-line prompt editor
- Save/revert functionality
- Default prompt restoration

### 9. Developer Settings (`developer` tab)
Development and debugging tools:

```javascript
developer: {
  enabled: true|false,
  enhanced_errors: true|false,
  endpoint_suggestions: true|false,
  debug_logging: true|false
}
```

**Developer Features:**
- System information display
- API endpoint discovery
- Enhanced error messaging
- Debug logging controls

## Key Methods

### Settings Management
```javascript
// Load settings from backend config.yaml
loadSettingsFromBackend()

// Save settings to backend config.yaml
saveSettings()

// Deep merge settings objects
deepMerge(target, source)
```

### Model Management
```javascript
// Load available LLM models
loadModels()

// Load available embedding models
loadEmbeddingModels()

// Notify backend of provider changes
notifyBackendOfProviderChange()
notifyBackendOfEmbeddingChange()
```

### Health Monitoring
```javascript
// Check system health status
checkHealthStatus()

// Get current LLM configuration display
getCurrentLLMDisplay()

// Get current embedding configuration
getCurrentEmbeddingConfig()
```

### Prompt Management
```javascript
// Load system prompts from backend
loadPrompts()

// Select prompt for editing
selectPrompt(prompt)

// Save edited prompt
savePrompt()

// Revert prompt to default
revertPromptToDefault(promptId)
```

### Developer Tools
```javascript
// Update developer configuration
updateDeveloperConfig()

// Load developer system information
loadDeveloperInfo()

// Show available API endpoints
showApiEndpoints()
```

## State Management

### Reactive State
```javascript
const settings = ref({})           // Main settings object
const isSettingsLoaded = ref(false)  // Loading state
const healthStatus = ref({})       // System health status
const developerInfo = ref(null)    // Developer information
const isSaving = ref(false)        // Save operation state
const saveMessage = ref('')        // Save result message
```

### Settings Persistence
1. **Primary**: Backend `config.yaml` file (manual save)
2. **Fallback**: Browser localStorage (auto-save on changes)
3. **Default**: Hardcoded defaults if both fail

### Health Monitoring
- **Interval**: 10-second health checks
- **Indicators**: Connection status for LLM and embedding models
- **Display**: Real-time status with visual indicators

## API Integration

### Configuration Endpoints
```javascript
// GET /api/settings/config - Load settings
// POST /api/settings/config - Save settings
```

### Model Discovery
```javascript
// GET /api/llm/models - Get available LLM models
// POST /api/llm/provider - Update LLM provider
```

### Health Monitoring
```javascript
// GET /api/system/health - System health status
```

### Developer Tools
```javascript
// GET /api/settings/system-info - System information
// GET /api/settings/api-endpoints - Available API endpoints
// POST /api/settings/developer-config - Update dev config
```

### Prompt Management
```javascript
// GET /api/prompts - Load system prompts
// POST /api/prompts/{id} - Save prompt
// DELETE /api/prompts/{id} - Revert prompt
```

## Error Handling

### Connection Errors
- **Fallback**: Local storage when backend unavailable
- **User Feedback**: Clear error messages with suggested actions
- **Recovery**: Automatic retry mechanisms

### Validation
- **Input Validation**: Real-time validation for numeric inputs
- **Range Checking**: Enforced min/max values
- **Format Validation**: URL and path format checking

### Model Loading Errors
```javascript
// Handle different API response formats
if (data.models && Array.isArray(data.models)) {
  // Process model array with object or string format
} else if (Array.isArray(data)) {
  // Direct array response
}
```

## Responsive Design

### Breakpoint Handling
- **Desktop**: Multi-column layout with tabs
- **Mobile**: Stacked layout with collapsible sections
- **Adaptive**: `clamp()` CSS functions for fluid sizing

### Mobile Optimizations
```css
@media (max-width: 768px) {
  .setting-item {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
}
```

## Usage Examples

### Basic Settings Access
```vue
<template>
  <SettingsPanel />
</template>

<script>
import SettingsPanel from '@/components/SettingsPanel.vue'

export default {
  components: { SettingsPanel }
}
</script>
```

### Programmatic Settings Update
```javascript
// Update LLM model
settings.value.backend.llm.local.providers.ollama.selected_model = 'new-model'
await notifyBackendOfProviderChange()

// Update UI theme
settings.value.ui.theme = 'dark'
await saveSettings()
```

### Health Status Monitoring
```javascript
// Check if LLM is connected
if (healthStatus.value.llm.connected) {
  console.log('LLM is connected:', healthStatus.value.llm.current_model)
}

// Monitor embedding status
if (healthStatus.value.embedding.connected) {
  console.log('Embedding model:', healthStatus.value.embedding.current_model)
}
```

## Configuration Examples

### Complete LLM Configuration
```javascript
const llmConfig = {
  provider_type: 'local',
  local: {
    provider: 'ollama',
    providers: {
      ollama: {
        endpoint: 'http://localhost:11434/api/generate',
        models: ['deepseek-r1:14b', 'artifish/llama3.2-uncensored:latest'],
        selected_model: 'deepseek-r1:14b'
      }
    }
  },
  embedding: {
    provider: 'ollama',
    providers: {
      ollama: {
        endpoint: 'http://localhost:11434/api/embeddings',
        models: ['nomic-embed-text:latest'],
        selected_model: 'nomic-embed-text:latest'
      }
    }
  }
}
```

### Memory Configuration
```javascript
const memoryConfig = {
  redis: {
    enabled: true,
    host: 'localhost',
    port: 6379
  },
  chromadb: {
    enabled: true,
    path: 'data/chromadb/chroma.sqlite3',
    collection_name: 'autobot_memory'
  }
}
```

## Best Practices

### Development
1. **State Management**: Use reactive refs for all dynamic data
2. **Error Handling**: Provide fallbacks for all API calls
3. **User Feedback**: Show loading states and save confirmations
4. **Validation**: Validate inputs before sending to backend

### Configuration
1. **Defaults**: Provide sensible defaults for all settings
2. **Persistence**: Auto-save to localStorage, manual save to backend
3. **Health Checks**: Monitor system status continuously
4. **Model Management**: Auto-detect and validate model availability

### Performance
1. **Lazy Loading**: Load settings only when panel is opened
2. **Debouncing**: Debounce API calls for frequent updates
3. **Caching**: Cache model lists to avoid repeated API calls
4. **Memory**: Clean up intervals on component unmount

## Troubleshooting

### Common Issues

**Settings not saving:**
```javascript
// Check network connection
console.log('API endpoint:', settings.value.backend.api_endpoint)

// Verify backend response
const response = await apiClient.post('/api/settings/config', settingsData)
console.log('Save response:', await response.json())
```

**Models not loading:**
```javascript
// Check LLM endpoint
fetch('http://localhost:11434/api/tags')
  .then(r => r.json())
  .then(data => console.log('Ollama models:', data))

// Verify API response format
console.log('Model API response structure:', {
  hasModels: !!data.models,
  isArray: Array.isArray(data.models)
})
```

**Health status not updating:**
```javascript
// Check health check interval
console.log('Health check interval active:', !!healthCheckInterval)

// Manual health check
await checkHealthStatus()
console.log('Health status:', healthStatus.value)
```

## Future Enhancements

### Planned Features
1. **Import/Export**: Settings backup and restore functionality
2. **Profiles**: Multiple configuration profiles
3. **Validation**: Real-time setting validation
4. **Themes**: Additional UI theme options
5. **Notifications**: Setting change notifications

### Integration Improvements
1. **Real-time Sync**: WebSocket-based setting synchronization
2. **Conflict Resolution**: Handle concurrent setting modifications
3. **Version Control**: Track setting change history
4. **Team Settings**: Shared configuration for team environments

---

The SettingsPanel component is the core configuration interface for AutoBot, providing comprehensive access to all system settings with real-time monitoring, error handling, and responsive design. It serves as the central hub for system administration and customization.
