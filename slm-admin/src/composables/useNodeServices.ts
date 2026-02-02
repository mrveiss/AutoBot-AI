// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Services Composable
 *
 * Service management operations for a specific node.
 * Used by NodeServicesPanel and FleetToolsTab Log Viewer.
 *
 * Issue #737 Phase 2: Shared composables
 */

import { ref, computed, toValue, type MaybeRef } from 'vue'
import { useSlmApi } from './useSlmApi'
import type { ServiceActionResponse, ServiceLogsResponse } from '@/types/slm'

export interface Service {
  name: string
  status: 'running' | 'stopped' | 'failed' | 'unknown'
  pid?: number
  memory_mb?: number
  cpu_percent?: number
  uptime?: string
  category?: 'autobot' | 'system'
}

export function useNodeServices(nodeId: MaybeRef<string>) {
  const api = useSlmApi()

  const services = ref<Service[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const resolvedNodeId = computed(() => toValue(nodeId))

  /**
   * Fetch all services for the node.
   */
  async function fetchServices(): Promise<Service[]> {
    if (!resolvedNodeId.value) {
      error.value = 'No node ID provided'
      return []
    }

    isLoading.value = true
    error.value = null

    try {
      const response = await api.getNodeServices(resolvedNodeId.value)
      services.value = response.services.map(s => ({
        name: s.name,
        status: s.status as Service['status'],
        pid: s.pid,
        memory_mb: s.memory_mb,
        cpu_percent: s.cpu_percent,
        uptime: s.uptime,
        category: s.category,
      }))
      return services.value
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch services'
      return []
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Start a service on the node.
   */
  async function startService(serviceName: string): Promise<ServiceActionResponse> {
    isLoading.value = true
    error.value = null

    try {
      const result = await api.startService(resolvedNodeId.value, serviceName)
      await fetchServices()
      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start service'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Stop a service on the node.
   */
  async function stopService(serviceName: string): Promise<ServiceActionResponse> {
    isLoading.value = true
    error.value = null

    try {
      const result = await api.stopService(resolvedNodeId.value, serviceName)
      await fetchServices()
      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to stop service'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Restart a service on the node.
   */
  async function restartService(serviceName: string): Promise<ServiceActionResponse> {
    isLoading.value = true
    error.value = null

    try {
      const result = await api.restartService(resolvedNodeId.value, serviceName)
      await fetchServices()
      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to restart service'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Get logs for a service.
   */
  async function getLogs(serviceName: string, lines = 100): Promise<string> {
    try {
      const response: ServiceLogsResponse = await api.getServiceLogs(
        resolvedNodeId.value,
        serviceName,
        { lines }
      )
      return response.logs || ''
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch logs'
      return ''
    }
  }

  /**
   * Get a specific service by name.
   */
  function getService(name: string): Service | undefined {
    return services.value.find(s => s.name === name)
  }

  /**
   * Check if a service is running.
   */
  function isServiceRunning(name: string): boolean {
    const service = getService(name)
    return service?.status === 'running'
  }

  return {
    services,
    isLoading,
    error,
    fetchServices,
    startService,
    stopService,
    restartService,
    getLogs,
    getService,
    isServiceRunning,
  }
}
