<template>
  <div class="settings-panel">
    <h2>Settings</h2>
    <div class="settings-tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>
    <div class="settings-content">
      <!-- Chat Settings -->
      <div v-if="activeTab === 'chat'" class="settings-section">
        <h3>Chat Settings</h3>
        <div class="setting-item">
          <label>Auto Scroll to Bottom</label>
          <input type="checkbox" v-model="settings.chat.auto_scroll" />
        </div>
        <div class="setting-item">
          <label>Max Messages</label>
          <input type="number" v-model="settings.chat.max_messages" min="10" max="1000" />
        </div>
        <div class="setting-item">
          <label>Message Retention (Days)</label>
          <input type="number" v-model="settings.chat.message_retention_days" min="1" max="365" />
        </div>
        <div v-if="activeBackendSubTab === 'memory'" class="sub-tab-content">
          <h3>Memory Settings</h3>
          <div class="setting-item">
            <label>Enable Long-Term Memory</label>
            <input type="checkbox" v-model="settings.memory.long_term.enabled" />
          </div>
          <div class="setting-item">
            <label>Long-Term Memory Retention (Days)</label>
            <input type="number" v-model="settings.memory.long_term.retention_days" min="1" max="365" :disabled="!settings.memory.long_term.enabled" />
          </div>
          <div class="setting-item">
            <label>Enable Short-Term Memory</label>
            <input type="checkbox" v-model="settings.memory.short_term.enabled" />
          </div>
          <div class="setting-item">
            <label>Short-Term Memory Duration (Minutes)</label>
            <input type="number" v-model="settings.memory.short_term.duration_minutes" min="1" max="1440" :disabled="!settings.memory.short_term.enabled" />
          </div>
          <div class="setting-item">
            <label>Enable Vector Storage</label>
            <input type="checkbox" v-model="settings.memory.vector_storage.enabled" />
          </div>
          <div class="setting-item">
            <label>Vector Storage Update Frequency (Days)</label>
            <input type="number" v-model="settings.memory.vector_storage.update_frequency_days" min="1" max="30" :disabled="!settings.memory.vector_storage.enabled" />
          </div>
          <div class="setting-item">
            <label>Enable ChromaDB</label>
            <input type="checkbox" v-model="settings.memory.chromadb.enabled" />
          </div>
          <div class="setting-item">
            <label>ChromaDB Path</label>
            <input type="text" v-model="settings.memory.chromadb.path" :disabled="!settings.memory.chromadb.enabled" placeholder="data/chromadb/chroma.sqlite3" />
          </div>
          <div class="setting-item">
            <label>ChromaDB Collection Name</label>
            <input type="text" v-model="settings.memory.chromadb.collection_name" :disabled="!settings.memory.chromadb.enabled" placeholder="autobot_memory" />
          </div>
          <div class="setting-item">
            <label>Enable Redis for Chat History</label>
            <input type="checkbox" v-model="settings.memory.redis.enabled" />
          </div>
          <div class="setting-item">
            <label>Redis Host</label>
            <input type="text" v-model="settings.memory.redis.host" :disabled="!settings.memory.redis.enabled" placeholder="localhost" />
          </div>
          <div class="setting-item">
            <label>Redis Port</label>
            <input type="number" v-model="settings.memory.redis.port" min="1" max="65535" :disabled="!settings.memory.redis.enabled" placeholder="6379" />
          </div>
        </div>
      </div>

      <!-- Backend Settings -->
      <div v-if="activeTab === 'backend'" class="settings-section">
        <div class="sub-tabs">
          <button 
            :class="{ active: activeBackendSubTab === 'general' }"
            @click="activeBackendSubTab = 'general'"
          >
            General
          </button>
          <button 
            :class="{ active: activeBackendSubTab === 'llm' }"
            @click="activeBackendSubTab = 'llm'"
          >
            LLM
          </button>
          <button 
            :class="{ active: activeBackendSubTab === 'memory' }"
            @click="activeBackendSubTab = 'memory'"
          >
            Memory
          </button>
        </div>
        <div v-if="activeBackendSubTab === 'general'" class="sub-tab-content">
          <h3>Backend General Settings</h3>
          <div class="setting-item">
            <label>API Endpoint</label>
            <input type="text" v-model="settings.backend.api_endpoint" />
          </div>
          <div class="setting-item">
            <label>Server Host</label>
            <input type="text" v-model="settings.backend.server_host" />
          </div>
          <div class="setting-item">
            <label>Server Port</label>
            <input type="number" v-model="settings.backend.server_port" min="1" max="65535" />
          </div>
          <div class="setting-item">
            <label>Chat Data Directory</label>
            <input type="text" v-model="settings.backend.chat_data_dir" />
          </div>
          <div class="setting-item">
            <label>Chat History File</label>
            <input type="text" v-model="settings.backend.chat_history_file" placeholder="data/chat_history.json" />
          </div>
          <div class="setting-item">
            <label>Knowledge Base DB</label>
            <input type="text" v-model="settings.backend.knowledge_base_db" placeholder="data/knowledge_base.db" />
          </div>
          <div class="setting-item">
            <label>Reliability Stats File</label>
            <input type="text" v-model="settings.backend.reliability_stats_file" placeholder="data/reliability_stats.json" />
          </div>
          <div class="setting-item">
            <label>Audit Log File</label>
            <input type="text" v-model="settings.backend.audit_log_file" placeholder="data/audit.log" />
          </div>
          <div class="setting-item">
            <label>CORS Origins (comma separated)</label>
            <input type="text" v-model="corsOriginsString" />
          </div>
        </div>
        <div v-if="activeBackendSubTab === 'llm'" class="sub-tab-content">
          <h3>LLM Settings</h3>
          <div class="setting-item">
            <label>Ollama Endpoint</label>
            <input type="text" v-model="settings.backend.ollama_endpoint" />
          </div>
          <div class="setting-item">
            <label>Model</label>
            <input type="text" v-model="settings.backend.ollama_model" />
          </div>
          <div class="setting-item">
            <label>Timeout (seconds)</label>
            <input type="number" v-model="settings.backend.timeout" min="10" max="300" />
          </div>
          <div class="setting-item">
            <label>Max Retries</label>
            <input type="number" v-model="settings.backend.max_retries" min="1" max="10" />
          </div>
          <div class="setting-item">
            <label>Enable Streaming</label>
            <input type="checkbox" v-model="settings.backend.streaming" />
          </div>
        </div>
      </div>

      <!-- UI Settings -->
      <div v-if="activeTab === 'ui'" class="settings-section">
        <h3>UI Settings</h3>
        <div class="setting-item">
          <label>Theme</label>
          <select v-model="settings.ui.theme">
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Font Size</label>
          <select v-model="settings.ui.font_size">
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Language</label>
          <select v-model="settings.ui.language">
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Enable Animations</label>
          <input type="checkbox" v-model="settings.ui.animations" />
        </div>
        <div class="setting-item">
          <label>Vue Developer Mode</label>
          <input type="checkbox" v-model="settings.ui.developer_mode" />
        </div>
      </div>

      <!-- Security Settings -->
      <div v-if="activeTab === 'security'" class="settings-section">
        <h3>Security Settings</h3>
        <div class="setting-item">
          <label>Enable Encryption</label>
          <input type="checkbox" v-model="settings.security.enable_encryption" />
        </div>
        <div class="setting-item">
          <label>Session Timeout (Minutes)</label>
          <input type="number" v-model="settings.security.session_timeout_minutes" min="1" max="1440" />
        </div>
      </div>

      <!-- Logging Settings -->
      <div v-if="activeTab === 'logging'" class="settings-section">
        <h3>Logging Settings</h3>
        <div class="setting-item">
          <label>Log Level</label>
          <select v-model="settings.logging.log_level">
            <option value="debug">Debug</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Log to File</label>
          <input type="checkbox" v-model="settings.logging.log_to_file" />
        </div>
        <div class="setting-item">
          <label>Log File Path</label>
          <input type="text" v-model="settings.logging.log_file_path" :disabled="!settings.logging.log_to_file" />
        </div>
      </div>

      <!-- Knowledge Base Settings -->
      <div v-if="activeTab === 'knowledgeBase'" class="settings-section">
        <h3>Knowledge Base</h3>
        <div class="setting-item">
          <label>Enable Knowledge Base</label>
          <input type="checkbox" v-model="settings.knowledge_base.enabled" />
        </div>
        <div class="setting-item">
          <label>Update Frequency (Days)</label>
          <input type="number" v-model="settings.knowledge_base.update_frequency_days" min="1" max="30" :disabled="!settings.knowledge_base.enabled" />
        </div>
      </div>

      <!-- Voice Interface Settings -->
      <div v-if="activeTab === 'voiceInterface'" class="settings-section">
        <h3>Voice Interface</h3>
        <div class="setting-item">
          <label>Enable Voice Interface</label>
          <input type="checkbox" v-model="settings.voice_interface.enabled" />
        </div>
        <div class="setting-item">
          <label>Voice</label>
          <select v-model="settings.voice_interface.voice" :disabled="!settings.voice_interface.enabled">
            <option value="default">Default</option>
            <option value="male1">Male 1</option>
            <option value="female1">Female 1</option>
          </select>
        </div>
        <div class="setting-item">
          <label>Speech Rate</label>
          <input type="number" v-model="settings.voice_interface.speech_rate" min="0.5" max="2.0" step="0.1" :disabled="!settings.voice_interface.enabled" />
        </div>
      </div>

      
      <!-- System Prompts Settings -->
      <div v-if="activeTab === 'prompts'" class="settings-section">
        <h3>System Prompts</h3>
        <div class="prompts-container">
          <div class="prompts-list">
            <div v-for="prompt in settings.prompts.list" :key="prompt.id" class="prompt-item" :class="{ 'active': settings.prompts.selectedPrompt && settings.prompts.selectedPrompt.id === prompt.id }" @click="selectPrompt(prompt)">
              <div class="prompt-name">{{ prompt.name || prompt.id }}</div>
              <div class="prompt-type">{{ prompt.type || 'Unknown Type' }}</div>
            </div>
            <div v-if="settings.prompts.list.length === 0" class="no-prompts">No prompts available. Please check backend connection.</div>
          </div>
          <div class="prompt-editor" v-if="settings.prompts.selectedPrompt">
            <h4>Editing: {{ settings.prompts.selectedPrompt.name || settings.prompts.selectedPrompt.id }}</h4>
            <textarea v-model="settings.prompts.editedContent" rows="10" placeholder="Edit prompt content here..."></textarea>
            <div class="editor-actions">
              <button @click="savePrompt">Save Changes</button>
              <button @click="revertPromptToDefault(settings.prompts.selectedPrompt.id)">Revert to Default</button>
              <button @click="settings.prompts.selectedPrompt = null">Cancel</button>
            </div>
          </div>
        </div>
        <div class="setting-item">
          <button class="control-button small" @click="loadPrompts">Load Prompts</button>
        </div>
      </div>
    </div>
    <div class="settings-actions">
      <button @click="saveSettings">Save Settings</button>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue';

export default {
  name: 'SettingsPanel',
  setup() {
    // Define tabs for settings organization
    const tabs = [
      { id: 'chat', label: 'Chat' },
      { id: 'backend', label: 'Backend' },
      { id: 'ui', label: 'UI' },
      { id: 'security', label: 'Security' },
      { id: 'logging', label: 'Logging' },
      { id: 'knowledgeBase', label: 'Knowledge Base' },
      { id: 'voiceInterface', label: 'Voice Interface' },
      { id: 'prompts', label: 'System Prompts' }
    ];
    const activeTab = ref('chat');
    const activeBackendSubTab = ref('general');

    // Settings structure to match a comprehensive config file
    const settings = ref({
      message_display: {
        show_thoughts: true,
        show_json: false,
        show_utility: false,
        show_planning: true,
        show_debug: false
      },
      chat: {
        auto_scroll: true,
        max_messages: 100,
        message_retention_days: 30
      },
      backend: {
        api_endpoint: 'http://localhost:8001',
        ollama_endpoint: 'http://localhost:11434/api/generate',
        ollama_model: 'llama2',
        server_host: '0.0.0.0',
        server_port: 8001,
        chat_data_dir: 'data/chats',
        chat_history_file: 'data/chat_history.json',
        knowledge_base_db: 'data/knowledge_base.db',
        reliability_stats_file: 'data/reliability_stats.json',
        audit_log_file: 'data/audit.log',
        cors_origins: [
          'http://localhost',
          'http://localhost:5173',
          'http://127.0.0.1:5173'
        ],
        timeout: 60,
        max_retries: 3,
        streaming: false
      },
      ui: {
        theme: 'light',
        font_size: 'medium',
        language: 'en',
        animations: true,
        developer_mode: false
      },
      security: {
        enable_encryption: false,
        session_timeout_minutes: 30
      },
      logging: {
        log_level: 'info',
        log_to_file: false,
        log_file_path: '/var/log/autobot.log'
      },
      knowledge_base: {
        enabled: true,
        update_frequency_days: 7
      },
      voice_interface: {
        enabled: false,
        voice: 'default',
        speech_rate: 1.0
      },
      memory: {
        long_term: {
          enabled: true,
          retention_days: 30
        },
        short_term: {
          enabled: true,
          duration_minutes: 30
        },
        vector_storage: {
          enabled: true,
          update_frequency_days: 7
        }
      },
      prompts: {
        list: [],
        selectedPrompt: null,
        editedContent: '',
        defaults: {}
      }
    });

    // Computed property for CORS origins as a string for input field
    const corsOriginsString = computed({
      get() {
        return settings.value.backend.cors_origins.join(', ');
      },
      set(value) {
        settings.value.backend.cors_origins = value.split(',').map(origin => origin.trim()).filter(origin => origin);
      }
    });

    onMounted(async () => {
      // Load settings from backend first, then local storage
      await loadSettingsFromBackend();
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        try {
          const parsedSettings = JSON.parse(savedSettings);
          // Merge with defaults to ensure all properties exist, prioritizing backend then local storage
          settings.value = deepMerge(deepMerge(defaultSettings(), settings.value), parsedSettings);
        } catch (e) {
          console.error('Error parsing saved settings:', e);
        }
      }
    });

    // Function to deep merge objects
    const deepMerge = (target, source) => {
      const output = { ...target };
      for (const key in source) {
        if (source.hasOwnProperty(key)) {
          if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
            output[key] = deepMerge(target[key] || {}, source[key]);
          } else {
            output[key] = source[key];
          }
        }
      }
      return output;
    };

    // Default settings structure
    const defaultSettings = () => ({
      message_display: {
        show_thoughts: true,
        show_json: false,
        show_utility: false,
        show_planning: true,
        show_debug: true  // Enabled by default for developer mode
      },
      chat: {
        auto_scroll: true,
        max_messages: 100,
        message_retention_days: 30
      },
      backend: {
        api_endpoint: 'http://localhost:8001',
        ollama_endpoint: 'http://localhost:11434/api/generate',
        ollama_model: 'llama2',
        server_host: '0.0.0.0',
        server_port: 8001,
        chat_data_dir: 'data/chats',
        chat_history_file: 'data/chat_history.json',
        knowledge_base_db: 'data/knowledge_base.db',
        reliability_stats_file: 'data/reliability_stats.json',
        audit_log_file: 'data/audit.log',
        cors_origins: [
          'http://localhost',
          'http://localhost:5173',
          'http://127.0.0.1:5173',
          'http://localhost:8080',
          'http://127.0.0.1:8080'
        ],
        timeout: 60,
        max_retries: 3,
        streaming: false
      },
      ui: {
        theme: 'light',
        font_size: 'medium',
        language: 'en',
        animations: true,
        developer_mode: false
      },
      security: {
        enable_encryption: false,
        session_timeout_minutes: 30
      },
      logging: {
        log_level: 'debug',  // Set to debug by default for developer mode
        log_to_file: false,
        log_file_path: '/var/log/autobot.log'
      },
      knowledge_base: {
        enabled: true,
        update_frequency_days: 7
      },
      voice_interface: {
        enabled: false,
        voice: 'default',
        speech_rate: 1.0
      },
      memory: {
        long_term: {
          enabled: true,
          retention_days: 30
        },
        short_term: {
          enabled: true,
          duration_minutes: 30
        },
        vector_storage: {
          enabled: true,
          update_frequency_days: 7
        }
      },
      prompts: {
        list: [],
        selectedPrompt: null,
        editedContent: '',
        defaults: {}
      }
    });

    // Function to load settings from backend
    const loadSettingsFromBackend = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings`);
        if (response.ok) {
          const backendSettings = await response.json();
          // Merge backend settings with local defaults to ensure all properties exist
          const mergedSettings = deepMerge(defaultSettings(), backendSettings);
          // Ensure memory settings are included even if not in backend data
          if (!mergedSettings.memory) {
            mergedSettings.memory = defaultSettings().memory;
          }
          settings.value = mergedSettings;
          // Save to local storage as well
          localStorage.setItem('chat_settings', JSON.stringify(settings.value));
        } else {
          console.error('Failed to load settings from backend:', response.statusText);
        }
      } catch (error) {
        console.error('Error loading settings from backend:', error);
      }
      // Load prompts after settings are loaded
      await loadPrompts();
    };

    // Function to save settings to local storage and backend
    const saveSettings = async () => {
      // Ensure memory settings are included in the saved data
      localStorage.setItem('chat_settings', JSON.stringify(settings.value));
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: settings.value })
        });
        if (!response.ok) {
          console.error('Failed to save settings to backend:', response.statusText);
        } else {
          console.log('Settings, including memory configurations, saved successfully to backend.');
        }
      } catch (error) {
        console.error('Error saving settings to backend:', error);
      }
    };

    // Watch for changes in settings and save them to local storage
    watch(settings, () => {
      localStorage.setItem('chat_settings', JSON.stringify(settings.value));
    }, { deep: true });

    // Function to load prompts from backend
    const loadPrompts = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts`);
        if (response.ok) {
          const promptsData = await response.json();
          settings.value.prompts.list = promptsData.prompts || [];
          settings.value.prompts.defaults = promptsData.defaults || {};
        } else {
          console.error('Failed to load prompts from backend:', response.statusText);
        }
      } catch (error) {
        console.error('Error loading prompts from backend:', error);
      }
    };

    // Function to select a prompt for editing
    const selectPrompt = (prompt) => {
      settings.value.prompts.selectedPrompt = prompt;
      settings.value.prompts.editedContent = prompt.content || '';
    };

    // Function to save edited prompt content
    const savePrompt = async () => {
      if (!settings.value.prompts.selectedPrompt) return;
      try {
        const promptId = settings.value.prompts.selectedPrompt.id;
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts/${promptId}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ content: settings.value.prompts.editedContent })
        });
        if (response.ok) {
          // Update the prompt in the list
          const updatedPrompt = await response.json();
          const index = settings.value.prompts.list.findIndex(p => p.id === promptId);
          if (index !== -1) {
            settings.value.prompts.list[index] = updatedPrompt;
          }
          // Clear selection
          settings.value.prompts.selectedPrompt = null;
          settings.value.prompts.editedContent = '';
        } else {
          console.error('Failed to save prompt to backend:', response.statusText);
        }
      } catch (error) {
        console.error('Error saving prompt to backend:', error);
      }
    };

    // Function to revert a prompt to default
    const revertPromptToDefault = async (promptId) => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts/${promptId}/revert`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Update the prompt in the list
          const updatedPrompt = await response.json();
          const index = settings.value.prompts.list.findIndex(p => p.id === promptId);
          if (index !== -1) {
            settings.value.prompts.list[index] = updatedPrompt;
          }
          // If this prompt was selected, update the editor
          if (settings.value.prompts.selectedPrompt && settings.value.prompts.selectedPrompt.id === promptId) {
            settings.value.prompts.selectedPrompt = updatedPrompt;
            settings.value.prompts.editedContent = updatedPrompt.content || '';
          }
        } else {
          console.error('Failed to revert prompt to default:', response.statusText);
        }
      } catch (error) {
        console.error('Error reverting prompt to default:', error);
      }
    };

    return {
      settings,
      saveSettings,
      tabs,
      activeTab,
      activeBackendSubTab,
      corsOriginsString,
      selectPrompt,
      savePrompt,
      revertPromptToDefault
    };
  }
};
</script>

<style scoped>
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

.prompts-container {
  display: flex;
  gap: clamp(10px, 1.5vw, 15px);
  height: 400px;
}

.prompts-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: clamp(5px, 0.8vw, 8px);
}

.prompt-item {
  padding: clamp(8px, 1vw, 10px);
  cursor: pointer;
  border-radius: 3px;
  margin-bottom: clamp(3px, 0.5vw, 5px);
  transition: background-color 0.2s;
}

.prompt-item:hover {
  background-color: #e9ecef;
}

.prompt-item.active {
  background-color: #007bff;
  color: white;
}

.prompt-name {
  font-size: clamp(12px, 1.5vw, 14px);
  font-weight: 500;
}

.prompt-type {
  font-size: clamp(10px, 1.2vw, 12px);
  opacity: 0.8;
}

.no-prompts {
  text-align: center;
  color: #6c757d;
  font-style: italic;
  padding: clamp(10px, 1.5vw, 15px);
}

.prompt-editor {
  flex: 2;
  display: flex;
  flex-direction: column;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: clamp(8px, 1vw, 10px);
}

.prompt-editor h4 {
  margin: 0 0 clamp(8px, 1vw, 10px) 0;
  font-size: clamp(14px, 1.6vw, 16px);
  color: #343a40;
}

.prompt-editor textarea {
  flex: 1;
  border: 1px solid #ced4da;
  border-radius: 4px;
  padding: clamp(5px, 0.8vw, 8px);
  font-size: clamp(12px, 1.4vw, 13px);
  resize: none;
  font-family: 'Courier New', Courier, monospace;
}

.prompt-editor textarea:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: clamp(5px, 0.8vw, 8px);
  margin-top: clamp(8px, 1vw, 10px);
}

.editor-actions button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: clamp(5px, 0.6vw, 6px) clamp(10px, 1.2vw, 12px);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-size: clamp(12px, 1.4vw, 13px);
}

.editor-actions button:hover {
  background-color: #0056b3;
}

.editor-actions button:nth-child(2) {
  background-color: #6c757d;
}

.editor-actions button:nth-child(2):hover {
  background-color: #5a6268;
}

.editor-actions button:nth-child(3) {
  background-color: #dc3545;
}

.editor-actions button:nth-child(3):hover {
  background-color: #c82333;
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

.setting-item input[type="checkbox"],
.setting-item input[type="radio"] {
  margin: 0;
}

.setting-item input[type="text"],
.setting-item input[type="number"],
.setting-item select {
  flex: 1;
  border: 1px solid #ced4da;
  border-radius: 4px;
  padding: clamp(4px, 0.6vw, 6px) clamp(8px, 1vw, 10px);
  font-size: clamp(12px, 1.5vw, 14px);
}

.setting-item input[type="text"]:focus,
.setting-item input[type="number"]:focus,
.setting-item select:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  padding: clamp(10px, 1.5vw, 15px) 0;
  border-top: 1px solid #e9ecef;
}

.settings-actions button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: clamp(6px, 0.8vw, 8px) clamp(12px, 1.5vw, 16px);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-size: clamp(12px, 1.5vw, 14px);
}

.settings-actions button:hover {
  background-color: #0056b3;
}
</style>
