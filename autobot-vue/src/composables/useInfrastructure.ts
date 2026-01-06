/**
 * Infrastructure Management Composable
 *
 * Provides state management and API integration for Ansible IaC infrastructure management
 */

import { ref, computed } from 'vue'
import { useApi } from './useApi'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useInfrastructure
const logger = createLogger('useInfrastructure')

export interface Host {
  id: string
  hostname: string
  ip_address: string
  ssh_user: string
  ssh_key_path?: string
  ssh_password?: string
  description?: string
  tags?: string[]
  ansible_group?: string
  status?: 'pending' | 'active' | 'error' | 'deploying'
  created_at?: string
  updated_at?: string
  last_deployed_at?: string
}

export interface Deployment {
  id: string
  host_ids: string[]
  status: 'pending' | 'running' | 'success' | 'failed'
  started_at?: string
  completed_at?: string
  logs?: string[]
  playbook?: string
}

export function useInfrastructure() {
  const api = useApi()

  // State
  const hosts = ref<Host[]>([])
  const deployments = ref<Deployment[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const activeHosts = computed(() => hosts.value.filter(h => h.status === 'active'))
  const pendingHosts = computed(() => hosts.value.filter(h => h.status === 'pending'))
  const errorHosts = computed(() => hosts.value.filter(h => h.status === 'error'))

  // API Methods

  /**
   * Fetch all hosts
   */
  async function fetchHosts() {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.get('/api/iac/hosts')
      const data = await response.json()
      hosts.value = data.hosts || []
      return data
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch hosts'
      // Issue #156 Fix: Handle null error.value with fallback
      showSubtleErrorNotification('Fetch Hosts Failed', error.value || 'Unknown error', 'error')
      logger.error('Error fetching hosts:', err)
      return { hosts: [] }
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Add new host
   */
  async function addHost(hostData: Partial<Host> | FormData) {
    isLoading.value = true
    error.value = null

    try {
      let response: any

      if (hostData instanceof FormData) {
        response = await api.post('/api/iac/hosts', hostData, {
          headers: {} // Let browser set multipart/form-data boundary
        })
      } else {
        response = await api.post('/api/iac/hosts', hostData)
      }

      const data = typeof response.json === 'function' ? await response.json() : response

      if (data.id) {
        hosts.value.push(data as Host)
      }

      // Issue #156 Fix: Change 'success' to 'info' (valid severity type)
      showSubtleErrorNotification('Host Added', `Successfully added ${data.hostname}`, 'info')
      return data
    } catch (err: any) {
      error.value = err.message || 'Failed to add host'
      // Issue #156 Fix: Handle null error.value with fallback
      showSubtleErrorNotification('Add Host Failed', error.value || 'Unknown error', 'error')
      logger.error('Error adding host:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Update existing host
   */
  async function updateHost(hostId: string, updates: Partial<Host>) {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.put(`/api/iac/hosts/${hostId}`, updates)
      const data = await response.json()

      const index = hosts.value.findIndex(h => h.id === hostId)
      if (index !== -1) {
        hosts.value[index] = { ...hosts.value[index], ...data }
      }

      // Issue #156 Fix: Change 'success' to 'info' (valid severity type)
      showSubtleErrorNotification('Host Updated', `Successfully updated ${data.hostname}`, 'info')
      return data
    } catch (err: any) {
      error.value = err.message || 'Failed to update host'
      // Issue #156 Fix: Handle null error.value with fallback
      showSubtleErrorNotification('Update Host Failed', error.value || 'Unknown error', 'error')
      logger.error('Error updating host:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Delete host
   */
  async function deleteHost(hostId: string) {
    isLoading.value = true
    error.value = null

    try {
      await api.delete(`/api/iac/hosts/${hostId}`)
      hosts.value = hosts.value.filter(h => h.id !== hostId)
      // Issue #156 Fix: Change 'success' to 'info' (valid severity type)
      showSubtleErrorNotification('Host Deleted', 'Successfully deleted host', 'info')
    } catch (err: any) {
      error.value = err.message || 'Failed to delete host'
      // Issue #156 Fix: Handle null error.value with fallback
      showSubtleErrorNotification('Delete Host Failed', error.value || 'Unknown error', 'error')
      logger.error('Error deleting host:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Deploy to host(s)
   */
  async function deployHost(hostIds: string[], playbook?: string) {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.post('/api/iac/deployments', {
        host_ids: hostIds,
        playbook: playbook || 'default.yml'
      })

      const data = await response.json()
      deployments.value.push(data as Deployment)

      // Update host status to deploying
      hostIds.forEach(hostId => {
        const host = hosts.value.find(h => h.id === hostId)
        if (host) {
          host.status = 'deploying'
        }
      })

      // Issue #156 Fix: Change 'success' to 'info' (valid severity type)
      showSubtleErrorNotification('Deployment Started', `Deploying to ${hostIds.length} host(s)`, 'info')
      return data
    } catch (err: any) {
      error.value = err.message || 'Failed to start deployment'
      // Issue #156 Fix: Handle null error.value with fallback
      showSubtleErrorNotification('Deployment Failed', error.value || 'Unknown error', 'error')
      logger.error('Error deploying:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Get deployment status
   */
  async function getDeploymentStatus(deploymentId: string) {
    try {
      const response = await api.get(`/api/iac/deployments/${deploymentId}`)
      const data = await response.json()

      // Update deployment in list
      const index = deployments.value.findIndex(d => d.id === deploymentId)
      if (index !== -1) {
        deployments.value[index] = data as Deployment
      }

      return data
    } catch (err: any) {
      logger.error('Error fetching deployment status:', err)
      return null
    }
  }

  /**
   * Get deployment logs (real-time or final)
   */
  async function getDeploymentLogs(deploymentId: string) {
    try {
      const response = await api.get(`/api/iac/deployments/${deploymentId}/logs`)
      const data = await response.json()
      return data.logs || []
    } catch (err: any) {
      logger.error('Error fetching deployment logs:', err)
      return []
    }
  }

  /**
   * Test SSH connection to host
   */
  async function testHostConnection(hostId: string) {
    try {
      const response = await api.post(`/api/iac/hosts/${hostId}/test`)
      const data = await response.json()

      if (data.success) {
        // Issue #156 Fix: Change 'success' to 'info' (valid severity type)
        showSubtleErrorNotification('Connection Test', 'Successfully connected to host', 'info')
      } else {
        showSubtleErrorNotification('Connection Test', data.error || 'Failed to connect', 'error')
      }

      return data
    } catch (err: any) {
      showSubtleErrorNotification('Connection Test', err.message || 'Connection test failed', 'error')
      logger.error('Error testing connection:', err)
      return { success: false, error: err.message }
    }
  }

  return {
    // State
    hosts,
    deployments,
    isLoading,
    error,

    // Computed
    activeHosts,
    pendingHosts,
    errorHosts,

    // Methods
    fetchHosts,
    addHost,
    updateHost,
    deleteHost,
    deployHost,
    getDeploymentStatus,
    getDeploymentLogs,
    testHostConnection
  }
}
