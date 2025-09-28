<template>
  <div class="async-error-demo">
    <div class="demo-header">
      <h2 class="demo-title">Async Component Error Boundary Demo</h2>
      <p class="demo-description">
        Test different async component failure scenarios and observe the error boundaries in action.
      </p>
    </div>

    <div class="demo-controls">
      <h3>Test Scenarios</h3>
      <div class="scenario-buttons">
        <button
          v-for="scenario in scenarios"
          :key="scenario.id"
          @click="loadScenario(scenario)"
          :class="['scenario-btn', { active: currentScenario?.id === scenario.id }]"
          :disabled="loading"
        >
          <i :class="scenario.icon"></i>
          {{ scenario.name }}
        </button>
      </div>
    </div>

    <div class="demo-content">
      <div class="scenario-info" v-if="currentScenario">
        <h4>{{ currentScenario.name }}</h4>
        <p>{{ currentScenario.description }}</p>
        <div class="expected-behavior">
          <strong>Expected Behavior:</strong> {{ currentScenario.expectedBehavior }}
        </div>
      </div>

      <div class="component-container">
        <component
          v-if="currentComponent"
          :is="currentComponent"
          :key="componentKey"
          @error="handleComponentError"
          @loaded="handleComponentLoaded"
          @retry="handleComponentRetry"
        />
        <div v-else class="no-scenario">
          <i class="fas fa-play"></i>
          <p>Select a scenario above to test async component error boundaries</p>
        </div>
      </div>
    </div>

    <div class="demo-stats">
      <h3>Error Boundary Statistics</h3>
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">Total Errors:</span>
          <span class="stat-value">{{ stats.totalErrors }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Retry Attempts:</span>
          <span class="stat-value">{{ stats.retryAttempts }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Successful Loads:</span>
          <span class="stat-value">{{ stats.successfulLoads }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Average Load Time:</span>
          <span class="stat-value">{{ stats.averageLoadTime }}ms</span>
        </div>
      </div>

      <div class="error-recovery-stats">
        <h4>Error Recovery Status</h4>
        <pre>{{ JSON.stringify(errorRecoveryStats, null, 2) }}</pre>
      </div>
    </div>

    <div class="demo-logs">
      <h3>Event Log</h3>
      <div class="log-container">
        <div
          v-for="(log, index) in logs"
          :key="index"
          :class="['log-entry', `log-${log.type}`]"
        >
          <span class="log-timestamp">{{ log.timestamp }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
      <button @click="clearLogs" class="clear-logs-btn">Clear Logs</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { createAsyncComponent, createLazyComponent, AsyncComponentErrorRecovery } from '@/utils/asyncComponentHelpers'

const loading = ref(false)
const currentScenario = ref(null)
const currentComponent = ref(null)
const componentKey = ref(0)
const logs = ref([])

const stats = ref({
  totalErrors: 0,
  retryAttempts: 0,
  successfulLoads: 0,
  averageLoadTime: 0,
  loadTimes: []
})

const errorRecoveryStats = computed(() => {
  return AsyncComponentErrorRecovery.getStats()
})

const scenarios = [
  {
    id: 'chunk-loading-failure',
    name: 'Chunk Loading Failure',
    icon: 'fas fa-exclamation-triangle',
    description: 'Simulates a chunk loading failure as would happen with network issues or outdated cached files.',
    expectedBehavior: 'Should show AsyncErrorFallback with user-friendly message and retry options.',
    createComponent: () => createLazyComponent(
      () => Promise.reject(new Error('Loading chunk 456 failed.')),
      'ChunkFailureDemo'
    )
  },
  {
    id: 'network-timeout',
    name: 'Network Timeout',
    icon: 'fas fa-clock',
    description: 'Simulates a network timeout during component loading.',
    expectedBehavior: 'Should show timeout message and offer retry with exponential backoff.',
    createComponent: () => createAsyncComponent(
      () => new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Request timeout')), 100)
      }),
      {
        name: 'TimeoutDemo',
        timeout: 200,
        maxRetries: 2
      }
    )
  },
  {
    id: 'network-error',
    name: 'Network Error',
    icon: 'fas fa-wifi',
    description: 'Simulates a network connectivity error.',
    expectedBehavior: 'Should show network error message and provide retry options.',
    createComponent: () => createAsyncComponent(
      () => Promise.reject(new Error('Failed to fetch')),
      {
        name: 'NetworkErrorDemo',
        maxRetries: 3
      }
    )
  },
  {
    id: 'intermittent-failure',
    name: 'Intermittent Failure',
    icon: 'fas fa-random',
    description: 'Fails twice then succeeds to test retry logic.',
    expectedBehavior: 'Should retry automatically and eventually load successfully.',
    createComponent: () => {
      let attempts = 0
      return createAsyncComponent(
        () => {
          attempts++
          if (attempts < 3) {
            return Promise.reject(new Error(`Intermittent failure (attempt ${attempts})`))
          }
          return Promise.resolve({
            template: '<div class="success-component">✅ Success after retries!</div>'
          })
        },
        {
          name: 'IntermittentDemo',
          maxRetries: 5,
          retryDelay: 500
        }
      )
    }
  },
  {
    id: 'slow-loading',
    name: 'Slow Loading',
    icon: 'fas fa-hourglass-half',
    description: 'Takes a long time to load to test loading states.',
    expectedBehavior: 'Should show animated loading state with progress indicator.',
    createComponent: () => createAsyncComponent(
      () => new Promise(resolve => {
        setTimeout(() => {
          resolve({
            template: '<div class="success-component">🚀 Loaded after delay!</div>'
          })
        }, 3000)
      }),
      {
        name: 'SlowLoadingDemo',
        timeout: 5000,
        loadingMessage: 'This component is taking a while to load...'
      }
    )
  },
  {
    id: 'css-chunk-failure',
    name: 'CSS Chunk Failure',
    icon: 'fas fa-paint-brush',
    description: 'Simulates CSS chunk loading failure.',
    expectedBehavior: 'Should show styling-related error message and reload option.',
    createComponent: () => createLazyComponent(
      () => Promise.reject(new Error('Loading CSS chunk styles.css failed.')),
      'CSSChunkFailureDemo'
    )
  },
  {
    id: 'module-not-found',
    name: 'Module Not Found',
    icon: 'fas fa-question-circle',
    description: 'Simulates missing module error.',
    expectedBehavior: 'Should show module error and suggest page refresh.',
    createComponent: () => createLazyComponent(
      () => Promise.reject(new Error('Module not found: ./NonexistentComponent.vue')),
      'ModuleNotFoundDemo'
    )
  },
  {
    id: 'successful-load',
    name: 'Successful Load',
    icon: 'fas fa-check-circle',
    description: 'Loads successfully to test normal behavior.',
    expectedBehavior: 'Should show loading state briefly then render component successfully.',
    createComponent: () => createAsyncComponent(
      () => Promise.resolve({
        template: `
          <div class="success-component">
            <h3>✅ Component Loaded Successfully!</h3>
            <p>This demonstrates normal async component loading.</p>
            <div class="success-details">
              <p><strong>Features tested:</strong></p>
              <ul>
                <li>Async component loading</li>
                <li>Loading state display</li>
                <li>Error boundary protection</li>
                <li>Success state rendering</li>
              </ul>
            </div>
          </div>
        `,
        style: `
          .success-component {
            padding: 2rem;
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
            border: 2px solid #28a745;
            border-radius: 12px;
            text-align: center;
          }
          .success-details {
            margin-top: 1rem;
            text-align: left;
          }
          .success-details ul {
            list-style-type: disc;
            margin-left: 2rem;
          }
        `
      }),
      {
        name: 'SuccessfulLoadDemo',
        loadingMessage: 'Loading successful component demo...'
      }
    )
  }
]

const addLog = (type: string, message: string) => {
  logs.value.unshift({
    type,
    message,
    timestamp: new Date().toLocaleTimeString()
  })

  // Keep only last 50 logs
  if (logs.value.length > 50) {
    logs.value = logs.value.slice(0, 50)
  }
}

const loadScenario = async (scenario) => {
  if (loading.value) return

  loading.value = true
  currentScenario.value = scenario

  addLog('info', `Loading scenario: ${scenario.name}`)

  try {
    const startTime = Date.now()
    currentComponent.value = scenario.createComponent()
    componentKey.value++ // Force component re-render

    // Wait a moment for component to attempt loading
    setTimeout(() => {
      loading.value = false
    }, 500)

  } catch (error) {
    loading.value = false
    addLog('error', `Failed to create scenario component: ${error.message}`)
  }
}

const handleComponentError = (error: Error) => {
  stats.value.totalErrors++
  addLog('error', `Component error: ${error.message}`)

  // Track with error recovery system
  if (currentScenario.value) {
    AsyncComponentErrorRecovery.markAsFailed(currentScenario.value.id)
  }
}

const handleComponentLoaded = (component) => {
  stats.value.successfulLoads++
  addLog('success', `Component loaded successfully: ${component?.name || 'Unknown'}`)

  // Reset error recovery state on success
  if (currentScenario.value) {
    AsyncComponentErrorRecovery.reset(currentScenario.value.id)
  }
}

const handleComponentRetry = (attempt: number) => {
  stats.value.retryAttempts++
  addLog('info', `Retry attempt #${attempt} for ${currentScenario.value?.name}`)

  if (currentScenario.value) {
    AsyncComponentErrorRecovery.incrementRetry(currentScenario.value.id)
  }
}

const clearLogs = () => {
  logs.value = []
  addLog('info', 'Logs cleared')
}

onMounted(() => {
  addLog('info', 'Async Error Boundary Demo initialized')
})
</script>

<style scoped>
.async-error-demo {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.demo-header {
  text-align: center;
  margin-bottom: 3rem;
}

.demo-title {
  font-size: 2.5rem;
  color: #2c3e50;
  margin-bottom: 1rem;
}

.demo-description {
  font-size: 1.1rem;
  color: #7f8c8d;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.6;
}

.demo-controls {
  margin-bottom: 3rem;
}

.demo-controls h3 {
  font-size: 1.5rem;
  color: #34495e;
  margin-bottom: 1rem;
}

.scenario-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.scenario-btn {
  padding: 1rem 1.5rem;
  border: 2px solid #e74c3c;
  background: white;
  color: #e74c3c;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
}

.scenario-btn:hover:not(:disabled) {
  background: #e74c3c;
  color: white;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(231, 76, 60, 0.3);
}

.scenario-btn.active {
  background: #e74c3c;
  color: white;
}

.scenario-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.demo-content {
  margin-bottom: 3rem;
}

.scenario-info {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  border-left: 4px solid #3498db;
}

.scenario-info h4 {
  color: #2c3e50;
  margin-bottom: 0.5rem;
}

.expected-behavior {
  margin-top: 1rem;
  padding: 0.75rem;
  background: #e8f4fd;
  border-radius: 4px;
  border-left: 3px solid #3498db;
}

.component-container {
  min-height: 300px;
  border: 2px dashed #bdc3c7;
  border-radius: 8px;
  padding: 2rem;
  background: #fdfdfd;
}

.no-scenario {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #95a5a6;
  text-align: center;
}

.no-scenario i {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.demo-stats {
  margin-bottom: 3rem;
}

.demo-stats h3 {
  font-size: 1.5rem;
  color: #34495e;
  margin-bottom: 1rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-item {
  padding: 1rem;
  background: white;
  border: 1px solid #ecf0f1;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  color: #7f8c8d;
  font-weight: 500;
}

.stat-value {
  color: #2c3e50;
  font-weight: bold;
  font-size: 1.1rem;
}

.error-recovery-stats {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  border: 1px solid #dee2e6;
}

.error-recovery-stats h4 {
  margin-bottom: 1rem;
  color: #495057;
}

.error-recovery-stats pre {
  background: #343a40;
  color: #f8f9fa;
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.875rem;
}

.demo-logs h3 {
  font-size: 1.5rem;
  color: #34495e;
  margin-bottom: 1rem;
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  background: #2c3e50;
  color: #ecf0f1;
  padding: 1rem;
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.875rem;
}

.log-entry {
  padding: 0.25rem 0;
  border-bottom: 1px solid #34495e;
}

.log-entry:last-child {
  border-bottom: none;
}

.log-timestamp {
  color: #95a5a6;
  margin-right: 1rem;
}

.log-error {
  color: #e74c3c;
}

.log-success {
  color: #27ae60;
}

.log-info {
  color: #3498db;
}

.clear-logs-btn {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  background: #95a5a6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.3s ease;
}

.clear-logs-btn:hover {
  background: #7f8c8d;
}

.success-component {
  padding: 2rem;
  background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
  border: 2px solid #28a745;
  border-radius: 12px;
  text-align: center;
}

.success-details {
  margin-top: 1rem;
  text-align: left;
}

.success-details ul {
  list-style-type: disc;
  margin-left: 2rem;
}

@media (max-width: 768px) {
  .async-error-demo {
    padding: 1rem;
  }

  .demo-title {
    font-size: 2rem;
  }

  .scenario-buttons {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>