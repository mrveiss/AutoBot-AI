<template>
  <div class="tls-certificates-view view-container-flex bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">TLS Certificate Management</h1>
          <p class="text-sm text-gray-600 mt-1">Manage mTLS certificates for secure service communication</p>
        </div>
        <div class="flex items-center space-x-3">
          <button
            @click="refreshEndpoints"
            :disabled="isLoading"
            class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              :class="{ 'animate-spin': isLoading }"
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            Refresh
          </button>
        </div>
      </div>

      <!-- Stats Bar -->
      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div class="bg-gray-50 rounded-lg px-4 py-3 border border-gray-200">
          <div class="text-sm font-medium text-gray-600">Total Certificates</div>
          <div class="text-2xl font-bold text-gray-900">{{ endpoints.length }}</div>
        </div>
        <div class="bg-green-50 rounded-lg px-4 py-3 border border-green-200">
          <div class="text-sm font-medium text-green-600">Active</div>
          <div class="text-2xl font-bold text-green-900">{{ activeCount }}</div>
        </div>
        <div class="bg-yellow-50 rounded-lg px-4 py-3 border border-yellow-200">
          <div class="text-sm font-medium text-yellow-600">Expiring Soon</div>
          <div class="text-2xl font-bold text-yellow-900">{{ expiringSoonCount }}</div>
        </div>
        <div class="bg-blue-50 rounded-lg px-4 py-3 border border-blue-200">
          <div class="text-sm font-medium text-blue-600">Nodes with TLS</div>
          <div class="text-2xl font-bold text-blue-900">{{ nodesWithTLS }}</div>
        </div>
      </div>
    </div>

    <!-- Authentication Notice -->
    <div v-if="!isAuthenticated" class="bg-yellow-50 border-b border-yellow-200 px-6 py-3">
      <div class="flex items-center">
        <svg class="w-5 h-5 text-yellow-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
        </svg>
        <span class="text-sm text-yellow-800">Please authenticate with the SLM backend to manage certificates.</span>
        <button
          @click="showAuthModal = true"
          class="ml-4 text-sm font-medium text-yellow-800 underline hover:text-yellow-900"
        >
          Login
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="flex-1 overflow-y-auto px-6 py-6">
      <!-- Loading State -->
      <div v-if="isLoading && endpoints.length === 0" class="flex items-center justify-center h-64">
        <div class="text-center">
          <svg class="animate-spin h-12 w-12 mx-auto text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p class="mt-4 text-gray-600">Loading certificates...</p>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else-if="endpoints.length === 0" class="text-center py-12">
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
        </svg>
        <h3 class="mt-2 text-sm font-medium text-gray-900">No TLS certificates</h3>
        <p class="mt-1 text-sm text-gray-500">Get started by uploading certificates to your nodes.</p>
        <div class="mt-6">
          <button
            @click="selectNodeForCert"
            :disabled="!isAuthenticated"
            class="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <svg class="-ml-1 mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
            </svg>
            Add Certificate
          </button>
        </div>
      </div>

      <!-- Certificates Table -->
      <div v-else class="bg-white rounded-lg shadow overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Node
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Certificate
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Common Name
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Expiry
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th scope="col" class="relative px-6 py-3">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="endpoint in endpoints" :key="endpoint.credential_id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="text-sm font-medium text-gray-900">{{ endpoint.hostname }}</div>
                <div class="text-sm text-gray-500">{{ endpoint.ip_address }}</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="text-sm text-gray-900">{{ endpoint.name || 'Unnamed' }}</div>
                <div class="text-xs text-gray-500 font-mono">{{ endpoint.credential_id.substring(0, 8) }}...</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ endpoint.common_name || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div v-if="endpoint.expires_at" class="text-sm">
                  <span :class="getExpiryClass(endpoint.days_until_expiry)">
                    {{ formatExpiryDate(endpoint.expires_at) }}
                  </span>
                  <div v-if="endpoint.days_until_expiry !== null" class="text-xs text-gray-500">
                    {{ endpoint.days_until_expiry }} days remaining
                  </div>
                </div>
                <span v-else class="text-sm text-gray-400">Unknown</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="endpoint.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                  class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full"
                >
                  {{ endpoint.is_active ? 'Active' : 'Inactive' }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <button
                  @click="editCredential(endpoint)"
                  class="text-indigo-600 hover:text-indigo-900 mr-3"
                >
                  Edit
                </button>
                <button
                  @click="confirmDelete(endpoint)"
                  class="text-red-600 hover:text-red-900"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TLS Credential Modal -->
    <TLSCredentialModal
      :visible="showCredentialModal"
      :node-id="selectedNodeId"
      :credential="selectedCredential"
      @close="closeCredentialModal"
      @submit="handleCredentialSubmit"
    />

    <!-- Node Selection Modal -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showNodeSelectModal"
          class="fixed inset-0 z-50 overflow-y-auto"
          @click.self="showNodeSelectModal = false"
        >
          <div class="flex min-h-full items-center justify-center p-4">
            <div class="fixed inset-0 bg-gray-500 bg-opacity-75"></div>
            <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
              <h3 class="text-lg font-medium text-gray-900 mb-4">Select Node</h3>
              <p class="text-sm text-gray-500 mb-4">Choose a node to add TLS certificates to:</p>
              <div class="space-y-2 max-h-64 overflow-y-auto">
                <button
                  v-for="node in nodes"
                  :key="node.node_id"
                  @click="selectNode(node.node_id)"
                  class="w-full text-left px-4 py-3 rounded-lg border border-gray-200 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <div class="font-medium text-gray-900">{{ node.hostname }}</div>
                  <div class="text-sm text-gray-500">{{ node.ip_address }}</div>
                </button>
              </div>
              <div class="mt-4 flex justify-end">
                <button
                  @click="showNodeSelectModal = false"
                  class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Auth Modal -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showAuthModal"
          class="fixed inset-0 z-50 overflow-y-auto"
          @click.self="showAuthModal = false"
        >
          <div class="flex min-h-full items-center justify-center p-4">
            <div class="fixed inset-0 bg-gray-500 bg-opacity-75"></div>
            <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
              <h3 class="text-lg font-medium text-gray-900 mb-4">SLM Authentication</h3>
              <form @submit.prevent="handleAuth">
                <div class="space-y-4">
                  <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                    <input
                      v-model="authForm.username"
                      type="text"
                      required
                      class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                    <input
                      v-model="authForm.password"
                      type="password"
                      required
                      class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    />
                  </div>
                </div>
                <div class="mt-6 flex justify-end space-x-3">
                  <button
                    type="button"
                    @click="showAuthModal = false"
                    class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    :disabled="isAuthenticating"
                    class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {{ isAuthenticating ? 'Logging in...' : 'Login' }}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * TLS Certificates View
 *
 * Fleet-wide TLS certificate management dashboard.
 * Issue #725: mTLS Migration
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, computed, onMounted } from 'vue'
import { useTLSCredentials } from '@/composables/useTLSCredentials'
import TLSCredentialModal from '@/components/infrastructure/TLSCredentialModal.vue'
import { createLogger } from '@/utils/debugUtils'
import type { TLSEndpoint, TLSCredential, TLSCredentialCreate, TLSCredentialUpdate } from '@/composables/useTLSCredentials'

const logger = createLogger('TLSCertificatesView')

const {
  endpoints,
  nodes,
  isLoading,
  expiringSoonCount,
  authenticate,
  isAuthenticated: checkAuth,
  fetchAllEndpoints,
  fetchNodes,
  createCredential,
  updateCredential,
  deleteCredential,
  getCredential,
} = useTLSCredentials()

// State
const showCredentialModal = ref(false)
const showNodeSelectModal = ref(false)
const showAuthModal = ref(false)
const selectedNodeId = ref('')
const selectedCredential = ref<TLSCredential | null>(null)
const isAuthenticating = ref(false)
const isAuthenticated = ref(false)

const authForm = ref({
  username: 'admin',
  password: '',
})

// Computed
const activeCount = computed(() => endpoints.value.filter(e => e.is_active).length)
const nodesWithTLS = computed(() => new Set(endpoints.value.map(e => e.node_id)).size)

// Methods
function getExpiryClass(days: number | null): string {
  if (days === null) return 'text-gray-500'
  if (days <= 7) return 'text-red-600 font-medium'
  if (days <= 30) return 'text-yellow-600'
  return 'text-green-600'
}

function formatExpiryDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

async function refreshEndpoints() {
  await fetchAllEndpoints()
}

async function selectNodeForCert() {
  if (nodes.value.length === 0) {
    await fetchNodes()
  }
  showNodeSelectModal.value = true
}

function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId
  selectedCredential.value = null
  showNodeSelectModal.value = false
  showCredentialModal.value = true
}

async function editCredential(endpoint: TLSEndpoint) {
  const cred = await getCredential(endpoint.credential_id)
  if (cred) {
    selectedNodeId.value = endpoint.node_id
    selectedCredential.value = cred
    showCredentialModal.value = true
  }
}

function closeCredentialModal() {
  showCredentialModal.value = false
  selectedCredential.value = null
  selectedNodeId.value = ''
}

async function handleCredentialSubmit(data: TLSCredentialCreate | TLSCredentialUpdate) {
  if (selectedCredential.value) {
    await updateCredential(selectedCredential.value.credential_id, data as TLSCredentialUpdate)
  } else {
    await createCredential(selectedNodeId.value, data as TLSCredentialCreate)
  }
  closeCredentialModal()
  await refreshEndpoints()
}

async function confirmDelete(endpoint: TLSEndpoint) {
  if (confirm(`Delete certificate "${endpoint.name || endpoint.credential_id}" from ${endpoint.hostname}?`)) {
    await deleteCredential(endpoint.credential_id)
    await refreshEndpoints()
  }
}

async function handleAuth() {
  isAuthenticating.value = true
  try {
    const success = await authenticate(authForm.value.username, authForm.value.password)
    if (success) {
      isAuthenticated.value = true
      showAuthModal.value = false
      await refreshEndpoints()
      await fetchNodes()
    }
  } finally {
    isAuthenticating.value = false
    authForm.value.password = ''
  }
}

onMounted(async () => {
  // Check if already authenticated (token might be cached)
  isAuthenticated.value = checkAuth()
  if (isAuthenticated.value) {
    await refreshEndpoints()
    await fetchNodes()
  }
})
</script>
