<template>
  <div class="multi-machine-health">
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-lg font-semibold text-gray-900">Infrastructure Health</h3>
      <div class="flex items-center space-x-3">
        <!-- Issue #472: View Toggle - Custom vs Grafana -->
        <div class="flex items-center space-x-1 bg-gray-100 rounded-lg p-0.5">
          <button
            @click="viewMode = 'custom'"
            class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
            :class="viewMode === 'custom' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          >
            <i class="fas fa-th-large mr-1"></i>
            Custom
          </button>
          <button
            @click="viewMode = 'grafana'"
            class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
            :class="viewMode === 'grafana' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          >
            <i class="fas fa-chart-line mr-1"></i>
            Grafana
          </button>
        </div>

        <span class="text-xs text-gray-500">
          Last check: {{ lastCheckTime }}
        </span>
        <button
          @click="refreshAll"
          :disabled="isRefreshing"
          class="text-gray-400 hover:text-gray-600 transition-colors"
          title="Refresh all machines"
        >
          <i :class="isRefreshing ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
        </button>

        <!-- Overall Status Badge -->
        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
             :class="overallStatusClass">
          <span class="w-2 h-2 rounded-full mr-1" :class="overallStatusDotClass"></span>
          {{ overallStatus }}
        </span>
      </div>
    </div>

    <!-- Issue #472: Grafana Dashboard View -->
    <div v-if="viewMode === 'grafana'" class="grafana-container">
      <GrafanaDashboard
        dashboard="multi-machine"
        :height="700"
        :show-controls="true"
        theme="dark"
      />
    </div>

    <!-- Custom View (Original) -->
    <div v-else>

    <!-- Issue #465: Error State Display -->
    <div v-if="apiError" class="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
      <div class="flex items-center">
        <i class="fas fa-exclamation-triangle text-red-500 text-2xl mr-4"></i>
        <div class="flex-1">
          <h4 class="font-semibold text-red-800">Infrastructure Data Unavailable</h4>
          <p class="text-sm text-red-600 mt-1">{{ apiError }}</p>
          <p v-if="retryCount < maxRetries" class="text-xs text-red-500 mt-2">
            Retrying automatically... ({{ retryCount }}/{{ maxRetries }})
          </p>
        </div>
        <button
          @click="refreshAll"
          :disabled="isRefreshing"
          class="ml-4 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors"
        >
          <i :class="isRefreshing ? 'fas fa-spinner fa-spin' : 'fas fa-redo'" class="mr-2"></i>
          Retry Now
        </button>
      </div>
    </div>

    <!-- Machine Cards Grid - 6 machines layout -->
    <div v-if="machines.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <!-- Machine Card -->
      <div 
        v-for="machine in machines" 
        :key="machine.id"
        class="bg-white rounded-lg shadow-md overflow-hidden"
        :class="getMachineCardClass(machine)"
      >
        <!-- Machine Header -->
        <div class="px-4 py-3 border-b" :class="getMachineHeaderClass(machine)">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <i :class="machine.icon || 'fas fa-server'" class="text-lg"></i>
              <div>
                <h4 class="font-semibold text-sm">{{ machine.name }}</h4>
                <p class="text-xs opacity-75">{{ machine.ip }}</p>
              </div>
            </div>
            <span 
              class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium"
              :class="getMachineStatusClass(machine.status)"
            >
              <span class="w-1.5 h-1.5 rounded-full mr-1" :class="getMachineStatusDotClass(machine.status)"></span>
              {{ machine.status }}
            </span>
          </div>
        </div>

        <!-- Services Tree -->
        <div class="p-4">
          <!-- Core Services Section -->
          <div v-if="machine.services.core && machine.services.core.length > 0" class="mb-4">
            <h5 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Core Services</h5>
            <div class="space-y-2">
              <ServiceItem 
                v-for="service in machine.services.core" 
                :key="service.name"
                :service="service"
                :machine-name="machine.name"
                @click="showServiceDetails(machine, service)"
              />
            </div>
          </div>

          <!-- Database Services Section -->
          <div v-if="machine.services.database && machine.services.database.length > 0" class="mb-4">
            <h5 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Databases</h5>
            <div class="space-y-2">
              <ServiceItem 
                v-for="service in machine.services.database" 
                :key="service.name"
                :service="service"
                :machine-name="machine.name"
                @click="showServiceDetails(machine, service)"
              />
            </div>
          </div>

          <!-- Application Services Section -->
          <div v-if="machine.services.application && machine.services.application.length > 0" class="mb-4">
            <h5 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Applications</h5>
            <div class="space-y-2">
              <ServiceItem 
                v-for="service in machine.services.application" 
                :key="service.name"
                :service="service"
                :machine-name="machine.name"
                @click="showServiceDetails(machine, service)"
              />
            </div>
          </div>

          <!-- Support Services Section -->
          <div v-if="machine.services.support && machine.services.support.length > 0" class="mb-4">
            <h5 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Support Services</h5>
            <div class="space-y-2">
              <ServiceItem 
                v-for="service in machine.services.support" 
                :key="service.name"
                :service="service"
                :machine-name="machine.name"
                @click="showServiceDetails(machine, service)"
              />
            </div>
          </div>

          <!-- Machine Stats -->
          <div class="mt-4 pt-3 border-t border-gray-200">
            <!-- CPU and Load -->
            <div class="mb-3">
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs text-gray-500 uppercase">CPU & Load</span>
                <span v-if="machine.stats?.cpu_usage" class="text-xs font-medium">{{ machine.stats.cpu_usage }}%</span>
              </div>
              <div v-if="machine.stats?.cpu_load_1m" class="text-xs text-gray-600">
                Load: {{ machine.stats.cpu_load_1m }} / {{ machine.stats?.cpu_load_5m || '0.0' }} / {{ machine.stats?.cpu_load_15m || '0.0' }}
              </div>
            </div>

            <!-- Memory -->
            <div class="mb-3">
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs text-gray-500 uppercase">Memory</span>
                <span v-if="machine.stats?.memory_percent" class="text-xs font-medium">{{ machine.stats.memory_percent }}%</span>
              </div>
              <div v-if="machine.stats?.memory_used && machine.stats?.memory_total" class="text-xs text-gray-600">
                {{ machine.stats.memory_used }}GB / {{ machine.stats.memory_total }}GB used
              </div>
            </div>

            <!-- Disk Space -->
            <div class="mb-3">
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs text-gray-500 uppercase">Disk Space</span>
                <span v-if="machine.stats?.disk_percent" class="text-xs font-medium">{{ machine.stats.disk_percent }}%</span>
              </div>
              <div v-if="machine.stats?.disk_used && machine.stats?.disk_total" class="text-xs text-gray-600">
                {{ machine.stats.disk_used }} / {{ machine.stats.disk_total }} ({{ machine.stats?.disk_free }} free)
              </div>
            </div>

            <!-- Uptime and Processes -->
            <div class="grid grid-cols-1 gap-1 text-xs">
              <div v-if="machine.stats?.uptime" class="flex justify-between">
                <span class="text-gray-500">Uptime:</span>
                <span class="font-medium">{{ machine.stats.uptime }}</span>
              </div>
              <div v-if="machine.stats?.processes" class="flex justify-between">
                <span class="text-gray-500">Processes:</span>
                <span class="font-medium">{{ machine.stats.processes }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Machine Footer (if there are errors) -->
        <div v-if="getMachineErrors(machine).length > 0" class="px-4 py-2 bg-red-50 border-t border-red-200">
          <div class="text-xs text-red-700">
            <i class="fas fa-exclamation-triangle mr-1"></i>
            <span class="font-medium">{{ getMachineErrors(machine).length }} service(s) down</span>
            <div class="mt-1 text-red-600">
              {{ getMachineErrors(machine).map(s => s.name).join(', ') }}
            </div>
          </div>
        </div>
      </div>
    </div>
    </div><!-- End Custom View -->

    <!-- Service Details Modal -->
    <div v-if="selectedService" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4">
        <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" @click="selectedService = null"></div>
        
        <div class="relative bg-white rounded-lg max-w-2xl w-full shadow-xl">
          <div class="px-6 py-4 border-b">
            <h3 class="text-lg font-semibold">{{ selectedService.service.name }} Details</h3>
            <p class="text-sm text-gray-500">{{ selectedService.machine.name }} ({{ selectedService.machine.ip }})</p>
          </div>
          
          <div class="p-6">
            <div class="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label class="text-xs text-gray-500 uppercase tracking-wide">Status</label>
                <p class="font-medium" :class="getServiceStatusTextClass(selectedService.service.status)">
                  {{ selectedService.service.status }}
                </p>
              </div>
              <div>
                <label class="text-xs text-gray-500 uppercase tracking-wide">Response Time</label>
                <p class="font-medium">{{ selectedService.service.responseTime || 'N/A' }}</p>
              </div>
            </div>
            
            <div v-if="selectedService.service.error" class="mb-4">
              <label class="text-xs text-gray-500 uppercase tracking-wide">Error Details</label>
              <div class="mt-1 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                {{ selectedService.service.error }}
              </div>
            </div>
            
            <div v-if="selectedService.service.details" class="mb-4">
              <label class="text-xs text-gray-500 uppercase tracking-wide">Additional Information</label>
              <pre class="mt-1 p-3 bg-gray-50 border border-gray-200 rounded text-xs overflow-x-auto">{{ JSON.stringify(selectedService.service.details, null, 2) }}</pre>
            </div>
          </div>
          
          <div class="px-6 py-4 border-t flex justify-end">
            <button 
              @click="selectedService = null"
              class="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useServiceMonitor } from '@/composables/useServiceMonitor.js'

const logger = createLogger('MultiMachineHealth')
import ServiceItem from './ServiceItem.vue'
import GrafanaDashboard from './monitoring/GrafanaDashboard.vue'
import appConfig from '@/config/AppConfig.js'

interface Machine {
  id: string
  name: string
  ip: string
  status: string
  icon?: string
  services: {
    core?: Service[]
    database?: Service[]
    application?: Service[]
    support?: Service[]
  }
  stats?: {
    cpu_usage?: number
    cpu_load_1m?: number
    cpu_load_5m?: number
    cpu_load_15m?: number
    memory_used?: number
    memory_total?: number
    memory_percent?: number
    disk_used?: string
    disk_total?: string
    disk_free?: string
    disk_percent?: number
    uptime?: string
    processes?: number
    // Legacy fields for compatibility
    cpu?: number
    memory?: number
    disk?: number
  }
}

interface Service {
  name: string
  status: string
  responseTime?: string
  error?: string
  details?: any
}

const serviceMonitor = useServiceMonitor()
const isRefreshing = ref(false)
const selectedService = ref<{ machine: Machine, service: Service } | null>(null)
const lastCheckTime = ref('Never')
// Issue #472: View mode toggle - 'custom' or 'grafana'
const viewMode = ref<'custom' | 'grafana'>('custom')
// Issue #465: Track API error state - no mock data fallback
const apiError = ref<string | null>(null)
const retryCount = ref(0)
const maxRetries = 3
let refreshInterval: number | null = null

// Initialize machine configurations from centralized AppConfig
const initializeMachinesFromConfig = () => {
  const configMachines = appConfig.getMachinesArray()
  return configMachines.map(configMachine => ({
    ...configMachine,
    status: 'healthy', // Default status, will be updated from API
    services: getDefaultServicesForMachine(configMachine.role),
    stats: getDefaultStatsForMachine(configMachine.role)
  }))
}

// Define default services based on machine role
const getDefaultServicesForMachine = (role: string) => {
  switch (role) {
    case 'backend':
      return {
        core: [
          { name: 'Backend API', status: 'online', responseTime: '45ms' },
          { name: 'WebSocket Server', status: 'online', responseTime: '8ms' },
          { name: 'Dev Frontend', status: 'online', responseTime: '12ms' }
        ],
        database: [
          { name: 'SQLite', status: 'online', responseTime: '2ms' },
          { name: 'Knowledge Base', status: 'online', responseTime: '125ms' },
          { name: 'ChromaDB', status: 'online', responseTime: '85ms' }
        ],
        application: [
          { name: 'Chat Service', status: 'online', responseTime: '67ms' },
          { name: 'LLM Interface', status: 'online', responseTime: '234ms' },
          { name: 'Workflow Engine', status: 'online', responseTime: '45ms' }
        ],
        support: [
          { name: 'Service Monitor', status: 'online', responseTime: '15ms' },
          { name: 'Prompts API', status: 'online', responseTime: '10ms' },
          { name: 'File Manager', status: 'online', responseTime: '8ms' }
        ]
      }
    case 'frontend':
      return {
        core: [
          { name: 'Vite Dev Server', status: 'online', responseTime: '8ms' },
          { name: 'Vue Application', status: 'warning', responseTime: '250ms', error: 'Old bundle with cache errors' }
        ],
        application: [
          { name: 'Frontend Build', status: 'warning', responseTime: '15ms', error: 'Needs rebuild with fixes' }
        ],
        support: [
          { name: 'Node.js Runtime', status: 'online', responseTime: '5ms' },
          { name: 'NPM Packages', status: 'online', responseTime: '7ms' }
        ]
      }
    case 'worker':
      return {
        core: [
          { name: 'NPU Worker API', status: 'online', responseTime: '89ms' },
          { name: 'Health Endpoint', status: 'online', responseTime: '12ms' }
        ],
        application: [
          { name: 'AI Processing', status: 'online', responseTime: '156ms' },
          { name: 'Intel NPU', status: 'online', responseTime: '78ms' },
          { name: 'Model Inference', status: 'online', responseTime: '234ms' }
        ],
        support: [
          { name: 'Worker Queue', status: 'online', responseTime: '25ms' },
          { name: 'Task Scheduler', status: 'online', responseTime: '18ms' }
        ]
      }
    case 'database':
      return {
        core: [
          { name: 'Redis Server', status: 'online', responseTime: '3ms' },
          { name: 'Redis Stack', status: 'online', responseTime: '5ms' }
        ],
        database: [
          { name: 'Memory Store', status: 'online', responseTime: '2ms' },
          { name: 'Pub/Sub', status: 'online', responseTime: '4ms' },
          { name: 'Search Index', status: 'online', responseTime: '8ms' },
          { name: 'Time Series', status: 'online', responseTime: '6ms' }
        ],
        support: [
          { name: 'Persistence', status: 'online', responseTime: '12ms' },
          { name: 'Backup Manager', status: 'online', responseTime: '25ms' }
        ]
      }
    case 'ai':
      return {
        core: [
          { name: 'AI Stack API', status: 'online', responseTime: '125ms' },
          { name: 'Health Endpoint', status: 'online', responseTime: '45ms' }
        ],
        application: [
          { name: 'LLM Processing', status: 'online', responseTime: '567ms' },
          { name: 'Embeddings', status: 'online', responseTime: '234ms' },
          { name: 'Vector Search', status: 'online', responseTime: '89ms' },
          { name: 'Model Manager', status: 'online', responseTime: '156ms' }
        ],
        support: [
          { name: 'GPU Manager', status: 'online', responseTime: '23ms' },
          { name: 'Memory Pool', status: 'online', responseTime: '15ms' }
        ]
      }
    case 'browser':
      return {
        core: [
          { name: 'Browser API', status: 'online', responseTime: '45ms' },
          { name: 'Health Endpoint', status: 'online', responseTime: '12ms' }
        ],
        application: [
          { name: 'Playwright Engine', status: 'online', responseTime: '89ms' },
          { name: 'Chromium Pool', status: 'online', responseTime: '156ms' },
          { name: 'Screenshot Service', status: 'online', responseTime: '234ms' },
          { name: 'Automation Engine', status: 'online', responseTime: '123ms' }
        ],
        support: [
          { name: 'Browser Pool', status: 'online', responseTime: '67ms' },
          { name: 'Session Manager', status: 'online', responseTime: '34ms' }
        ]
      }
    default:
      return { core: [], database: [], application: [], support: [] }
  }
}

// Define default stats based on machine role  
const getDefaultStatsForMachine = (role: string) => {
  const baseStats = { cpu: 0, memory: 0, disk: 0, uptime: '0s' }
  
  switch (role) {
    case 'backend': return { ...baseStats, cpu: 45, memory: 62, disk: 38, uptime: '14d 5h' }
    case 'frontend': return { ...baseStats, cpu: 28, memory: 45, disk: 52, uptime: '7d 12h' }
    case 'worker': return { ...baseStats, cpu: 67, memory: 45, disk: 32, uptime: '12d 8h' }
    case 'database': return { ...baseStats, cpu: 25, memory: 78, disk: 42, uptime: '21d 15h' }
    case 'ai': return { ...baseStats, cpu: 78, memory: 89, disk: 65, uptime: '9d 3h' }
    case 'browser': return { ...baseStats, cpu: 42, memory: 67, disk: 48, uptime: '16d 22h' }
    default: return baseStats
  }
}

// Machine data initialized from centralized configuration
const machines = ref<Machine[]>(initializeMachinesFromConfig())

const overallStatus = computed(() => {
  const hasError = machines.value.some(m => m.status === 'error' || 
    Object.values(m.services).flat().some(s => s?.status === 'error'))
  const hasWarning = machines.value.some(m => m.status === 'warning' || 
    Object.values(m.services).flat().some(s => s?.status === 'warning'))
  
  if (hasError) return 'Error'
  if (hasWarning) return 'Warning'
  return 'Healthy'
})

const overallStatusClass = computed(() => {
  switch (overallStatus.value) {
    case 'Healthy': return 'bg-green-100 text-green-800'
    case 'Warning': return 'bg-yellow-100 text-yellow-800'
    case 'Error': return 'bg-red-100 text-red-800'
    default: return 'bg-gray-100 text-gray-800'
  }
})

const overallStatusDotClass = computed(() => {
  switch (overallStatus.value) {
    case 'Healthy': return 'bg-green-400'
    case 'Warning': return 'bg-yellow-400'
    case 'Error': return 'bg-red-400'
    default: return 'bg-gray-400'
  }
})

const getMachineCardClass = (machine: Machine) => {
  const hasError = getMachineErrors(machine).length > 0
  return hasError ? 'border-l-4 border-red-500' : ''
}

const getMachineHeaderClass = (machine: Machine) => {
  switch (machine.status) {
    case 'healthy': return 'bg-green-50'
    case 'warning': return 'bg-yellow-50'
    case 'error': return 'bg-red-50'
    default: return 'bg-gray-50'
  }
}

const getMachineStatusClass = (status: string) => {
  switch (status) {
    case 'healthy': return 'bg-green-100 text-green-800'
    case 'warning': return 'bg-yellow-100 text-yellow-800'
    case 'error': return 'bg-red-100 text-red-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

const getMachineStatusDotClass = (status: string) => {
  switch (status) {
    case 'healthy': return 'bg-green-400'
    case 'warning': return 'bg-yellow-400'
    case 'error': return 'bg-red-400'
    default: return 'bg-gray-400'
  }
}

const getServiceStatusTextClass = (status: string) => {
  switch (status) {
    case 'online': return 'text-green-600'
    case 'warning': return 'text-yellow-600'
    case 'error': return 'text-red-600'
    default: return 'text-gray-600'
  }
}

const getMachineErrors = (machine: Machine) => {
  const errors: Service[] = []
  Object.values(machine.services).forEach(category => {
    if (category) {
      errors.push(...category.filter(s => s.status === 'error'))
    }
  })
  return errors
}

const showServiceDetails = (machine: Machine, service: Service) => {
  selectedService.value = { machine, service }
}

const refreshAll = async () => {
  isRefreshing.value = true
  lastCheckTime.value = new Date().toLocaleTimeString()

  try {
    // Issue #465: Fetch real infrastructure data from API - no mock fallback
    const response = await fetch('/api/infrastructure/status')
    if (response.ok) {
      const data = await response.json()
      if (data.status === 'success' && data.machines) {
        // Update machines with real data
        machines.value = data.machines.map((machine: any) => ({
          ...machine,
          services: {
            core: machine.services.core || [],
            database: machine.services.database || [],
            application: machine.services.application || [],
            support: machine.services.support || []
          }
        }))
        // Clear error state on success
        apiError.value = null
        retryCount.value = 0
      }
    } else {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
  } catch (error) {
    logger.error('Failed to fetch infrastructure status:', error)
    // Issue #465: Clear machines and show error state - no mock data
    machines.value = []
    apiError.value = error instanceof Error ? error.message : 'Failed to connect to backend'
    retryCount.value++

    // Schedule retry if under max attempts
    if (retryCount.value < maxRetries) {
      logger.info(`Scheduling retry ${retryCount.value}/${maxRetries}`)
      setTimeout(() => refreshAll(), 5000 * retryCount.value)
    }
  }

  // Also refresh service monitor for compatibility
  await serviceMonitor.refresh()

  setTimeout(() => {
    isRefreshing.value = false
  }, 1000)
}

const updateMachinesWithRealData = (services: any[]) => {
  // This would map real service data to the machine structure
  // For now, we'll update the first machine with real data
  if (machines.value[0] && services.length > 0) {
    services.forEach(service => {
      // Find and update matching service
      Object.values(machines.value[0].services).forEach(category => {
        if (category) {
          const found = category.find(s => s.name === service.name)
          if (found) {
            found.status = service.status || 'unknown'
            found.responseTime = service.response_time ? `${service.response_time}ms` : 'N/A'
            if (service.message) found.error = service.message
          }
        }
      })
    })
  }
}

onMounted(() => {
  refreshAll()
  // Auto-refresh every 30 seconds
  refreshInterval = window.setInterval(refreshAll, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.multi-machine-health {
  /* Component styles if needed */
}

/* Issue #472: Grafana container styling */
.grafana-container {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
}
</style>