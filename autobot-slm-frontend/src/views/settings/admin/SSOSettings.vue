// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * SSOSettings - SSO/OIDC Provider Configuration (MVA-1735)
 *
 * Admin-only page for managing SSO/OIDC/LDAP/SAML provider configuration.
 * Backend fully implemented; composable at src/composables/useSsoApi.ts.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import {
  useSsoApi,
  type SSOProviderResponse,
  type SSOProviderCreate,
  type SSOProviderUpdate,
  type SSOProviderHealthResponse,
} from '@/composables/useSsoApi'
import { getStatusBadgeClass, getStatusLabel } from '@/utils/node-status'

const api = useSsoApi()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)

const providers = ref<SSOProviderResponse[]>([])
const showCreateForm = ref(false)
const editingProvider = ref<SSOProviderResponse | null>(null)

// Health dashboard state
const healthMap = ref<Record<string, SSOProviderHealthResponse>>({})

function providerHealth(providerId: string): SSOProviderHealthResponse | null {
  return healthMap.value[providerId] ?? null
}

// Provider types with their endpoint templates
const PROVIDER_TYPES = [
  { value: 'okta', label: 'Okta' },
  { value: 'azure_ad', label: 'Azure AD (Microsoft Entra)' },
  { value: 'google', label: 'Google Workspace' },
  { value: 'ldap', label: 'LDAP' },
  { value: 'saml', label: 'SAML' },
  { value: 'generic_oidc', label: 'Generic OIDC' },
]

interface ProviderFormData {
  name: string
  provider_type: string
  is_active: boolean
  allow_user_creation: boolean
  default_role: string
  // OAuth2/OIDC fields
  okta_domain?: string
  azure_tenant_id?: string
  client_id?: string
  client_secret?: string
  client_secret_changed: boolean
  authorize_url?: string
  token_url?: string
  userinfo_url?: string
  scope?: string
  // LDAP fields
  server_uri?: string
  bind_dn?: string
  bind_password?: string
  base_dn?: string
  search_filter?: string
  user_dn_template?: string
  // SAML fields
  sp_entity_id?: string
  acs_url?: string
  idp_metadata_url?: string
  // Claim mapping
  claim_email?: string
  claim_display_name?: string
  claim_username?: string
  claim_groups?: string
}

const formData = reactive<ProviderFormData>({
  name: '',
  provider_type: 'okta',
  is_active: true,
  allow_user_creation: true,
  default_role: 'user',
  client_secret_changed: false,
  scope: 'openid email profile',
  claim_email: 'email',
  claim_display_name: 'name',
  claim_username: 'preferred_username',
  claim_groups: 'groups',
})

function showSuccessMsg(msg: string) {
  success.value = msg
  setTimeout(() => { success.value = null }, 3000)
}

function showErrorMsg(msg: string) {
  error.value = msg
}

// Auto-fill endpoint URLs based on provider type
function autofillEndpoints() {
  if (formData.provider_type === 'okta' && formData.okta_domain) {
    const domain = formData.okta_domain
    formData.authorize_url = `https://${domain}/oauth2/v1/authorize`
    formData.token_url = `https://${domain}/oauth2/v1/token`
    formData.userinfo_url = `https://${domain}/oauth2/v1/userinfo`
  } else if (formData.provider_type === 'azure_ad' && formData.azure_tenant_id) {
    const tenant = formData.azure_tenant_id
    formData.authorize_url = `https://login.microsoftonline.com/${tenant}/oauth2/v2.0/authorize`
    formData.token_url = `https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`
    formData.userinfo_url = `https://graph.microsoft.com/v1.0/me`
  } else if (formData.provider_type === 'google') {
    formData.authorize_url = 'https://accounts.google.com/o/oauth2/v2/auth'
    formData.token_url = 'https://oauth2.googleapis.com/token'
    formData.userinfo_url = 'https://openidconnect.googleapis.com/v1/userinfo'
  }
}

const isOAuth2Provider = computed(() => {
  return ['okta', 'azure_ad', 'google', 'generic_oidc'].includes(formData.provider_type)
})

const isLDAPProvider = computed(() => {
  return formData.provider_type === 'ldap'
})

const isSAMLProvider = computed(() => {
  return formData.provider_type === 'saml'
})

async function fetchProviders(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [listResponse, healthItems] = await Promise.all([
      api.listProviders(),
      api.getProvidersHealth().catch(() => [] as SSOProviderHealthResponse[]),
    ])
    providers.value = listResponse.providers
    healthMap.value = Object.fromEntries(healthItems.map((h) => [h.provider_id, h]))
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Failed to load SSO providers'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(formData, {
    name: '',
    provider_type: 'okta',
    is_active: true,
    allow_user_creation: true,
    default_role: 'user',
    client_secret_changed: false,
    scope: 'openid email profile',
    claim_email: 'email',
    claim_display_name: 'name',
    claim_username: 'preferred_username',
    claim_groups: 'groups',
    okta_domain: '',
    azure_tenant_id: '',
    client_id: '',
    client_secret: '',
    authorize_url: '',
    token_url: '',
    userinfo_url: '',
    server_uri: '',
    bind_dn: '',
    bind_password: '',
    base_dn: '',
    search_filter: '',
    user_dn_template: '',
    sp_entity_id: '',
    acs_url: '',
    idp_metadata_url: '',
  })
  editingProvider.value = null
}

function openCreateForm() {
  resetForm()
  showCreateForm.value = true
}

function closeForm() {
  showCreateForm.value = false
  resetForm()
}

function editProvider(provider: SSOProviderResponse) {
  editingProvider.value = provider
  showCreateForm.value = true

  // Populate form with provider data
  formData.name = provider.name
  formData.provider_type = provider.provider_type
  formData.is_active = provider.is_active
  formData.allow_user_creation = provider.allow_user_creation
  formData.default_role = provider.default_role || 'user'
  formData.client_secret_changed = false
  formData.client_secret = '' // Write-only, show as ••••

  // Parse config object (provider-specific fields stored in config JSON)
  const cfg = provider as unknown as { config?: Record<string, unknown> }
  if (cfg.config) {
    // OAuth2/OIDC fields
    formData.client_id = cfg.config.client_id as string
    formData.authorize_url = cfg.config.authorize_url as string
    formData.token_url = cfg.config.token_url as string
    formData.userinfo_url = cfg.config.userinfo_url as string
    formData.scope = (cfg.config.scope as string) || 'openid email profile'
    // LDAP fields
    formData.server_uri = cfg.config.server_uri as string
    formData.bind_dn = cfg.config.bind_dn as string
    formData.base_dn = cfg.config.base_dn as string
    formData.search_filter = cfg.config.search_filter as string
    formData.user_dn_template = cfg.config.user_dn_template as string
    // SAML fields
    formData.sp_entity_id = cfg.config.sp_entity_id as string
    formData.acs_url = cfg.config.acs_url as string
    formData.idp_metadata_url = cfg.config.idp_metadata_url as string
    // Claim mapping
    const mapping = cfg.config.claim_mapping as Record<string, string> | undefined
    if (mapping) {
      formData.claim_email = mapping.email || 'email'
      formData.claim_display_name = mapping.display_name || 'name'
      formData.claim_username = mapping.username || 'preferred_username'
      formData.claim_groups = mapping.groups || 'groups'
    }
  }
}

async function saveProvider(): Promise<void> {
  if (!formData.name) {
    error.value = 'Provider name is required'
    return
  }

  saving.value = true
  error.value = null

  try {
    // Build config object based on provider type
    const config: Record<string, unknown> = {}

    if (isOAuth2Provider.value) {
      config.client_id = formData.client_id
      if (formData.client_secret_changed && formData.client_secret) {
        config.client_secret = formData.client_secret
      }
      config.authorize_url = formData.authorize_url
      config.token_url = formData.token_url
      config.userinfo_url = formData.userinfo_url
      config.scope = formData.scope
    } else if (isLDAPProvider.value) {
      config.server_uri = formData.server_uri
      config.bind_dn = formData.bind_dn
      if (formData.bind_password) {
        config.bind_password = formData.bind_password
      }
      config.base_dn = formData.base_dn
      config.search_filter = formData.search_filter
      config.user_dn_template = formData.user_dn_template
    } else if (isSAMLProvider.value) {
      config.sp_entity_id = formData.sp_entity_id
      config.acs_url = formData.acs_url
      config.idp_metadata_url = formData.idp_metadata_url
    }

    // Add claim mapping
    config.claim_mapping = {
      email: formData.claim_email,
      display_name: formData.claim_display_name,
      username: formData.claim_username,
      groups: formData.claim_groups,
    }

    if (editingProvider.value) {
      // Update existing provider
      const updateData: SSOProviderUpdate = {
        name: formData.name,
        is_active: formData.is_active,
        allow_user_creation: formData.allow_user_creation,
        default_role: formData.default_role,
        config,
      }
      await api.updateProvider(editingProvider.value.id, updateData)
      showSuccessMsg('Provider updated successfully')
    } else {
      // Create new provider
      const createData: SSOProviderCreate = {
        name: formData.name,
        provider_type: formData.provider_type,
        is_active: formData.is_active,
        allow_user_creation: formData.allow_user_creation,
        default_role: formData.default_role,
        config,
      }
      await api.createProvider(createData)
      showSuccessMsg('Provider created successfully')
    }

    closeForm()
    await fetchProviders()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Failed to save provider'
  } finally {
    saving.value = false
  }
}

async function toggleProvider(provider: SSOProviderResponse): Promise<void> {
  try {
    await api.updateProvider(provider.id, {
      is_active: !provider.is_active,
    })
    provider.is_active = !provider.is_active
    showSuccessMsg(`Provider ${provider.is_active ? 'enabled' : 'disabled'}`)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    showErrorMsg(err.response?.data?.detail || 'Failed to toggle provider')
  }
}

async function testConnection(provider: SSOProviderResponse): Promise<void> {
  testing.value = true
  testResult.value = null
  error.value = null

  try {
    const result = await api.testProvider(provider.id)
    testResult.value = result
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    testResult.value = {
      success: false,
      message: err.response?.data?.detail || 'Connection test failed',
    }
  } finally {
    testing.value = false
  }
}

async function deleteProvider(provider: SSOProviderResponse): Promise<void> {
  if (!confirm(`Delete SSO provider "${provider.name}"? This cannot be undone.`)) {
    return
  }

  try {
    await api.deleteProvider(provider.id)
    showSuccessMsg('Provider deleted successfully')
    await fetchProviders()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    showErrorMsg(err.response?.data?.detail || 'Failed to delete provider')
  }
}

onMounted(fetchProviders)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div
      v-if="error"
      class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button class="ml-auto text-red-500 hover:text-red-700" @click="error = null" aria-label="Dismiss error">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div
      v-if="success"
      class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Test Result Banner -->
    <div
      v-if="testResult"
      class="p-4 rounded-lg flex items-center gap-3"
      :class="testResult.success
        ? 'bg-green-50 border border-green-200 text-green-700'
        : 'bg-red-50 border border-red-200 text-red-700'"
    >
      <svg v-if="testResult.success" class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
      </svg>
      <svg v-else class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
      {{ testResult.message }}
      <button class="ml-auto opacity-60 hover:opacity-100" @click="testResult = null" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">SSO / OIDC Configuration</h2>
        <p class="text-sm text-gray-500 mt-1">Manage single sign-on providers for user authentication</p>
      </div>
      <button
        @click="openCreateForm"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        Add Provider
      </button>
    </div>

    <!-- Provider List -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
    </div>

    <div v-else-if="providers.length === 0" class="text-center py-12">
      <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
      </svg>
      <p class="text-gray-500">No SSO providers configured</p>
      <button
        @click="openCreateForm"
        class="mt-4 text-blue-600 hover:text-blue-700"
      >
        Add your first provider
      </button>
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="provider in providers"
        :key="provider.id"
        class="bg-white border border-gray-200 rounded-lg p-4"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-3">
              <h3 class="font-medium text-gray-900">{{ provider.name }}</h3>
              <span
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="provider.is_active
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-600'"
              >
                {{ provider.is_active ? 'Enabled' : 'Disabled' }}
              </span>
              <!-- Health badge (sourced from /sso-providers/health) -->
              <span
                v-if="providerHealth(provider.id)"
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="getStatusBadgeClass(providerHealth(provider.id)!.health_status)"
              >
                {{ getStatusLabel(providerHealth(provider.id)!.health_status) }}
              </span>
              <span class="text-xs text-gray-500 uppercase tracking-wide">
                {{ PROVIDER_TYPES.find(t => t.value === provider.provider_type)?.label || provider.provider_type }}
              </span>
            </div>
            <div class="mt-2 text-sm text-gray-600 space-y-1">
              <p>Default role: <span class="font-medium">{{ provider.default_role || 'user' }}</span></p>
              <p>Allow user creation: <span class="font-medium">{{ provider.allow_user_creation ? 'Yes' : 'No' }}</span></p>
              <template v-if="providerHealth(provider.id)">
                <p class="text-xs text-gray-500">
                  Logins (7d): {{ providerHealth(provider.id)!.success_count }} success /
                  {{ providerHealth(provider.id)!.failure_count }} failed
                </p>
                <p v-if="providerHealth(provider.id)!.last_success_at" class="text-xs text-gray-500">
                  Last success: {{ new Date(providerHealth(provider.id)!.last_success_at!).toLocaleString() }}
                </p>
              </template>
              <p v-if="provider.last_sync_at" class="text-xs text-gray-500">
                Last sync: {{ new Date(provider.last_sync_at).toLocaleString() }}
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <!-- Test Connection (LDAP only) -->
            <button
              v-if="provider.provider_type === 'ldap'"
              @click="testConnection(provider)"
              :disabled="testing"
              class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {{ testing ? 'Testing...' : 'Test' }}
            </button>

            <!-- Toggle Enable/Disable -->
            <button
              @click="toggleProvider(provider)"
              class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {{ provider.is_active ? 'Disable' : 'Enable' }}
            </button>

            <!-- Edit -->
            <button
              @click="editProvider(provider)"
              class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Edit
            </button>

            <!-- Delete -->
            <button
              @click="deleteProvider(provider)"
              class="px-3 py-1.5 text-sm text-red-600 border border-red-300 rounded-lg hover:bg-red-50 transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Form Modal -->
    <div
      v-if="showCreateForm"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      @click.self="closeForm"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h3 class="text-lg font-semibold">
            {{ editingProvider ? 'Edit' : 'Create' }} SSO Provider
          </h3>
          <button @click="closeForm" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="p-6 space-y-6">
          <!-- Basic Info -->
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Provider Name</label>
              <input
                v-model="formData.name"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., Company Okta"
              />
            </div>

            <div v-if="!editingProvider">
              <label class="block text-sm font-medium text-gray-700 mb-1">Provider Type</label>
              <select
                v-model="formData.provider_type"
                @change="autofillEndpoints"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option v-for="type in PROVIDER_TYPES" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
            </div>

            <div class="flex items-center gap-4">
              <label class="flex items-center gap-2">
                <input
                  v-model="formData.is_active"
                  type="checkbox"
                  class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
                <span class="text-sm text-gray-700">Enabled</span>
              </label>

              <label class="flex items-center gap-2">
                <input
                  v-model="formData.allow_user_creation"
                  type="checkbox"
                  class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                />
                <span class="text-sm text-gray-700">Allow user creation</span>
              </label>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Default Role</label>
              <select
                v-model="formData.default_role"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>

          <!-- OAuth2/OIDC Fields -->
          <div v-if="isOAuth2Provider" class="space-y-4 border-t border-gray-200 pt-6">
            <h4 class="font-medium text-gray-900">OAuth2 / OIDC Configuration</h4>

            <!-- Provider-specific templates -->
            <div v-if="formData.provider_type === 'okta'">
              <label class="block text-sm font-medium text-gray-700 mb-1">Okta Domain</label>
              <input
                v-model="formData.okta_domain"
                @blur="autofillEndpoints"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., company.okta.com"
              />
              <p class="mt-1 text-xs text-gray-500">Endpoints will be auto-filled based on your domain</p>
            </div>

            <div v-if="formData.provider_type === 'azure_ad'">
              <label class="block text-sm font-medium text-gray-700 mb-1">Tenant ID</label>
              <input
                v-model="formData.azure_tenant_id"
                @blur="autofillEndpoints"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., 12345678-1234-1234-1234-123456789012"
              />
              <p class="mt-1 text-xs text-gray-500">Endpoints will be auto-filled based on your tenant ID</p>
            </div>

            <div v-if="formData.provider_type === 'google'">
              <p class="text-sm text-gray-600 bg-blue-50 border border-blue-200 rounded-lg p-3">
                Google Workspace endpoints are pre-configured. Just enter your OAuth2 credentials below.
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
              <input
                v-model="formData.client_id"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Client Secret
                <span v-if="editingProvider" class="text-xs text-gray-500">(leave blank to keep current)</span>
              </label>
              <input
                v-model="formData.client_secret"
                @input="formData.client_secret_changed = true"
                type="password"
                :placeholder="editingProvider ? '••••••••' : ''"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Authorization URL</label>
              <input
                v-model="formData.authorize_url"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Token URL</label>
              <input
                v-model="formData.token_url"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">UserInfo URL</label>
              <input
                v-model="formData.userinfo_url"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Scope</label>
              <input
                v-model="formData.scope"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="openid email profile"
              />
            </div>
          </div>

          <!-- LDAP Fields -->
          <div v-if="isLDAPProvider" class="space-y-4 border-t border-gray-200 pt-6">
            <h4 class="font-medium text-gray-900">LDAP Configuration</h4>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Server URI</label>
              <input
                v-model="formData.server_uri"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="ldap://ldap.company.com:389"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Bind DN</label>
              <input
                v-model="formData.bind_dn"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="cn=admin,dc=company,dc=com"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Bind Password</label>
              <input
                v-model="formData.bind_password"
                type="password"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Base DN</label>
              <input
                v-model="formData.base_dn"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="ou=users,dc=company,dc=com"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Search Filter</label>
              <input
                v-model="formData.search_filter"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="(uid={username})"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">User DN Template</label>
              <input
                v-model="formData.user_dn_template"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="uid={username},ou=users,dc=company,dc=com"
              />
            </div>
          </div>

          <!-- SAML Fields -->
          <div v-if="isSAMLProvider" class="space-y-4 border-t border-gray-200 pt-6">
            <h4 class="font-medium text-gray-900">SAML Configuration</h4>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">SP Entity ID</label>
              <input
                v-model="formData.sp_entity_id"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="https://your-autobot.com/saml"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">ACS URL (Assertion Consumer Service)</label>
              <input
                v-model="formData.acs_url"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="https://your-autobot.com/saml/acs"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">IdP Metadata URL</label>
              <input
                v-model="formData.idp_metadata_url"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="https://idp.company.com/metadata"
              />
            </div>
          </div>

          <!-- Claim Mapping -->
          <div class="space-y-4 border-t border-gray-200 pt-6">
            <h4 class="font-medium text-gray-900">Claim Mapping</h4>
            <p class="text-sm text-gray-600">Map IdP claims to AutoBot user fields</p>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Email Claim</label>
                <input
                  v-model="formData.claim_email"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="email"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Display Name Claim</label>
                <input
                  v-model="formData.claim_display_name"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="name"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Username Claim</label>
                <input
                  v-model="formData.claim_username"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="preferred_username"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Groups Claim</label>
                <input
                  v-model="formData.claim_groups"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="groups"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Form Actions -->
        <div class="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex justify-end gap-3">
          <button
            @click="closeForm"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
          >
            Cancel
          </button>
          <button
            @click="saveProvider"
            :disabled="saving || !formData.name"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ saving ? 'Saving...' : (editingProvider ? 'Update Provider' : 'Create Provider') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
