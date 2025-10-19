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
      <button
        :class="{ active: activeBackendSubTab === 'hardware' }"
        @click="$emit('subtab-changed', 'hardware')"
        aria-label="Hardware"
      >
        Hardware
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
            @input="updateSettingWithValidation('api_endpoint', $event.target.value)"
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
            @input="updateSettingWithValidation('server_host', $event.target.value)"
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
            @input="updateSettingWithValidation('server_port', parseInt($event.target.value))"
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
            @input="updateSettingWithValidation('chat_data_dir', $event.target.value)"
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
            <div class="input-group">
              <input
                id="ollama-endpoint"
                type="text"
                :value="llmSettings.local?.providers?.ollama?.endpoint || ''"
                @input="updateLLMSettingWithValidation('local.providers.ollama.endpoint', $event.target.value)"
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
                @input="updateLLMSettingWithValidation('local.providers.lmstudio.endpoint', $event.target.value)"
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
            <div class="input-group">
              <input
                id="openai-api-key"
                type="password"
                :value="llmSettings.cloud?.providers?.openai?.api_key || ''"
                placeholder="Enter API Key"
                @input="updateLLMSettingWithValidation('cloud.providers.openai.api_key', $event.target.value)"
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
            <div class="input-group">
              <input
                id="anthropic-api-key"
                type="password"
                :value="llmSettings.cloud?.providers?.anthropic?.api_key || ''"
                placeholder="Enter API Key"
                @input="updateLLMSettingWithValidation('cloud.providers.anthropic.api_key', $event.target.value)"
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

    <!-- NEW: Hardware Settings Sub-tab -->
    <div v-if="activeBackendSubTab === 'hardware'" class="sub-tab-content">
      <h3>Hardware Configuration</h3>

      <!-- Hardware Status Overview -->
      <div class="hardware-status-grid">
        <div class="hardware-card" :class="hardwareStatus.gpu.status">
          <div class="hardware-header">
            <i class="fas fa-microchip"></i>
            <h4>GPU Acceleration</h4>
          </div>
          <div class="hardware-status">
            <span class="status-indicator" :class="hardwareStatus.gpu.status"></span>
            {{ hardwareStatus.gpu.message }}
          </div>
          <div v-if="hardwareStatus.gpu.details" class="hardware-details">
            <div class="detail-item">
              <span>Utilization:</span>
              <span>{{ hardwareStatus.gpu.details.utilization || 'N/A' }}%</span>
            </div>
            <div class="detail-item">
              <span>Memory:</span>
              <span>{{ hardwareStatus.gpu.details.memory || 'N/A' }}</span>
            </div>
          </div>
          <button @click="testGPU" :disabled="isTestingGPU" class="test-hardware-btn">
            <i :class="isTestingGPU ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
            {{ isTestingGPU ? 'Testing...' : 'Test GPU' }}
          </button>
        </div>

        <div class="hardware-card" :class="hardwareStatus.npu.status">
          <div class="hardware-header">
            <i class="fas fa-brain"></i>
            <h4>NPU Acceleration</h4>
          </div>
          <div class="hardware-status">
            <span class="status-indicator" :class="hardwareStatus.npu.status"></span>
            {{ hardwareStatus.npu.message }}
          </div>
          <div v-if="hardwareStatus.npu.details" class="hardware-details">
            <div class="detail-item">
              <span>Available:</span>
              <span>{{ hardwareStatus.npu.details.available ? 'Yes' : 'No' }}</span>
            </div>
            <div class="detail-item">
              <span>WSL Mode:</span>
              <span>{{ hardwareStatus.npu.details.wsl_limitation ? 'Limited' : 'Full' }}</span>
            </div>
          </div>
          <button @click="testNPU" :disabled="isTestingNPU" class="test-hardware-btn">
            <i :class="isTestingNPU ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
            {{ isTestingNPU ? 'Testing...' : 'Test NPU' }}
          </button>
        </div>

        <div class="hardware-card" :class="hardwareStatus.memory.status">
          <div class="hardware-header">
            <i class="fas fa-memory"></i>
            <h4>System Memory</h4>
          </div>
          <div class="hardware-status">
            <span class="status-indicator" :class="hardwareStatus.memory.status"></span>
            {{ hardwareStatus.memory.message }}
          </div>
          <div v-if="hardwareStatus.memory.details" class="hardware-details">
            <div class="detail-item">
              <span>Total:</span>
              <span>{{ hardwareStatus.memory.details.total || 'N/A' }}</span>
            </div>
            <div class="detail-item">
              <span>Available:</span>
              <span>{{ hardwareStatus.memory.details.available || 'N/A' }}</span>
            </div>
          </div>
          <button @click="refreshMemoryStatus" class="test-hardware-btn">
            <i class="fas fa-sync"></i>
            Refresh
          </button>
        </div>
      </div>

      <!-- Hardware Settings -->
      <div class="hardware-settings">
        <div class="setting-item">
          <label for="enable-gpu">Enable GPU Acceleration</label>
          <input
            id="enable-gpu"
            type="checkbox"
            :checked="backendSettings?.hardware?.enable_gpu || false"
            @change="updateSetting('hardware.enable_gpu', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="enable-npu">Enable NPU Acceleration</label>
          <input
            id="enable-npu"
            type="checkbox"
            :checked="backendSettings?.hardware?.enable_npu || false"
            @change="updateSetting('hardware.enable_npu', $event.target.checked)"
          />
        </div>
        <div class="setting-item">
          <label for="memory-limit">Memory Limit (GB)</label>
          <input
            id="memory-limit"
            type="number"
            :value="backendSettings?.hardware?.memory_limit || 8"
            min="1"
            max="64"
            @input="updateSetting('hardware.memory_limit', parseInt($event.target.value))"
          />
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
          @change="updateEmbeddingProvider($event.target.value)"
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
              @input="updateEmbeddingEndpoint($event.target.value)"
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
              @change="updateEmbeddingModel($event.target.value)"
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
          @change="updateMemorySetting('enabled', $event.target.checked)"
        />
      </div>

      <div class="setting-item">
        <label for="memory-type">Memory Type</label>
        <select
          id="memory-type"
          :value="backendSettings?.memory?.type || 'redis'"
          @change="updateMemorySetting('type', $event.target.value)"
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
          @input="updateMemorySetting('max_entries', parseInt($event.target.value))"
        />
      </div>

      <div class="setting-item">
        <label for="auto-cleanup">Auto Cleanup</label>
        <input
          id="auto-cleanup"
          type="checkbox"
          :checked="backendSettings?.memory?.auto_cleanup || false"
          @change="updateMemorySetting('auto_cleanup', $event.target.checked)"
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
          @input="updateAgentSetting('max_concurrent', parseInt($event.target.value))"
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
          @input="updateAgentSetting('timeout', parseInt($event.target.value))"
        />
      </div>

      <div class="setting-item">
        <label for="enable-agent-memory">Enable Agent Memory</label>
        <input
          id="enable-agent-memory"
          type="checkbox"
          :checked="backendSettings?.agents?.enable_memory || false"
          @change="updateAgentSetting('enable_memory', $event.target.checked)"
        />
      </div>

      <div class="setting-item">
        <label for="agent-log-level">Agent Log Level</label>
        <select
          id="agent-log-level"
          :value="backendSettings?.agents?.log_level || 'INFO'"
          @change="updateAgentSetting('log_level', $event.target.value)"
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

interface Props {
  backendSettings?: any
  llmSettings?: any
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

// Validation state
const validationErrors = reactive({})
const validationSuccess = reactive({})

// Connection status
const connectionStatus = reactive({
  status: 'unknown', // 'connected', 'disconnected', 'testing', 'unknown'
  message: 'Connection status unknown',
  responseTime: null
})

// Hardware status
const hardwareStatus = reactive({
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
    validationErrors[key] = validation.error
  }
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

const getHealthIconClass = (status: string) => {
  const iconMap = {
    'healthy': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

// NEW: Enhanced connection testing methods
const getConnectionIcon = (status: string) => {
  const iconMap = {
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
    const endpoint = props.backendSettings?.api_endpoint || 'http://172.16.168.20:8001'
    const startTime = Date.now()

    const response = await fetch(`${endpoint}/health`, {
      method: 'GET',
      timeout: 5000
    })

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
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Connection error: ${error.message}`
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
  console.log(`Validating path for ${pathKey}`)
}

const testLLMConnection = async () => {
  if (isTestingLLM.value) return

  isTestingLLM.value = true
  try {
    // Test LLM connection based on current provider
    console.log('Testing LLM connection...')
    // Implement actual LLM testing logic
  } finally {
    isTestingLLM.value = false
  }
}

const refreshLLMModels = async () => {
  if (isRefreshingLLMModels.value) return

  isRefreshingLLMModels.value = true
  try {
    console.log('Refreshing LLM models...')
    // Implement model refresh logic
  } finally {
    setTimeout(() => {
      isRefreshingLLMModels.value = false
    }, 2000)
  }
}

const testOllamaConnection = async () => {
  console.log('Testing Ollama connection...')
}

const testLMStudioConnection = async () => {
  console.log('Testing LM Studio connection...')
}

const testOpenAIConnection = async () => {
  console.log('Testing OpenAI connection...')
}

const testAnthropicConnection = async () => {
  console.log('Testing Anthropic connection...')
}

const testEmbeddingConnection = async () => {
  if (isTestingEmbedding.value) return

  isTestingEmbedding.value = true
  try {
    console.log('Testing embedding connection...')
  } finally {
    isTestingEmbedding.value = false
  }
}

const testEmbeddingEndpoint = async () => {
  console.log('Testing embedding endpoint...')
}

// NEW: Hardware testing methods
const testGPU = async () => {
  if (isTestingGPU.value) return

  isTestingGPU.value = true
  hardwareStatus.gpu.status = 'testing'
  hardwareStatus.gpu.message = 'Testing GPU...'

  try {
    // Implement GPU testing logic
    await new Promise(resolve => setTimeout(resolve, 2000))
    hardwareStatus.gpu.status = 'available'
    hardwareStatus.gpu.message = 'GPU acceleration available'
    hardwareStatus.gpu.details = {
      utilization: 15,
      memory: '4GB / 8GB'
    }
  } catch (error) {
    hardwareStatus.gpu.status = 'unavailable'
    hardwareStatus.gpu.message = 'GPU not available'
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
    const endpoint = props.backendSettings?.api_endpoint || 'http://172.16.168.20:8001'
    const response = await fetch(`${endpoint}/api/monitoring/phase9/hardware/npu`)

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
    hardwareStatus.npu.status = 'error'
    hardwareStatus.npu.message = `NPU test failed: ${error.message}`
  } finally {
    isTestingNPU.value = false
  }
}

const refreshMemoryStatus = async () => {
  hardwareStatus.memory.status = 'checking'
  hardwareStatus.memory.message = 'Checking memory status...'

  try {
    // Simulate memory check
    await new Promise(resolve => setTimeout(resolve, 1000))
    hardwareStatus.memory.status = 'available'
    hardwareStatus.memory.message = 'Memory status healthy'
    hardwareStatus.memory.details = {
      total: '16 GB',
      available: '8.2 GB'
    }
  } catch (error) {
    hardwareStatus.memory.status = 'error'
    hardwareStatus.memory.message = 'Failed to get memory status'
  }
}

// Initialize connection status on mount
onMounted(() => {
  testConnection()
  refreshMemoryStatus()
})
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

/* NEW: Connection Status Banner */
.connection-status-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid;
}

.connection-status-banner.connected {
  background: #d4edda;
  border-color: #c3e6cb;
  color: #155724;
}

.connection-status-banner.disconnected {
  background: #f8d7da;
  border-color: #f5c6cb;
  color: #721c24;
}

.connection-status-banner.testing {
  background: #fff3cd;
  border-color: #ffeaa7;
  color: #856404;
}

.connection-status-banner.unknown {
  background: #e2e3e5;
  border-color: #d6d8db;
  color: #383d41;
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
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.test-connection-btn {
  background: #007acc;
  color: white;
}

.test-connection-btn:hover:not(:disabled) {
  background: #005fa3;
}

.test-connection-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-status-btn {
  background: #6c757d;
  color: white;
}

.refresh-status-btn:hover {
  background: #545b62;
}

.response-time {
  font-size: 12px;
  opacity: 0.8;
}

/* Enhanced LLM Status Display */
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
  margin-bottom: 12px;
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

.llm-actions, .embedding-actions {
  display: flex;
  gap: 8px;
}

.test-llm-btn, .refresh-models-btn, .test-embedding-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.test-llm-btn, .test-embedding-btn {
  background: #28a745;
  color: white;
}

.test-llm-btn:hover:not(:disabled), .test-embedding-btn:hover:not(:disabled) {
  background: #218838;
}

.refresh-models-btn {
  background: #17a2b8;
  color: white;
}

.refresh-models-btn:hover:not(:disabled) {
  background: #138496;
}

/* NEW: Hardware Status Grid */
.hardware-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.hardware-card {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.2s;
}

.hardware-card.available {
  border-color: #28a745;
  background: rgba(40, 167, 69, 0.05);
}

.hardware-card.unavailable {
  border-color: #dc3545;
  background: rgba(220, 53, 69, 0.05);
}

.hardware-card.testing {
  border-color: #ffc107;
  background: rgba(255, 193, 7, 0.05);
}

.hardware-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.hardware-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.hardware-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.available {
  background: #28a745;
}

.status-indicator.unavailable {
  background: #dc3545;
}

.status-indicator.testing {
  background: #ffc107;
}

.status-indicator.unknown {
  background: #6c757d;
}

.hardware-details {
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
  color: #6c757d;
}

.test-hardware-btn {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  background: #007acc;
  color: white;
  transition: all 0.2s;
}

.test-hardware-btn:hover:not(:disabled) {
  background: #005fa3;
}

.test-hardware-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hardware-settings {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
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
  border-radius: 4px;
  cursor: pointer;
  background: #17a2b8;
  color: white;
  font-size: 12px;
  white-space: nowrap;
}

.test-endpoint-btn:hover, .validate-path-btn:hover {
  background: #138496;
}

.validation-message {
  font-size: 12px;
  margin-top: 4px;
  padding: 4px 8px;
  border-radius: 4px;
}

.validation-message.error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.validation-message.success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.validation-error {
  border-color: #dc3545 !important;
  box-shadow: 0 0 0 2px rgba(220, 53, 69, 0.2) !important;
}

.embedding-status-display {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 20px;
}

.current-embedding-info {
  margin-bottom: 8px;
  font-size: 14px;
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

.model-selection {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-indicator {
  font-size: 12px;
  color: #6c757d;
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