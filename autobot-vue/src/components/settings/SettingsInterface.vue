<template>
  <div class="settings-interface">
    <!-- Header -->
    <div class="settings-header">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200">
        AutoBot Settings
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400">
        Configure AutoBot system settings, preferences, and integrations
      </p>
    </div>

    <!-- Settings Navigation -->
    <div class="settings-nav">
      <div class="nav-tabs">
        <button 
          v-for="tab in settingsTabs" 
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="tabButtonClass(tab.id)"
          class="tab-button"
        >
          <component :is="tab.icon" class="w-4 h-4" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <!-- Settings Content -->
    <div class="settings-content">
      <!-- General Settings -->
      <div v-if="activeTab === 'general'" class="tab-content">
        <div class="settings-section">
          <h3 class="section-title">General Settings</h3>
          <div class="settings-grid">
            <div class="setting-item">
              <label class="setting-label">Theme</label>
              <select class="setting-input">
                <option value="auto">Auto (System)</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </div>
            
            <div class="setting-item">
              <label class="setting-label">Language</label>
              <select class="setting-input">
                <option value="en">English</option>
                <option value="es">Spanish</option>
                <option value="fr">French</option>
              </select>
            </div>

            <div class="setting-item">
              <label class="setting-label">Auto-save Interval (minutes)</label>
              <input type="number" class="setting-input" min="1" max="60" value="5" />
            </div>
          </div>
        </div>
      </div>

      <!-- AI/LLM Settings -->
      <div v-if="activeTab === 'ai'" class="tab-content">
        <div class="settings-section">
          <h3 class="section-title">AI & LLM Configuration</h3>
          <div class="settings-grid">
            <div class="setting-item">
              <label class="setting-label">Default LLM Provider</label>
              <select class="setting-input">
                <option value="ollama">Ollama (Local)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div class="setting-item">
              <label class="setting-label">Response Temperature</label>
              <input type="range" class="setting-slider" min="0" max="2" step="0.1" value="0.7" />
              <span class="slider-value">0.7</span>
            </div>

            <div class="setting-item">
              <label class="setting-label">Max Response Length</label>
              <input type="number" class="setting-input" min="100" max="4000" value="2000" />
            </div>
          </div>
        </div>
      </div>

      <!-- Network Settings -->
      <div v-if="activeTab === 'network'" class="tab-content">
        <div class="settings-section">
          <h3 class="section-title">Network Configuration</h3>
          <div class="settings-grid">
            <div class="setting-item">
              <label class="setting-label">API Timeout (seconds)</label>
              <input type="number" class="setting-input" min="5" max="300" value="30" />
            </div>

            <div class="setting-item">
              <label class="setting-label">Enable Proxy</label>
              <input type="checkbox" class="setting-checkbox" />
            </div>

            <div class="setting-item">
              <label class="setting-label">Max Concurrent Requests</label>
              <input type="number" class="setting-input" min="1" max="20" value="5" />
            </div>
          </div>
        </div>
      </div>

      <!-- Security Settings -->
      <div v-if="activeTab === 'security'" class="tab-content">
        <div class="settings-section">
          <h3 class="section-title">Security & Privacy</h3>
          <div class="settings-grid">
            <div class="setting-item">
              <label class="setting-label">Session Timeout (minutes)</label>
              <input type="number" class="setting-input" min="15" max="480" value="60" />
            </div>

            <div class="setting-item">
              <label class="setting-label">Enable Audit Logging</label>
              <input type="checkbox" class="setting-checkbox" checked />
            </div>

            <div class="setting-item">
              <label class="setting-label">Data Retention (days)</label>
              <input type="number" class="setting-input" min="1" max="365" value="30" />
            </div>
          </div>
        </div>
      </div>

      <!-- Advanced Settings -->
      <div v-if="activeTab === 'advanced'" class="tab-content">
        <div class="settings-section">
          <h3 class="section-title">Advanced Configuration</h3>
          <div class="settings-grid">
            <div class="setting-item">
              <label class="setting-label">Debug Mode</label>
              <input type="checkbox" class="setting-checkbox" />
            </div>

            <div class="setting-item">
              <label class="setting-label">Cache Size (MB)</label>
              <input type="number" class="setting-input" min="50" max="1000" value="200" />
            </div>

            <div class="setting-item">
              <label class="setting-label">Worker Threads</label>
              <input type="number" class="setting-input" min="1" max="16" value="4" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="settings-actions">
      <button class="btn-secondary">Reset to Defaults</button>
      <button class="btn-primary">Save Settings</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { 
  CogIcon,
  CpuChipIcon,
  GlobeAltIcon,
  ShieldCheckIcon,
  WrenchScrewdriverIcon
} from '@heroicons/vue/24/outline'

const activeTab = ref('general')

const settingsTabs = [
  {
    id: 'general',
    label: 'General',
    icon: CogIcon,
    description: 'Basic application settings'
  },
  {
    id: 'ai',
    label: 'AI/LLM',
    icon: CpuChipIcon,
    description: 'AI and language model configuration'
  },
  {
    id: 'network',
    label: 'Network',
    icon: GlobeAltIcon,
    description: 'Network and connectivity settings'
  },
  {
    id: 'security',
    label: 'Security',
    icon: ShieldCheckIcon,
    description: 'Security and privacy settings'
  },
  {
    id: 'advanced',
    label: 'Advanced',
    icon: WrenchScrewdriverIcon,
    description: 'Advanced system configuration'
  }
]

const tabButtonClass = computed(() => (tabId) => {
  const baseClasses = 'flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors font-medium'
  const activeClasses = 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-700'
  const inactiveClasses = 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-800 dark:hover:text-gray-200'
  
  return `${baseClasses} ${activeTab.value === tabId ? activeClasses : inactiveClasses}`
})
</script>

<style scoped>
.settings-interface {
  @apply flex flex-col h-full bg-gray-50 dark:bg-gray-900;
}

.settings-header {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700;
}

.settings-nav {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700;
}

.nav-tabs {
  @apply flex flex-wrap gap-2;
}

.tab-button {
  @apply text-sm border;
}

.settings-content {
  @apply flex-1 overflow-auto p-6;
}

.tab-content {
  @apply space-y-6;
}

.settings-section {
  @apply bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700;
}

.section-title {
  @apply text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4;
}

.settings-grid {
  @apply grid grid-cols-1 md:grid-cols-2 gap-4;
}

.setting-item {
  @apply space-y-2;
}

.setting-label {
  @apply block text-sm font-medium text-gray-700 dark:text-gray-300;
}

.setting-input {
  @apply w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100;
}

.setting-slider {
  @apply w-full;
}

.slider-value {
  @apply text-sm text-gray-600 dark:text-gray-400 ml-2;
}

.setting-checkbox {
  @apply rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500;
}

.settings-actions {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 flex justify-end space-x-3;
}

.btn-primary {
  @apply px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors;
}

.btn-secondary {
  @apply px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 text-gray-800 dark:text-gray-200 rounded-lg font-medium transition-colors;
}

/* Responsive design */
@media (max-width: 768px) {
  .nav-tabs {
    @apply grid grid-cols-2 gap-2;
  }
  
  .tab-button {
    @apply text-xs px-2 py-1;
  }
  
  .tab-button span {
    @apply hidden sm:inline;
  }

  .settings-grid {
    @apply grid-cols-1;
  }
}
</style>