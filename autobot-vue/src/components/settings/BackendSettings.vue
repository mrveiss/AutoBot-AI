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
      <div class="setting-item">
        <label for="api-endpoint">API Endpoint</label>
        <input
          id="api-endpoint"
          type="text"
          :value="backendSettings?.api_endpoint || ''"
          @input="updateSetting('api_endpoint', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="server-host">Server Host</label>
        <input
          id="server-host"
          type="text"
          :value="backendSettings?.server_host || ''"
          @input="updateSetting('server_host', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="server-port">Server Port</label>
        <input
          id="server-port"
          type="number"
          :value="backendSettings?.server_port || 8001"
          min="1"
          max="65535"
          @input="updateSetting('server_port', parseInt($event.target.value))"
        />
      </div>
      <div class="setting-item">
        <label for="chat-data-dir">Chat Data Directory</label>
        <input
          id="chat-data-dir"
          type="text"
          :value="backendSettings?.chat_data_dir || ''"
          @input="updateSetting('chat_data_dir', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="chat-history-file">Chat History File</label>
        <input
          id="chat-history-file"
          type="text"
          :value="backendSettings?.chat_history_file || ''"
          placeholder="data/chat_history.json"
          @input="updateSetting('chat_history_file', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="knowledge-base-db">Knowledge Base DB</label>
        <input
          id="knowledge-base-db"
          type="text"
          :value="backendSettings?.knowledge_base_db || ''"
          placeholder="data/knowledge_base.db"
          @input="updateSetting('knowledge_base_db', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="reliability-stats-file">Reliability Stats File</label>
        <input
          id="reliability-stats-file"
          type="text"
          :value="backendSettings?.reliability_stats_file || ''"
          placeholder="data/reliability_stats.json"
          @input="updateSetting('reliability_stats_file', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="logs-directory">Logs Directory</label>
        <input
          id="logs-directory"
          type="text"
          :value="backendSettings?.logs_directory || ''"
          placeholder="logs/"
          @input="updateSetting('logs_directory', $event.target.value)"
        />
      </div>
      <div class="setting-item">
        <label for="chat-enabled">Chat Enabled</label>
        <input
          id="chat-enabled"
          type="checkbox"
          :checked="backendSettings?.chat_enabled || false"
          @change="updateSetting('chat_enabled', $event.target.checked)"
        />
      </div>
      <div class="setting-item">
        <label for="knowledge-base-enabled">Knowledge Base Enabled</label>
        <input
          id="knowledge-base-enabled"
          type="checkbox"
          :checked="backendSettings?.knowledge_base_enabled || false"
          @change="updateSetting('knowledge_base_enabled', $event.target.checked)"
        />
      </div>
      <div class="setting-item">
        <label for="auto-backup-chat">Auto Backup Chat</label>
        <input
          id="auto-backup-chat"
          type="checkbox"
          :checked="backendSettings?.auto_backup_chat || false"
          @change="updateSetting('auto_backup_chat', $event.target.checked)"
        />
      </div>
    </div>

    <!-- LLM Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'llm'" class="sub-tab-content">
      <h3>LLM Configuration</h3>

      <!-- LLM Status Display -->
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
      </div>

      <div class="setting-item">
        <label for="provider-type">Provider Type</label>
        <select
          id="provider-type"
          :value="llmSettings?.provider_type || 'local'"
          @change="updateLLMSetting('provider_type', $event.target.value)"
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
            @change="updateLLMSetting('local.provider', $event.target.value)"
          >
            <option value="ollama">Ollama</option>
            <option value="lmstudio">LM Studio</option>
          </select>
        </div>

        <!-- Ollama Settings -->
        <div v-if="llmSettings.local?.provider === 'ollama'" class="provider-config">
          <div class="setting-item">
            <label for="ollama-endpoint">Ollama Endpoint</label>
            <input
              id="ollama-endpoint"
              type="text"
              :value="llmSettings.local?.providers?.ollama?.endpoint || ''"
              @input="updateLLMSetting('local.providers.ollama.endpoint', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="ollama-model">Model</label>
            <select
              id="ollama-model"
              :value="llmSettings.local?.providers?.ollama?.selected_model || ''"
              @change="updateLLMSetting('local.providers.ollama.selected_model', $event.target.value)"
            >
              <option
                v-for="model in llmSettings.local?.providers?.ollama?.models || []"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
          </div>
        </div>

        <!-- LM Studio Settings -->
        <div v-else-if="llmSettings.local?.provider === 'lmstudio'" class="provider-config">
          <div class="setting-item">
            <label for="lmstudio-endpoint">LM Studio Endpoint</label>
            <input
              id="lmstudio-endpoint"
              type="text"
              :value="llmSettings.local?.providers?.lmstudio?.endpoint || ''"
              @input="updateLLMSetting('local.providers.lmstudio.endpoint', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="lmstudio-model">Model</label>
            <select
              id="lmstudio-model"
              :value="llmSettings.local?.providers?.lmstudio?.selected_model || ''"
              @change="updateLLMSetting('local.providers.lmstudio.selected_model', $event.target.value)"
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
            @change="updateLLMSetting('cloud.provider', $event.target.value)"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </div>

        <!-- OpenAI Settings -->
        <div v-if="llmSettings.cloud?.provider === 'openai'" class="provider-config">
          <div class="setting-item">
            <label for="openai-api-key">API Key</label>
            <input
              id="openai-api-key"
              type="password"
              :value="llmSettings.cloud?.providers?.openai?.api_key || ''"
              placeholder="Enter API Key"
              @input="updateLLMSetting('cloud.providers.openai.api_key', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="openai-endpoint">Endpoint</label>
            <input
              id="openai-endpoint"
              type="text"
              :value="llmSettings.cloud?.providers?.openai?.endpoint || ''"
              @input="updateLLMSetting('cloud.providers.openai.endpoint', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="openai-model">Model</label>
            <select
              id="openai-model"
              :value="llmSettings.cloud?.providers?.openai?.selected_model || ''"
              @change="updateLLMSetting('cloud.providers.openai.selected_model', $event.target.value)"
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
            <input
              id="anthropic-api-key"
              type="password"
              :value="llmSettings.cloud?.providers?.anthropic?.api_key || ''"
              placeholder="Enter API Key"
              @input="updateLLMSetting('cloud.providers.anthropic.api_key', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="anthropic-endpoint">Endpoint</label>
            <input
              id="anthropic-endpoint"
              type="text"
              :value="llmSettings.cloud?.providers?.anthropic?.endpoint || ''"
              @input="updateLLMSetting('cloud.providers.anthropic.endpoint', $event.target.value)"
            />
          </div>
          <div class="setting-item">
            <label for="anthropic-model">Model</label>
            <select
              id="anthropic-model"
              :value="llmSettings.cloud?.providers?.anthropic?.selected_model || ''"
              @change="updateLLMSetting('cloud.providers.anthropic.selected_model', $event.target.value)"
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
      <p class="placeholder-text">Embedding configuration will be implemented here.</p>
    </div>

    <!-- Memory Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'memory'" class="sub-tab-content">
      <h3>Memory Configuration</h3>

      <!-- Redis Memory Settings -->
      <div class="memory-section">
        <h4>Redis Configuration</h4>
        <div class="setting-item">
          <label for="redis-enabled">Redis Enabled</label>
          <input
            id="redis-enabled"
            type="checkbox"
            :checked="memorySettings?.redis?.enabled || false"
            @change="updateMemorySetting('redis.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="redis-host">Redis Host</label>
          <input
            id="redis-host"
            type="text"
            :value="memorySettings?.redis?.host || ''"
            placeholder="172.16.168.23"
            @input="updateMemorySetting('redis.host', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="redis-port">Redis Port</label>
          <input
            id="redis-port"
            type="number"
            :value="memorySettings?.redis?.port || 6379"
            min="1"
            max="65535"
            @input="updateMemorySetting('redis.port', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="redis-timeout">Connection Timeout (seconds)</label>
          <input
            id="redis-timeout"
            type="number"
            :value="memorySettings?.redis?.timeout || 5"
            min="1"
            max="60"
            @input="updateMemorySetting('redis.timeout', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="redis-max-connections">Max Connections</label>
          <input
            id="redis-max-connections"
            type="number"
            :value="memorySettings?.redis?.max_connections || 20"
            min="1"
            max="100"
            @input="updateMemorySetting('redis.max_connections', parseInt($event.target.value))"
          />
        </div>
      </div>

      <!-- ChromaDB Memory Settings -->
      <div class="memory-section">
        <h4>ChromaDB Configuration</h4>
        <div class="setting-item">
          <label for="chromadb-enabled">ChromaDB Enabled</label>
          <input
            id="chromadb-enabled"
            type="checkbox"
            :checked="memorySettings?.chromadb?.enabled || false"
            @change="updateMemorySetting('chromadb.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="chromadb-path">ChromaDB Path</label>
          <input
            id="chromadb-path"
            type="text"
            :value="memorySettings?.chromadb?.path || ''"
            placeholder="data/chromadb"
            @input="updateMemorySetting('chromadb.path', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="chromadb-collection">Collection Name</label>
          <input
            id="chromadb-collection"
            type="text"
            :value="memorySettings?.chromadb?.collection_name || ''"
            placeholder="autobot_memory"
            @input="updateMemorySetting('chromadb.collection_name', $event.target.value)"
          />
        </div>
      </div>

      <!-- Memory Retention Settings -->
      <div class="memory-section">
        <h4>Memory Retention</h4>
        <div class="setting-item">
          <label for="short-term-enabled">Short Term Memory</label>
          <input
            id="short-term-enabled"
            type="checkbox"
            :checked="memorySettings?.short_term?.enabled || false"
            @change="updateMemorySetting('short_term.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="short-term-duration">Duration (minutes)</label>
          <input
            id="short-term-duration"
            type="number"
            :value="memorySettings?.short_term?.duration_minutes || 30"
            min="1"
            max="1440"
            @input="updateMemorySetting('short_term.duration_minutes', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="long-term-enabled">Long Term Memory</label>
          <input
            id="long-term-enabled"
            type="checkbox"
            :checked="memorySettings?.long_term?.enabled || false"
            @change="updateMemorySetting('long_term.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="long-term-retention">Retention (days)</label>
          <input
            id="long-term-retention"
            type="number"
            :value="memorySettings?.long_term?.retention_days || 30"
            min="1"
            max="365"
            @input="updateMemorySetting('long_term.retention_days', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="vector-storage-enabled">Vector Storage</label>
          <input
            id="vector-storage-enabled"
            type="checkbox"
            :checked="memorySettings?.vector_storage?.enabled || false"
            @change="updateMemorySetting('vector_storage.enabled', $event.target.checked)"
          />
        </div>
      </div>
    </div>

    <!-- Agents Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'agents'" class="sub-tab-content">
      <h3>Agents Configuration</h3>

      <!-- Chat Agent -->
      <div class="agent-section">
        <h4>Chat Agent</h4>
        <div class="setting-item">
          <label for="chat-agent-enabled">Enabled</label>
          <input
            id="chat-agent-enabled"
            type="checkbox"
            :checked="agentSettings?.chat?.enabled || false"
            @change="updateAgentSetting('chat.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="chat-agent-model">Model</label>
          <input
            id="chat-agent-model"
            type="text"
            :value="agentSettings?.chat?.model || ''"
            placeholder="llama3.2:1b-instruct-q4_K_M"
            @input="updateAgentSetting('chat.model', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="chat-agent-streaming">Streaming</label>
          <input
            id="chat-agent-streaming"
            type="checkbox"
            :checked="agentSettings?.chat?.streaming || false"
            @change="updateAgentSetting('chat.streaming', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="chat-agent-max-history">Max History</label>
          <input
            id="chat-agent-max-history"
            type="number"
            :value="agentSettings?.chat?.max_history || 100"
            min="1"
            max="1000"
            @input="updateAgentSetting('chat.max_history', parseInt($event.target.value))"
          />
        </div>
      </div>

      <!-- Classification Agent -->
      <div class="agent-section">
        <h4>Classification Agent</h4>
        <div class="setting-item">
          <label for="classification-agent-enabled">Enabled</label>
          <input
            id="classification-agent-enabled"
            type="checkbox"
            :checked="agentSettings?.classification?.enabled || false"
            @change="updateAgentSetting('classification.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="classification-agent-model">Model</label>
          <input
            id="classification-agent-model"
            type="text"
            :value="agentSettings?.classification?.model || ''"
            placeholder="gemma2:2b"
            @input="updateAgentSetting('classification.model', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="classification-agent-timeout">Timeout (seconds)</label>
          <input
            id="classification-agent-timeout"
            type="number"
            :value="agentSettings?.classification?.timeout_seconds || 10"
            min="1"
            max="60"
            @input="updateAgentSetting('classification.timeout_seconds', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="classification-agent-fallback">Fallback Enabled</label>
          <input
            id="classification-agent-fallback"
            type="checkbox"
            :checked="agentSettings?.classification?.fallback_enabled || false"
            @change="updateAgentSetting('classification.fallback_enabled', $event.target.checked)"
          />
        </div>
      </div>

      <!-- KB Librarian Agent -->
      <div class="agent-section">
        <h4>Knowledge Base Librarian</h4>
        <div class="setting-item">
          <label for="kb-librarian-enabled">Enabled</label>
          <input
            id="kb-librarian-enabled"
            type="checkbox"
            :checked="agentSettings?.kb_librarian?.enabled || false"
            @change="updateAgentSetting('kb_librarian.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="kb-librarian-model">Model</label>
          <input
            id="kb-librarian-model"
            type="text"
            :value="agentSettings?.kb_librarian?.model || ''"
            placeholder="llama3.2:1b-instruct-q4_K_M"
            @input="updateAgentSetting('kb_librarian.model', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="kb-librarian-timeout">Timeout (seconds)</label>
          <input
            id="kb-librarian-timeout"
            type="number"
            :value="agentSettings?.kb_librarian?.timeout_seconds || 15"
            min="1"
            max="120"
            @input="updateAgentSetting('kb_librarian.timeout_seconds', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="kb-librarian-max-results">Max Results</label>
          <input
            id="kb-librarian-max-results"
            type="number"
            :value="agentSettings?.kb_librarian?.max_results || 5"
            min="1"
            max="50"
            @input="updateAgentSetting('kb_librarian.max_results', parseInt($event.target.value))"
          />
        </div>
      </div>

      <!-- Research Agent -->
      <div class="agent-section">
        <h4>Research Agent</h4>
        <div class="setting-item">
          <label for="research-agent-enabled">Enabled</label>
          <input
            id="research-agent-enabled"
            type="checkbox"
            :checked="agentSettings?.research?.enabled || false"
            @change="updateAgentSetting('research.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="research-agent-model">Model</label>
          <input
            id="research-agent-model"
            type="text"
            :value="agentSettings?.research?.model || ''"
            placeholder="llama3.2:1b-instruct-q4_K_M"
            @input="updateAgentSetting('research.model', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="research-agent-timeout">Timeout (seconds)</label>
          <input
            id="research-agent-timeout"
            type="number"
            :value="agentSettings?.research?.timeout_seconds || 30"
            min="1"
            max="300"
            @input="updateAgentSetting('research.timeout_seconds', parseInt($event.target.value))"
          />
        </div>
        <div class="setting-item">
          <label for="research-agent-browser">Browser Enabled</label>
          <input
            id="research-agent-browser"
            type="checkbox"
            :checked="agentSettings?.research?.browser_enabled || false"
            @change="updateAgentSetting('research.browser_enabled', $event.target.checked)"
          />
        </div>
      </div>

      <!-- System Commands Agent -->
      <div class="agent-section">
        <h4>System Commands Agent</h4>
        <div class="setting-item">
          <label for="system-commands-enabled">Enabled</label>
          <input
            id="system-commands-enabled"
            type="checkbox"
            :checked="agentSettings?.system_commands?.enabled || false"
            @change="updateAgentSetting('system_commands.enabled', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="system-commands-model">Model</label>
          <input
            id="system-commands-model"
            type="text"
            :value="agentSettings?.system_commands?.model || ''"
            placeholder="llama3.2:1b-instruct-q4_K_M"
            @input="updateAgentSetting('system_commands.model', $event.target.value)"
          />
        </div>
        <div class="setting-item">
          <label for="system-commands-approval">Approval Required</label>
          <input
            id="system-commands-approval"
            type="checkbox"
            :checked="agentSettings?.system_commands?.approval_required || false"
            @change="updateAgentSetting('system_commands.approval_required', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="system-commands-safety">Safety Enabled</label>
          <input
            id="system-commands-safety"
            type="checkbox"
            :checked="agentSettings?.system_commands?.safety_enabled || false"
            @change="updateAgentSetting('system_commands.safety_enabled', $event.target.checked)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface HealthStatus {
  backend?: {
    llm_provider?: {
      status: string
      message: string
    }
  }
}

interface LLMSettings {
  provider_type: 'local' | 'cloud'
  local?: {
    provider: string
    providers?: {
      ollama?: {
        endpoint: string
        selected_model: string
        models: string[]
      }
      lmstudio?: {
        endpoint: string
        selected_model: string
        models: string[]
      }
    }
  }
  cloud?: {
    provider: string
    providers?: {
      openai?: {
        api_key: string
        endpoint: string
        selected_model: string
        models: string[]
      }
      anthropic?: {
        api_key: string
        endpoint: string
        selected_model: string
        models: string[]
      }
    }
  }
}

interface MemorySettings {
  redis?: {
    enabled: boolean
    host: string
    port: number
    timeout: number
    max_connections: number
  }
  chromadb?: {
    enabled: boolean
    path: string
    collection_name: string
  }
  short_term?: {
    enabled: boolean
    duration_minutes: number
  }
  long_term?: {
    enabled: boolean
    retention_days: number
  }
  vector_storage?: {
    enabled: boolean
  }
}

interface AgentSettings {
  chat?: {
    enabled: boolean
    model: string
    streaming: boolean
    max_history: number
  }
  classification?: {
    enabled: boolean
    model: string
    timeout_seconds: number
    fallback_enabled: boolean
  }
  kb_librarian?: {
    enabled: boolean
    model: string
    timeout_seconds: number
    max_results: number
  }
  research?: {
    enabled: boolean
    model: string
    timeout_seconds: number
    browser_enabled: boolean
  }
  system_commands?: {
    enabled: boolean
    model: string
    approval_required: boolean
    safety_enabled: boolean
  }
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
  llm?: LLMSettings
  memory?: MemorySettings
  agents?: AgentSettings
}

interface Props {
  backendSettings: BackendSettings | null | undefined
  isSettingsLoaded: boolean
  activeBackendSubTab: string
  healthStatus: HealthStatus | null
  currentLLMDisplay: string
}

interface Emits {
  (e: 'subtab-changed', subtab: string): void
  (e: 'setting-changed', key: string, value: any): void
  (e: 'llm-setting-changed', key: string, value: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const llmSettings = computed(() => props.backendSettings?.llm)
const memorySettings = computed(() => props.backendSettings?.memory)
const agentSettings = computed(() => props.backendSettings?.agents)

const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

const updateLLMSetting = (key: string, value: any) => {
  emit('llm-setting-changed', key, value)
}

const updateMemorySetting = (key: string, value: any) => {
  emit('setting-changed', `memory.${key}`, value)
}

const updateAgentSetting = (key: string, value: any) => {
  emit('setting-changed', `agents.${key}`, value)
}

const getHealthIconClass = (status: string) => {
  const iconMap = {
    'healthy': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}
</script>

<style scoped>
.settings-section {
  margin-bottom: 30px;
  background: #ffffff;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.sub-tabs {
  display: flex;
  border-bottom: 1px solid #e0e0e0;
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
  color: #666;
  font-weight: 500;
}

.sub-tabs button:hover {
  background-color: #f5f5f5;
  color: #333;
}

.sub-tabs button.active {
  border-bottom-color: #007acc;
  color: #007acc;
  background-color: #f9f9f9;
}

.sub-tab-content h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.llm-status-display {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 20px;
}

.current-llm-info {
  margin-bottom: 8px;
  font-size: 14px;
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.health-indicator.healthy {
  color: #28a745;
}

.health-indicator.warning {
  color: #ffc107;
}

.health-indicator.error {
  color: #dc3545;
}

.health-indicator.unknown {
  color: #6c757d;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: #34495e;
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 200px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.provider-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.provider-config {
  margin-top: 16px;
  padding-left: 20px;
  border-left: 3px solid #007acc;
}

.placeholder-text {
  color: #6c757d;
  font-style: italic;
  text-align: center;
  padding: 40px 20px;
  background: #f8f9fa;
  border-radius: 6px;
  margin: 20px 0;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: #2d2d2d;
    border-color: #404040;
  }

  .sub-tabs {
    border-bottom-color: #404040;
  }

  .sub-tabs button {
    color: #ccc;
  }

  .sub-tabs button:hover {
    background-color: #333;
    color: #fff;
  }

  .sub-tabs button.active {
    background-color: #2d2d2d;
    color: #4fc3f7;
    border-bottom-color: #4fc3f7;
  }

  .sub-tab-content h3 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }

  .llm-status-display {
    background: #383838;
    border-color: #555;
  }

  .setting-item {
    border-bottom-color: #404040;
  }

  .setting-item label {
    color: #e0e0e0;
  }

  .setting-item input,
  .setting-item select {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .provider-section {
    border-top-color: #404040;
  }

  .provider-config {
    border-left-color: #4fc3f7;
  }

  .placeholder-text {
    background: #383838;
    color: #aaa;
  }

  .memory-section,
  .agent-section {
    background: #383838;
    border-color: #555;
  }

  .memory-section h4,
  .agent-section h4 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }
}

.memory-section,
.agent-section {
  margin-top: 20px;
  padding: 20px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
}

.memory-section h4,
.agent-section h4 {
  margin: 0 0 16px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 16px;
  border-bottom: 1px solid #3498db;
  padding-bottom: 6px;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: 16px;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: 4px;
  }

  .setting-item input,
  .setting-item select {
    min-width: auto;
    width: 100%;
  }

  .provider-config {
    padding-left: 12px;
  }
}
</style>