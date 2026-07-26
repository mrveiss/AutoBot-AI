// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * TLS Certificate Management Composable
 *
 * Provides state management and API integration for TLS certificate management
 * via the SLM (Service Lifecycle Manager) backend.
 *
 * Issue #725: mTLS Migration - Frontend TLS Management
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, computed } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import { SlmClient } from '@/utils/slmClient'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from './useLoadingState'

const logger = createLogger('useTLSCredentials')

// =============================================================================
// Types
// =============================================================================

export interface TLSCredential {
  id: number
  credential_id: string
  node_id: string
  name: string | null
  common_name: string | null
  expires_at: string | null
  fingerprint: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TLSEndpoint {
  credential_id: string
  node_id: string
  hostname: string
  ip_address: string
  name: string | null
  common_name: string | null
  expires_at: string | null
  is_active: boolean
  days_until_expiry: number | null
}

export interface TLSCredentialCreate {
  name?: string
  ca_cert: string
  server_cert: string
  server_key: string
}

export interface TLSCredentialUpdate {
  name?: string
  ca_cert?: string
  server_cert?: string
  server_key?: string
  is_active?: boolean
}

export interface SLMNode {
  id: number
  node_id: string
  hostname: string
  ip_address: string
  status: string
  roles: string[]
}

// =============================================================================
// State
// =============================================================================

const credentials = ref<TLSCredential[]>([])
const endpoints = ref<TLSEndpoint[]>([])
const nodes = ref<SLMNode[]>([])
const { isLoading, wrap } = useLoadingState()
const error = ref<string | null>(null)
const authToken = ref<string | null>(null)

// SLM bridge scoped to this composable's in-memory token (read live per request).
// The base URL (getSLMUrl) and token injection are owned by the canonical bridge;
// endpoint paths keep the getApiBase() prefix exactly as before.
const slm = new SlmClient(() => authToken.value)

// =============================================================================
// Computed
// =============================================================================

const activeCredentials = computed(() =>
  credentials.value.filter(c => c.is_active)
)

const expiringCredentials = computed(() =>
  endpoints.value.filter(e =>
    e.days_until_expiry !== null && e.days_until_expiry <= 30
  )
)

const expiringSoonCount = computed(() => expiringCredentials.value.length)

// =============================================================================
// Authentication
// =============================================================================

/**
 * Authenticate with SLM backend.
 */
async function authenticate(username: string, password: string): Promise<boolean> {
  try {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    // Token-acquisition endpoint: credential-based, so skip bearer injection.
    const response = await slm.rawRequest('/api/auth/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
      skipAuth: true,
    })

    if (!response.ok) {
      throw new Error('Authentication failed')
    }

    const data = await response.json()
    authToken.value = data.access_token
    return true
  } catch (err: unknown) {
    logger.error('SLM authentication failed:', err)
    return false
  }
}

/**
 * Set authentication token directly.
 */
function setAuthToken(token: string): void {
  authToken.value = token
}

/**
 * Check if authenticated.
 */
function isAuthenticated(): boolean {
  return authToken.value !== null
}

// =============================================================================
// Node Operations
// =============================================================================

/**
 * Fetch all nodes from SLM.
 */
async function fetchNodes(): Promise<SLMNode[]> {
  error.value = null
  return wrap(async () => {
    try {
      const data = await slm.get<{ nodes?: SLMNode[] }>(`${getApiBase()}/nodes`)
      nodes.value = data.nodes || []
      return nodes.value
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch nodes'
      error.value = message
      showSubtleErrorNotification('Fetch Nodes Failed', message, 'error')
      logger.error('Error fetching nodes:', err)
      return []
    }
  })
}

// =============================================================================
// TLS Credential Operations
// =============================================================================

/**
 * Fetch TLS credentials for a specific node.
 */
async function fetchNodeCredentials(nodeId: string): Promise<TLSCredential[]> {
  error.value = null
  return wrap(async () => {
    try {
      const data = await slm.get<{ credentials?: TLSCredential[] }>(
        `${getApiBase()}/nodes/${nodeId}/tls-credentials`
      )
      credentials.value = data.credentials || []
      return credentials.value
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch TLS credentials'
      error.value = message
      showSubtleErrorNotification('Fetch TLS Credentials Failed', message, 'error')
      logger.error('Error fetching TLS credentials:', err)
      return []
    }
  })
}

/**
 * Create a new TLS credential for a node.
 */
async function createCredential(
  nodeId: string,
  data: TLSCredentialCreate
): Promise<TLSCredential | null> {
  error.value = null
  return wrap(async () => {
    try {
      const credential = await slm.post<TLSCredential>(
        `${getApiBase()}/nodes/${nodeId}/tls-credentials`,
        data
      )
      credentials.value.push(credential)
      showSubtleErrorNotification('TLS Credential Created', 'Certificate uploaded successfully', 'info')
      return credential
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create TLS credential'
      error.value = message
      showSubtleErrorNotification('Create TLS Credential Failed', message, 'error')
      logger.error('Error creating TLS credential:', err)
      return null
    }
  })
}

/**
 * Update an existing TLS credential.
 */
async function updateCredential(
  credentialId: string,
  data: TLSCredentialUpdate
): Promise<TLSCredential | null> {
  error.value = null
  return wrap(async () => {
    try {
      const updated = await slm.patch<TLSCredential>(
        `${getApiBase()}/tls/credentials/${credentialId}`,
        data
      )
      const index = credentials.value.findIndex(c => c.credential_id === credentialId)
      if (index !== -1) {
        credentials.value[index] = updated
      }
      showSubtleErrorNotification('TLS Credential Updated', 'Certificate updated successfully', 'info')
      return updated
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to update TLS credential'
      error.value = message
      showSubtleErrorNotification('Update TLS Credential Failed', message, 'error')
      logger.error('Error updating TLS credential:', err)
      return null
    }
  })
}

/**
 * Delete a TLS credential.
 */
async function deleteCredential(credentialId: string): Promise<boolean> {
  error.value = null
  return wrap(async () => {
    try {
      await slm.delete(`${getApiBase()}/tls/credentials/${credentialId}`)
      credentials.value = credentials.value.filter(c => c.credential_id !== credentialId)
      endpoints.value = endpoints.value.filter(e => e.credential_id !== credentialId)
      showSubtleErrorNotification('TLS Credential Deleted', 'Certificate removed successfully', 'info')
      return true
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete TLS credential'
      error.value = message
      showSubtleErrorNotification('Delete TLS Credential Failed', message, 'error')
      logger.error('Error deleting TLS credential:', err)
      return false
    }
  })
}

/**
 * Get a single TLS credential by ID.
 */
async function getCredential(credentialId: string): Promise<TLSCredential | null> {
  try {
    return await slm.get<TLSCredential>(`${getApiBase()}/tls/credentials/${credentialId}`)
  } catch (err: unknown) {
    logger.error('Error fetching TLS credential:', err)
    return null
  }
}

// =============================================================================
// Fleet-wide Operations
// =============================================================================

/**
 * Fetch all TLS endpoints across the fleet.
 */
async function fetchAllEndpoints(): Promise<TLSEndpoint[]> {
  error.value = null
  return wrap(async () => {
    try {
      const data = await slm.get<{ endpoints?: TLSEndpoint[] }>(`${getApiBase()}/tls/endpoints`)
      endpoints.value = data.endpoints || []
      return endpoints.value
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch TLS endpoints'
      error.value = message
      showSubtleErrorNotification('Fetch TLS Endpoints Failed', message, 'error')
      logger.error('Error fetching TLS endpoints:', err)
      return []
    }
  })
}

/**
 * Fetch certificates expiring within specified days.
 */
async function fetchExpiringCertificates(days: number = 30): Promise<TLSEndpoint[]> {
  try {
    const data = await slm.get<{ endpoints?: TLSEndpoint[] }>(
      `${getApiBase()}/tls/expiring?days=${days}`
    )
    return data.endpoints || []
  } catch (err: unknown) {
    logger.error('Error fetching expiring certificates:', err)
    return []
  }
}

// =============================================================================
// Export Composable
// =============================================================================

export function useTLSCredentials() {
  return {
    // State
    credentials,
    endpoints,
    nodes,
    isLoading,
    error,

    // Computed
    activeCredentials,
    expiringCredentials,
    expiringSoonCount,

    // Authentication
    authenticate,
    setAuthToken,
    isAuthenticated,

    // Node Operations
    fetchNodes,

    // Credential Operations
    fetchNodeCredentials,
    createCredential,
    updateCredential,
    deleteCredential,
    getCredential,

    // Fleet Operations
    fetchAllEndpoints,
    fetchExpiringCertificates,
  }
}
