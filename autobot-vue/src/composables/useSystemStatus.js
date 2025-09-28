/**
 * System Status Management Composable
 * Extracted from App.vue for better maintainability
 */

import { ref, computed } from 'vue'

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
    { name: 'Redis', status: 'warning', statusText: 'Disk Issues' },
    { name: 'Ollama', status: 'error', statusText: 'Disconnected' },
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
      // Get VM status from dedicated backend endpoint (fast)
      const vmResponse = await fetch('/api/vms/status')
      const updatedServices = []

      if (vmResponse.ok) {
        const vmData = await vmResponse.json()

        // Add VM status from backend aggregation
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
      }

      // Get basic services from lightweight endpoint
      try {
        const servicesResponse = await fetch('/api/services', { timeout: 5000 })
        if (servicesResponse.ok) {
          const servicesData = await servicesResponse.json()

          // Map backend services to frontend display
          const serviceMap = {
            'backend': 'Backend API',
            'redis': 'Redis',
            'ollama': 'Ollama'
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
        }
      } catch (e) {
        console.warn('Services endpoint failed, using fallback data')
      }

      // Add frontend and websocket status (local)
      updatedServices.push(
        { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
        { name: 'WebSocket', status: 'healthy', statusText: 'Connected' }
      )

      // Update systemServices with real data
      systemServices.value = updatedServices

      // Update system status based on real data
      const hasErrors = systemServices.value.some(s => s.status === 'error')
      const hasWarnings = systemServices.value.some(s => s.status === 'warning')

      systemStatus.value = {
        isHealthy: !hasErrors && !hasWarnings,
        hasIssues: hasErrors,
        lastChecked: new Date()
      }
    } catch (error) {
      console.warn('Failed to refresh system status:', error)
      // Keep existing values on error
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