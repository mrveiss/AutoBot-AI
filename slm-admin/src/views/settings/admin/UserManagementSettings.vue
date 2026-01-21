// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * UserManagementSettings - User and RBAC Management
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides user profile management, preferences, security settings, and RBAC.
 */

import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAutobotApi, type UserResponse } from '@/composables/useAutobotApi'

const authStore = useAuthStore()
const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// User list state (for admins)
const users = ref<UserResponse[]>([])
const selectedUser = ref<UserResponse | null>(null)
const showCreateUserModal = ref(false)
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

// Password change form
const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
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

// Methods
async function loadUsers(): Promise<void> {
  if (!isAdmin.value) return

  loading.value = true
  error.value = null

  try {
    const response = await api.getUsers()
    users.value = response.data
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load users'
  } finally {
    loading.value = false
  }
}

async function createUser(): Promise<void> {
  if (newUserForm.password !== newUserForm.confirmPassword) {
    error.value = 'Passwords do not match'
    return
  }

  saving.value = true
  error.value = null

  try {
    await api.createUser({
      username: newUserForm.username,
      email: newUserForm.email,
      password: newUserForm.password,
      roles: newUserForm.roles,
    })

    success.value = 'User created successfully'
    showCreateUserModal.value = false

    // Reset form
    newUserForm.username = ''
    newUserForm.email = ''
    newUserForm.password = ''
    newUserForm.confirmPassword = ''
    newUserForm.roles = ['user']

    await loadUsers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create user'
  } finally {
    saving.value = false
  }
}

async function deleteUser(userId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this user?')) return

  saving.value = true
  error.value = null

  try {
    await api.deleteUser(userId)
    success.value = 'User deleted successfully'
    await loadUsers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete user'
  } finally {
    saving.value = false
  }
}

async function changePassword(): Promise<void> {
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    error.value = 'New passwords do not match'
    return
  }

  saving.value = true
  error.value = null

  try {
    // Call password change API through AutoBot backend
    const response = await fetch('/autobot-api/auth/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token}`,
      },
      body: JSON.stringify({
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword,
      }),
    })

    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.detail || 'Failed to change password')
    }

    success.value = 'Password changed successfully'
    showChangePasswordModal.value = false

    // Reset form
    passwordForm.currentPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''

    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to change password'
  } finally {
    saving.value = false
  }
}

async function checkRbacStatus(): Promise<void> {
  if (!isAdmin.value) return

  try {
    const response = await fetch('/autobot-api/settings/rbac/status', {
      headers: {
        Authorization: `Bearer ${authStore.token}`,
      },
    })

    if (response.ok) {
      const data = await response.json()
      rbacStatus.initialized = data.initialized
      rbacStatus.message = data.message
    }
  } catch (e) {
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
      success.value = data.message || 'RBAC initialized successfully'
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

async function savePreferences(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    await api.updateSettingsSection('preferences', preferences)
    success.value = 'Preferences saved successfully'
    setTimeout(() => { success.value = null }, 3000)
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
    await api.updateSettingsSection('security', securitySettings)
    success.value = 'Security settings saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save security settings'
  } finally {
    saving.value = false
  }
}

function logout(): void {
  authStore.logout()
}

// Load data on mount
onMounted(async () => {
  // Set profile from current auth
  profileForm.username = authStore.user?.username || ''

  if (isAdmin.value) {
    await loadUsers()
    await checkRbacStatus()
  }
})

// Watch auth changes
watch(() => authStore.user, (newUser) => {
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
        <button
          @click="logout"
          class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2"
        >
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
        <!-- Theme -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Theme</label>
            <p class="text-xs text-gray-500 mt-1">Choose your preferred color scheme</p>
          </div>
          <select
            v-model="preferences.theme"
            class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="auto">Auto (System)</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>

        <!-- Language -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Language</label>
            <p class="text-xs text-gray-500 mt-1">Interface language</p>
          </div>
          <select
            v-model="preferences.language"
            class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>

        <!-- Notifications -->
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

        <!-- Auto-save -->
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
        <button
          @click="savePreferences"
          :disabled="saving"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          Save Preferences
        </button>
      </div>
    </div>

    <!-- Security Settings -->
    <div v-if="authStore.isAuthenticated" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Security</h2>

      <div class="space-y-4">
        <!-- Session Timeout -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Session Timeout</label>
            <p class="text-xs text-gray-500 mt-1">Auto-logout after inactivity (minutes)</p>
          </div>
          <input
            v-model.number="securitySettings.sessionTimeout"
            type="number"
            min="5"
            max="1440"
            class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>

        <!-- Require Reauth -->
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

        <!-- Change Password -->
        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">Password</label>
            <p class="text-xs text-gray-500 mt-1">Change your account password</p>
          </div>
          <button
            @click="showChangePasswordModal = true"
            class="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            Change Password
          </button>
        </div>
      </div>

      <div class="mt-6 flex justify-end">
        <button
          @click="saveSecuritySettings"
          :disabled="saving"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          Save Security Settings
        </button>
      </div>
    </div>

    <!-- User Management (Admin Only) -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">User Management</h2>
        <button
          @click="showCreateUserModal = true"
          class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Add User
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-8">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Users Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Username</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Email</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Roles</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Last Login</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-3 px-4 text-sm font-medium text-gray-900">{{ user.username }}</td>
              <td class="py-3 px-4 text-sm text-gray-600">{{ user.email || '-' }}</td>
              <td class="py-3 px-4">
                <div class="flex gap-1 flex-wrap">
                  <span
                    v-for="role in user.roles"
                    :key="role"
                    :class="[
                      'px-2 py-0.5 rounded-full text-xs font-medium',
                      role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700',
                    ]"
                  >
                    {{ role }}
                  </span>
                </div>
              </td>
              <td class="py-3 px-4 text-sm text-gray-600">{{ user.last_login || 'Never' }}</td>
              <td class="py-3 px-4 text-right">
                <button
                  @click="deleteUser(user.id)"
                  class="text-red-600 hover:text-red-800 p-1"
                  title="Delete user"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </td>
            </tr>
            <tr v-if="users.length === 0">
              <td colspan="5" class="py-8 text-center text-gray-500">
                No users found
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- RBAC Management (Admin Only) -->
    <div v-if="isAdmin" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Role-Based Access Control</h2>

      <div class="p-4 rounded-lg mb-4" :class="rbacStatus.initialized ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'">
        <div class="flex items-center gap-3">
          <svg
            :class="['w-5 h-5', rbacStatus.initialized ? 'text-green-500' : 'text-yellow-500']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              :d="rbacStatus.initialized ? 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' : 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'"
            />
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
        <button
          @click="showRbacModal = true"
          :disabled="isInitializingRbac"
          class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="isInitializingRbac" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Initialize RBAC
        </button>
        <button
          @click="checkRbacStatus"
          class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh Status
        </button>
      </div>
    </div>

    <!-- Change Password Modal -->
    <div v-if="showChangePasswordModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showChangePasswordModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Change Password</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Current Password</label>
            <input
              v-model="passwordForm.currentPassword"
              type="password"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">New Password</label>
            <input
              v-model="passwordForm.newPassword"
              type="password"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
            <p class="text-xs text-gray-500 mt-1">
              At least 8 characters with uppercase, lowercase, and a number.
            </p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
            <input
              v-model="passwordForm.confirmPassword"
              type="password"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showChangePasswordModal = false"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="changePassword"
            :disabled="saving"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Change Password
          </button>
        </div>
      </div>
    </div>

    <!-- Create User Modal -->
    <div v-if="showCreateUserModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showCreateUserModal = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Create User</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              v-model="newUserForm.username"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              v-model="newUserForm.email"
              type="email"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              v-model="newUserForm.password"
              type="password"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
            <input
              v-model="newUserForm.confirmPassword"
              type="password"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Role</label>
            <select
              v-model="newUserForm.roles[0]"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="readonly">Read Only</option>
            </select>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showCreateUserModal = false"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="createUser"
            :disabled="saving"
            class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Create User
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
                This will create system permissions and roles in the database. It is safe to run multiple times - existing entries will not be duplicated.
              </p>
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <input
              id="create-admin"
              v-model="rbacInitOptions.createAdmin"
              type="checkbox"
              class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <label for="create-admin" class="text-sm text-gray-700">Create initial admin user</label>
          </div>

          <div v-if="rbacInitOptions.createAdmin">
            <label class="block text-sm font-medium text-gray-700 mb-1">Admin Username</label>
            <input
              v-model="rbacInitOptions.adminUsername"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showRbacModal = false"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="initializeRbac"
            :disabled="isInitializingRbac"
            class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="isInitializingRbac" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            Initialize RBAC
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
