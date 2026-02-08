// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * UserManagementSettings - User, Team, and RBAC Management
 *
 * Manages SLM admin users, AutoBot application users, and teams.
 * Issue #576 - User Management System Phase 3 (Frontend).
 * Issue #729 - Migrated from main AutoBot frontend.
 */

import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAutobotApi, type UserResponse } from '@/composables/useAutobotApi'
import {
  useSlmUserApi,
  type SlmUserResponse,
  type TeamResponse,
} from '@/composables/useSlmUserApi'
import {
  useSsoApi,
  type SSOProviderResponse,
  type SSOProviderCreate,
} from '@/composables/useSsoApi'
import PasswordChangeForm from '@shared/components/PasswordChangeForm.vue'

const authStore = useAuthStore()
const autobotApi = useAutobotApi()
const slmApi = useSlmUserApi()
const ssoApi = useSsoApi()

// State
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Tab state for user management section
const activeTab = ref<'slm-admins' | 'autobot-users' | 'teams' | 'sso'>('slm-admins')

// User list state
const legacyUsers = ref<UserResponse[]>([])
const slmUsers = ref<SlmUserResponse[]>([])
const autobotUsers = ref<SlmUserResponse[]>([])
const teams = ref<TeamResponse[]>([])
const ssoProviders = ref<SSOProviderResponse[]>([])
const selectedUser = ref<UserResponse | null>(null)
const showCreateUserModal = ref(false)
const showCreateTeamModal = ref(false)
const showCreateProviderModal = ref(false)
const showChangePasswordModal = ref(false)
const showRbacModal = ref(false)

// Profile form
const profileForm = reactive({
  username: '',
  email: '',
  roles: [] as string[],
})

// New user form
const newUserForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  roles: ['user'],
})

// New team form
const newTeamForm = reactive({
  name: '',
  description: '',
})

// New SSO provider form
const newProviderForm = reactive({
  provider_type: 'google',
  name: '',
  config: {} as Record<string, unknown>,
  is_active: true,
  allow_user_creation: true,
  default_role: 'user',
})

// Preferences
const preferences = reactive({
  enableNotifications: true,
  autoSaveSettings: true,
  theme: 'auto' as 'auto' | 'light' | 'dark',
  language: 'en',
})

// Security settings
const securitySettings = reactive({
  sessionTimeout: 30,
  requireReauth: true,
})

// RBAC state
const rbacStatus = reactive({
  initialized: false,
  message: 'Checking RBAC status...',
})
const isInitializingRbac = ref(false)
const rbacInitOptions = reactive({
  createAdmin: false,
  adminUsername: 'admin',
})

// Computed
const isAdmin = computed(() => authStore.isAdmin)

const currentUser = computed(() => {
  return legacyUsers.value.find((u: UserResponse) => u.username === authStore.user?.username) || null
})

const isAdminReset = computed(() => {
  return isAdmin.value && selectedUser.value?.id !== currentUser.value?.id
})

const passwordChangeUserId = computed(() => {
  return selectedUser.value?.id || currentUser.value?.id || ''
})

// ===========================================================================
// Data Loading
// ===========================================================================

async function loadSlmUsers(): Promise<void> {
  try {
    const response = await slmApi.getSlmUsers()
    slmUsers.value = response.users
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load SLM users'
  }
}

async function loadAutobotUsers(): Promise<void> {
  try {
    const response = await slmApi.getAutobotUsers()
    autobotUsers.value = response.users
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load AutoBot users'
  }
}

async function loadTeams(): Promise<void> {
  try {
    const response = await slmApi.getTeams()
    teams.value = response.teams
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load teams'
  }
}

async function loadSsoProviders(): Promise<void> {
  try {
    const response = await ssoApi.listProviders()
    ssoProviders.value = response.providers
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load SSO providers'
  }
}

async function loadLegacyUsers(): Promise<void> {
  try {
    legacyUsers.value = await autobotApi.getUsers()
  } catch {
    // Legacy API may not be available - not critical
  }
}

async function loadAllData(): Promise<void> {
  if (!isAdmin.value) return

  loading.value = true
  error.value = null

  try {
    await Promise.all([
      loadSlmUsers(),
      loadAutobotUsers(),
      loadTeams(),
      loadSsoProviders(),
      loadLegacyUsers(),
    ])
  } finally {
    loading.value = false
  }
}

// ===========================================================================
// User CRUD
// ===========================================================================

async function createUser(): Promise<void> {
  if (newUserForm.password !== newUserForm.confirmPassword) {
    error.value = 'Passwords do not match'
    return
  }

  saving.value = true
  error.value = null

  try {
    const payload = {
      email: newUserForm.email,
      username: newUserForm.username,
      password: newUserForm.password,
    }

    if (activeTab.value === 'slm-admins') {
      await slmApi.createSlmUser(payload)
    } else {
      await slmApi.createAutobotUser(payload)
    }

    showSuccess('User created successfully')
    showCreateUserModal.value = false
    resetNewUserForm()
    await refreshActiveTab()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create user'
  } finally {
    saving.value = false
  }
}

async function deleteSlmUser(userId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this SLM admin?')) return

  saving.value = true
  try {
    await slmApi.deleteSlmUser(userId)
    showSuccess('SLM user deleted successfully')
    await loadSlmUsers()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete user'
  } finally {
    saving.value = false
  }
}

async function deleteAutobotUser(userId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this user?')) return

  saving.value = true
  try {
    await slmApi.deleteAutobotUser(userId)
    showSuccess('AutoBot user deleted successfully')
    await loadAutobotUsers()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete user'
  } finally {
    saving.value = false
  }
}

// ===========================================================================
// Team CRUD
// ===========================================================================

async function createTeam(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    await slmApi.createTeam({
      name: newTeamForm.name,
      description: newTeamForm.description || undefined,
    })

    showSuccess('Team created successfully')
    showCreateTeamModal.value = false
    newTeamForm.name = ''
    newTeamForm.description = ''
    await loadTeams()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create team'
  } finally {
    saving.value = false
  }
}

async function deleteTeam(teamId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this team?')) return

  saving.value = true
  try {
    await slmApi.deleteTeam(teamId)
    showSuccess('Team deleted successfully')
    await loadTeams()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete team'
  } finally {
    saving.value = false
  }
}

// ===========================================================================
// Password & RBAC
// ===========================================================================

function openPasswordChangeModal(user?: UserResponse): void {
  selectedUser.value = user || currentUser.value
  showChangePasswordModal.value = true
}

function handlePasswordChangeSuccess(message: string): void {
  showSuccess(message)
  showChangePasswordModal.value = false
  selectedUser.value = null
}

function handlePasswordChangeError(errorMsg: string): void {
  error.value = errorMsg
  setTimeout(() => { error.value = null }, 5000)
}

async function checkRbacStatus(): Promise<void> {
  if (!isAdmin.value) return

  try {
    const response = await fetch('/autobot-api/settings/rbac/status', {
      headers: { Authorization: `Bearer ${authStore.token}` },
    })

    if (response.ok) {
      const data = await response.json()
      rbacStatus.initialized = data.initialized
      rbacStatus.message = data.message
    }
  } catch {
    rbacStatus.message = 'Failed to check RBAC status'
  }
}

async function initializeRbac(): Promise<void> {
  isInitializingRbac.value = true
  error.value = null

  try {
    const response = await fetch('/autobot-api/settings/rbac/initialize', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token}`,
      },
      body: JSON.stringify({
        create_admin: rbacInitOptions.createAdmin,
        admin_username: rbacInitOptions.adminUsername,
      }),
    })

    if (response.ok) {
      const data = await response.json()
      showSuccess(data.message || 'RBAC initialized successfully')
      showRbacModal.value = false
      await checkRbacStatus()
    } else {
      const data = await response.json()
      throw new Error(data.detail || 'Failed to initialize RBAC')
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to initialize RBAC'
  } finally {
    isInitializingRbac.value = false
  }
}

// ===========================================================================
// Settings
// ===========================================================================

async function savePreferences(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    await autobotApi.updateSettingsSection('preferences', preferences)
    showSuccess('Preferences saved successfully')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save preferences'
  } finally {
    saving.value = false
  }
}

async function saveSecuritySettings(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    await autobotApi.updateSettingsSection('security', securitySettings)
    showSuccess('Security settings saved successfully')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save security settings'
  } finally {
    saving.value = false
  }
}

function logout(): void {
  authStore.logout()
}

// ===========================================================================
// Helpers
// ===========================================================================

function showSuccess(message: string): void {
  success.value = message
  setTimeout(() => { success.value = null }, 3000)
}

function resetNewUserForm(): void {
  newUserForm.username = ''
  newUserForm.email = ''
  newUserForm.password = ''
  newUserForm.confirmPassword = ''
  newUserForm.roles = ['user']
}

async function createSsoProvider(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    const payload: SSOProviderCreate = {
      provider_type: newProviderForm.provider_type,
      name: newProviderForm.name,
      config: newProviderForm.config,
      is_active: newProviderForm.is_active,
      allow_user_creation: newProviderForm.allow_user_creation,
      default_role: newProviderForm.default_role,
    }

    await ssoApi.createProvider(payload)
    showSuccess('SSO provider created successfully')
    showCreateProviderModal.value = false
    resetNewProviderForm()
    await loadSsoProviders()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create SSO provider'
  } finally {
    saving.value = false
  }
}

async function deleteSsoProvider(providerId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this SSO provider?')) return

  saving.value = true
  try {
    await ssoApi.deleteProvider(providerId)
    showSuccess('SSO provider deleted successfully')
    await loadSsoProviders()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete SSO provider'
  } finally {
    saving.value = false
  }
}

async function testSsoProvider(providerId: string): Promise<void> {
  try {
    const result = await ssoApi.testProvider(providerId)
    if (result.success) {
      showSuccess(result.message || 'SSO provider connection successful')
    } else {
      error.value = result.message || 'SSO provider connection test failed'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to test SSO provider'
  }
}

function resetNewProviderForm(): void {
  newProviderForm.provider_type = 'google'
  newProviderForm.name = ''
  newProviderForm.config = {}
  newProviderForm.is_active = true
  newProviderForm.allow_user_creation = true
  newProviderForm.default_role = 'user'
}

async function refreshActiveTab(): Promise<void> {
  if (activeTab.value === 'slm-admins') await loadSlmUsers()
  else if (activeTab.value === 'autobot-users') await loadAutobotUsers()
  else if (activeTab.value === 'sso') await loadSsoProviders()
  else await loadTeams()
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ===========================================================================
// Lifecycle
// ===========================================================================

onMounted(async () => {
  profileForm.username = authStore.user?.username || ''

  if (isAdmin.value) {
    await loadAllData()
    await checkRbacStatus()
  }
})

watch(() => authStore.user, (newUser: typeof authStore.user) => {
  if (newUser) {
    profileForm.username = newUser.username
  }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button @click="error = null" class="ml-auto text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Authentication Status -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Authentication Status</h2>

      <div v-if="authStore.isAuthenticated" class="flex items-center gap-4 p-4 bg-green-50 border border-green-200 rounded-lg">
        <div class="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center">
          <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="flex-1">
          <p class="font-medium text-green-800">Authenticated</p>
          <p class="text-sm text-green-600">{{ authStore.user?.username }} ({{ isAdmin ? 'Admin' : 'User' }})</p>
        </div>
        <button @click="logout" class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Logout
        </button>
      </div>

      <div v-else class="flex items-center gap-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <div class="w-10 h-10 bg-yellow-500 rounded-full flex items-center justify-center">
          <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div class="flex-1">
          <p class="font-medium text-yellow-800">Not Authenticated</p>
          <p class="text-sm text-yellow-600">Please log in to access user management</p>
        </div>
      </div>
    </div>

    <!-- User Preferences -->
    <div v-if="authStore.isAuthenticated" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">User Preferences</h2>

      <div class="space-y-4">
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Theme</label>
            <p class="text-xs text-gray-500 mt-1">Choose your preferred color scheme</p>
          </div>
          <select v-model="preferences.theme" class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
            <option value="auto">Auto (System)</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>

        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Language</label>
            <p class="text-xs text-gray-500 mt-1">Interface language</p>
          </div>
          <select v-model="preferences.language" class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>

        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Enable Notifications</label>
            <p class="text-xs text-gray-500 mt-1">Receive system notifications</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="preferences.enableNotifications" class="sr-only peer" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">Auto-save Settings</label>
            <p class="text-xs text-gray-500 mt-1">Automatically save changes</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="preferences.autoSaveSettings" class="sr-only peer" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>
      </div>

      <div class="mt-6 flex justify-end">
        <button @click="savePreferences" :disabled="saving" class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Save Preferences
        </button>
      </div>
    </div>

    <!-- Security Settings -->
    <div v-if="authStore.isAuthenticated" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Security</h2>

      <div class="space-y-4">
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Session Timeout</label>
            <p class="text-xs text-gray-500 mt-1">Auto-logout after inactivity (minutes)</p>
          </div>
          <input v-model.number="securitySettings.sessionTimeout" type="number" min="5" max="1440" class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>

        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Require Re-authentication</label>
            <p class="text-xs text-gray-500 mt-1">For sensitive operations</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="securitySettings.requireReauth" class="sr-only peer" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">Password</label>
            <p class="text-xs text-gray-500 mt-1">Change your account password</p>
          </div>
          <button @click="openPasswordChangeModal()" class="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            Change Password
          </button>
        </div>
      </div>

      <div class="mt-6 flex justify-end">
        <button @click="saveSecuritySettings" :disabled="saving" class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Save Security Settings
        </button>
      </div>
    </div>

    <!-- User Management (Admin Only) - Tabbed Interface -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <!-- Tab Navigation -->
      <div class="border-b border-gray-200 mb-6">
        <nav class="flex gap-1">
          <button
            @click="activeTab = 'slm-admins'"
            :class="[
              'px-4 py-2.5 font-medium text-sm border-b-2 transition-colors',
              activeTab === 'slm-admins'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            SLM Administrators
          </button>
          <button
            @click="activeTab = 'autobot-users'"
            :class="[
              'px-4 py-2.5 font-medium text-sm border-b-2 transition-colors',
              activeTab === 'autobot-users'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            AutoBot Users
          </button>
          <button
            @click="activeTab = 'teams'"
            :class="[
              'px-4 py-2.5 font-medium text-sm border-b-2 transition-colors',
              activeTab === 'teams'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            Teams
          </button>
          <button
            @click="activeTab = 'sso'"
            :class="[
              'px-4 py-2.5 font-medium text-sm border-b-2 transition-colors',
              activeTab === 'sso'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            SSO Providers
          </button>
        </nav>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-8">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- SLM Administrators Tab -->
      <div v-else-if="activeTab === 'slm-admins'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">SLM Fleet Administrators</h2>
            <p class="text-sm text-gray-500">Users who manage the AutoBot fleet via the SLM admin dashboard</p>
          </div>
          <button @click="showCreateUserModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Add SLM Admin
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Username</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Email</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Roles</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Last Login</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in slmUsers" :key="user.id" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ user.username }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ user.email }}</td>
                <td class="py-3 px-4">
                  <div class="flex gap-1 flex-wrap">
                    <span v-for="role in user.roles" :key="role.id" class="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                      {{ role.name }}
                    </span>
                  </div>
                </td>
                <td class="py-3 px-4">
                  <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', user.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700']">
                    {{ user.is_active ? 'Active' : 'Inactive' }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(user.last_login_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <button @click="deleteSlmUser(user.id)" class="text-red-600 hover:text-red-800 p-1" title="Delete user">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="slmUsers.length === 0">
                <td colspan="6" class="py-8 text-center text-gray-500">No SLM administrators found</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- AutoBot Users Tab -->
      <div v-else-if="activeTab === 'autobot-users'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">AutoBot Application Users</h2>
            <p class="text-sm text-gray-500">Users who access AutoBot chat, workflows, and tools</p>
          </div>
          <button @click="showCreateUserModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Add User
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Username</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Email</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Roles</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Last Login</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in autobotUsers" :key="user.id" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ user.username }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ user.email }}</td>
                <td class="py-3 px-4">
                  <div class="flex gap-1 flex-wrap">
                    <span v-for="role in user.roles" :key="role.id" class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                      {{ role.name }}
                    </span>
                  </div>
                </td>
                <td class="py-3 px-4">
                  <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', user.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700']">
                    {{ user.is_active ? 'Active' : 'Inactive' }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(user.last_login_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <button @click="deleteAutobotUser(user.id)" class="text-red-600 hover:text-red-800 p-1" title="Delete user">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="autobotUsers.length === 0">
                <td colspan="6" class="py-8 text-center text-gray-500">No AutoBot users found</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Teams Tab -->
      <div v-else-if="activeTab === 'teams'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">AutoBot Teams</h2>
            <p class="text-sm text-gray-500">Organize users into teams for collaboration and shared resources</p>
          </div>
          <button @click="showCreateTeamModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Create Team
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Name</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Description</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Created</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="team in teams" :key="team.id" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ team.name }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ team.description || '-' }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(team.created_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <button @click="deleteTeam(team.id)" class="text-red-600 hover:text-red-800 p-1" title="Delete team">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="teams.length === 0">
                <td colspan="4" class="py-8 text-center text-gray-500">No teams found</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SSO Providers Tab -->
      <div v-else-if="activeTab === 'sso'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">SSO Providers</h2>
            <p class="text-sm text-gray-500">Configure OAuth2, LDAP, and SAML authentication providers</p>
          </div>
          <button @click="showCreateProviderModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Add Provider
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Name</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Type</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Last Sync</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="provider in ssoProviders" :key="provider.id" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ provider.name }}</td>
                <td class="py-3 px-4">
                  <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                    {{ provider.provider_type }}
                  </span>
                </td>
                <td class="py-3 px-4">
                  <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', provider.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700']">
                    {{ provider.is_active ? 'Active' : 'Inactive' }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ provider.last_sync_at ? new Date(provider.last_sync_at).toLocaleString() : 'Never' }}</td>
                <td class="py-3 px-4 text-right">
                  <div class="flex justify-end gap-2">
                    <button @click="testSsoProvider(provider.id)" class="text-blue-600 hover:text-blue-800 p-1" title="Test connection">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                    </button>
                    <button @click="deleteSsoProvider(provider.id)" class="text-red-600 hover:text-red-800 p-1" title="Delete provider">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="ssoProviders.length === 0">
                <td colspan="5" class="py-8 text-center text-gray-500">No SSO providers configured</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- RBAC Management (Admin Only) -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Role-Based Access Control</h2>

      <div class="p-4 rounded-lg mb-4" :class="rbacStatus.initialized ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'">
        <div class="flex items-center gap-3">
          <svg :class="['w-5 h-5', rbacStatus.initialized ? 'text-green-500' : 'text-yellow-500']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="rbacStatus.initialized ? 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' : 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'" />
          </svg>
          <div>
            <p :class="['font-medium', rbacStatus.initialized ? 'text-green-800' : 'text-yellow-800']">
              {{ rbacStatus.initialized ? 'RBAC Initialized' : 'RBAC Not Initialized' }}
            </p>
            <p :class="['text-sm', rbacStatus.initialized ? 'text-green-600' : 'text-yellow-600']">
              {{ rbacStatus.message }}
            </p>
          </div>
        </div>
      </div>

      <div class="p-4 bg-gray-50 rounded-lg mb-4">
        <p class="text-sm text-gray-600"><strong>System Permissions:</strong> 23 permissions across 8 resources</p>
        <p class="text-sm text-gray-600"><strong>System Roles:</strong> admin, user, readonly, guest</p>
      </div>

      <div class="flex gap-3">
        <button @click="showRbacModal = true" :disabled="isInitializingRbac" class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="isInitializingRbac" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Initialize RBAC
        </button>
        <button @click="checkRbacStatus" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh Status
        </button>
      </div>
    </div>

    <!-- Change Password Modal -->
    <div v-if="showChangePasswordModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showChangePasswordModal = false; selectedUser = null"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          {{ isAdminReset ? `Reset Password for ${selectedUser?.username}` : 'Change Password' }}
        </h3>

        <PasswordChangeForm
          v-if="passwordChangeUserId"
          :user-id="passwordChangeUserId"
          :require-current-password="!isAdminReset"
          @success="handlePasswordChangeSuccess"
          @error="handlePasswordChangeError"
        />

        <div class="flex justify-end mt-4">
          <button @click="showChangePasswordModal = false; selectedUser = null" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
            Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Create User Modal -->
    <div v-if="showCreateUserModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showCreateUserModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          {{ activeTab === 'slm-admins' ? 'Create SLM Administrator' : 'Create AutoBot User' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input v-model="newUserForm.username" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" placeholder="Lowercase, letters, numbers, underscores" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input v-model="newUserForm.email" type="email" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input v-model="newUserForm.password" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" placeholder="Min 8 chars, upper + lower + digit" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
            <input v-model="newUserForm.confirmPassword" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button @click="showCreateUserModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
            Cancel
          </button>
          <button @click="createUser" :disabled="saving" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2">
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Create
          </button>
        </div>
      </div>
    </div>

    <!-- Create Team Modal -->
    <div v-if="showCreateTeamModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showCreateTeamModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Create Team</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Team Name</label>
            <input v-model="newTeamForm.name" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" placeholder="e.g., Engineering, Design" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Description (optional)</label>
            <textarea v-model="newTeamForm.description" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" placeholder="Brief description of the team's purpose"></textarea>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button @click="showCreateTeamModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
            Cancel
          </button>
          <button @click="createTeam" :disabled="saving || !newTeamForm.name" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2">
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Create Team
          </button>
        </div>
      </div>
    </div>

    <!-- RBAC Init Modal -->
    <div v-if="showRbacModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showRbacModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Initialize RBAC System</h3>

        <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg mb-4">
          <div class="flex gap-3">
            <svg class="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p class="font-medium text-yellow-800">RBAC Initialization</p>
              <p class="text-sm text-yellow-700">
                This will create system permissions and roles in the database. It is safe to run multiple times.
              </p>
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <input id="create-admin" v-model="rbacInitOptions.createAdmin" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500" />
            <label for="create-admin" class="text-sm text-gray-700">Create initial admin user</label>
          </div>

          <div v-if="rbacInitOptions.createAdmin">
            <label class="block text-sm font-medium text-gray-700 mb-1">Admin Username</label>
            <input v-model="rbacInitOptions.adminUsername" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button @click="showRbacModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
            Cancel
          </button>
          <button @click="initializeRbac" :disabled="isInitializingRbac" class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2">
            <svg v-if="isInitializingRbac" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Initialize RBAC
          </button>
        </div>
      </div>
    </div>

    <!-- Create SSO Provider Modal -->
    <div v-if="showCreateProviderModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showCreateProviderModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Add SSO Provider</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Provider Type</label>
            <select v-model="newProviderForm.provider_type" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
              <option value="google">Google OAuth</option>
              <option value="github">GitHub</option>
              <option value="microsoft_entra">Microsoft Entra ID</option>
              <option value="ldap">LDAP</option>
              <option value="active_directory">Active Directory</option>
              <option value="saml">SAML 2.0</option>
              <option value="google_workspace">Google Workspace</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input v-model="newProviderForm.name" type="text" placeholder="e.g., Company Google SSO" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
            <input v-model="(newProviderForm.config as Record<string, string>).client_id" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Client Secret</label>
            <input v-model="(newProviderForm.config as Record<string, string>).client_secret" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div class="flex items-center gap-3">
            <input id="sso-active" v-model="newProviderForm.is_active" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500" />
            <label for="sso-active" class="text-sm text-gray-700">Active</label>
          </div>
          <div class="flex items-center gap-3">
            <input id="sso-provision" v-model="newProviderForm.allow_user_creation" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500" />
            <label for="sso-provision" class="text-sm text-gray-700">Allow automatic user creation (JIT provisioning)</label>
          </div>
        </div>
        <div class="flex justify-end gap-3 mt-6">
          <button @click="showCreateProviderModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">Cancel</button>
          <button @click="createSsoProvider" :disabled="saving" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50">Create Provider</button>
        </div>
      </div>
    </div>
  </div>
</template>
