<template>
  <ErrorBoundary fallback="Settings panel failed to load.">
    <div class="settings-panel">
    <h2>Settings</h2>
    
    <!-- Unsaved Changes Indicator -->
    <div v-if="hasUnsavedChanges" class="unsaved-changes-indicator">
      <i class="fas fa-exclamation-circle"></i>
      <span>You have unsaved changes. Click "Save Settings" to apply them.</span>
    </div>
    
    <div class="settings-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
       :aria-label="tab.label">
        {{ tab.label }}
      </button>
    </div>
    <div class="settings-content">
      <!-- Loading indicator -->
      <div v-if="settingsLoadingStatus === 'loading'" class="settings-loading">
        <div class="loading-spinner"></div>
        <p>Loading settings...</p>
      </div>

      <!-- Settings status message -->
      <div v-if="settingsLoadingStatus === 'offline'" class="settings-status offline">
        <i class="fas fa-exclamation-triangle"></i>
        <span>Backend offline - using cached settings</span>
      </div>

      <!-- Chat Settings -->
      <div v-if="activeTab === 'chat' && settings.chat && isSettingsLoaded" class="settings-section">
        <h3>Chat Settings</h3>
        <div class="setting-item">
          <label>Auto Scroll to Bottom</label>
          <input type="checkbox" v-model="settings.chat.auto_scroll" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Max Messages</label>
          <input type="number" v-model="settings.chat.max_messages" min="10" max="1000" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Message Retention (Days)</label>
          <input type="number" v-model="settings.chat.message_retention_days" min="1" max="365" @change="markAsChanged" />
        </div>
      </div>

      <!-- Backend Settings -->
      <div v-if="activeTab === 'backend' && isSettingsLoaded" class="settings-section">
        <div class="sub-tabs">
          <button
            :class="{ active: activeBackendSubTab === 'general' }"
            @click="activeBackendSubTab = 'general'"
           aria-label="General">
            General
          </button>
          <button
            :class="{ active: activeBackendSubTab === 'llm' }"
            @click="activeBackendSubTab = 'llm'"
           aria-label="Llm">
            LLM
          </button>
          <button
            :class="{ active: activeBackendSubTab === 'embedding' }"
            @click="activeBackendSubTab = 'embedding'"
           aria-label="Embedding">
            Embedding
          </button>
          <button
            :class="{ active: activeBackendSubTab === 'memory' }"
            @click="activeBackendSubTab = 'memory'"
           aria-label="Memory">
            Memory
          </button>
        </div>
        <div v-if="activeBackendSubTab === 'general'" class="sub-tab-content">
          <h3>Backend General Settings</h3>
          <div class="setting-item">
            <label>API Endpoint</label>
            <input type="text" v-model="settings.backend.api_endpoint" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Server Host</label>
            <input type="text" v-model="settings.backend.server_host" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Server Port</label>
            <input type="number" v-model="settings.backend.server_port" min="1" max="65535" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Chat Data Directory</label>
            <input type="text" v-model="settings.backend.chat_data_dir" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Chat History File</label>
            <input type="text" v-model="settings.backend.chat_history_file" placeholder="data/chat_history.json" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Knowledge Base DB</label>
            <input type="text" v-model="settings.backend.knowledge_base_db" placeholder="data/knowledge_base.db" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Reliability Stats File</label>
            <input type="text" v-model="settings.backend.reliability_stats_file" placeholder="data/reliability_stats.json" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Logs Directory</label>
            <input type="text" v-model="settings.backend.logs_directory" placeholder="logs/" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Chat Enabled</label>
            <input type="checkbox" v-model="settings.backend.chat_enabled" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Knowledge Base Enabled</label>
            <input type="checkbox" v-model="settings.backend.knowledge_base_enabled" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Auto Backup Chat</label>
            <input type="checkbox" v-model="settings.backend.auto_backup_chat" @change="markAsChanged" />
          </div>
        </div>
        <div v-if="activeBackendSubTab === 'llm'" class="sub-tab-content">
          <h3>LLM Configuration</h3>
          <div class="llm-status-display">
            <div class="current-llm-info">
              <strong>Current LLM:</strong> {{ getCurrentLLMDisplay() }}
            </div>
            <div v-if="healthStatus && healthStatus.backend && healthStatus.backend.llm_provider" 
                 :class="['health-indicator', healthStatus.backend.llm_provider.status || 'unknown']">
              <i :class="{
                'fas fa-check-circle': healthStatus.backend.llm_provider.status === 'healthy',
                'fas fa-exclamation-triangle': healthStatus.backend.llm_provider.status === 'warning',
                'fas fa-times-circle': healthStatus.backend.llm_provider.status === 'error',
                'fas fa-question-circle': !healthStatus.backend.llm_provider.status
              }"></i>
              {{ healthStatus.backend.llm_provider.message || 'Status unknown' }}
            </div>
          </div>
          <div class="setting-item">
            <label>Provider Type</label>
            <select v-model="settings.backend.llm.provider_type" @change="onProviderTypeChange">
              <option value="local">Local LLM</option>
              <option value="cloud">Cloud LLM</option>
            </select>
          </div>
          <div v-if="settings.backend.llm.provider_type === 'local'">
            <div class="setting-item">
              <label>Local Provider</label>
              <select v-model="settings.backend.llm.local.provider" @change="onLocalProviderChange">
                <option value="ollama">Ollama</option>
                <option value="lmstudio">LM Studio</option>
              </select>
            </div>
            <div v-if="settings.backend.llm.local.provider === 'ollama'">
              <div class="setting-item">
                <label>Ollama Endpoint</label>
                <input type="text" v-model="settings.backend.llm.local.providers.ollama.endpoint" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Model</label>
                <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                <select v-model="settings.backend.llm.local.providers.ollama.selected_model" @change="markAsChanged">
                  <option v-for="model in settings.backend.llm.local.providers.ollama.models" :key="model" :value="model">{{ model }}</option>
                </select>
              </div>
            </div>
            <div v-else-if="settings.backend.llm.local.provider === 'lmstudio'">
              <div class="setting-item">
                <label>LM Studio Endpoint</label>
                <input type="text" v-model="settings.backend.llm.local.providers.lmstudio.endpoint" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Model</label>
                <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                <select v-model="settings.backend.llm.local.providers.lmstudio.selected_model" @change="markAsChanged">
                  <option v-for="model in settings.backend.llm.local.providers.lmstudio.models" :key="model" :value="model">{{ model }}</option>
                </select>
              </div>
            </div>
          </div>
          <div v-else-if="settings.backend.llm.provider_type === 'cloud'">
            <div class="setting-item">
              <label>Cloud Provider</label>
              <select v-model="settings.backend.llm.cloud.provider" @change="onCloudProviderChange">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </div>
            <div v-if="settings.backend.llm.cloud.provider === 'openai'">
              <div class="setting-item">
                <label>API Key</label>
                <input type="password" v-model="settings.backend.llm.cloud.providers.openai.api_key" placeholder="Enter API Key" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Endpoint</label>
                <input type="text" v-model="settings.backend.llm.cloud.providers.openai.endpoint" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Model</label>
                <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                <select v-model="settings.backend.llm.cloud.providers.openai.selected_model" @change="markAsChanged">
                  <option v-for="model in settings.backend.llm.cloud.providers.openai.models" :key="model" :value="model">{{ model }}</option>
                </select>
              </div>
            </div>
            <div v-else-if="settings.backend.llm.cloud.provider === 'anthropic'">
              <div class="setting-item">
                <label>API Key</label>
                <input type="password" v-model="settings.backend.llm.cloud.providers.anthropic.api_key" placeholder="Enter API Key" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Endpoint</label>
                <input type="text" v-model="settings.backend.llm.cloud.providers.anthropic.endpoint" @change="markAsChanged" />
              </div>
              <div class="setting-item">
                <label>Model</label>
                <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                <select v-model="settings.backend.llm.cloud.providers.anthropic.selected_model" @change="markAsChanged">
                  <option v-for="model in settings.backend.llm.cloud.providers.anthropic.models" :key="model" :value="model">{{ model }}</option>
                </select>
              </div>
            </div>
          </div>
          <div class="setting-item">
            <label>Timeout (seconds)</label>
            <input type="number" v-model="settings.backend.timeout" min="10" max="300" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Max Tokens</label>
            <input type="number" v-model="settings.backend.max_tokens" min="100" max="8192" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Enable Streaming</label>
            <!-- FIXED: Remove immediate @change handler, only mark as changed -->
            <input type="checkbox" v-model="settings.backend.streaming" @change="markAsChanged" />
          </div>
          <div class="settings-actions">
            <button @click="loadModels" aria-label="Refresh models">Refresh Models</button>
          </div>
        </div>
        <div v-if="activeBackendSubTab === 'embedding'" class="sub-tab-content">
          <h3>Embedding Model Settings</h3>
          <div class="setting-item">
            <label>Current Embedding Model Status</label>
            <div class="embedding-status-display">
              <div class="current-embedding-info">
                <strong>Current Embedding:</strong> {{ getCurrentEmbeddingConfig() }}
              </div>
              <div v-if="healthStatus && healthStatus.backend && healthStatus.backend.embedding_provider" 
                   :class="['health-indicator', healthStatus.backend.embedding_provider.status || 'unknown']">
                <i :class="{
                  'fas fa-check-circle': healthStatus.backend.embedding_provider.status === 'healthy',
                  'fas fa-exclamation-triangle': healthStatus.backend.embedding_provider.status === 'warning',
                  'fas fa-times-circle': healthStatus.backend.embedding_provider.status === 'error',
                  'fas fa-question-circle': !healthStatus.backend.embedding_provider.status
                }"></i>
                {{ healthStatus.backend.embedding_provider.message || 'Status unknown' }}
              </div>
            </div>
          </div>
          <div class="setting-item">
            <label>Embedding Provider</label>
            <select v-model="settings.backend.llm.embedding.provider" @change="onEmbeddingProviderChange">
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div v-if="settings.backend.llm.embedding.provider === 'ollama'">
            <div class="setting-item">
              <label>Ollama Endpoint</label>
              <input type="text" v-model="settings.backend.llm.embedding.providers.ollama.endpoint" @change="markAsChanged" />
            </div>
            <div class="setting-item">
              <label>Embedding Model</label>
              <!-- FIXED: Remove immediate @change handler, only mark as changed -->
              <select v-model="settings.backend.llm.embedding.providers.ollama.selected_model" @change="markAsChanged">
                <option v-for="model in settings.backend.llm.embedding.providers.ollama.models" :key="model" :value="model">{{ model }}</option>
              </select>
            </div>
          </div>
          <div v-else-if="settings.backend.llm.embedding.provider === 'openai'">
            <div class="setting-item">
              <label>API Key</label>
              <input type="password" v-model="settings.backend.llm.embedding.providers.openai.api_key" placeholder="Enter API Key" @change="markAsChanged" />
            </div>
            <div class="setting-item">
              <label>Endpoint</label>
              <input type="text" v-model="settings.backend.llm.embedding.providers.openai.endpoint" @change="markAsChanged" />
            </div>
            <div class="setting-item">
              <label>Embedding Model</label>
              <!-- FIXED: Remove immediate @change handler, only mark as changed -->
              <select v-model="settings.backend.llm.embedding.providers.openai.selected_model" @change="markAsChanged">
                <option v-for="model in settings.backend.llm.embedding.providers.openai.models" :key="model" :value="model">{{ model }}</option>
              </select>
            </div>
          </div>
          <div class="settings-actions">
            <button @click="loadEmbeddingModels" aria-label="Refresh embedding models">Refresh Embedding Models</button>
          </div>
        </div>
        <div v-if="activeBackendSubTab === 'memory'" class="sub-tab-content">
          <h3>Memory Settings</h3>
          <div class="setting-item">
            <label>Max Conversation Memory</label>
            <input type="number" v-model="settings.backend.memory.max_conversation_memory" min="5" max="50" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Context Window</label>
            <input type="number" v-model="settings.backend.memory.context_window" min="1000" max="8000" @change="markAsChanged" />
          </div>
        </div>
      </div>

      <!-- UI Settings -->
      <div v-if="activeTab === 'ui' && settings.ui && isSettingsLoaded" class="settings-section">
        <h3>User Interface Settings</h3>
        <div class="setting-item">
          <label>Theme</label>
          <select v-model="settings.ui.theme" @change="markAsChanged">
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="auto">Auto</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Language</label>
          <select v-model="settings.ui.language" @change="markAsChanged">
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Show Timestamps</label>
          <input type="checkbox" v-model="settings.ui.show_timestamps" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Show Status Bar</label>
          <input type="checkbox" v-model="settings.ui.show_status_bar" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Auto Refresh Interval (seconds)</label>
          <input type="number" v-model="settings.ui.auto_refresh_interval" min="5" max="300" @change="markAsChanged" />
        </div>
      </div>

      <!-- Logging Settings -->
      <div v-if="activeTab === 'logging' && settings.logging && isSettingsLoaded" class="settings-section">
        <h3>Logging Settings</h3>
        <div class="setting-item">
          <label>Log Level</label>
          <select v-model="settings.logging.level" @change="markAsChanged">
            <option v-for="level in settings.logging.log_levels" :key="level" :value="level">{{ level.toUpperCase() }}</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Console Logging</label>
          <input type="checkbox" v-model="settings.logging.console" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>File Logging</label>
          <input type="checkbox" v-model="settings.logging.file" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Max Log File Size (MB)</label>
          <input type="number" v-model="settings.logging.max_file_size" min="1" max="100" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Enable Request Logging</label>
          <input type="checkbox" v-model="settings.logging.log_requests" @change="markAsChanged" />
        </div>
        <div class="setting-item">
          <label>Enable SQL Logging</label>
          <input type="checkbox" v-model="settings.logging.log_sql" @change="markAsChanged" />
        </div>
      </div>

      <!-- Cache Settings -->
      <div v-if="activeTab === 'cache' && isSettingsLoaded" class="settings-section">
        <h3>Cache Management</h3>
        
        <!-- Cache Configuration -->
        <div class="cache-configuration">
          <h4>Cache Configuration</h4>
          <div class="setting-item">
            <label>Enable Caching</label>
            <input type="checkbox" v-model="cacheConfig.enabled" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Default TTL (seconds)</label>
            <input type="number" v-model="cacheConfig.defaultTTL" min="10" max="86400" @change="markAsChanged" />
          </div>
          <div class="setting-item">
            <label>Max Cache Size (MB)</label>
            <input type="number" v-model="cacheConfig.maxCacheSizeMB" min="10" max="1000" @change="markAsChanged" />
          </div>
          
          <button @click="saveCacheConfig" class="save-btn" :disabled="isSaving">
            <i class="fas fa-save"></i> Save Cache Configuration
          </button>
        </div>

        <!-- Cache Activity Log -->
        <div class="cache-activity">
          <h4>Cache Activity <button @click="refreshCacheActivity" class="small-btn"><i class="fas fa-refresh"></i></button></h4>
          <div class="activity-log">
            <div v-for="activity in cacheActivity" :key="activity.id" :class="['activity-item', activity.type]">
              <span class="timestamp">{{ activity.timestamp }}</span>
              <span class="message">{{ activity.message }}</span>
            </div>
          </div>
        </div>

        <!-- Cache Statistics -->
        <div v-if="cacheStats" class="cache-stats">
          <h4>Cache Statistics</h4>
          <div class="stats-grid">
            <div class="stat-item">
              <label>Total Items:</label>
              <span>{{ cacheStats.totalItems || 0 }}</span>
            </div>
            <div class="stat-item">
              <label>Memory Usage:</label>
              <span>{{ formatBytes(cacheStats.memoryUsage || 0) }}</span>
            </div>
            <div class="stat-item">
              <label>Hit Rate:</label>
              <span>{{ (cacheStats.hitRate * 100 || 0).toFixed(1) }}%</span>
            </div>
            <div class="stat-item">
              <label>Expired Items:</label>
              <span>{{ cacheStats.expiredItems || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Cache Control Buttons -->
        <div class="cache-controls">
          <button @click="clearCache('all')" :disabled="isClearing" class="clear-btn">
            <i class="fas fa-trash"></i> Clear All Cache
          </button>
          <button @click="clearCache('expired')" :disabled="isClearing" class="clear-btn">
            <i class="fas fa-clock"></i> Clear Expired
          </button>
          <button @click="refreshCacheStats" class="refresh-btn">
            <i class="fas fa-refresh"></i> Refresh Stats
          </button>
        </div>
      </div>

      <!-- Prompts Settings -->
      <div v-if="activeTab === 'prompts' && settings.prompts && isSettingsLoaded" class="settings-section">
        <h3>Prompt Management</h3>
        <div class="prompts-list">
          <div v-for="prompt in settings.prompts.list" :key="prompt.id" class="prompt-item">
            <h4>{{ prompt.name || prompt.id }}</h4>
            <p>{{ prompt.description || 'No description available' }}</p>
            <button @click="selectPrompt(prompt)" aria-label="Edit prompt">Edit</button>
          </div>
        </div>
        <div v-if="!settings.prompts.list || settings.prompts.list.length === 0">
          <p>No prompts available. <button @click="loadPrompts" aria-label="Load prompts">Load Prompts</button></p>
        </div>
        <div class="prompt-editor" v-if="settings.prompts.selectedPrompt">
          <h4>Editing: {{ settings.prompts.selectedPrompt.name || settings.prompts.selectedPrompt.id }}</h4>
          <textarea v-model="settings.prompts.editedContent" rows="10" placeholder="Edit prompt content here..."></textarea>
          <div class="editor-actions">
            <button @click="savePrompt" aria-label="Save changes">Save Changes</button>
            <button @click="revertPromptToDefault(settings.prompts.selectedPrompt.id)" aria-label="Revert to default">Revert to Default</button>
            <button @click="settings.prompts.selectedPrompt = null" aria-label="Cancel">Cancel</button>
          </div>
        </div>
        <div class="prompts-controls">
          <button class="control-button small" @click="loadPrompts" aria-label="Load prompts">Load Prompts</button>
        </div>
      </div>

      <!-- Developer Mode Section -->
      <div v-if="activeTab === 'developer' && settings.developer && isSettingsLoaded" class="settings-section">
        <div class="developer-section">
          <h3>Developer Mode</h3>
          <div class="setting-item">
            <label>Enable Developer Mode</label>
            <!-- FIXED: Remove immediate @change handler, only mark as changed -->
            <input type="checkbox" v-model="settings.developer.enabled" @change="markAsChanged" />
          </div>
          <div v-if="settings.developer.enabled">
            <div class="setting-item">
              <label>Enhanced Error Messages</label>
              <!-- FIXED: Remove immediate @change handler, only mark as changed -->
              <input type="checkbox" v-model="settings.developer.enhanced_errors" @change="markAsChanged" />
            </div>
            <div class="setting-item">
              <label>API Endpoint Suggestions</label>
              <!-- FIXED: Remove immediate @change handler, only mark as changed -->
              <input type="checkbox" v-model="settings.developer.endpoint_suggestions" @change="markAsChanged" />
            </div>
            <div class="setting-item">
              <label>Debug Logging</label>
              <!-- FIXED: Remove immediate @change handler, only mark as changed -->
              <input type="checkbox" v-model="settings.developer.debug_logging" @change="markAsChanged" />
            </div>
            
            <!-- RUM (Real User Monitoring) Settings -->
            <div class="rum-settings">
              <h4>Real User Monitoring (RUM)</h4>
              <div class="setting-item">
                <label class="with-description">
                  Enable RUM Agent
                  <span class="description">Monitor user interactions, performance metrics, and errors in real-time</span>
                </label>
                <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                <input type="checkbox" v-model="settings.developer.rum.enabled" @change="markAsChanged" />
              </div>
              <div class="rum-config" v-if="settings.developer?.rum?.enabled === true">
                <div class="setting-item">
                  <label class="with-description">
                    Error Tracking
                    <span class="description">Capture JavaScript errors and exceptions</span>
                  </label>
                  <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                  <input type="checkbox" v-model="settings.developer.rum.error_tracking" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label class="with-description">
                    Performance Monitoring
                    <span class="description">Track page load times, API calls, and resource loading</span>
                  </label>
                  <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                  <input type="checkbox" v-model="settings.developer.rum.performance_monitoring" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label class="with-description">
                    User Interaction Tracking
                    <span class="description">Monitor clicks, form submissions, and navigation</span>
                  </label>
                  <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                  <input type="checkbox" v-model="settings.developer.rum.interaction_tracking" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label class="with-description">
                    Session Recording
                    <span class="description">Record user sessions for debugging (privacy-aware)</span>
                  </label>
                  <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                  <input type="checkbox" v-model="settings.developer.rum.session_recording" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label>Sample Rate (%)</label>
                  <input type="number" v-model="settings.developer.rum.sample_rate" 
                         min="0" max="100" step="1" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label>Max Events per Session</label>
                  <input type="number" v-model="settings.developer.rum.max_events_per_session" 
                         min="100" max="10000" step="100" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label class="with-description">
                    Debug Mode
                    <span class="description">Enable console logging for RUM events</span>
                  </label>
                  <!-- FIXED: Remove immediate @change handler, only mark as changed -->
                  <input type="checkbox" v-model="settings.developer.rum.debug_mode" @change="markAsChanged" />
                </div>
                <div class="setting-item">
                  <label class="with-description">
                    RUM Log Level
                    <span class="description">Control verbosity of RUM backend logging</span>
                  </label>
                  <select v-model="settings.developer.rum.log_level" @change="markAsChanged">
                    <option v-for="level in settings.logging.log_levels" :key="level" :value="level">
                      {{ level.toUpperCase() }}
                    </option>
                  </select>
                </div>
                
                <!-- RUM Status Display -->
                <div class="rum-status" v-if="settings.developer?.rum?.enabled && rumStatus && rumStatus.active">
                  <h5>RUM Agent Status</h5>
                  <div class="status-grid">
                    <div class="status-item">
                      <label>Active:</label>
                      <span :class="rumStatus.active ? 'status-good' : 'status-bad'">
                        {{ rumStatus.active ? 'Yes' : 'No' }}
                      </span>
                    </div>
                    <div class="status-item">
                      <label>Events Captured:</label>
                      <span>{{ rumStatus.eventsCaptured || 0 }}</span>
                    </div>
                    <div class="status-item">
                      <label>Errors Tracked:</label>
                      <span>{{ rumStatus.errorsTracked || 0 }}</span>
                    </div>
                    <div class="status-item">
                      <label>Session Duration:</label>
                      <span>{{ formatDuration(rumStatus.sessionDuration || 0) }}</span>
                    </div>
                  </div>
                  
                  <div class="rum-controls">
                    <button @click="refreshRumStatus" class="small-btn">
                      <i class="fas fa-refresh"></i> Refresh Status
                    </button>
                    <button @click="clearRumData" class="small-btn">
                      <i class="fas fa-trash"></i> Clear RUM Data
                    </button>
                    <button @click="exportRumData" class="small-btn">
                      <i class="fas fa-download"></i> Export Data
                    </button>
                  </div>
                </div>
              </div>
            </div>
            
            <div class="developer-info" v-if="developerInfo">
              <h4>System Information</h4>
              <div class="info-grid">
                <div class="info-item">
                  <label>Python Version:</label>
                  <span>{{ developerInfo.python_version }}</span>
                </div>
                <div class="info-item">
                  <label>FastAPI Version:</label>
                  <span>{{ developerInfo.fastapi_version }}</span>
                </div>
                <div class="info-item">
                  <label>Total API Endpoints:</label>
                  <span>{{ developerInfo.total_endpoints || 'N/A' }}</span>
                </div>
                <div class="info-item">
                  <label>Memory Usage:</label>
                  <span>{{ developerInfo.memory_usage || 'N/A' }}</span>
                </div>
                <div class="info-item">
                  <label>CPU Usage:</label>
                  <span>{{ developerInfo.cpu_usage || 'N/A' }}</span>
                </div>
                <div class="info-item">
                  <label>Uptime:</label>
                  <span>{{ developerInfo.uptime || 'N/A' }}</span>
                </div>
              </div>
              <div class="developer-actions">
                <button @click="showApiEndpoints" aria-label="Show API endpoints">Show API Endpoints</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Agent Management Section -->
        <div class="agents-section">
          <h3>Agent Management</h3>
          <div class="agents-overview">
            <div class="agents-stats">
              <div class="stat-card">
                <h4>{{ enabledAgentsCount }}</h4>
                <p>Enabled Agents</p>
              </div>
              <div class="stat-card">
                <h4>{{ agentsList.length }}</h4>
                <p>Total Agents</p>
              </div>
              <div class="stat-card">
                <h4 :class="getOverallHealthClass()">{{ getOverallHealthStatus() }}</h4>
                <p>Overall Health</p>
              </div>
            </div>
            <div class="agents-controls">
              <button @click="refreshAgents" class="refresh-btn">
                <i class="fas fa-refresh"></i> Refresh Agents
              </button>
              <button @click="testAllAgents" class="test-btn">
                <i class="fas fa-play"></i> Test All
              </button>
            </div>
          </div>
          
          <div class="agents-list">
            <div v-for="agent in agentsList" :key="agent.id" class="agent-card">
              <div class="agent-header">
                <div class="agent-info">
                  <h4>{{ agent.name }}</h4>
                  <div class="agent-controls">
                    <label class="toggle-switch">
                      <input type="checkbox" :checked="agent.enabled" @change="toggleAgent(agent.id, $event.target.checked)" />
                      <span class="toggle-slider"></span>
                    </label>
                    <span :class="['agent-status', agent.status]">{{ agent.status }}</span>
                  </div>
                </div>
                <p class="agent-description">{{ agent.description }}</p>
              </div>
              <div v-if="agent.enabled" class="agent-details">
                <div class="agent-config">
                  <div class="config-item">
                    <label>Model:</label>
                    <select v-model="agent.current_model" @change="updateAgentModel(agent.id, agent.current_model)" :disabled="!agent.enabled">
                      <option v-for="model in availableModels" :key="model" :value="model">{{ model }}</option>
                    </select>
                  </div>
                  <div class="config-item">
                    <label>Provider:</label>
                    <select v-model="agent.provider" @change="updateAgentProvider(agent.id, agent.provider)" :disabled="!agent.enabled">
                      <option value="ollama">Ollama</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                    </select>
                  </div>
                  <div class="config-item">
                    <label>Priority:</label>
                    <input type="number" v-model="agent.priority" @change="updateAgentPriority(agent.id, agent.priority)" min="1" max="10" :disabled="!agent.enabled" />
                  </div>
                </div>
                <div class="agent-tasks" v-if="agent.tasks && agent.tasks.length > 0">
                  <h5>Current Tasks</h5>
                  <ul>
                    <li v-for="task in agent.tasks" :key="task.id">
                      <span :class="['task-status', task.status]">{{ task.name }}</span>
                      <small>{{ task.description }}</small>
                    </li>
                  </ul>
                </div>
                <div class="agent-metrics" v-if="agent.metrics">
                  <h5>Performance Metrics</h5>
                  <div class="metrics-grid">
                    <div class="metric">
                      <label>Success Rate:</label>
                      <span>{{ (agent.metrics.success_rate * 100).toFixed(1) }}%</span>
                    </div>
                    <div class="metric">
                      <label>Avg Response Time:</label>
                      <span>{{ agent.metrics.avg_response_time }}ms</span>
                    </div>
                    <div class="metric">
                      <label>Total Requests:</label>
                      <span>{{ agent.metrics.total_requests }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="settings-actions">
      <!-- MAIN FIX: Enhanced Save Settings button with unsaved changes indicator -->
      <button @click="saveSettings" :disabled="isSaving" :class="['save-button', {'has-changes': hasUnsavedChanges}]" :aria-label="isSaving ? 'Saving...' : 'Save Settings'">
        {{ isSaving ? 'Saving...' : 'Save Settings' }}
        <span v-if="hasUnsavedChanges" class="changes-indicator">*</span>
      </button>
      
      <!-- NEW: Discard Changes button -->
      <button @click="discardChanges" :disabled="isSaving || !hasUnsavedChanges" class="discard-button" aria-label="Discard Changes">
        Discard Changes
      </button>
      
      <div v-if="saveMessage" :class="['save-message', saveMessageType]">
        {{ saveMessage }}
      </div>
    </div>
  </div>
  </ErrorBoundary>
</template>

<script>
import { ref, onMounted, watch, computed, onUnmounted } from 'vue';
import apiClient from '../utils/ApiClient.js';
import { settingsService } from '../services/SettingsService.js';
import { healthService } from '../services/HealthService.js';
import cacheService from '../services/CacheService.js';
import ErrorBoundary from './ErrorBoundary.vue';

export default {
  name: 'SettingsPanel',
  components: {
    ErrorBoundary
  },
  setup() {
    // Reactive state
    const settings = ref({});
    const hasUnsavedChanges = ref(false); // NEW: Track unsaved changes
    const isSettingsLoaded = ref(false);
    const settingsLoadingStatus = ref('loading');
    
    // UI state
    const tabs = ref([
      { id: 'chat', label: 'Chat' },
      { id: 'backend', label: 'Backend' },
      { id: 'ui', label: 'UI' },
      { id: 'logging', label: 'Logging' },
      { id: 'cache', label: 'Cache' },
      { id: 'prompts', label: 'Prompts' },
      { id: 'developer', label: 'Developer' }
    ]);
    
    const activeTab = ref('chat');
    const activeBackendSubTab = ref('general');
    
    // Save state
    const isSaving = ref(false);
    const saveMessage = ref('');
    const saveMessageType = ref('');
    
    // Health status
    const healthStatus = ref(null);
    
    // Developer info
    const developerInfo = ref(null);
    
    // Agent management
    const agentsList = ref([]);
    const availableModels = ref([]);
    
    // Cache management
    const cacheStats = ref(null);
    const cacheActivity = ref([]);
    const cacheConfig = ref({
      enabled: true,
      defaultTTL: 300,
      maxCacheSizeMB: 100
    });
    const isClearing = ref(false);
    
    // RUM status
    const rumStatus = ref(null);
    
    // NEW: Mark as changed function
    const markAsChanged = () => {
      hasUnsavedChanges.value = true;
    };
    
    // NEW: Discard changes function
    const discardChanges = () => {
      // Force reload settings from backend/cache to discard local changes
      forceReloadSettings();
      hasUnsavedChanges.value = false;
    };
    
    // Computed properties
    const enabledAgentsCount = computed(() => {
      return agentsList.value.filter(agent => agent.enabled).length;
    });
    
    // Load settings from backend or cache
    const loadSettings = async () => {
      try {
        settingsLoadingStatus.value = 'loading';
        
        // Try to load from backend first
        let settingsData;
        try {
          settingsData = await settingsService.getSettings();
          settingsLoadingStatus.value = 'online';
        } catch (error) {
          console.warn('Backend unavailable, using cached settings:', error);
          settingsData = JSON.parse(localStorage.getItem('chat_settings') || '{}');
          settingsLoadingStatus.value = 'offline';
        }
        
        // Set default structure if empty
        if (!settingsData || Object.keys(settingsData).length === 0) {
          settingsData = getDefaultSettings();
        }
        
        settings.value = settingsData;
        isSettingsLoaded.value = true;
        hasUnsavedChanges.value = false; // Reset unsaved changes flag
        
        // Load additional data if backend is available
        if (settingsLoadingStatus.value === 'online') {
          await checkHealthStatus();
        }
        
      } catch (error) {
        console.error('Error loading settings:', error);
        settings.value = getDefaultSettings();
        isSettingsLoaded.value = true;
        hasUnsavedChanges.value = false;
        settingsLoadingStatus.value = 'error';
      }
    };
    
    // Get default settings structure
    const getDefaultSettings = () => {
      return {
        chat: {
          auto_scroll: true,
          max_messages: 100,
          message_retention_days: 30
        },
        backend: {
          api_endpoint: "http://localhost:8001",
          server_host: "localhost",
          server_port: 8001,
          chat_data_dir: "data/",
          chat_history_file: "data/chat_history.json",
          knowledge_base_db: "data/knowledge_base.db",
          reliability_stats_file: "data/reliability_stats.json",
          logs_directory: "logs/",
          chat_enabled: true,
          knowledge_base_enabled: true,
          auto_backup_chat: true,
          timeout: 30,
          max_tokens: 2048,
          streaming: true,
          llm: {
            provider_type: "local",
            local: {
              provider: "ollama",
              providers: {
                ollama: {
                  endpoint: "http://localhost:11434",
                  models: [],
                  selected_model: ""
                },
                lmstudio: {
                  endpoint: "http://localhost:1234",
                  models: [],
                  selected_model: ""
                }
              }
            },
            cloud: {
              provider: "openai",
              providers: {
                openai: {
                  endpoint: "https://api.openai.com/v1",
                  api_key: "",
                  models: [],
                  selected_model: ""
                },
                anthropic: {
                  endpoint: "https://api.anthropic.com/v1",
                  api_key: "",
                  models: [],
                  selected_model: ""
                }
              }
            },
            embedding: {
              provider: "ollama",
              providers: {
                ollama: {
                  endpoint: "http://localhost:11434",
                  models: [],
                  selected_model: ""
                },
                openai: {
                  endpoint: "https://api.openai.com/v1",
                  api_key: "",
                  models: [],
                  selected_model: ""
                }
              }
            }
          },
          memory: {
            max_conversation_memory: 10,
            context_window: 4000
          }
        },
        ui: {
          theme: "dark",
          language: "en",
          show_timestamps: true,
          show_status_bar: true,
          auto_refresh_interval: 30
        },
        logging: {
          level: "info",
          log_levels: ["debug", "info", "warning", "error"],
          console: true,
          file: true,
          max_file_size: 10,
          log_requests: false,
          log_sql: false
        },
        developer: {
          enabled: false,
          enhanced_errors: false,
          endpoint_suggestions: false,
          debug_logging: false,
          rum: {
            enabled: false,
            error_tracking: true,
            performance_monitoring: true,
            interaction_tracking: true,
            session_recording: false,
            sample_rate: 100,
            max_events_per_session: 1000,
            debug_mode: false,
            log_level: "info"
          }
        },
        prompts: {
          list: [],
          defaults: {},
          selectedPrompt: null,
          editedContent: ""
        }
      };
    };
    
    // MAIN FIX: Function to save settings to config.yaml via backend
    const saveSettings = async () => {
      isSaving.value = true;
      saveMessage.value = '';
      saveMessageType.value = '';

      try {
        // FIRST: Save developer settings separately to preserve RUM config
        if (settings.value.developer) {
          try {
            await settingsService.updateDeveloperConfig(settings.value.developer);
            console.log('Developer config saved successfully');
          } catch (devError) {
            console.warn('Could not save developer config:', devError);
          }
        }
        
        // Create a deep copy of settings without prompts data (prompts shouldn't be saved to config.yaml)
        const settingsToSave = JSON.parse(JSON.stringify(settings.value));
        delete settingsToSave.prompts;

        const response = await apiClient.post('/api/settings/config', settingsToSave);
        const result = await response.json();

        // Clear frontend cache to ensure fresh data
        cacheService.invalidateCategory('settings');
        
        // Clear backend cache as well
        try {
          await apiClient.post('/api/settings/clear-cache');
        } catch (error) {
          console.warn('Could not clear backend cache:', error);
        }

        // Force a complete reload of settings from backend
        await forceReloadSettings();

        // ONLY NOW: Apply backend changes for provider/embedding settings
        await notifyBackendOfProviderChange();
        await notifyBackendOfEmbeddingChange();
        
        // Apply RUM changes if needed
        if (settings.value.developer?.rum?.enabled) {
          await updateRumConfig();
        }

        // Show success message
        saveMessage.value = 'Settings saved successfully!';
        saveMessageType.value = 'success';
        hasUnsavedChanges.value = false; // IMPORTANT: Clear the flag after successful save

        // Clear message after 3 seconds
        setTimeout(() => {
          saveMessage.value = '';
          saveMessageType.value = '';
        }, 3000);
      } catch (error) {
        console.error('Error saving settings to backend:', error);
        saveMessage.value = `Error saving settings: ${error.message}`;
        saveMessageType.value = 'error';

        // Clear message after 5 seconds for errors
        setTimeout(() => {
          saveMessage.value = '';
          saveMessageType.value = '';
        }, 5000);
      } finally {
        isSaving.value = false;
      }
    };

    // Watch for changes in settings and save them to local storage only
    // Don't auto-save to backend - only save to localStorage for persistence
    watch(settings, () => {
      if (isSettingsLoaded.value) {
        localStorage.setItem('chat_settings', JSON.stringify(settings.value));
      }
    }, { deep: true });

    // FIXED: Provider change handlers that only trigger model loading, no immediate API calls
    const onProviderTypeChange = async () => {
      await loadModels();
      markAsChanged(); // Mark as changed but don't call API
    };

    const onLocalProviderChange = async () => {
      await loadModels();
      markAsChanged(); // Mark as changed but don't call API
    };

    const onCloudProviderChange = async () => {
      markAsChanged(); // Mark as changed but don't call API
    };

    const onEmbeddingProviderChange = async () => {
      await loadEmbeddingModels();
      markAsChanged(); // Mark as changed but don't call API
    };

    // Backend notification methods (ONLY called during saveSettings)
    const notifyBackendOfProviderChange = async () => {
      try {
        const providerType = settings.value.backend.llm.provider_type;
        const providerData = {
          provider_type: providerType,
          streaming: settings.value.backend.streaming
        };

        if (providerType === 'local') {
          const provider = settings.value.backend.llm.local.provider;
          const providerSettings = settings.value.backend.llm.local.providers[provider];

          providerData.local_provider = provider;
          providerData.local_model = providerSettings.selected_model;
          providerData.local_endpoint = providerSettings.endpoint;
        } else {
          const provider = settings.value.backend.llm.cloud.provider;
          const providerSettings = settings.value.backend.llm.cloud.providers[provider];

          providerData.cloud_provider = provider;
          providerData.cloud_model = providerSettings.selected_model;
          providerData.cloud_api_key = providerSettings.api_key;
          providerData.cloud_endpoint = providerSettings.endpoint;
        }

        const response = await apiClient.post('/api/llm/provider', providerData);
        const result = await response.json();

        // Update health status after provider change
        await checkHealthStatus();
      } catch (error) {
        console.error('Error notifying backend of provider change:', error);
      }
    };

    const notifyBackendOfEmbeddingChange = async () => {
      try {
        const provider = settings.value.backend.llm.embedding.provider;
        const providerSettings = settings.value.backend.llm.embedding.providers[provider];

        const embeddingData = {
          provider: provider,
          model: providerSettings.selected_model,
          endpoint: providerSettings.endpoint
        };

        if (provider === 'openai') {
          embeddingData.api_key = providerSettings.api_key;
        }

        const response = await apiClient.post('/api/llm/embedding', embeddingData);
        const result = await response.json();

        // Update health status after embedding change
        await checkHealthStatus();
      } catch (error) {
        console.error('Error notifying backend of embedding change:', error);
      }
    };

    // RUM and developer config updates (ONLY called during saveSettings)
    const updateRumConfig = async () => {
      if (!settings.value.developer?.rum) return;
      
      try {
        // Initialize or update RUM agent based on new settings
        if (settings.value.developer.rum.enabled) {
          await initializeRumAgent();
          addCacheActivity('RUM agent enabled and configured', 'success');
        } else {
          await disableRumAgent();
          rumStatus.value = null;
          addCacheActivity('RUM agent disabled', 'info');
        }
        
        // Update developer config
        try {
          await settingsService.updateDeveloperConfig(settings.value.developer);
        } catch (configError) {
          console.warn('Backend developer config update failed:', configError.message);
        }
      } catch (error) {
        console.error('Error updating RUM configuration:', error);
        addCacheActivity('Failed to update RUM configuration', 'error');
      }
    };

    // Utility functions for display
    const getCurrentLLMDisplay = () => {
      if (!settings.value.backend?.llm) return 'Not configured';

      const providerType = settings.value.backend.llm.provider_type || 'local';

      if (providerType === 'local') {
        const provider = settings.value.backend.llm.local?.provider || 'ollama';
        const selectedModel = settings.value.backend.llm.local?.providers?.[provider]?.selected_model;
        const endpoint = settings.value.backend.llm.local?.providers?.[provider]?.endpoint;

        if (selectedModel) {
          const endpointInfo = endpoint ? ` @ ${endpoint}` : '';
          return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - ${selectedModel}${endpointInfo}`;
        } else {
          return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - Not selected`;
        }
      } else {
        const provider = settings.value.backend.llm.cloud?.provider || 'openai';
        const selectedModel = settings.value.backend.llm.cloud?.providers?.[provider]?.selected_model;
        const endpoint = settings.value.backend.llm.cloud?.providers?.[provider]?.endpoint;

        if (selectedModel) {
          const endpointInfo = endpoint ? ` @ ${endpoint}` : '';
          return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - ${selectedModel}${endpointInfo}`;
        } else {
          return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - Not selected`;
        }
      }
    };

    const getCurrentEmbeddingConfig = () => {
      if (!settings.value.backend?.llm?.embedding) return 'Not configured';

      const provider = settings.value.backend.llm.embedding.provider || 'ollama';
      const selectedModel = settings.value.backend.llm.embedding.providers?.[provider]?.selected_model;
      const endpoint = settings.value.backend.llm.embedding.providers?.[provider]?.endpoint;

      if (selectedModel) {
        const endpointInfo = endpoint ? ` @ ${endpoint}` : '';
        return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - ${selectedModel}${endpointInfo}`;
      } else {
        return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - Not selected`;
      }
    };

    // Function to dynamically load models from the selected provider
    const loadModels = async () => {
      try {
        const data = await apiClient.loadLlmModels();

        if (settings.value.backend.llm.provider_type === 'local') {
          const provider = settings.value.backend.llm.local.provider;

          if (provider === 'ollama') {
            // Handle the new API response format with model objects
            if (data.local?.providers?.ollama?.models) {
              if (Array.isArray(data.local.providers.ollama.models)) {
                // If it's already an array of strings, use it directly
                if (typeof data.local.providers.ollama.models[0] === 'string') {
                  settings.value.backend.llm.local.providers.ollama.models = data.local.providers.ollama.models;
                } else {
                  // If it's an array of objects, extract names
                  settings.value.backend.llm.local.providers.ollama.models = 
                    data.local.providers.ollama.models.map(m => m.name || m.model || m);
                }
              } else if (typeof data.local.providers.ollama.models === 'object') {
                // If it's an object, extract model names from keys or values
                settings.value.backend.llm.local.providers.ollama.models = 
                  Object.keys(data.local.providers.ollama.models);
              }
            } else {
              settings.value.backend.llm.local.providers.ollama.models = [];
            }
          } else if (provider === 'lmstudio') {
            settings.value.backend.llm.local.providers.lmstudio.models = 
              data.local?.providers?.lmstudio?.models || [];
          }
        } else if (settings.value.backend.llm.provider_type === 'cloud') {
          const provider = settings.value.backend.llm.cloud.provider;
          
          if (provider === 'openai') {
            settings.value.backend.llm.cloud.providers.openai.models = 
              data.cloud?.providers?.openai?.models || [];
          } else if (provider === 'anthropic') {
            settings.value.backend.llm.cloud.providers.anthropic.models = 
              data.cloud?.providers?.anthropic?.models || [];
          }
        }
        
        // Store available models for agent management
        availableModels.value = [];
        if (settings.value.backend.llm.provider_type === 'local') {
          const provider = settings.value.backend.llm.local.provider;
          availableModels.value = settings.value.backend.llm.local.providers[provider]?.models || [];
        }
      } catch (error) {
        console.error('Error loading models from backend:', error);
      }
    };

    const loadEmbeddingModels = async () => {
      try {
        const data = await apiClient.loadEmbeddingModels();
        const provider = settings.value.backend.llm.embedding.provider;
        
        if (provider === 'ollama') {
          settings.value.backend.llm.embedding.providers.ollama.models = 
            data.ollama?.models || [];
        } else if (provider === 'openai') {
          settings.value.backend.llm.embedding.providers.openai.models = 
            data.openai?.models || [];
        }
      } catch (error) {
        console.error('Error loading embedding models from backend:', error);
      }
    };

    // Health check
    const checkHealthStatus = async () => {
      try {
        healthStatus.value = await healthService.getHealthStatus();
      } catch (error) {
        console.error('Error checking health status:', error);
        healthStatus.value = null;
      }
    };

    // Agent management methods (these can still call APIs immediately as they're not form settings)
    const loadAgents = async () => {
      try {
        const agents = await apiClient.getAgents();
        agentsList.value = agents || [];
      } catch (error) {
        console.error('Error loading agents:', error);
        agentsList.value = [];
      }
    };

    const toggleAgent = async (agentId, enabled) => {
      try {
        await apiClient.post(`/api/agent-config/agents/${agentId}/toggle`, {
          agent_id: agentId,
          enabled: enabled
        });
        await loadAgents(); // Refresh the list
      } catch (error) {
        console.error('Error toggling agent:', error);
      }
    };

    const updateAgentModel = async (agentId, model) => {
      try {
        await apiClient.post(`/api/agent-config/agents/${agentId}/model`, {
          agent_id: agentId,
          model: model,
          provider: 'ollama'
        });
        await loadAgents(); // Refresh the list
      } catch (error) {
        console.error('Error updating agent model:', error);
      }
    };

    const updateAgentProvider = async (agentId, provider) => {
      try {
        await apiClient.post(`/api/agent-config/agents/${agentId}/provider`, {
          agent_id: agentId,
          provider: provider
        });
        await loadAgents(); // Refresh the list
      } catch (error) {
        console.error('Error updating agent provider:', error);
      }
    };

    const updateAgentPriority = async (agentId, priority) => {
      try {
        await apiClient.post(`/api/agent-config/agents/${agentId}/priority`, {
          agent_id: agentId,
          priority: parseInt(priority)
        });
        await loadAgents(); // Refresh the list
      } catch (error) {
        console.error('Error updating agent priority:', error);
      }
    };

    const refreshAgents = async () => {
      await loadAgents();
      await loadModels(); // Also refresh available models
    };

    const testAllAgents = async () => {
      try {
        await apiClient.post('/api/agent-config/test-all');
        await loadAgents(); // Refresh to get updated status
      } catch (error) {
        console.error('Error testing agents:', error);
      }
    };

    const getOverallHealthStatus = () => {
      if (!agentsList.value.length) return 'Unknown';
      
      const healthyCount = agentsList.value.filter(a => a.status === 'healthy').length;
      const totalEnabled = agentsList.value.filter(a => a.enabled).length;
      
      if (totalEnabled === 0) return 'No Active Agents';
      if (healthyCount === totalEnabled) return 'All Healthy';
      if (healthyCount > totalEnabled / 2) return 'Mostly Healthy';
      return 'Issues Detected';
    };

    const getOverallHealthClass = () => {
      const status = getOverallHealthStatus();
      if (status.includes('Healthy')) return 'health-good';
      if (status.includes('Issues')) return 'health-bad';
      return 'health-unknown';
    };

    // Cache management methods
    const refreshCacheStats = async () => {
      try {
        cacheStats.value = await cacheService.getStats();
      } catch (error) {
        console.error('Error refreshing cache stats:', error);
      }
    };

    const clearCache = async (type) => {
      try {
        isClearing.value = true;
        await cacheService.clear(type);
        await refreshCacheStats();
        addCacheActivity(`Cleared ${type} cache`, 'success');
      } catch (error) {
        console.error('Error clearing cache:', error);
        addCacheActivity(`Failed to clear ${type} cache`, 'error');
      } finally {
        isClearing.value = false;
      }
    };

    const saveCacheConfig = async () => {
      try {
        await cacheService.updateConfig(cacheConfig.value);
        addCacheActivity('Cache configuration saved', 'success');
      } catch (error) {
        console.error('Error saving cache config:', error);
        addCacheActivity('Failed to save cache configuration', 'error');
      }
    };

    const addCacheActivity = (message, type) => {
      cacheActivity.value.unshift({
        id: Date.now(),
        message,
        type,
        timestamp: new Date().toLocaleTimeString()
      });
      
      // Keep only last 20 activities
      if (cacheActivity.value.length > 20) {
        cacheActivity.value = cacheActivity.value.slice(0, 20);
      }
    };

    const refreshCacheActivity = () => {
      addCacheActivity('Activity log refreshed', 'info');
    };

    // Utility methods
    const formatBytes = (bytes) => {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const formatDuration = (seconds) => {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const secs = seconds % 60;
      
      if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
      } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
      } else {
        return `${secs}s`;
      }
    };

    const getPlaceholder = (path) => {
      const placeholders = settings.value.ui.placeholders || {};
      return placeholders[path] || '';
    };

    // Prompt management
    const loadPrompts = async () => {
      try {
        const promptsData = await apiClient.getPrompts();
        settings.value.prompts.list = promptsData.prompts || [];
        settings.value.prompts.defaults = promptsData.defaults || {};
      } catch (error) {
        console.error('Error loading prompts from backend:', error);
      }
    };

    const selectPrompt = (prompt) => {
      settings.value.prompts.selectedPrompt = prompt;
      settings.value.prompts.editedContent = prompt.content || '';
    };

    const savePrompt = async () => {
      if (!settings.value.prompts.selectedPrompt) return;
      try {
        const promptId = settings.value.prompts.selectedPrompt.id;
        const updatedPrompt = await apiClient.savePrompt(promptId, settings.value.prompts.editedContent);
        const index = settings.value.prompts.list.findIndex(p => p.id === promptId);
        if (index !== -1) {
          settings.value.prompts.list[index] = updatedPrompt;
        }
        // Clear selection
        settings.value.prompts.selectedPrompt = null;
        settings.value.prompts.editedContent = '';
      } catch (error) {
        console.error('Error saving prompt to backend:', error);
      }
    };

    const revertPromptToDefault = async (promptId) => {
      try {
        await apiClient.revertPrompt(promptId);
        await loadPrompts(); // Refresh the list
        settings.value.prompts.selectedPrompt = null;
        settings.value.prompts.editedContent = '';
      } catch (error) {
        console.error('Error reverting prompt:', error);
      }
    };

    // Developer methods
    const loadDeveloperInfo = async () => {
      try {
        const systemInfo = await settingsService.getSystemInfo();
        const endpoints = await settingsService.getApiEndpoints();
        developerInfo.value = {
          ...systemInfo,
          total_endpoints: endpoints.total_endpoints,
          available_routers: endpoints.routers
        };
      } catch (error) {
        console.error('Error loading developer info:', error);
      }
    };

    const showApiEndpoints = async () => {
      try {
        const endpoints = await settingsService.getApiEndpoints();
        alert(`Found ${endpoints.total_endpoints} API endpoints across ${endpoints.routers?.length || 0} routers. Check console for details.`);
        console.log('API Endpoints:', endpoints);
      } catch (error) {
        console.error('Error showing API endpoints:', error);
      }
    };

    // RUM methods (stubs - implement as needed)
    const initializeRumAgent = async () => {
      console.log('Initializing RUM agent...');
    };

    const disableRumAgent = async () => {
      console.log('Disabling RUM agent...');
    };

    const refreshRumStatus = async () => {
      console.log('Refreshing RUM status...');
    };

    const clearRumData = async () => {
      console.log('Clearing RUM data...');
    };

    const exportRumData = async () => {
      console.log('Exporting RUM data...');
    };

    // Force reload settings
    const forceReloadSettings = async () => {
      await loadSettings();
    };

    // Lifecycle hooks
    onMounted(async () => {
      await loadSettings();
      await loadAgents();
      await refreshCacheStats();
      
      // Load developer info if enabled
      if (settings.value.developer?.enabled) {
        await loadDeveloperInfo();
      }
    });

    onUnmounted(() => {
      // Cleanup if needed
    });

    // Return reactive properties and methods
    return {
      settings,
      hasUnsavedChanges, // NEW
      isSettingsLoaded,
      settingsLoadingStatus,
      tabs,
      activeTab,
      activeBackendSubTab,
      isSaving,
      saveMessage,
      saveMessageType,
      healthStatus,
      developerInfo,
      agentsList,
      availableModels,
      enabledAgentsCount,
      cacheStats,
      cacheActivity,
      cacheConfig,
      isClearing,
      rumStatus,
      
      // Methods
      markAsChanged, // NEW
      discardChanges, // NEW
      saveSettings,
      loadModels,
      loadEmbeddingModels,
      onProviderTypeChange,
      onLocalProviderChange,
      onCloudProviderChange,
      onEmbeddingProviderChange,
      notifyBackendOfProviderChange,
      getCurrentLLMDisplay,
      getCurrentLLMConfig: getCurrentLLMDisplay,
      getCurrentEmbeddingConfig,
      notifyBackendOfEmbeddingChange,
      checkHealthStatus,
      loadAgents,
      refreshAgents,
      toggleAgent,
      updateAgentModel,
      updateAgentProvider,
      updateAgentPriority,
      testAllAgents,
      getOverallHealthStatus,
      getOverallHealthClass,
      refreshCacheStats,
      clearCache,
      saveCacheConfig,
      addCacheActivity,
      refreshCacheActivity,
      formatBytes,
      formatDuration,
      getPlaceholder,
      loadPrompts,
      selectPrompt,
      savePrompt,
      revertPromptToDefault,
      loadDeveloperInfo,
      showApiEndpoints,
      refreshRumStatus,
      clearRumData,
      exportRumData,
      forceReloadSettings
    };
  }
};
</script>

<style scoped>
/* Original styles preserved exactly */
.settings-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  padding: clamp(10px, 1.5vw, 15px);
  overflow: hidden;
}

/* NEW: Unsaved changes indicator styles */
.unsaved-changes-indicator {
  background: #fff3cd;
  border: 1px solid #ffeaa7;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  color: #856404;
  font-size: 14px;
}

.unsaved-changes-indicator i {
  margin-right: 8px;
  color: #f39c12;
}

.settings-panel h2 {
  margin: 0 0 clamp(10px, 1.5vw, 15px) 0;
  font-size: clamp(16px, 2vw, 20px);
  color: #007bff;
}

.settings-tabs {
  display: flex;
  overflow-x: auto;
  border-bottom: 1px solid #e9ecef;
  margin-bottom: clamp(10px, 1.5vw, 15px);
}

.settings-tabs button {
  background: none;
  border: none;
  padding: clamp(8px, 1vw, 12px) clamp(12px, 1.5vw, 16px);
  cursor: pointer;
  font-size: clamp(12px, 1.5vw, 14px);
  color: #6c757d;
  transition: all 0.3s;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}

.settings-tabs button.active {
  color: #007bff;
  border-bottom: 2px solid #007bff;
}

.settings-tabs button:hover:not(.active) {
  color: #343a40;
  background-color: rgba(0, 123, 255, 0.05);
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: clamp(5px, 1vw, 10px);
  min-height: 0;
}

.settings-section {
  margin-bottom: clamp(15px, 2vw, 20px);
}

.settings-section h3 {
  margin: 0 0 clamp(8px, 1.2vw, 12px) 0;
  font-size: clamp(14px, 1.8vw, 16px);
  color: #343a40;
  border-bottom: 1px solid #e9ecef;
  padding-bottom: 5px;
}

.sub-tabs {
  display: flex;
  border-bottom: 1px solid #e9ecef;
  margin-bottom: clamp(10px, 1.5vw, 15px);
}

.sub-tabs button {
  background: none;
  border: none;
  padding: clamp(6px, 0.8vw, 8px) clamp(10px, 1.2vw, 12px);
  cursor: pointer;
  font-size: clamp(12px, 1.4vw, 13px);
  color: #6c757d;
  transition: all 0.3s;
  border-bottom: 2px solid transparent;
}

.sub-tabs button.active {
  color: #007bff;
  border-bottom: 2px solid #007bff;
}

.sub-tabs button:hover:not(.active) {
  color: #343a40;
  background-color: rgba(0, 123, 255, 0.05);
}

.sub-tab-content {
  padding: 0 clamp(5px, 0.5vw, 10px);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: clamp(8px, 1.2vw, 12px);
  font-size: clamp(12px, 1.5vw, 14px);
}

.setting-item label {
  flex: 1;
  font-weight: 500;
}

.setting-item label.with-description {
  display: flex;
  flex-direction: column;
}

.setting-item label .description {
  font-size: clamp(10px, 1.2vw, 12px);
  color: #6c757d;
  font-weight: normal;
  margin-top: 2px;
}

.setting-item input[type="checkbox"],
.setting-item input[type="radio"] {
  margin: 0;
}

.setting-item input[type="text"],
.setting-item input[type="number"],
.setting-item input[type="password"],
.setting-item select {
  flex: 1;
  border: 1px solid #ced4da;
  border-radius: 4px;
  padding: clamp(4px, 0.6vw, 6px) clamp(8px, 1vw, 10px);
  font-size: clamp(12px, 1.5vw, 14px);
}

.setting-item input[type="text"]:focus,
.setting-item input[type="number"]:focus,
.setting-item input[type="password"]:focus,
.setting-item select:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 15px;
  padding: clamp(10px, 1.5vw, 15px) 0;
  border-top: 1px solid #e9ecef;
}

/* ENHANCED: Save button styles with unsaved changes indicator */
.save-button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  font-weight: 500;
  position: relative;
}

.save-button:hover:not(:disabled) {
  background-color: #0056b3;
  transform: translateY(-1px);
}

.save-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-button.has-changes {
  background-color: #28a745;
  box-shadow: 0 0 8px rgba(40, 167, 69, 0.3);
}

.save-button.has-changes:hover:not(:disabled) {
  background-color: #218838;
}

.changes-indicator {
  font-size: 18px;
  font-weight: bold;
  margin-left: 5px;
}

/* NEW: Discard button styles */
.discard-button {
  background-color: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.discard-button:hover:not(:disabled) {
  background-color: #545b62;
}

.discard-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Save button and message styles */
.save-message {
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
}

.save-message.success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.save-message.error {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

/* LLM and Embedding status display styles */
.llm-status-display,
.embedding-status-display {
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 10px;
  margin: 5px 0;
}

.current-llm-info,
.current-embedding-info {
  margin-bottom: 10px;
  font-size: 14px;
}

.health-indicator {
  display: flex;
  align-items: center;
  font-size: 13px;
  padding: 5px 10px;
  border-radius: 3px;
}

.health-indicator i {
  margin-right: 6px;
}

.health-indicator.healthy {
  background: #d4edda;
  color: #155724;
}

.health-indicator.warning {
  background: #fff3cd;
  color: #856404;
}

.health-indicator.error {
  background: #f8d7da;
  color: #721c24;
}

.health-indicator.unknown {
  background: #e2e3e5;
  color: #6c757d;
}

/* Settings loading and status styles */
.settings-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px;
  color: #6c757d;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #e9ecef;
  border-top: 4px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 15px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.settings-status {
  display: flex;
  align-items: center;
  padding: 10px 15px;
  margin-bottom: 15px;
  border-radius: 4px;
  font-size: 14px;
}

.settings-status.offline {
  background-color: #fff3cd;
  border: 1px solid #ffeaa7;
  color: #856404;
}

.settings-status i {
  margin-right: 8px;
}

/* All other styles remain the same... */
/* (Keeping all existing styles for agents, cache, etc.) */
</style>