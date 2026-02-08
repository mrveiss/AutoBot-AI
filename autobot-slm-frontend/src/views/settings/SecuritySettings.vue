<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, reactive, onMounted } from 'vue'
import {
  useMfaApi,
  type MFASetupResponse,
  type MFAStatusResponse,
} from '@/composables/useMfaApi'
import {
  useApiKeyApi,
  type APIKeyResponse,
  type APIKeyCreate,
  type APIKeyCreateResponse,
} from '@/composables/useApiKeyApi'

const mfaApi = useMfaApi()
const apiKeyApi = useApiKeyApi()

const loading = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const mfaStatus = ref<MFAStatusResponse | null>(null)
const showMFASetupModal = ref(false)
const setupData = ref<MFASetupResponse | null>(null)
const mfaSetupCode = ref('')
const showBackupCodes = ref(false)
const backupCodes = ref<string[]>([])
const disablePassword = ref('')
const showDisableModal = ref(false)
const showRegenerateModal = ref(false)
const regeneratePassword = ref('')

const apiKeys = ref<APIKeyResponse[]>([])
const availableScopes = ref<Record<string, string>>({})
const showCreateKeyModal = ref(false)
const createdKey = ref<APIKeyCreateResponse | null>(null)
const showKeyCreatedModal = ref(false)
const newKeyForm = reactive<APIKeyCreate>({
  name: '',
  description: '',
  scopes: [],
  expires_days: undefined,
})

async function loadMFAStatus(): Promise<void> {
  try {
    mfaStatus.value = await mfaApi.getMFAStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load MFA status'
  }
}

async function startMFASetup(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    setupData.value = await mfaApi.setupMFA()
    showMFASetupModal.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to start MFA setup'
  } finally {
    loading.value = false
  }
}

async function verifyMFASetup(): Promise<void> {
  if (!mfaSetupCode.value || mfaSetupCode.value.length < 6) {
    error.value = 'Please enter a valid 6-digit code'
    return
  }

  loading.value = true
  error.value = null
  try {
    const result = await mfaApi.verifySetup(mfaSetupCode.value)
    if (result.success) {
      success.value = 'MFA enabled successfully'
      backupCodes.value = setupData.value?.backup_codes || []
      showMFASetupModal.value = false
      showBackupCodes.value = true
      mfaSetupCode.value = ''
      setupData.value = null
      await loadMFAStatus()
    } else {
      error.value = result.message || 'Verification failed'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to verify MFA code'
  } finally {
    loading.value = false
  }
}

function cancelMFASetup(): void {
  showMFASetupModal.value = false
  mfaSetupCode.value = ''
  setupData.value = null
}

async function disableMFA(): Promise<void> {
  if (!disablePassword.value) {
    error.value = 'Password is required'
    return
  }

  loading.value = true
  error.value = null
  try {
    await mfaApi.disableMFA(disablePassword.value)
    success.value = 'MFA disabled successfully'
    showDisableModal.value = false
    disablePassword.value = ''
    await loadMFAStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to disable MFA'
  } finally {
    loading.value = false
  }
}

async function regenerateBackupCodes(): Promise<void> {
  if (!regeneratePassword.value) {
    error.value = 'Password is required'
    return
  }

  loading.value = true
  error.value = null
  try {
    const result = await mfaApi.regenerateBackupCodes(regeneratePassword.value)
    backupCodes.value = result.backup_codes
    showRegenerateModal.value = false
    regeneratePassword.value = ''
    showBackupCodes.value = true
    await loadMFAStatus()
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : 'Failed to regenerate backup codes'
  } finally {
    loading.value = false
  }
}

async function loadAPIKeys(): Promise<void> {
  try {
    const result = await apiKeyApi.listKeys()
    apiKeys.value = result.keys
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load API keys'
  }
}

async function loadScopes(): Promise<void> {
  try {
    availableScopes.value = await apiKeyApi.getScopes()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load scopes'
  }
}

function openCreateKeyModal(): void {
  newKeyForm.name = ''
  newKeyForm.description = ''
  newKeyForm.scopes = []
  newKeyForm.expires_days = undefined
  showCreateKeyModal.value = true
}

async function createAPIKey(): Promise<void> {
  if (!newKeyForm.name || newKeyForm.scopes.length === 0) {
    error.value = 'Name and at least one scope are required'
    return
  }

  loading.value = true
  error.value = null
  try {
    createdKey.value = await apiKeyApi.createKey(newKeyForm)
    showCreateKeyModal.value = false
    showKeyCreatedModal.value = true
    await loadAPIKeys()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create API key'
  } finally {
    loading.value = false
  }
}

async function revokeAPIKey(keyId: string): Promise<void> {
  const confirmed = confirm(
    'Are you sure you want to revoke this API key? This action cannot be undone.'
  )
  if (!confirmed) return

  loading.value = true
  error.value = null
  try {
    await apiKeyApi.revokeKey(keyId)
    success.value = 'API key revoked successfully'
    await loadAPIKeys()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to revoke API key'
  } finally {
    loading.value = false
  }
}

function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text)
  success.value = 'Copied to clipboard'
  setTimeout(() => (success.value = null), 3000)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleString()
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadMFAStatus(), loadAPIKeys(), loadScopes()])
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg p-4">
      <div class="flex items-center gap-2 text-red-700">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span class="text-sm">{{ error }}</span>
      </div>
    </div>

    <div
      v-if="success"
      class="bg-green-50 border border-green-200 rounded-lg p-4"
    >
      <div class="flex items-center gap-2 text-green-700">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span class="text-sm">{{ success }}</span>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-xl font-semibold text-gray-900 mb-4">
        Two-Factor Authentication
      </h2>

      <div v-if="mfaStatus?.enabled" class="space-y-4">
        <div
          class="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start gap-3"
        >
          <svg
            class="w-6 h-6 text-green-600 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
          <div class="flex-1">
            <h3 class="font-semibold text-green-900">MFA is enabled</h3>
            <p class="text-sm text-green-700 mt-1">
              Your account is protected with {{ mfaStatus.method }} authentication
            </p>
            <div class="mt-2 text-sm text-green-700">
              <p>Backup codes remaining: {{ mfaStatus.backup_codes_remaining }}</p>
              <p v-if="mfaStatus.last_verified_at">
                Last verified: {{ formatDate(mfaStatus.last_verified_at) }}
              </p>
            </div>
          </div>
        </div>

        <div class="flex gap-3">
          <button
            @click="showDisableModal = true"
            class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Disable MFA
          </button>
          <button
            @click="showRegenerateModal = true"
            class="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
          >
            Regenerate Backup Codes
          </button>
        </div>
      </div>

      <div v-else class="space-y-4">
        <div
          class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-start gap-3"
        >
          <svg
            class="w-6 h-6 text-yellow-600 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <div>
            <h3 class="font-semibold text-yellow-900">MFA is not enabled</h3>
            <p class="text-sm text-yellow-700 mt-1">
              Enable two-factor authentication to add an extra layer of security
              to your account
            </p>
          </div>
        </div>

        <button
          @click="startMFASetup"
          :disabled="loading"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
        >
          Enable 2FA
        </button>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold text-gray-900">API Keys</h2>
        <button
          @click="openCreateKeyModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Create API Key
        </button>
      </div>

      <div v-if="apiKeys.length === 0" class="text-center py-8 text-gray-500">
        <svg
          class="w-12 h-12 mx-auto mb-3 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
          />
        </svg>
        <p>No API keys created yet</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Name
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Key Prefix
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Scopes
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Usage
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Expires
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="key in apiKeys" :key="key.id">
              <td class="px-4 py-3 whitespace-nowrap">
                <div>
                  <div class="text-sm font-medium text-gray-900">
                    {{ key.name }}
                  </div>
                  <div
                    v-if="key.description"
                    class="text-xs text-gray-500"
                  >
                    {{ key.description }}
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <code
                  class="text-xs bg-gray-100 px-2 py-1 rounded"
                >{{ key.key_prefix }}...</code>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="scope in key.scopes"
                    :key="scope"
                    class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                  >
                    {{ scope }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                <div>{{ key.usage_count }} uses</div>
                <div class="text-xs">{{ formatDate(key.last_used_at) }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                {{ formatDate(key.expires_at) }}
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm">
                <button
                  @click="revokeAPIKey(key.id)"
                  class="text-red-600 hover:text-red-800"
                >
                  Revoke
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div
      v-if="showMFASetupModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          Enable Two-Factor Authentication
        </h3>

        <div class="space-y-4">
          <div class="text-sm text-gray-600">
            <p class="mb-2">
              Scan the QR code with your authenticator app or enter the secret manually:
            </p>
            <div class="bg-gray-50 p-4 rounded border border-gray-200">
              <p class="font-mono text-xs break-all mb-2">
                {{ setupData?.secret }}
              </p>
              <button
                @click="copyToClipboard(setupData?.secret || '')"
                class="text-xs text-primary-600 hover:text-primary-700"
              >
                Copy Secret
              </button>
            </div>
            <p class="mt-3 text-xs">
              Manual Entry URI (for apps that support it):
            </p>
            <div class="bg-gray-50 p-2 rounded border border-gray-200 mt-1">
              <p class="font-mono text-xs break-all">
                {{ setupData?.otpauth_uri }}
              </p>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Enter verification code
            </label>
            <input
              v-model="mfaSetupCode"
              type="text"
              inputmode="numeric"
              maxlength="6"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="000000"
            />
          </div>

          <div class="flex gap-3">
            <button
              @click="verifyMFASetup"
              :disabled="loading || mfaSetupCode.length < 6"
              class="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              Verify and Enable
            </button>
            <button
              @click="cancelMFASetup"
              :disabled="loading"
              class="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showBackupCodes"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          Backup Codes
        </h3>

        <div class="space-y-4">
          <div
            class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800"
          >
            Save these backup codes in a secure location. Each code can only be
            used once.
          </div>

          <div class="bg-gray-50 p-4 rounded border border-gray-200">
            <div class="grid grid-cols-2 gap-2">
              <code
                v-for="(code, idx) in backupCodes"
                :key="idx"
                class="text-sm font-mono"
              >{{ code }}</code>
            </div>
          </div>

          <div class="flex gap-3">
            <button
              @click="copyToClipboard(backupCodes.join('\n'))"
              class="flex-1 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
            >
              Copy All
            </button>
            <button
              @click="showBackupCodes = false"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showDisableModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Disable MFA</h3>

        <div class="space-y-4">
          <p class="text-sm text-gray-600">
            Enter your password to confirm disabling two-factor authentication.
          </p>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              v-model="disablePassword"
              type="password"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Enter your password"
            />
          </div>

          <div class="flex gap-3">
            <button
              @click="disableMFA"
              :disabled="loading || !disablePassword"
              class="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              Disable MFA
            </button>
            <button
              @click="
                (showDisableModal = false), (disablePassword = '')
              "
              :disabled="loading"
              class="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showRegenerateModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          Regenerate Backup Codes
        </h3>

        <div class="space-y-4">
          <div
            class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800"
          >
            This will invalidate your existing backup codes and generate new ones.
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              v-model="regeneratePassword"
              type="password"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Enter your password"
            />
          </div>

          <div class="flex gap-3">
            <button
              @click="regenerateBackupCodes"
              :disabled="loading || !regeneratePassword"
              class="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              Regenerate
            </button>
            <button
              @click="
                (showRegenerateModal = false),
                  (regeneratePassword = '')
              "
              :disabled="loading"
              class="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showCreateKeyModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          Create API Key
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              v-model="newKeyForm.name"
              type="text"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="My API Key"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Description (optional)
            </label>
            <input
              v-model="newKeyForm.description"
              type="text"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="What this key is for"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Scopes
            </label>
            <div class="space-y-2 max-h-48 overflow-y-auto">
              <label
                v-for="(description, scope) in availableScopes"
                :key="scope"
                class="flex items-start gap-2"
              >
                <input
                  v-model="newKeyForm.scopes"
                  type="checkbox"
                  :value="scope"
                  class="mt-1"
                />
                <div>
                  <div class="text-sm font-medium">{{ scope }}</div>
                  <div class="text-xs text-gray-500">{{ description }}</div>
                </div>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Expiration
            </label>
            <select
              v-model="newKeyForm.expires_days"
              class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option :value="undefined">Never</option>
              <option :value="30">30 days</option>
              <option :value="60">60 days</option>
              <option :value="90">90 days</option>
              <option :value="365">1 year</option>
            </select>
          </div>

          <div class="flex gap-3">
            <button
              @click="createAPIKey"
              :disabled="loading || !newKeyForm.name || newKeyForm.scopes.length === 0"
              class="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              Create Key
            </button>
            <button
              @click="showCreateKeyModal = false"
              :disabled="loading"
              class="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showKeyCreatedModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          API Key Created
        </h3>

        <div class="space-y-4">
          <div
            class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800"
          >
            This key will not be shown again. Save it in a secure location.
          </div>

          <div class="bg-gray-50 p-4 rounded border border-gray-200">
            <code class="text-sm font-mono break-all">{{ createdKey?.key }}</code>
          </div>

          <div class="flex gap-3">
            <button
              @click="copyToClipboard(createdKey?.key || '')"
              class="flex-1 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
            >
              Copy Key
            </button>
            <button
              @click="showKeyCreatedModal = false"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
