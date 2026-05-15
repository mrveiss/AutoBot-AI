// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Connection Test Composable
 *
 * Unified connection testing for nodes. Used by FleetOverview,
 * NodeCard, and AddNodeModal.
 *
 * Issue #737 Phase 2: Shared composables
 */

import { ref } from 'vue'
import { useSlmApi } from './useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import type { ConnectionTestResult, ConnectionTestRequest } from '@/types/slm'

export function useNodeConnectionTest() {
  const api = useSlmApi()
  const fleetStore = useFleetStore()

  const isLoading = ref(false)
  const result = ref<ConnectionTestResult | null>(null)
  const error = ref<string | null>(null)

  /**
   * Test connection to a node by its ID.
   * Retrieves node details from store and tests connection.
   */
  async function testByNodeId(nodeId: string): Promise<ConnectionTestResult> {
    const node = fleetStore.getNode(nodeId)
    if (!node) {
      const err: ConnectionTestResult = { success: false, error: `Node ${nodeId} not found` }
      result.value = err
      error.value = err.error || null
      return err
    }

    return testByAddress({
      ip_address: node.ip_address,
      ssh_user: node.ssh_user || 'autobot',
      ssh_port: node.ssh_port || 22,
      auth_method: node.auth_method || 'key',
    })
  }

  /**
   * Test connection using explicit address parameters.
   * Used for testing before node registration.
   */
  async function testByAddress(params: ConnectionTestRequest): Promise<ConnectionTestResult> {
    isLoading.value = true
    error.value = null
    result.value = null

    try {
      const testResult = await api.testConnection(params)
      result.value = testResult
      return testResult
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Connection test failed'
      const errorResult: ConnectionTestResult = {
        success: false,
        error: errorMessage,
      }
      result.value = errorResult
      error.value = errorMessage
      return errorResult
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Reset state for reuse.
   */
  function reset(): void {
    isLoading.value = false
    result.value = null
    error.value = null
  }

  return {
    isLoading,
    result,
    error,
    testByNodeId,
    testByAddress,
    reset,
  }
}
