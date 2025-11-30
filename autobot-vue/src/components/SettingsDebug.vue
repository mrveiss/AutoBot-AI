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
.settings-debug {
  padding: 20px;
  font-family: monospace;
}

.debug-info {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 5px;
  margin: 10px 0;
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 10px;
  border-radius: 4px;
  margin: 5px 0;
}

.success {
  background: #e8f5e8;
  color: #2e7d32;
  padding: 10px;
  border-radius: 4px;
  margin: 5px 0;
}

.test-button {
  background: #2196f3;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  margin: 10px 0;
}

.test-button:hover {
  background: #1976d2;
}

pre {
  background: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
}
</style>