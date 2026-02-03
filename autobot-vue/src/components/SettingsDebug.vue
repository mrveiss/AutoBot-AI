<template>
  <div class="settings-debug">
    <h1>Settings Debug Component</h1>
    <div class="debug-info">
      <h2>Component Loading Test</h2>
      <p>✅ This component is loading correctly</p>
      
      <h3>Error State Check</h3>
      <div v-if="hasError" class="error">
        <p>❌ Error detected: {{ errorMessage }}</p>
      </div>
      <div v-else class="success">
        <p>✅ No errors detected</p>
      </div>
      
      <h3>Store Status</h3>
      <p>App Store: {{ appStoreStatus }}</p>
      
      <h3>Service Status</h3>
      <p>Settings Service: {{ settingsServiceStatus }}</p>
      <p>Health Service: {{ healthServiceStatus }}</p>
      <p>Cache Service: {{ cacheServiceStatus }}</p>
      
      <h3>Route Information</h3>
      <p>Current Route: {{ $route?.path }}</p>
      <p>Route Name: {{ $route?.name }}</p>
      <p>Matched Components: {{ $route?.matched?.length || 0 }}</p>
      
      <button @click="testSettingsPanel" class="test-button">
        Test Load SettingsPanel Component
      </button>
      
      <div v-if="settingsPanelError" class="error">
        <h4>SettingsPanel Error:</h4>
        <pre>{{ settingsPanelError }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/useAppStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsDebug')

const hasError = ref(false)
const errorMessage = ref('')
const appStoreStatus = ref('Unknown')
const settingsServiceStatus = ref('Unknown')
const healthServiceStatus = ref('Unknown')
const cacheServiceStatus = ref('Unknown')
const settingsPanelError = ref(null)

onMounted(async () => {
  try {
    // Test app store
    const appStore = useAppStore()
    appStoreStatus.value = appStore ? 'Available' : 'Not Available'
    
    // Test services
    try {
      const { settingsService } = await import('@/services/SettingsService.js')
      settingsServiceStatus.value = settingsService ? 'Available' : 'Not Available'
    } catch (error) {
      settingsServiceStatus.value = `Error: ${error.message}`
    }
    
    try {
      const { healthService } = await import('@/services/HealthService.js')
      healthServiceStatus.value = healthService ? 'Available' : 'Not Available'
    } catch (error) {
      healthServiceStatus.value = `Error: ${error.message}`
    }
    
    try {
      const cacheService = await import('@/services/CacheService.js')
      cacheServiceStatus.value = cacheService ? 'Available' : 'Not Available'
    } catch (error) {
      cacheServiceStatus.value = `Error: ${error.message}`
    }
    
  } catch (error) {
    hasError.value = true
    errorMessage.value = error.message
  }
})

const testSettingsPanel = async () => {
  try {
    settingsPanelError.value = null
    
    const SettingsPanel = await import('@/components/SettingsPanel.vue')
    
  } catch (error) {
    logger.error('SettingsPanel import failed:', error)
    settingsPanelError.value = error.message + '\n' + error.stack
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.settings-debug {
  padding: var(--spacing-5);
  font-family: var(--font-mono);
}

.debug-info {
  background: var(--bg-tertiary);
  padding: var(--spacing-4);
  border-radius: var(--radius-md);
  margin: var(--spacing-2-5) 0;
}

.error {
  background: var(--color-error-bg);
  color: var(--color-error-dark, #c62828);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-sm);
  margin: var(--spacing-1) 0;
}

.success {
  background: var(--color-success-bg);
  color: var(--color-success-dark, #2e7d32);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-sm);
  margin: var(--spacing-1) 0;
}

.test-button {
  background: var(--color-info);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-2-5) var(--spacing-5);
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin: var(--spacing-2-5) 0;
}

.test-button:hover {
  background: var(--color-info-hover);
}

pre {
  background: var(--bg-tertiary);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  white-space: pre-wrap;
}
</style>