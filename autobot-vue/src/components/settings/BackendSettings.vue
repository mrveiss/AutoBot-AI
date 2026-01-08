<template>
  <div v-if="isSettingsLoaded" class="settings-section">
    <div class="sub-tabs">
      <button
        :class="{ active: activeBackendSubTab === 'general' }"
        @click="$emit('subtab-changed', 'general')"
        aria-label="General"
      >
        General
      </button>
      <button
        :class="{ active: activeBackendSubTab === 'llm' }"
        @click="$emit('subtab-changed', 'llm')"
        aria-label="LLM"
      >
        LLM
      </button>
      <button
        :class="{ active: activeBackendSubTab === 'embedding' }"
        @click="$emit('subtab-changed', 'embedding')"
        aria-label="Embedding"
      >
        Embedding
      </button>
      <button
        :class="{ active: activeBackendSubTab === 'memory' }"
        @click="$emit('subtab-changed', 'memory')"
        aria-label="Memory"
      >
        Memory
      </button>
      <button
        :class="{ active: activeBackendSubTab === 'agents' }"
        @click="$emit('subtab-changed', 'agents')"
        aria-label="Agents"
      >
        Agents
      </button>
    </div>

    <!-- General Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'general'" class="sub-tab-content">
      <h3>Backend General Settings</h3>

      <!-- Connection Status Banner -->
      <div class="connection-status-banner" :class="connectionStatus.status">
        <div class="status-info">
          <i :class="getConnectionIcon(connectionStatus.status)"></i>
          <span class="status-text">{{ connectionStatus.message }}</span>
          <span v-if="connectionStatus.responseTime" class="response-time">
            ({{ connectionStatus.responseTime }}ms)
          </span>
        </div>
        <div class="status-actions">
          <button
            @click="testConnection"
            :disabled="isTestingConnection"
            class="test-connection-btn"
          >
            <i :class="isTestingConnection ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
            {{ isTestingConnection ? 'Testing...' : 'Test Connection' }}
          </button>
          <button @click="refreshConnectionStatus" class="refresh-status-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
      </div>

      <div class="setting-item">
        <label for="api-endpoint">API Endpoint</label>
        <div class="input-group">
          <input
            id="api-endpoint"
            type="text"
            :value="backendSettings?.api_endpoint || ''"
            @input="handleInputChange('api_endpoint')"
            :class="{ 'validation-error': validationErrors.api_endpoint }"
          />
          <div v-if="validationErrors.api_endpoint" class="validation-message error">
            {{ validationErrors.api_endpoint }}
          </div>
          <div v-else-if="validationSuccess.api_endpoint" class="validation-message success">
            ✓ Valid endpoint format
          </div>
        </div>
      </div>

      <div class="setting-item">
        <label for="server-host">Server Host</label>
        <div class="input-group">
          <input
            id="server-host"
            type="text"
            :value="backendSettings?.server_host || ''"
            @input="handleInputChange('server_host')"
            :class="{ 'validation-error': validationErrors.server_host }"
          />
          <div v-if="validationErrors.server_host" class="validation-message error">
            {{ validationErrors.server_host }}
          </div>
          <div v-else-if="validationSuccess.server_host" class="validation-message success">
            ✓ Valid host format
          </div>
        </div>
      </div>

      <div class="setting-item">
        <label for="server-port">Server Port</label>
        <div class="input-group">
          <input
            id="server-port"
            type="number"
            :value="backendSettings?.server_port || 8001"
            min="1"
            max="65535"
            @input="handleNumberInputChange('server_port')"
            :class="{ 'validation-error': validationErrors.server_port }"
          />
          <div v-if="validationErrors.server_port" class="validation-message error">
            {{ validationErrors.server_port }}
          </div>
          <div v-else-if="validationSuccess.server_port" class="validation-message success">
            ✓ Valid port range (1-65535)
          </div>
        </div>
      </div>

      <div class="setting-item">
        <label for="chat-data-dir">Chat Data Directory</label>
        <div class="input-group">
          <input
            id="chat-data-dir"
            type="text"
            :value="backendSettings?.chat_data_dir || ''"
            @input="handleInputChange('chat_data_dir')"
          />
          <button @click="validatePath('chat_data_dir')" class="validate-path-btn">
            <i class="fas fa-folder-open"></i> Check Path
          </button>
        </div>
      </div>

      <div class="setting-item">
        <label for="chat-history-file">Chat History File</label>
        <input
          id="chat-history-file"
          type="text"
          :value="backendSettings?.chat_history_file || ''"
          placeholder="data/chat_history.json"
          @input="handleGeneralInputChange('chat_history_file')"
        />
      </div>
      <div class="setting-item">
        <label for="knowledge-base-db">Knowledge Base DB</label>
        <input
          id="knowledge-base-db"
          type="text"
          :value="backendSettings?.knowledge_base_db || ''"
          placeholder="data/knowledge_base.db"
          @input="handleGeneralInputChange('knowledge_base_db')"
        />
      </div>
      <div class="setting-item">
        <label for="reliability-stats-file">Reliability Stats File</label>
        <input
          id="reliability-stats-file"
          type="text"
          :value="backendSettings?.reliability_stats_file || ''"
          placeholder="data/reliability_stats.json"
          @input="handleGeneralInputChange('reliability_stats_file')"
        />
      </div>
      <div class="setting-item">
        <label for="logs-directory">Logs Directory</label>
        <input
          id="logs-directory"
          type="text"
          :value="backendSettings?.logs_directory || ''"
          placeholder="logs/"
          @input="handleGeneralInputChange('logs_directory')"
        />
      </div>
      <div class="setting-item">
        <label for="chat-enabled">Chat Enabled</label>
        <input
          id="chat-enabled"
          type="checkbox"
          :checked="backendSettings?.chat_enabled || false"
          @change="handleGeneralCheckboxChange('chat_enabled')"
        />
      </div>
      <div class="setting-item">
        <label for="knowledge-base-enabled">Knowledge Base Enabled</label>
        <input
          id="knowledge-base-enabled"
          type="checkbox"
          :checked="backendSettings?.knowledge_base_enabled || false"
          @change="handleGeneralCheckboxChange('knowledge_base_enabled')"
        />
      </div>
      <div class="setting-item">
        <label for="auto-backup-chat">Auto Backup Chat</label>
        <input
          id="auto-backup-chat"
          type="checkbox"
          :checked="backendSettings?.auto_backup_chat || false"
          @change="handleGeneralCheckboxChange('auto_backup_chat')"
        />
      </div>
    </div>

    <!-- LLM Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'llm'" class="sub-tab-content">
      <h3>LLM Configuration</h3>

      <!-- Enhanced LLM Status Display -->
      <div class="llm-status-display">
        <div class="current-llm-info">
          <strong>Current LLM:</strong> {{ currentLLMDisplay }}
        </div>
        <div
          v-if="healthStatus?.backend?.llm_provider"
          :class="['health-indicator', healthStatus.backend.llm_provider.status || 'unknown']"
        >
          <i :class="getHealthIconClass(healthStatus.backend.llm_provider.status)"></i>
          {{ healthStatus.backend.llm_provider.message || 'Status unknown' }}
        </div>
        <div class="llm-actions">
          <button @click="testLLMConnection" :disabled="isTestingLLM" class="test-llm-btn">
            <i :class="isTestingLLM ? 'fas fa-spinner fa-spin' : 'fas fa-brain'"></i>
            {{ isTestingLLM ? 'Testing LLM...' : 'Test LLM' }}
          </button>
          <button @click="refreshLLMModels" :disabled="isRefreshingLLMModels" class="refresh-models-btn">
            <i :class="isRefreshingLLMModels ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
            {{ isRefreshingLLMModels ? 'Refreshing...' : 'Refresh Models' }}
          </button>
        </div>
      </div>

      <div class="setting-item">
        <label for="provider-type">Provider Type</label>
        <select
          id="provider-type"
          :value="llmSettings?.provider_type || 'local'"
          @change="handleLLMSelectChange('provider_type')"
        >
          <option value="local">Local LLM</option>
          <option value="cloud">Cloud LLM</option>
        </select>
      </div>

      <!-- Local LLM Settings -->
      <div v-if="llmSettings?.provider_type === 'local'" class="provider-section">
        <div class="setting-item">
          <label for="local-provider">Local Provider</label>
          <select
            id="local-provider"
            :value="llmSettings.local?.provider || 'ollama'"
            @change="handleLLMSelectChange('local.provider')"
          >
            <option value="ollama">Ollama</option>
            <option value="lmstudio">LM Studio</option>
          </select>
        </div>

        <!-- Ollama Settings -->
        <div v-if="llmSettings.local?.provider === 'ollama'" class="provider-config">
          <div class="setting-item">
            <label for="ollama-endpoint">Ollama Endpoint</label>
            <div class="input-group">
              <input
                id="ollama-endpoint"
                type="text"
                :value="llmSettings.local?.providers?.ollama?.endpoint || ''"
                @input="handleLLMInputChangeValidated('local.providers.ollama.endpoint')"
                :class="{ 'validation-error': validationErrors.ollama_endpoint }"
              />
              <button @click="testOllamaConnection" class="test-endpoint-btn">
                <i class="fas fa-plug"></i>
              </button>
            </div>
          </div>
          <div class="setting-item">
            <label for="ollama-model">Model</label>
            <div class="model-selection">
              <select
                id="ollama-model"
                :value="llmSettings.local?.providers?.ollama?.selected_model || ''"
                @change="handleLLMSelectChange('local.providers.ollama.selected_model')"
              >
                <option
                  v-for="model in llmSettings.local?.providers?.ollama?.models || []"
                  :key="model"
                  :value="model"
                >
                  {{ model }}
                </option>
              </select>
              <div v-if="isRefreshingLLMModels" class="loading-indicator">
                <i class="fas fa-spinner fa-spin"></i> Loading models...
              </div>
            </div>
          </div>
        </div>

        <!-- LM Studio Settings -->
        <div v-else-if="llmSettings.local?.provider === 'lmstudio'" class="provider-config">
          <div class="setting-item">
            <label for="lmstudio-endpoint">LM Studio Endpoint</label>
            <div class="input-group">
              <input
                id="lmstudio-endpoint"
                type="text"
                :value="llmSettings.local?.providers?.lmstudio?.endpoint || ''"
                @input="handleLLMInputChangeValidated('local.providers.lmstudio.endpoint')"
                :class="{ 'validation-error': validationErrors.lmstudio_endpoint }"
              />
              <button @click="testLMStudioConnection" class="test-endpoint-btn">
                <i class="fas fa-plug"></i>
              </button>
            </div>
          </div>
          <div class="setting-item">
            <label for="lmstudio-model">Model</label>
            <select
              id="lmstudio-model"
              :value="llmSettings.local?.providers?.lmstudio?.selected_model || ''"
              @change="handleLLMSelectChange('local.providers.lmstudio.selected_model')"
            >
              <option
                v-for="model in llmSettings.local?.providers?.lmstudio?.models || []"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <!-- Cloud LLM Settings -->
      <div v-else-if="llmSettings?.provider_type === 'cloud'" class="provider-section">
        <div class="setting-item">
          <label for="cloud-provider">Cloud Provider</label>
          <select
            id="cloud-provider"
            :value="llmSettings.cloud?.provider || 'openai'"
            @change="handleLLMSelectChange('cloud.provider')"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </div>

        <!-- OpenAI Settings -->
        <div v-if="llmSettings.cloud?.provider === 'openai'" class="provider-config">
          <div class="setting-item">
            <label for="openai-api-key">API Key</label>
            <div class="input-group">
              <input
                id="openai-api-key"
                type="password"
                :value="llmSettings.cloud?.providers?.openai?.api_key || ''"
                placeholder="Enter API Key"
                @input="handleLLMInputChangeValidated('cloud.providers.openai.api_key')"
                :class="{ 'validation-error': validationErrors.openai_api_key }"
              />
              <button @click="testOpenAIConnection" class="test-endpoint-btn">
                <i class="fas fa-key"></i> Test
              </button>
            </div>
          </div>
          <div class="setting-item">
            <label for="openai-endpoint">Endpoint</label>
            <input
              id="openai-endpoint"
              type="text"
              :value="llmSettings.cloud?.providers?.openai?.endpoint || ''"
              @input="handleLLMInputChange('cloud.providers.openai.endpoint')"
            />
          </div>
          <div class="setting-item">
            <label for="openai-model">Model</label>
            <select
              id="openai-model"
              :value="llmSettings.cloud?.providers?.openai?.selected_model || ''"
              @change="handleLLMSelectChange('cloud.providers.openai.selected_model')"
            >
              <option
                v-for="model in llmSettings.cloud?.providers?.openai?.models || []"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
          </div>
        </div>

        <!-- Anthropic Settings -->
        <div v-else-if="llmSettings.cloud?.provider === 'anthropic'" class="provider-config">
          <div class="setting-item">
            <label for="anthropic-api-key">API Key</label>
            <div class="input-group">
              <input
                id="anthropic-api-key"
                type="password"
                :value="llmSettings.cloud?.providers?.anthropic?.api_key || ''"
                placeholder="Enter API Key"
                @input="handleLLMInputChangeValidated('cloud.providers.anthropic.api_key')"
                :class="{ 'validation-error': validationErrors.anthropic_api_key }"
              />
              <button @click="testAnthropicConnection" class="test-endpoint-btn">
                <i class="fas fa-key"></i> Test
              </button>
            </div>
          </div>
          <div class="setting-item">
            <label for="anthropic-model">Model</label>
            <select
              id="anthropic-model"
              :value="llmSettings.cloud?.providers?.anthropic?.selected_model || ''"
              @change="handleLLMSelectChange('cloud.providers.anthropic.selected_model')"
            >
              <option
                v-for="model in llmSettings.cloud?.providers?.anthropic?.models || []"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- Embedding Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'embedding'" class="sub-tab-content">
      <h3>Embedding Configuration</h3>

      <!-- Embedding Status Display -->
      <div v-if="embeddingStatus" class="embedding-status-display">
        <div class="current-embedding-info">
          <strong>Current Embedding Model:</strong> {{ getCurrentEmbeddingModel() }}
        </div>
        <div
          :class="['health-indicator', embeddingStatus.status || 'unknown']"
        >
          <i :class="getHealthIconClass(embeddingStatus.status)"></i>
          {{ embeddingStatus.message || 'Status unknown' }}
        </div>
        <div class="embedding-actions">
          <button @click="testEmbeddingConnection" :disabled="isTestingEmbedding" class="test-embedding-btn">
            <i :class="isTestingEmbedding ? 'fas fa-spinner fa-spin' : 'fas fa-vector-square'"></i>
            {{ isTestingEmbedding ? 'Testing...' : 'Test Embedding' }}
          </button>
          <button @click="refreshEmbeddingModels" :disabled="isRefreshingModels" class="refresh-models-btn">
            <i :class="isRefreshingModels ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
            {{ isRefreshingModels ? 'Refreshing...' : 'Refresh Models' }}
          </button>
        </div>
      </div>

      <div class="setting-item">
        <label for="embedding-provider">Embedding Provider</label>
        <select
          id="embedding-provider"
          :value="embeddingSettings?.provider || 'ollama'"
          @change="handleEmbeddingProviderChange"
        >
          <option value="ollama">Ollama</option>
          <option value="openai">OpenAI</option>
          <option value="huggingface">Hugging Face</option>
        </select>
      </div>

      <!-- Provider-specific settings -->
      <div class="provider-section">
        <div class="setting-item">
          <label for="embedding-endpoint">Endpoint</label>
          <div class="input-group">
            <input
              id="embedding-endpoint"
              type="text"
              :value="getCurrentEmbeddingEndpoint()"
              @input="handleEmbeddingEndpointChange"
              :class="{ 'validation-error': validationErrors.embedding_endpoint }"
            />
            <button @click="testEmbeddingEndpoint" class="test-endpoint-btn">
              <i class="fas fa-plug"></i>
            </button>
          </div>
        </div>

        <div class="setting-item">
          <label for="embedding-model">Model</label>
          <div class="model-selection">
            <select
              id="embedding-model"
              :value="getCurrentEmbeddingModel()"
              @change="handleEmbeddingModelChange"
            >
              <option
                v-for="model in getAvailableEmbeddingModels()"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
            <div v-if="isRefreshingModels" class="loading-indicator">
              <i class="fas fa-spinner fa-spin"></i> Loading models...
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Memory Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'memory'" class="sub-tab-content">
      <h3>Memory Configuration</h3>

      <div class="setting-item">
        <label for="enable-memory">Enable Memory System</label>
        <input
          id="enable-memory"
          type="checkbox"
          :checked="backendSettings?.memory?.enabled || false"
          @change="handleMemoryCheckboxChange('enabled')"
        />
      </div>

      <div class="setting-item">
        <label for="memory-type">Memory Type</label>
        <select
          id="memory-type"
          :value="backendSettings?.memory?.type || 'redis'"
          @change="handleMemorySelectChange('type')"
        >
          <option value="redis">Redis</option>
          <option value="chroma">ChromaDB</option>
          <option value="memory">In-Memory</option>
        </select>
      </div>

      <div class="setting-item">
        <label for="memory-limit">Memory Limit (entries)</label>
        <input
          id="memory-limit"
          type="number"
          :value="backendSettings?.memory?.max_entries || 1000"
          min="100"
          max="10000"
          @input="handleMemoryInputChange('max_entries')"
        />
      </div>

      <div class="setting-item">
        <label for="auto-cleanup">Auto Cleanup</label>
        <input
          id="auto-cleanup"
          type="checkbox"
          :checked="backendSettings?.memory?.auto_cleanup || false"
          @change="handleMemoryCheckboxChange('auto_cleanup')"
        />
      </div>
    </div>

    <!-- Agents Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'agents'" class="sub-tab-content">
      <h3>Agent Configuration</h3>

      <div class="setting-item">
        <label for="max-agents">Maximum Concurrent Agents</label>
        <input
          id="max-agents"
          type="number"
          :value="backendSettings?.agents?.max_concurrent || 5"
          min="1"
          max="20"
          @input="handleAgentInputChange('max_concurrent')"
        />
      </div>

      <div class="setting-item">
        <label for="agent-timeout">Agent Timeout (seconds)</label>
        <input
          id="agent-timeout"
          type="number"
          :value="backendSettings?.agents?.timeout || 300"
          min="30"
          max="3600"
          @input="handleAgentInputChange('timeout')"
        />
      </div>

      <div class="setting-item">
        <label for="enable-agent-memory">Enable Agent Memory</label>
        <input
          id="enable-agent-memory"
          type="checkbox"
          :checked="backendSettings?.agents?.enable_memory || false"
          @change="handleAgentCheckboxChange('enable_memory')"
        />
      </div>

      <div class="setting-item">
        <label for="agent-log-level">Agent Log Level</label>
        <select
          id="agent-log-level"
          :value="backendSettings?.agents?.log_level || 'INFO'"
          @change="handleAgentSelectChange('log_level')"
        >
          <option value="DEBUG">Debug</option>
          <option value="INFO">Info</option>
          <option value="WARNING">Warning</option>
          <option value="ERROR">Error</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { HealthStatus } from "@/types/settings"

import { computed, ref, reactive, onMounted } from 'vue'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BackendSettings')


interface EmbeddingSettings {
  provider: string
  providers: {
    [key: string]: {
      endpoint?: string
      selected_model?: string
      models?: string[]
    }
  }
}

interface EmbeddingStatus {
  status: string
  message: string
}

// Issue #156 Fix: Proper TypeScript interfaces instead of 'any'
interface HardwareSettings {
  enable_gpu?: boolean
  enable_npu?: boolean
  memory_limit?: number
}

interface MemorySettings {
  enabled?: boolean
  type?: string
  max_entries?: number
  auto_cleanup?: boolean
}

interface AgentSettings {
  max_concurrent?: number
  timeout?: number
  enable_memory?: boolean
  log_level?: string
}

interface ProviderConfig {
  endpoint?: string
  selected_model?: string
  models?: string[]
  api_key?: string
}

interface LocalLLMSettings {
  provider?: string
  providers?: {
    ollama?: ProviderConfig
    lmstudio?: ProviderConfig
  }
}

interface CloudLLMSettings {
  provider?: string
  providers?: {
    openai?: ProviderConfig
    anthropic?: ProviderConfig
  }
}

interface LLMSettings {
  provider_type?: string
  local?: LocalLLMSettings
  cloud?: CloudLLMSettings
}

interface BackendSettings {
  api_endpoint?: string
  server_host?: string
  server_port?: number
  chat_data_dir?: string
  chat_history_file?: string
  knowledge_base_db?: string
  reliability_stats_file?: string
  logs_directory?: string
  chat_enabled?: boolean
  knowledge_base_enabled?: boolean
  auto_backup_chat?: boolean
  hardware?: HardwareSettings
  memory?: MemorySettings
  agents?: AgentSettings
  llm?: LLMSettings
}

interface Props {
  backendSettings?: BackendSettings
  llmSettings?: LLMSettings
  isSettingsLoaded: boolean
  activeBackendSubTab: string
  healthStatus: HealthStatus | null
  currentLLMDisplay: string
  embeddingSettings?: EmbeddingSettings | null
  embeddingStatus?: EmbeddingStatus | null
}

interface Emits {
  (e: 'subtab-changed', subtab: string): void
  (e: 'setting-changed', key: string, value: any): void
  (e: 'llm-setting-changed', key: string, value: any): void
  (e: 'embedding-setting-changed', key: string, value: any): void
  (e: 'refresh-embedding-models', provider: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Enhanced reactive state
const isTestingConnection = ref(false)
const isTestingLLM = ref(false)
const isTestingEmbedding = ref(false)
const isTestingGPU = ref(false)
const isTestingNPU = ref(false)
const isRefreshingModels = ref(false)
const isRefreshingLLMModels = ref(false)

// Type definitions for hardware status
interface GPUDetails {
  utilization: number
  memory: string
  temperature: string
  name: string
}

interface NPUDetails {
  available: boolean
  wsl_limitation: boolean
}

interface MemoryDetails {
  total: string
  available: string
  used: string
  percent: string
}

interface HardwareStatusItem<T> {
  status: string
  message: string
  details: T | null
}

interface ConnectionStatus {
  status: string
  message: string
  responseTime: number | null
}

interface HardwareStatus {
  gpu: HardwareStatusItem<GPUDetails>
  npu: HardwareStatusItem<NPUDetails>
  memory: HardwareStatusItem<MemoryDetails>
}

// Validation state
const validationErrors = reactive<Record<string, string>>({})
const validationSuccess = reactive<Record<string, boolean>>({})

// Connection status
const connectionStatus = reactive<ConnectionStatus>({
  status: 'unknown', // 'connected', 'disconnected', 'testing', 'unknown'
  message: 'Connection status unknown',
  responseTime: null
})

// Hardware status
const hardwareStatus = reactive<HardwareStatus>({
  gpu: {
    status: 'unknown',
    message: 'GPU status not checked',
    details: null
  },
  npu: {
    status: 'unknown',
    message: 'NPU status not checked',
    details: null
  },
  memory: {
    status: 'unknown',
    message: 'Memory status not checked',
    details: null
  }
})

// Computed properties
const llmSettings = computed(() => props.backendSettings?.llm)
const memorySettings = computed(() => props.backendSettings?.memory)
const agentSettings = computed(() => props.backendSettings?.agents)

const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

// Enhanced update setting with validation
const updateSettingWithValidation = (key: string, value: any) => {
  // Clear previous validation state
  delete validationErrors[key]
  delete validationSuccess[key]

  // Validate based on key
  const validation = validateSetting(key, value)

  if (validation.isValid) {
    validationSuccess[key] = true
    emit('setting-changed', key, value)
  } else {
    validationErrors[key] = validation.error || 'Validation failed'
  }
}

// Typed event handlers for input fields
const handleInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSettingWithValidation(key, target.value)
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSettingWithValidation(key, parseInt(target.value))
}

const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.checked)
}

const handleLLMInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('llm-setting-changed', key, target.value)
}

const handleLLMNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('llm-setting-changed', key, parseFloat(target.value))
}

const handleEmbeddingInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('embedding-setting-changed', key, target.value)
}

// Additional typed event handlers for all input types
const handleGeneralInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.value)
}

const handleGeneralNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, parseInt(target.value))
}

const handleGeneralCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.checked)
}

const handleGeneralSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateSetting(key, target.value)
}

const handleLLMInputChangeValidated = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateLLMSettingWithValidation(key, target.value)
}

const handleLLMSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateLLMSetting(key, target.value)
}

const handleLLMCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateLLMSetting(key, target.checked)
}

// Embedding settings handlers
const handleEmbeddingProviderChange = (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateEmbeddingProvider(target.value)
}

const handleEmbeddingModelChange = (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateEmbeddingModel(target.value)
}

const handleEmbeddingEndpointChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  updateEmbeddingEndpoint(target.value)
}

// Memory settings handlers
const handleMemoryInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateMemorySetting(key, parseInt(target.value))
}

const handleMemoryCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateMemorySetting(key, target.checked)
}

const handleMemorySelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateMemorySetting(key, target.value)
}

// Agent settings handlers
const handleAgentInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateAgentSetting(key, parseInt(target.value))
}

const handleAgentCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateAgentSetting(key, target.checked)
}

const handleAgentSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  updateAgentSetting(key, target.value)
}

const validateSetting = (key: string, value: any) => {
  switch (key) {
    case 'api_endpoint':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'API endpoint is required' }
      }
      if (!value.startsWith('http://') && !value.startsWith('https://')) {
        return { isValid: false, error: 'Must start with http:// or https://' }
      }
      return { isValid: true }

    case 'server_host':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'Server host is required' }
      }
      // Basic hostname/IP validation
      const hostRegex = /^[a-zA-Z0-9.-]+$/
      if (!hostRegex.test(value)) {
        return { isValid: false, error: 'Invalid host format' }
      }
      return { isValid: true }

    case 'server_port':
      if (!value || isNaN(value) || value < 1 || value > 65535) {
        return { isValid: false, error: 'Port must be between 1 and 65535' }
      }
      return { isValid: true }

    default:
      return { isValid: true }
  }
}

const updateLLMSetting = (key: string, value: any) => {
  emit('llm-setting-changed', key, value)
}

const updateLLMSettingWithValidation = (key: string, value: any) => {
  // Clear previous validation
  const validationKey = key.replace(/\./g, '_')
  delete validationErrors[validationKey]

  // Validate endpoint URLs
  if (key.includes('endpoint')) {
    if (!value || !value.startsWith('http')) {
      validationErrors[validationKey] = 'Must be a valid HTTP URL'
      return
    }
  }

  // Validate API keys
  if (key.includes('api_key')) {
    if (!value || value.length < 10) {
      validationErrors[validationKey] = 'API key appears to be invalid'
      return
    }
  }

  emit('llm-setting-changed', key, value)
}

// Embedding-related computed properties and methods
const embeddingSettings = computed(() => props.embeddingSettings)
const embeddingStatus = computed(() => props.embeddingStatus)

const getCurrentEmbeddingModel = () => {
  const provider = embeddingSettings.value?.provider || 'ollama'
  return embeddingSettings.value?.providers?.[provider]?.selected_model || ''
}

const getCurrentEmbeddingEndpoint = () => {
  const provider = embeddingSettings.value?.provider || 'ollama'
  return embeddingSettings.value?.providers?.[provider]?.endpoint || ''
}

const getAvailableEmbeddingModels = () => {
  const provider = embeddingSettings.value?.provider || 'ollama'
  return embeddingSettings.value?.providers?.[provider]?.models || []
}

const updateEmbeddingProvider = (provider: string) => {
  emit('embedding-setting-changed', 'provider', provider)
}

const updateEmbeddingModel = (model: string) => {
  const provider = embeddingSettings.value?.provider || 'ollama'
  emit('embedding-setting-changed', `providers.${provider}.selected_model`, model)
}

const updateEmbeddingEndpoint = (endpoint: string) => {
  const provider = embeddingSettings.value?.provider || 'ollama'
  emit('embedding-setting-changed', `providers.${provider}.endpoint`, endpoint)
}

const refreshEmbeddingModels = async () => {
  if (isRefreshingModels.value) return

  isRefreshingModels.value = true
  try {
    const provider = embeddingSettings.value?.provider || 'ollama'
    emit('refresh-embedding-models', provider)
  } finally {
    setTimeout(() => {
      isRefreshingModels.value = false
    }, 2000)
  }
}

const updateMemorySetting = (key: string, value: any) => {
  emit('setting-changed', `memory.${key}`, value)
}

const updateAgentSetting = (key: string, value: any) => {
  emit('setting-changed', `agents.${key}`, value)
}

const getHealthIconClass = (status: string | undefined) => {
  const iconMap: Record<string, string> = {
    'healthy': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle'
  }
  return iconMap[status || 'unknown'] || 'fas fa-question-circle'
}

// NEW: Enhanced connection testing methods
const getConnectionIcon = (status: string) => {
  const iconMap: Record<string, string> = {
    'connected': 'fas fa-check-circle',
    'disconnected': 'fas fa-times-circle',
    'testing': 'fas fa-spinner fa-spin',
    'unknown': 'fas fa-question-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

const testConnection = async () => {
  if (isTestingConnection.value) return

  isTestingConnection.value = true
  connectionStatus.status = 'testing'
  connectionStatus.message = 'Testing connection...'

  try {
    const endpoint = props.backendSettings?.api_endpoint || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    const startTime = Date.now()

    // Use AbortController for timeout
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)

    const response = await fetch(`${endpoint}/health`, {
      method: 'GET',
      signal: controller.signal
    })

    clearTimeout(timeoutId)
    const responseTime = Date.now() - startTime
    connectionStatus.responseTime = responseTime

    if (response.ok) {
      connectionStatus.status = 'connected'
      connectionStatus.message = 'Backend connection successful'
    } else {
      connectionStatus.status = 'disconnected'
      connectionStatus.message = `Connection failed (${response.status})`
    }
  } catch (error) {
    const err = error as Error
    logger.error('Connection test failed:', err)
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Connection error: ${err.message}`
    connectionStatus.responseTime = null
  } finally {
    isTestingConnection.value = false
  }
}

const refreshConnectionStatus = async () => {
  await testConnection()
}

const validatePath = async (pathKey: string) => {
  // Placeholder for path validation
}

const testLLMConnection = async () => {
  if (isTestingLLM.value) return

  isTestingLLM.value = true
  try {
    // Test LLM connection based on current provider
    // Implement actual LLM testing logic
  } finally {
    isTestingLLM.value = false
  }
}

const refreshLLMModels = async () => {
  if (isRefreshingLLMModels.value) return

  isRefreshingLLMModels.value = true
  try {
    // Implement model refresh logic
  } finally {
    setTimeout(() => {
      isRefreshingLLMModels.value = false
    }, 2000)
  }
}

const testOllamaConnection = async () => {
}

const testLMStudioConnection = async () => {
}

const testOpenAIConnection = async () => {
}

const testAnthropicConnection = async () => {
}

const testEmbeddingConnection = async () => {
  if (isTestingEmbedding.value) return

  isTestingEmbedding.value = true
  try {
  } finally {
    isTestingEmbedding.value = false
  }
}

const testEmbeddingEndpoint = async () => {
}

// NEW: Hardware testing methods
const testGPU = async () => {
  if (isTestingGPU.value) return

  isTestingGPU.value = true
  hardwareStatus.gpu.status = 'testing'
  hardwareStatus.gpu.message = 'Testing GPU...'

  try {
    // Real GPU detection API call
    const endpoint = props.backendSettings?.api_endpoint || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    const response = await fetch(`${endpoint}/api/monitoring/hardware/gpu`)

    if (response.ok) {
      const data = await response.json()

      if (data.available) {
        hardwareStatus.gpu.status = 'available'
        hardwareStatus.gpu.message = 'GPU acceleration available'

        // Extract real GPU metrics
        const metrics = data.current_metrics || {}
        const memoryGB = metrics.memory_used && metrics.memory_total
          ? `${(metrics.memory_used / 1024).toFixed(1)}GB / ${(metrics.memory_total / 1024).toFixed(1)}GB`
          : 'Unknown'

        hardwareStatus.gpu.details = {
          utilization: metrics.utilization_percent || 0,
          memory: memoryGB,
          temperature: metrics.temperature_celsius ? `${metrics.temperature_celsius}°C` : 'N/A',
          name: metrics.gpu_name || 'Unknown GPU'
        }
      } else {
        hardwareStatus.gpu.status = 'unavailable'
        hardwareStatus.gpu.message = data.message || 'GPU not available or accessible'
      }
    } else {
      hardwareStatus.gpu.status = 'error'
      hardwareStatus.gpu.message = 'Failed to query GPU status'
    }
  } catch (error) {
    const err = error as Error
    logger.error('GPU test failed:', err)
    hardwareStatus.gpu.status = 'error'
    hardwareStatus.gpu.message = `GPU test failed: ${err.message}`
  } finally {
    isTestingGPU.value = false
  }
}

const testNPU = async () => {
  if (isTestingNPU.value) return

  isTestingNPU.value = true
  hardwareStatus.npu.status = 'testing'
  hardwareStatus.npu.message = 'Testing NPU...'

  try {
    const endpoint = props.backendSettings?.api_endpoint || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    const response = await fetch(`${endpoint}/api/monitoring/hardware/npu`)

    if (response.ok) {
      const data = await response.json()
      hardwareStatus.npu.status = data.available ? 'available' : 'unavailable'
      hardwareStatus.npu.message = data.message || 'NPU status retrieved'
      hardwareStatus.npu.details = {
        available: data.available,
        wsl_limitation: true
      }
    } else {
      hardwareStatus.npu.status = 'unavailable'
      hardwareStatus.npu.message = 'NPU not accessible'
    }
  } catch (error) {
    const err = error as Error
    logger.error('NPU test failed:', err)
    hardwareStatus.npu.status = 'error'
    hardwareStatus.npu.message = `NPU test failed: ${err.message}`
  } finally {
    isTestingNPU.value = false
  }
}

const refreshMemoryStatus = async () => {
  hardwareStatus.memory.status = 'checking'
  hardwareStatus.memory.message = 'Checking memory status...'

  try {
    // Real system metrics API call
    const endpoint = props.backendSettings?.api_endpoint || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    const response = await fetch(`${endpoint}/api/system/metrics`)

    if (response.ok) {
      const data = await response.json()

      if (data.system && data.system.memory) {
        const memory = data.system.memory
        hardwareStatus.memory.status = 'available'
        hardwareStatus.memory.message = 'Memory status healthy'

        // Convert bytes to GB for display
        const totalGB = (memory.total / (1024 ** 3)).toFixed(1)
        const availableGB = (memory.available / (1024 ** 3)).toFixed(1)
        const usedGB = (memory.used / (1024 ** 3)).toFixed(1)

        hardwareStatus.memory.details = {
          total: `${totalGB} GB`,
          available: `${availableGB} GB`,
          used: `${usedGB} GB`,
          percent: memory.percent.toFixed(1) + '%'
        }
      } else {
        hardwareStatus.memory.status = 'unavailable'
        hardwareStatus.memory.message = 'Memory data not available'
      }
    } else {
      hardwareStatus.memory.status = 'error'
      hardwareStatus.memory.message = 'Failed to query memory status'
    }
  } catch (error) {
    const err = error as Error
    logger.error('Memory status check failed:', err)
    hardwareStatus.memory.status = 'error'
    hardwareStatus.memory.message = `Failed to get memory status: ${err.message}`
  }
}

// Initialize connection status on mount
onMounted(() => {
  testConnection()
  refreshMemoryStatus()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

.settings-section {
  margin-bottom: 30px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-sm);
}

.sub-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: 20px;
  overflow-x: auto;
}

.sub-tabs button {
  background: none;
  border: none;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s ease;
  white-space: nowrap;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.sub-tabs button:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.sub-tabs button.active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--bg-secondary);
}

.sub-tab-content h3 {
  margin: 0 0 20px 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-lg);
  border-bottom: 2px solid var(--color-info);
  padding-bottom: 8px;
}

/* Connection Status Banner */
.connection-status-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  border: 1px solid;
}

.connection-status-banner.connected {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success-dark);
}

.connection-status-banner.disconnected {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error-dark);
}

.connection-status-banner.testing {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning-dark);
}

.connection-status-banner.unknown {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
  color: var(--text-muted);
}

.status-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-actions {
  display: flex;
  gap: 8px;
}

.test-connection-btn, .refresh-status-btn {
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all 0.2s;
}

.test-connection-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.test-connection-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.test-connection-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-status-btn {
  background: var(--color-secondary);
  color: var(--text-on-primary);
}

.refresh-status-btn:hover {
  background: var(--color-secondary-hover);
}

.response-time {
  font-size: var(--text-xs);
  opacity: 0.8;
}

/* Enhanced LLM Status Display */
.llm-status-display {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 20px;
}

.current-llm-info {
  margin-bottom: 8px;
  font-size: var(--text-sm);
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  margin-bottom: 12px;
}

.health-indicator.healthy {
  color: var(--color-success);
}

.health-indicator.warning {
  color: var(--color-warning);
}

.health-indicator.error {
  color: var(--color-error);
}

.health-indicator.unknown {
  color: var(--text-secondary);
}

.llm-actions, .embedding-actions {
  display: flex;
  gap: 8px;
}

.test-llm-btn, .refresh-models-btn, .test-embedding-btn {
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all 0.2s;
}

.test-llm-btn, .test-embedding-btn {
  background: var(--color-success);
  color: var(--text-on-success);
}

.test-llm-btn:hover:not(:disabled), .test-embedding-btn:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.refresh-models-btn {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.refresh-models-btn:hover:not(:disabled) {
  background: var(--color-info-hover);
}

/* Hardware Status Grid */
.hardware-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.hardware-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: 20px;
  transition: all 0.2s;
}

.hardware-card.available {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.hardware-card.unavailable {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.hardware-card.testing {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.hardware-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.hardware-header h4 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.hardware-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: var(--text-sm);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
}

.status-indicator.available {
  background: var(--color-success);
}

.status-indicator.unavailable {
  background: var(--color-error);
}

.status-indicator.testing {
  background: var(--color-warning);
}

.status-indicator.unknown {
  background: var(--text-secondary);
}

.hardware-details {
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  margin-bottom: 4px;
  color: var(--text-secondary);
}

.test-hardware-btn {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  background: var(--color-primary);
  color: var(--text-on-primary);
  transition: all 0.2s;
}

.test-hardware-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.test-hardware-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hardware-settings {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-default);
}

/* Enhanced Input Groups */
.input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-direction: column;
  align-items: stretch;
}

.input-group input {
  flex: 1;
}

.test-endpoint-btn, .validate-path-btn {
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  background: var(--color-info);
  color: var(--text-on-primary);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.test-endpoint-btn:hover, .validate-path-btn:hover {
  background: var(--color-info-hover);
}

.validation-message {
  font-size: var(--text-xs);
  margin-top: 4px;
  padding: 4px 8px;
  border-radius: var(--radius-default);
}

.validation-message.error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border: 1px solid var(--color-error-border);
}

.validation-message.success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
  border: 1px solid var(--color-success-border);
}

.validation-error {
  border-color: var(--color-error) !important;
  box-shadow: 0 0 0 2px var(--color-error-bg) !important;
}

.embedding-status-display {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 20px;
}

.current-embedding-info {
  margin-bottom: 8px;
  font-size: var(--text-sm);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-light);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 200px;
  padding: 8px 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  transition: border-color 0.2s ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.provider-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-default);
}

.provider-config {
  margin-top: 16px;
  padding-left: 20px;
  border-left: 3px solid var(--color-primary);
}

.model-selection {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-indicator {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Responsive Design */
@media (max-width: 768px) {
  .connection-status-banner {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .status-actions {
    justify-content: center;
  }

  .hardware-status-grid {
    grid-template-columns: 1fr;
  }

  .setting-item {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .setting-item label {
    margin-right: 0;
  }

  .setting-item input,
  .setting-item select {
    min-width: unset;
    width: 100%;
  }

  .input-group {
    flex-direction: column;
  }

  .llm-actions, .embedding-actions {
    flex-direction: column;
  }
}
</style>
