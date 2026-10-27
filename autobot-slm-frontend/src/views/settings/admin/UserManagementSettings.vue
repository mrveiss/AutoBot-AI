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
import { useI18n } from 'vue-i18n'
import { formatDateTime } from '@/composables/useTimezone'
import { useAuthStore } from '@/stores/auth'
import { getSlmApiBase } from '@/config/ssot-config'
import {
  useAutobotApi,
  autobotApiErrorMessage,
} from '@/composables/useAutobotApi'
import {
  useSlmUserApi,
  type SlmUserResponse,
  type AutobotTeamResponse,
} from '@/composables/useSlmUserApi'
import {
  useSsoApi,
  type SSOProviderResponse,
  type SSOProviderCreate,
} from '@/composables/useSsoApi'
import PasswordChangeForm from '@shared/components/PasswordChangeForm.vue'
import { BaseAlert, BaseModal } from '@autobot/ui'

const { t } = useI18n()
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
const slmUsers = ref<SlmUserResponse[]>([])
const autobotUsers = ref<SlmUserResponse[]>([])
const teams = ref<AutobotTeamResponse[]>([])
const ssoProviders = ref<SSOProviderResponse[]>([])
const selectedUser = ref<SlmUserResponse | null>(null)
const selectedUserType = ref<'slm' | 'autobot'>('slm')
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

// RBAC state
const rbacStatus = reactive({
  initialized: false,
  message: t('settings.admin.userManagementSettings.checkingRbacStatus'),
})
const isInitializingRbac = ref(false)
const rbacInitOptions = reactive({
  createAdmin: false,
  adminUsername: 'admin',
})

// Computed
const isAdmin = computed(() => authStore.isAdmin)

// #15533: the signed-in identity of this frontend is an SLM user — `POST
// /api/auth/login` on the SLM authenticates against the SLM user table and
// `/api/auth/me` reports `user_type: "slm_admin"`. Resolving it from the main
// backend's user list (the pre-#15533 source) produced a main-backend id that
// was then posted to the SLM, under a `/api/users/...` namespace the SLM does
// not serve. `slmUsers` is the list the id has to come from.
const currentUser = computed(() => {
  return slmUsers.value.find((u: SlmUserResponse) => u.username === authStore.user?.username) || null
})

const isAdminReset = computed(() => {
  return isAdmin.value && selectedUser.value?.id !== currentUser.value?.id
})

const passwordChangeUserId = computed(() => {
  return selectedUser.value?.id || currentUser.value?.id || ''
})

// Both branches name a route the SLM serves — see `/api/slm-users/{user_id}/
// change-password` and `/api/autobot-users/{user_id}/change-password` in
// `autobot-slm-frontend/openapi.json`. There is no third namespace: the
// `legacy` branch this used to carry named `/api/users/...`, which no SLM
// router mounts (#15533).
const passwordChangeApiEndpoint = computed(() => {
  const uid = passwordChangeUserId.value
  if (!uid) return ''
  const base = getSlmApiBase()
  if (selectedUserType.value === 'autobot') return `${base}/autobot-users/${uid}/change-password`
  return `${base}/slm-users/${uid}/change-password`
})

// ===========================================================================
// Data Loading
// ===========================================================================

async function loadSlmUsers(): Promise<void> {
  try {
    const response = await slmApi.getSlmUsers()
    slmUsers.value = response.users
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToLoadSlmUsers')
  }
}

async function loadAutobotUsers(): Promise<void> {
  try {
    const response = await slmApi.getAutobotUsers()
    autobotUsers.value = response.users
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToLoadAutobotUsers')
  }
}

async function loadTeams(): Promise<void> {
  try {
    const response = await slmApi.getTeams()
    teams.value = response.teams
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToLoadTeams')
  }
}

async function loadSsoProviders(): Promise<void> {
  try {
    const response = await ssoApi.listProviders()
    ssoProviders.value = response.providers
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToLoadSsoProviders')
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
    error.value = t('settings.admin.userManagementSettings.passwordsDoNotMatch')
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

    showSuccess(t('settings.admin.userManagementSettings.userCreated'))
    showCreateUserModal.value = false
    resetNewUserForm()
    await refreshActiveTab()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToCreateUser')
  } finally {
    saving.value = false
  }
}

async function deleteSlmUser(userId: string): Promise<void> {
  if (!confirm(t('settings.admin.userManagementSettings.confirmDeleteSlmAdmin'))) return

  saving.value = true
  try {
    await slmApi.deleteSlmUser(userId)
    showSuccess(t('settings.admin.userManagementSettings.slmUserDeleted'))
    await loadSlmUsers()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToDeleteUser')
  } finally {
    saving.value = false
  }
}

async function deleteAutobotUser(userId: string): Promise<void> {
  if (!confirm(t('settings.admin.userManagementSettings.confirmDeleteUser'))) return

  saving.value = true
  try {
    await slmApi.deleteAutobotUser(userId)
    showSuccess(t('settings.admin.userManagementSettings.autobotUserDeleted'))
    await loadAutobotUsers()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToDeleteUser')
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

    showSuccess(t('settings.admin.userManagementSettings.teamCreated'))
    showCreateTeamModal.value = false
    newTeamForm.name = ''
    newTeamForm.description = ''
    await loadTeams()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToCreateTeam')
  } finally {
    saving.value = false
  }
}

async function deleteTeam(teamId: string): Promise<void> {
  if (!confirm(t('settings.admin.userManagementSettings.confirmDeleteTeam'))) return

  saving.value = true
  try {
    await slmApi.deleteTeam(teamId)
    showSuccess(t('settings.admin.userManagementSettings.teamDeleted'))
    await loadTeams()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToDeleteTeam')
  } finally {
    saving.value = false
  }
}

// ===========================================================================
// Password & RBAC
// ===========================================================================

function openPasswordChangeModal(
  user?: SlmUserResponse,
  type: 'slm' | 'autobot' = 'slm',
): void {
  selectedUser.value = user ?? currentUser.value
  selectedUserType.value = type
  showChangePasswordModal.value = true
}

function handlePasswordChangeSuccess(message: string): void {
  showSuccess(message)
  showChangePasswordModal.value = false
  selectedUser.value = null
  selectedUserType.value = 'slm'
}

function handlePasswordChangeError(errorMsg: string): void {
  error.value = errorMsg
  setTimeout(() => { error.value = null }, 5000)
}

async function checkRbacStatus(): Promise<void> {
  if (!isAdmin.value) return

  try {
    const data = await autobotApi.getRbacStatus()
    rbacStatus.initialized = data.initialized
    rbacStatus.message = data.message
  } catch {
    rbacStatus.message = t('settings.admin.userManagementSettings.failedToCheckRbacStatus')
  }
}

async function initializeRbac(): Promise<void> {
  isInitializingRbac.value = true
  error.value = null

  try {
    const data = await autobotApi.initializeRbac({
      create_admin: rbacInitOptions.createAdmin,
      admin_username: rbacInitOptions.adminUsername,
    })
    showSuccess(data.message || t('settings.admin.userManagementSettings.rbacInitializedSuccessfully'))
    showRbacModal.value = false
    await checkRbacStatus()
  } catch (e) {
    error.value = autobotApiErrorMessage(e, 'Failed to initialize RBAC')
  } finally {
    isInitializingRbac.value = false
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
      // This form does not collect `is_social`; the contract requires it, so
      // state the backend default explicitly rather than relying on omission.
      is_social: false,
    }

    await ssoApi.createProvider(payload)
    showSuccess(t('settings.admin.userManagementSettings.ssoProviderCreated'))
    showCreateProviderModal.value = false
    resetNewProviderForm()
    await loadSsoProviders()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToCreateSsoProvider')
  } finally {
    saving.value = false
  }
}

async function deleteSsoProvider(providerId: string): Promise<void> {
  if (!confirm(t('settings.admin.userManagementSettings.confirmDeleteSsoProvider'))) return

  saving.value = true
  try {
    await ssoApi.deleteProvider(providerId)
    showSuccess(t('settings.admin.userManagementSettings.ssoProviderDeleted'))
    await loadSsoProviders()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToDeleteSsoProvider')
  } finally {
    saving.value = false
  }
}

async function testSsoProvider(providerId: string): Promise<void> {
  try {
    const result = await ssoApi.testProvider(providerId)
    if (result.success) {
      showSuccess(result.message || t('settings.admin.userManagementSettings.ssoConnectionSuccessful'))
    } else {
      error.value = result.message || t('settings.admin.userManagementSettings.ssoConnectionFailed')
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.userManagementSettings.failedToTestSsoProvider')
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

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Never'
  return formatDateTime(dateStr)
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
    <BaseAlert v-if="error" variant="error" :message="error" dismissible :dismiss-label="$t('settings.admin.userManagementSettings.dismissError')" @dismiss="error = null" />

    <BaseAlert v-if="success" variant="success" :message="success" />

    <!-- Authentication Status -->
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">{{ $t('settings.admin.userManagementSettings.authenticationStatus') }}</h2>

      <BaseAlert
        v-if="authStore.isAuthenticated"
        variant="success"
        :title="$t('settings.admin.userManagementSettings.authenticated')"
      >
        {{ authStore.user?.username }} ({{ isAdmin ? $t('common.sidebar.admin') : $t('common.sidebar.user') }})
        <template #actions>
          <button @click="logout" class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.logout') }}
          </button>
        </template>
      </BaseAlert>

      <BaseAlert
        v-else
        variant="warning"
        :title="$t('settings.admin.userManagementSettings.notAuthenticated')"
        :message="$t('settings.admin.userManagementSettings.pleaseLogInTo')"
      />
    </div>

    <!-- Preferences, session timeout and re-auth are hidden until a backend stores them (#18733). -->
    <!-- Security Settings -->
    <div v-if="authStore.isAuthenticated" class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">{{ $t('settings.admin.userManagementSettings.security') }}</h2>

      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">{{ $t('settings.admin.userManagementSettings.password') }}</label>
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.admin.userManagementSettings.changeYourAccountPassword') }}</p>
          </div>
          <button @click="openPasswordChangeModal()" class="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.changePassword') }}
          </button>
        </div>
      </div>
    </div>

    <!-- User Management (Admin Only) - Tabbed Interface -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
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
            {{ $t('settings.admin.userManagementSettings.sLMAdministrators') }}
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
            {{ $t('settings.admin.userManagementSettings.autoBotUsers') }}
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
            {{ $t('settings.admin.userManagementSettings.teams') }}
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
            {{ $t('settings.admin.userManagementSettings.sSOProviders') }}
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
            <h2 class="text-lg font-semibold text-gray-900">{{ $t('settings.admin.userManagementSettings.sLMFleetAdministrators') }}</h2>
            <p class="text-sm text-gray-500">{{ $t('settings.admin.userManagementSettings.usersWhoManageThe') }}</p>
          </div>
          <button @click="showCreateUserModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.addSLMAdmin') }}
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.username') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.email') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.roles') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.status') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.lastLogin') }}</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.actions') }}</th>
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
                    {{ user.is_active ? $t('settings.admin.userManagementSettings.active') : $t('settings.admin.userManagementSettings.inactive') }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(user.last_login_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <div class="flex items-center justify-end gap-1">
                    <button @click="openPasswordChangeModal(user, 'slm')" class="text-amber-600 hover:text-amber-800 p-1" :title="$t('settings.admin.userManagementSettings.resetPassword')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                    </button>
                    <button @click="deleteSlmUser(user.id)" class="text-red-600 hover:text-red-800 p-1" :title="$t('settings.admin.userManagementSettings.deleteUser')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="slmUsers.length === 0">
                <td colspan="6" class="py-8 text-center text-gray-500">{{ $t('settings.admin.userManagementSettings.noSLMAdministratorsFound') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- AutoBot Users Tab -->
      <div v-else-if="activeTab === 'autobot-users'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ $t('settings.admin.userManagementSettings.autoBotApplicationUsers') }}</h2>
            <p class="text-sm text-gray-500">{{ $t('settings.admin.userManagementSettings.usersWhoAccessAutoBot') }}</p>
          </div>
          <button @click="showCreateUserModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.addUser') }}
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.username') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.email') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.roles') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.status') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.lastLogin') }}</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.actions') }}</th>
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
                    {{ user.is_active ? $t('settings.admin.userManagementSettings.active') : $t('settings.admin.userManagementSettings.inactive') }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(user.last_login_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <div class="flex items-center justify-end gap-1">
                    <button @click="openPasswordChangeModal(user, 'autobot')" class="text-amber-600 hover:text-amber-800 p-1" :title="$t('settings.admin.userManagementSettings.resetPassword')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                    </button>
                    <button @click="deleteAutobotUser(user.id)" class="text-red-600 hover:text-red-800 p-1" :title="$t('settings.admin.userManagementSettings.deleteUser')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="autobotUsers.length === 0">
                <td colspan="6" class="py-8 text-center text-gray-500">{{ $t('settings.admin.userManagementSettings.noAutoBotUsersFound') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Teams Tab -->
      <div v-else-if="activeTab === 'teams'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ $t('settings.admin.userManagementSettings.autoBotTeams') }}</h2>
            <p class="text-sm text-gray-500">{{ $t('settings.admin.userManagementSettings.organizeUsersIntoTeams') }}</p>
          </div>
          <button @click="showCreateTeamModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.createTeam') }}
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.name') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.description') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.created') }}</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="team in teams" :key="team.id" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ team.name }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ team.description || '-' }}</td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDate(team.created_at) }}</td>
                <td class="py-3 px-4 text-right">
                  <button @click="deleteTeam(team.id)" class="text-red-600 hover:text-red-800 p-1" :title="$t('settings.admin.userManagementSettings.deleteTeam')">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="teams.length === 0">
                <td colspan="4" class="py-8 text-center text-gray-500">{{ $t('settings.admin.userManagementSettings.noTeamsFound') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SSO Providers Tab -->
      <div v-else-if="activeTab === 'sso'">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ $t('settings.admin.userManagementSettings.sSOProviders') }}</h2>
            <p class="text-sm text-gray-500">{{ $t('settings.admin.userManagementSettings.configureOAuth2LDAPAnd') }}</p>
          </div>
          <button @click="showCreateProviderModal = true" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            {{ $t('settings.admin.userManagementSettings.addProvider') }}
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.name') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.type') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.status') }}</th>
                <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.lastSync') }}</th>
                <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">{{ $t('settings.admin.userManagementSettings.actions') }}</th>
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
                    {{ provider.is_active ? $t('settings.admin.userManagementSettings.active') : $t('settings.admin.userManagementSettings.inactive') }}
                  </span>
                </td>
                <td class="py-3 px-4 text-sm text-gray-600">{{ formatDateTime(provider.last_sync_at ?? null) }}</td>
                <td class="py-3 px-4 text-right">
                  <div class="flex justify-end gap-2">
                    <button @click="testSsoProvider(provider.id)" class="text-blue-600 hover:text-blue-800 p-1" :title="$t('settings.admin.userManagementSettings.testConnection')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                    </button>
                    <button @click="deleteSsoProvider(provider.id)" class="text-red-600 hover:text-red-800 p-1" :title="$t('settings.admin.userManagementSettings.deleteProvider')">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="ssoProviders.length === 0">
                <td colspan="5" class="py-8 text-center text-gray-500">{{ $t('settings.admin.userManagementSettings.noSSOProvidersConfigured') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- RBAC Management (Admin Only) -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">{{ $t('settings.admin.userManagementSettings.roleBasedAccessControl') }}</h2>

      <BaseAlert
        :variant="rbacStatus.initialized ? 'success' : 'warning'"
        class="mb-4"
        :title="rbacStatus.initialized ? $t('settings.admin.userManagementSettings.rBACInitialized') : $t('settings.admin.userManagementSettings.rBACNotInitialized')"
        :message="rbacStatus.message"
      />

      <div class="p-4 bg-gray-50 rounded-lg mb-4">
        <p class="text-sm text-gray-600"><strong>{{ $t('settings.admin.userManagementSettings.systemPermissions') }}</strong> {{ $t('settings.admin.userManagementSettings.23PermissionsAcross8') }}</p>
        <p class="text-sm text-gray-600"><strong>{{ $t('settings.admin.userManagementSettings.systemRoles') }}</strong> {{ $t('settings.admin.userManagementSettings.adminUserReadonlyGuest') }}</p>
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
          {{ $t('settings.admin.userManagementSettings.initializeRBAC') }}
        </button>
        <button @click="checkRbacStatus" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ $t('settings.admin.userManagementSettings.refreshStatus') }}
        </button>
      </div>
    </div>

    <!-- Change Password Modal -->
    <BaseModal
      v-model="showChangePasswordModal"
      :title="isAdminReset ? $t('settings.admin.userManagementSettings.resetPasswordFor', { username: selectedUser?.username ?? '' }) : $t('settings.admin.userManagementSettings.changePassword')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
      @close="selectedUser = null; selectedUserType = 'slm'"
    >
      <PasswordChangeForm
        v-if="passwordChangeUserId"
        :user-id="passwordChangeUserId"
        :require-current-password="!isAdminReset"
        :api-endpoint="passwordChangeApiEndpoint"
        :auth-token="authStore.token ?? undefined"
        @success="handlePasswordChangeSuccess"
        @error="handlePasswordChangeError"
      />
      <template #actions>
        <button @click="showChangePasswordModal = false; selectedUser = null; selectedUserType = 'slm'" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
          {{ $t('settings.admin.userManagementSettings.cancel') }}
        </button>
      </template>
    </BaseModal>

    <!-- Create User Modal -->
    <BaseModal
      :close-on-esc="!saving"
      v-model="showCreateUserModal"
      :title="activeTab === 'slm-admins' ? $t('settings.admin.userManagementSettings.createSLMAdministrator') : $t('settings.admin.userManagementSettings.createAutoBotUser')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.username') }}</label>
          <input v-model="newUserForm.username" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" :placeholder="$t('settings.admin.userManagementSettings.lowercaseLettersNumbersUnderscores')" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.email') }}</label>
          <input v-model="newUserForm.email" type="email" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.password') }}</label>
          <input v-model="newUserForm.password" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" :placeholder="$t('settings.admin.userManagementSettings.min8CharsUpperLowerDigit')" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.confirmPassword') }}</label>
          <input v-model="newUserForm.confirmPassword" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
      </div>
      <template #actions>
        <button @click="showCreateUserModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
          {{ $t('settings.admin.userManagementSettings.cancel') }}
        </button>
        <button @click="createUser" :disabled="saving" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ $t('settings.admin.userManagementSettings.create') }}
        </button>
      </template>
    </BaseModal>

    <!-- Create Team Modal -->
    <BaseModal
      :close-on-esc="!saving"
      v-model="showCreateTeamModal"
      :title="$t('settings.admin.userManagementSettings.createTeam')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.teamName') }}</label>
          <input v-model="newTeamForm.name" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" :placeholder="$t('settings.admin.userManagementSettings.eGEngineeringDesign')" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.descriptionOptional') }}</label>
          <textarea v-model="newTeamForm.description" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" :placeholder="$t('settings.admin.userManagementSettings.briefDescriptionOfTheTeamS')"></textarea>
        </div>
      </div>
      <template #actions>
        <button @click="showCreateTeamModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
          {{ $t('settings.admin.userManagementSettings.cancel') }}
        </button>
        <button @click="createTeam" :disabled="saving || !newTeamForm.name" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ $t('settings.admin.userManagementSettings.createTeam') }}
        </button>
      </template>
    </BaseModal>

    <!-- RBAC Init Modal -->
    <BaseModal
      :close-on-esc="!isInitializingRbac"
      v-model="showRbacModal"
      :title="$t('settings.admin.userManagementSettings.initializeRBACSystem')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <BaseAlert
        variant="warning"
        class="mb-4"
        :title="$t('settings.admin.userManagementSettings.rBACInitialization')"
        :message="$t('settings.admin.userManagementSettings.thisWillCreateSystem')"
      />

      <div class="space-y-4">
        <div class="flex items-center gap-3">
          <input id="create-admin" v-model="rbacInitOptions.createAdmin" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded-sm focus:ring-primary-500" />
          <label for="create-admin" class="text-sm text-gray-700">{{ $t('settings.admin.userManagementSettings.createInitialAdminUser') }}</label>
        </div>

        <div v-if="rbacInitOptions.createAdmin">
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.adminUsername') }}</label>
          <input v-model="rbacInitOptions.adminUsername" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
      </div>
      <template #actions>
        <button @click="showRbacModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
          {{ $t('settings.admin.userManagementSettings.cancel') }}
        </button>
        <button @click="initializeRbac" :disabled="isInitializingRbac" class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2">
          <svg v-if="isInitializingRbac" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ $t('settings.admin.userManagementSettings.initializeRBAC') }}
        </button>
      </template>
    </BaseModal>

    <!-- Create SSO Provider Modal -->
    <BaseModal
      :close-on-esc="!saving"
      v-model="showCreateProviderModal"
      :title="$t('settings.admin.userManagementSettings.addSSOProvider')"
      width="32rem"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.providerType') }}</label>
          <select v-model="newProviderForm.provider_type" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
            <option value="google">{{ $t('settings.admin.userManagementSettings.googleOAuth') }}</option>
            <option value="github">{{ $t('settings.admin.userManagementSettings.gitHub') }}</option>
            <option value="microsoft_entra">{{ $t('settings.admin.userManagementSettings.microsoftEntraID') }}</option>
            <option value="ldap">{{ $t('settings.admin.userManagementSettings.lDAP') }}</option>
            <option value="active_directory">{{ $t('settings.admin.userManagementSettings.activeDirectory') }}</option>
            <option value="saml">{{ $t('settings.admin.userManagementSettings.sAML20') }}</option>
            <option value="google_workspace">{{ $t('settings.admin.userManagementSettings.googleWorkspace') }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.displayName') }}</label>
          <input v-model="newProviderForm.name" type="text" :placeholder="$t('settings.admin.userManagementSettings.eGCompanyGoogleSSO')" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.clientID') }}</label>
          <input v-model="(newProviderForm.config as Record<string, string>).client_id" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.userManagementSettings.clientSecret') }}</label>
          <input v-model="(newProviderForm.config as Record<string, string>).client_secret" type="password" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
        </div>
        <div class="flex items-center gap-3">
          <input id="sso-active" v-model="newProviderForm.is_active" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded-sm focus:ring-primary-500" />
          <label for="sso-active" class="text-sm text-gray-700">{{ $t('settings.admin.userManagementSettings.active') }}</label>
        </div>
        <div class="flex items-center gap-3">
          <input id="sso-provision" v-model="newProviderForm.allow_user_creation" type="checkbox" class="w-4 h-4 text-primary-600 border-gray-300 rounded-sm focus:ring-primary-500" />
          <label for="sso-provision" class="text-sm text-gray-700">{{ $t('settings.admin.userManagementSettings.allowAutomaticUserCreation') }}</label>
        </div>
      </div>
      <template #actions>
        <button @click="showCreateProviderModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">{{ $t('settings.admin.userManagementSettings.cancel') }}</button>
        <button @click="createSsoProvider" :disabled="saving" class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50">{{ $t('settings.admin.userManagementSettings.createProvider') }}</button>
      </template>
    </BaseModal>
  </div>
</template>
