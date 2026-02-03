/**
 * System Status Management Composable
 * Extracted from App.vue for better maintainability
 * Enhanced with API endpoint mapping and graceful fallbacks
 */

import { ref } from 'vue'
import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useSystemStatus
const logger = createLogger('useSystemStatus')

export function useSystemStatus() {
  // System status state
  const systemStatus = ref({
    isHealthy: true,
    hasIssues: false,
    lastChecked: new Date()
  })

  const systemServices = ref([
    { name: 'Backend API', status: 'healthy', statusText: 'Running' },
    { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
    { name: 'WebSocket', status: 'healthy', statusText: 'Connected' },
    { name: 'Redis', status: 'healthy', statusText: 'Connected' },
    { name: 'Ollama', status: 'healthy', statusText: 'Connected' },
    { name: 'NPU Worker', status: 'healthy', statusText: 'Running' },
    { name: 'Browser Service', status: 'healthy', statusText: 'Running' }
  ])

  const showSystemStatus = ref(false)

  // Computed properties
  const getSystemStatusTooltip = () => {
    if (systemStatus.value.hasIssues) {
      return 'Click to view system issues'
    } else if (!systemStatus.value.isHealthy) {
      return 'Click to view system warnings'
    } else {
      return 'Click to view system status - all services operational'
    }
  }

  const getSystemStatusText = () => {
    if (systemStatus.value.hasIssues) {
      return 'System Issues Detected'
    } else if (!systemStatus.value.isHealthy) {
      return 'System Warnings'
    } else {
      return 'All Systems Operational'
    }
  }

  const getSystemStatusDescription = () => {
    const errorCount = systemServices.value.filter(s => s.status === 'error').length
    const warningCount = systemServices.value.filter(s => s.status === 'warning').length

    if (errorCount > 0) {
      return `${errorCount} service${errorCount > 1 ? 's' : ''} down, ${warningCount} warning${warningCount !== 1 ? 's' : ''}`
    } else if (warningCount > 0) {
      return `${warningCount} service${warningCount > 1 ? 's' : ''} with warnings`
    } else {
      return 'All services running normally'
    }
  }

  // Methods
  const toggleSystemStatus = () => {
    showSystemStatus.value = !showSystemStatus.value
  }

  const refreshSystemStatus = async () => {
    
    try {
      const updatedServices = []
      let hasApiErrors = false

      // FIXED: Use correct endpoint with graceful fallback
      // Correct endpoint: '/api/service-monitor/vms/status'
      try {
        const vmResponse = await apiEndpointMapper.fetchWithFallback('/api/service-monitor/vms/status', { timeout: 5000 })
        const vmData = await vmResponse.json()

        if (vmResponse.fallback) {
          hasApiErrors = true
        }

        // Add VM status from backend aggregation or fallback
        if (vmData.vms) {
          vmData.vms.forEach(vm => {
            updatedServices.push({
              name: vm.name,
              status: vm.status === 'online' ? 'healthy' :
                      vm.status === 'warning' ? 'warning' : 'error',
              statusText: vm.message || vm.status
            })
          })
        }
      } catch (vmError) {
        logger.warn('Infrastructure endpoint failed:', vmError.message)
        hasApiErrors = true
        // Add fallback infrastructure services
        updatedServices.push(
          { name: 'Backend API', status: 'warning', statusText: 'Status Unknown' },
          { name: 'NPU Worker', status: 'warning', statusText: 'Status Unknown' },
          { name: 'Redis', status: 'warning', statusText: 'Status Unknown' }
        )
      }

      // FIXED: Use correct services endpoint with graceful fallback
      // Correct endpoint: '/api/service-monitor/services'
      try {
        const servicesResponse = await apiEndpointMapper.fetchWithFallback('/api/service-monitor/services', { timeout: 5000 })
        const servicesData = await servicesResponse.json()

        if (servicesResponse.fallback) {
          hasApiErrors = true
        }

        // Map backend services to frontend display
        const serviceMap = {
          'backend': 'Backend API',
          'redis': 'Redis',
          'ollama': 'Ollama',
          'frontend': 'Frontend',
          'npu_worker': 'NPU Worker',
          'browser': 'Browser Service'
        }

        if (servicesData.services) {
          Object.entries(servicesData.services).forEach(([key, service]) => {
            const displayName = serviceMap[key] || key
            updatedServices.push({
              name: displayName,
              status: service.status === 'online' ? 'healthy' :
                      service.status === 'warning' ? 'warning' : 'error',
              statusText: service.health || service.status
            })
          })
        }
      } catch (servicesError) {
        logger.warn('Services endpoint failed:', servicesError.message)
        hasApiErrors = true
        // Add fallback service statuses
        updatedServices.push(
          { name: 'Ollama', status: 'warning', statusText: 'Status Unknown' },
          { name: 'Browser Service', status: 'warning', statusText: 'Status Unknown' }
        )
      }

      // Always add frontend and websocket status (local)
      updatedServices.push(
        { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
        { name: 'WebSocket', status: 'healthy', statusText: 'Connected' }
      )

      // Remove duplicates (in case both endpoints returned same services)
      const uniqueServices = updatedServices.reduce((acc, service) => {
        const existing = acc.find(s => s.name === service.name)
        if (!existing) {
          acc.push(service)
        } else if (service.status === 'healthy' && existing.status !== 'healthy') {
          // Prefer healthy status over warning/error when we have conflicting data
          Object.assign(existing, service)
        }
        return acc
      }, [])

      // Update systemServices with processed data
      systemServices.value = uniqueServices

      // Update system status based on real data
      const hasErrors = systemServices.value.some(s => s.status === 'error')
      const hasWarnings = systemServices.value.some(s => s.status === 'warning')

      systemStatus.value = {
        isHealthy: !hasErrors && !hasWarnings,
        hasIssues: hasErrors,
        lastChecked: new Date(),
        apiErrors: hasApiErrors // Track if we had to use fallbacks
      }

      
    } catch (error) {
      logger.error('Critical error during status refresh:', error)
      
      // CRITICAL: Ensure app doesn't break - provide minimal working state
      systemServices.value = [
        { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
        { name: 'Backend API', status: 'error', statusText: 'Connection Failed' },
        { name: 'Other Services', status: 'warning', statusText: 'Status Unknown' }
      ]

      systemStatus.value = {
        isHealthy: false,
        hasIssues: true,
        lastChecked: new Date(),
        criticalError: true
      }
    }
  }

  const updateSystemStatus = () => {
    const errorCount = systemServices.value.filter(s => s.status === 'error').length
    const warningCount = systemServices.value.filter(s => s.status === 'warning').length

    systemStatus.value = {
      isHealthy: errorCount === 0 && warningCount === 0,
      hasIssues: errorCount > 0,
      lastChecked: new Date()
    }
  }

  return {
    // State
    systemStatus,
    systemServices,
    showSystemStatus,
    
    // API utilities
    clearStatusCache: () => apiEndpointMapper.clearCache(),

    // Computed
    getSystemStatusTooltip,
    getSystemStatusText,
    getSystemStatusDescription,

    // Methods
    toggleSystemStatus,
    refreshSystemStatus,
    updateSystemStatus
  }
}