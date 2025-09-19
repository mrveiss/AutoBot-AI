/**
 * Service Monitoring Composable
 * Provides real-time service status monitoring
 */
import { ref, computed, onMounted, onUnmounted, getCurrentInstance } from 'vue'
import { apiService } from '@/services/api.js'

export function useServiceMonitor() {
  // Service monitoring state
  const services = ref([])
  const systemResources = ref({})
  const overallStatus = ref('loading')
  const lastCheck = ref(null)
  const isLoading = ref(false)
  const error = ref(null)
  
  // Service summary stats
  const serviceSummary = ref({
    total: 0,
    online: 0,
    warning: 0,
    error: 0,
    offline: 0
  })
  
  // Auto-refresh interval
  let refreshInterval = null
  const REFRESH_INTERVAL = 30000 // 30 seconds
  
  // Computed properties
  const healthyServices = computed(() => {
    return serviceSummary.value.online || 0
  })
  
  const healthPercentage = computed(() => {
    if (serviceSummary.value.total === 0) return 0
    return Math.round((serviceSummary.value.online / serviceSummary.value.total) * 100)
  })
  
  const statusColor = computed(() => {
    switch (overallStatus.value) {
      case 'online': return 'green'
      case 'warning': return 'yellow'
      case 'error': return 'red'
      case 'offline': return 'red'
      default: return 'gray'
    }
  })
  
  const statusIcon = computed(() => {
    switch (overallStatus.value) {
      case 'online': return 'fas fa-check-circle'
      case 'warning': return 'fas fa-exclamation-triangle'
      case 'error': return 'fas fa-times-circle'
      case 'offline': return 'fas fa-times-circle'
      case 'loading': return 'fas fa-spinner fa-spin'
      default: return 'fas fa-question-circle'
    }
  })
  
  const statusMessage = computed(() => {
    switch (overallStatus.value) {
      case 'online': return `${serviceSummary.value.online} services online`
      case 'warning': return `${serviceSummary.value.warning} service(s) need attention`
      case 'error': return `${serviceSummary.value.error} service(s) have errors`
      case 'offline': return `${serviceSummary.value.offline} service(s) offline`
      case 'loading': return 'Checking services...'
      default: return 'Status unknown'
    }
  })
  
  // Service categories for dashboard grouping
  const servicesByCategory = computed(() => {
    const categories = {}
    services.value.forEach(service => {
      if (!categories[service.category]) {
        categories[service.category] = []
      }
      categories[service.category].push(service)
    })
    return categories
  })
  
  // Core services (most important ones for dashboard)
  const coreServices = computed(() => {
    return services.value.filter(s => 
      ['core', 'database', 'web', 'ai'].includes(s.category)
    ).slice(0, 8) // Limit to 8 for dashboard display
  })
  
  // Fetch service status
  const fetchServiceStatus = async () => {
    if (isLoading.value) return // Prevent concurrent requests
    
    try {
      isLoading.value = true
      error.value = null
      
      console.log('Fetching service status...')
      const data = await apiService.get('/api/services/status')
      console.log('Service status response:', data)
      console.log('Response type:', typeof data)
      
      // Backend returns data directly, not wrapped in success/data structure
      if (data && typeof data === 'object') {
        // Update service data
        services.value = data.services || []
        systemResources.value = data.system_resources || {}
        overallStatus.value = data.overall_status || 'unknown'
        serviceSummary.value = data.summary || { total: 0, online: 0, warning: 0, error: 0, offline: 0 }
        lastCheck.value = new Date()
        
        // Log status for debugging
        console.log(`Service Monitor: ${serviceSummary.value.online}/${serviceSummary.value.total} services online`)
        
      } else {
        console.error('Invalid response data:', data)
        throw new Error('Invalid response format from service status endpoint')
      }
      
    } catch (err) {
      console.error('Service monitoring error:', err)
      console.error('Error stack:', err.stack)
      error.value = err.message
      overallStatus.value = 'error'
      
      // Fallback data
      services.value = [
        {
          name: 'Service Monitor',
          status: 'error',
          message: 'Unable to fetch service status',
          icon: 'fas fa-exclamation-triangle',
          category: 'monitoring'
        }
      ]
      serviceSummary.value = { total: 1, online: 0, warning: 0, error: 1, offline: 0 }
      
    } finally {
      isLoading.value = false
    }
  }
  
  // Quick health check (lighter weight)
  const fetchHealthCheck = async () => {
    try {
      const data = await apiService.get('/api/services/health')
      
      if (data && typeof data === 'object') {
        overallStatus.value = data.status
        serviceSummary.value.online = data.healthy || 0
        serviceSummary.value.total = data.total || 0
        serviceSummary.value.warning = data.warnings || 0
        serviceSummary.value.error = data.errors || 0
        lastCheck.value = new Date()
      }
    } catch (err) {
      console.warn('Health check failed:', err.message)
    }
  }
  
  // Start monitoring
  const startMonitoring = () => {
    // Initial load
    fetchServiceStatus()
    
    // Set up auto-refresh
    refreshInterval = setInterval(() => {
      // Alternate between full status and quick health check
      const isFullCheck = Math.floor(Date.now() / REFRESH_INTERVAL) % 2 === 0
      if (isFullCheck) {
        fetchServiceStatus()
      } else {
        fetchHealthCheck()
      }
    }, REFRESH_INTERVAL)
  }
  
  // Stop monitoring
  const stopMonitoring = () => {
    if (refreshInterval) {
      clearInterval(refreshInterval)
      refreshInterval = null
    }
  }
  
  // Refresh manually
  const refresh = () => {
    fetchServiceStatus()
  }
  
  // Get service by name
  const getService = (name) => {
    return services.value.find(s => s.name === name)
  }
  
  // Get services by status
  const getServicesByStatus = (status) => {
    return services.value.filter(s => s.status === status)
  }
  
  // Format response time
  const formatResponseTime = (ms) => {
    if (!ms) return 'N/A'
    if (ms < 100) return `${ms}ms`
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }
  
  // Format last check time
  const formatLastCheck = () => {
    if (!lastCheck.value) return 'Never'
    
    // Ensure lastCheck.value is a valid Date
    let checkTime = lastCheck.value
    if (!(checkTime instanceof Date)) {
      checkTime = new Date(checkTime)
      if (isNaN(checkTime.getTime())) return 'Never'
    }
    
    const now = new Date()
    const diff = now - checkTime
    
    if (diff < 60000) return 'Just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    return checkTime.toLocaleTimeString()
  }
  
  // Lifecycle
  onMounted(() => {
    startMonitoring()
  })
  
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      stopMonitoring()
    })
  } else {
    console.warn('useServiceMonitor: Not inside Vue component, manual cleanup required')
  }
  
  return {
    // State
    services,
    systemResources,
    overallStatus,
    serviceSummary,
    lastCheck,
    isLoading,
    error,
    
    // Computed
    healthyServices,
    healthPercentage,
    statusColor,
    statusIcon,
    statusMessage,
    servicesByCategory,
    coreServices,
    
    // Methods
    fetchServiceStatus,
    fetchHealthCheck,
    startMonitoring,
    stopMonitoring,
    refresh,
    getService,
    getServicesByStatus,
    formatResponseTime,
    formatLastCheck
  }
}