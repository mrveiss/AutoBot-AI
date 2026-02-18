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
import { getSLMUrl } from '@/config/ssot-config'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'

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
const isLoading = ref(false)
const error = ref<string | null>(null)
const authToken = ref<string | null>(null)

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
// HTTP Helpers
// =============================================================================

async function slmFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const baseUrl = getSLMUrl()
  const url = `${baseUrl}${path}`

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (authToken.value) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${authToken.value}`
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`)
  }

  return response
}

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

    const response = await fetch(`${getSLMUrl()}/api/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
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
  isLoading.value = true
  error.value = null

  try {
    const response = await slmFetch('/api/nodes')
    const data = await response.json()
    nodes.value = data.nodes || []
    return nodes.value
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to fetch nodes'
    error.value = message
    showSubtleErrorNotification('Fetch Nodes Failed', message, 'error')
    logger.error('Error fetching nodes:', err)
    return []
  } finally {
    isLoading.value = false
  }
}

// =============================================================================
// TLS Credential Operations
// =============================================================================

/**
 * Fetch TLS credentials for a specific node.
 */
async function fetchNodeCredentials(nodeId: string): Promise<TLSCredential[]> {
  isLoading.value = true
  error.value = null

  try {
    const response = await slmFetch(`/api/nodes/${nodeId}/tls-credentials`)
    const data = await response.json()
    credentials.value = data.credentials || []
    return credentials.value
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to fetch TLS credentials'
    error.value = message
    showSubtleErrorNotification('Fetch TLS Credentials Failed', message, 'error')
    logger.error('Error fetching TLS credentials:', err)
    return []
  } finally {
    isLoading.value = false
  }
}

/**
 * Create a new TLS credential for a node.
 */
async function createCredential(
  nodeId: string,
  data: TLSCredentialCreate
): Promise<TLSCredential | null> {
  isLoading.value = true
  error.value = null

  try {
    const response = await slmFetch(`/api/nodes/${nodeId}/tls-credentials`, {
      method: 'POST',
      body: JSON.stringify(data),
    })

    const credential = await response.json()
    credentials.value.push(credential)
    showSubtleErrorNotification('TLS Credential Created', 'Certificate uploaded successfully', 'info')
    return credential
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to create TLS credential'
    error.value = message
    showSubtleErrorNotification('Create TLS Credential Failed', message, 'error')
    logger.error('Error creating TLS credential:', err)
    return null
  } finally {
    isLoading.value = false
  }
}

/**
 * Update an existing TLS credential.
 */
async function updateCredential(
  credentialId: string,
  data: TLSCredentialUpdate
): Promise<TLSCredential | null> {
  isLoading.value = true
  error.value = null

  try {
    const response = await slmFetch(`/api/tls/credentials/${credentialId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })

    const updated = await response.json()
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
  } finally {
    isLoading.value = false
  }
}

/**
 * Delete a TLS credential.
 */
async function deleteCredential(credentialId: string): Promise<boolean> {
  isLoading.value = true
  error.value = null

  try {
    await slmFetch(`/api/tls/credentials/${credentialId}`, {
      method: 'DELETE',
    })

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
  } finally {
    isLoading.value = false
  }
}

/**
 * Get a single TLS credential by ID.
 */
async function getCredential(credentialId: string): Promise<TLSCredential | null> {
  try {
    const response = await slmFetch(`/api/tls/credentials/${credentialId}`)
    return await response.json()
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
  isLoading.value = true
  error.value = null

  try {
    const response = await slmFetch('/api/tls/endpoints')
    const data = await response.json()
    endpoints.value = data.endpoints || []
    return endpoints.value
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to fetch TLS endpoints'
    error.value = message
    showSubtleErrorNotification('Fetch TLS Endpoints Failed', message, 'error')
    logger.error('Error fetching TLS endpoints:', err)
    return []
  } finally {
    isLoading.value = false
  }
}

/**
 * Fetch certificates expiring within specified days.
 */
async function fetchExpiringCertificates(days: number = 30): Promise<TLSEndpoint[]> {
  try {
    const response = await slmFetch(`/api/tls/expiring?days=${days}`)
    const data = await response.json()
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
