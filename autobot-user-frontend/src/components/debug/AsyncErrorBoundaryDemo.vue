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
        <EmptyState
          v-else
          icon="fas fa-play"
          message="Select a scenario above to test async component error boundaries"
        />
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
import EmptyState from '@/components/ui/EmptyState.vue'

// Issue #156 Fix: Add proper TypeScript interfaces
interface Scenario {
  id: string
  name: string
  icon: string
  description: string
  expectedBehavior: string
  createComponent: () => any
}

interface LogEntry {
  type: string
  message: string
  timestamp: string
}

interface DemoStats {
  totalErrors: number
  retryAttempts: number
  successfulLoads: number
  averageLoadTime: number
  loadTimes: number[]
}

const loading = ref(false)
const currentScenario = ref<Scenario | null>(null)
const currentComponent = ref<any>(null)
const componentKey = ref(0)
const logs = ref<LogEntry[]>([])

const stats = ref<DemoStats>({
  totalErrors: 0,
  retryAttempts: 0,
  successfulLoads: 0,
  averageLoadTime: 0,
  loadTimes: []
})

const errorRecoveryStats = computed(() => {
  return AsyncComponentErrorRecovery.getStats()
})

// Issue #156 Fix: Explicitly type scenarios array
const scenarios: Scenario[] = [
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
        // Issue #704: Note - inline styles in dynamic component templates
        // These use CSS custom properties with fallbacks for runtime rendering
        style: `
          .success-component {
            padding: 2rem;
            background: linear-gradient(135deg, var(--color-success-bg, #d4edda) 0%, var(--color-success-bg-hover, #c3e6cb) 100%);
            border: 2px solid var(--color-success, #28a745);
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

// Issue #156 Fix: Type scenario parameter
const loadScenario = async (scenario: Scenario) => {
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

  } catch (error: unknown) {
    loading.value = false
    const errorMessage = error instanceof Error ? error.message : String(error)
    addLog('error', `Failed to create scenario component: ${errorMessage}`)
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

// Issue #156 Fix: Type component parameter
const handleComponentLoaded = (component: any) => {
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
/**
 * AsyncErrorBoundaryDemo.vue - Styles migrated to design tokens
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 */

.async-error-demo {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-8);
  font-family: var(--font-sans);
}

.demo-header {
  text-align: center;
  margin-bottom: var(--spacing-12);
}

.demo-title {
  font-size: var(--text-4xl);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.demo-description {
  font-size: var(--text-lg);
  color: var(--text-secondary);
  max-width: 600px;
  margin: 0 auto;
  line-height: var(--leading-relaxed);
}

.demo-controls {
  margin-bottom: var(--spacing-12);
}

.demo-controls h3 {
  font-size: var(--text-2xl);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.scenario-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.scenario-btn {
  padding: var(--spacing-4) var(--spacing-6);
  border: 2px solid var(--color-error);
  background: var(--bg-card);
  color: var(--color-error);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
}

.scenario-btn:hover:not(:disabled) {
  background: var(--color-error);
  color: var(--text-on-error);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px var(--color-error-bg);
}

.scenario-btn.active {
  background: var(--color-error);
  color: var(--text-on-error);
}

.scenario-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.demo-content {
  margin-bottom: var(--spacing-12);
}

.scenario-info {
  background: var(--bg-secondary);
  padding: var(--spacing-6);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-8);
  border-left: 4px solid var(--color-info);
}

.scenario-info h4 {
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.expected-behavior {
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--color-info-bg);
  border-radius: var(--radius-default);
  border-left: 3px solid var(--color-info);
}

.component-container {
  min-height: 300px;
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-8);
  background: var(--bg-card);
}

.demo-stats {
  margin-bottom: var(--spacing-12);
}

.demo-stats h3 {
  font-size: var(--text-2xl);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-8);
}

.stat-item {
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.stat-value {
  color: var(--text-primary);
  font-weight: var(--font-bold);
  font-size: var(--text-lg);
}

.error-recovery-stats {
  background: var(--bg-secondary);
  padding: var(--spacing-6);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.error-recovery-stats h4 {
  margin-bottom: var(--spacing-4);
  color: var(--text-secondary);
}

.error-recovery-stats pre {
  background: var(--code-bg);
  color: var(--code-text);
  padding: var(--spacing-4);
  border-radius: var(--radius-default);
  overflow-x: auto;
  font-size: var(--text-sm);
  font-family: var(--font-mono);
}

.demo-logs h3 {
  font-size: var(--text-2xl);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.log-entry {
  padding: var(--spacing-1) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.log-entry:last-child {
  border-bottom: none;
}

.log-timestamp {
  color: var(--text-tertiary);
  margin-right: var(--spacing-4);
}

.log-error {
  color: var(--color-error);
}

.log-success {
  color: var(--color-success);
}

.log-info {
  color: var(--color-info);
}

.clear-logs-btn {
  margin-top: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-secondary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  transition: background var(--duration-300) var(--ease-in-out);
}

.clear-logs-btn:hover {
  background: var(--color-secondary-hover);
}

.success-component {
  padding: var(--spacing-8);
  background: linear-gradient(135deg, var(--color-success-bg) 0%, var(--color-success-bg-hover) 100%);
  border: 2px solid var(--color-success);
  border-radius: var(--radius-xl);
  text-align: center;
}

.success-details {
  margin-top: var(--spacing-4);
  text-align: left;
}

.success-details ul {
  list-style-type: disc;
  margin-left: var(--spacing-8);
}

@media (max-width: 768px) {
  .async-error-demo {
    padding: var(--spacing-4);
  }

  .demo-title {
    font-size: var(--text-3xl);
  }

  .scenario-buttons {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
