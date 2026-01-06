<template>
  <div class="user-management-settings">
    <h3>User Management</h3>

    <!-- Authentication Status -->
    <div class="settings-section">
      <h4>Authentication Status</h4>
      <div class="auth-status">
        <div v-if="userStore.isAuthenticated" class="auth-status-card authenticated">
          <i class="fas fa-check-circle"></i>
          <div class="status-info">
            <span class="status-label">Authenticated</span>
            <span class="user-info">{{ userStore.currentUser?.username }} ({{ userStore.currentUser?.role }})</span>
          </div>
          <button @click="handleLogout" class="logout-btn">
            <i class="fas fa-sign-out-alt"></i>
            Logout
          </button>
        </div>

        <div v-else class="auth-status-card unauthenticated">
          <i class="fas fa-exclamation-triangle"></i>
          <div class="status-info">
            <span class="status-label">Not Authenticated</span>
            <span class="user-info">Please log in to access user features</span>
          </div>
          <button @click="showLoginModal = true" class="login-btn">
            <i class="fas fa-sign-in-alt"></i>
            Login
          </button>
        </div>
      </div>
    </div>

    <!-- User Profile Management -->
    <div v-if="userStore.isAuthenticated" class="settings-section">
      <h4>Profile Settings</h4>
      <div class="profile-settings">
        <div class="form-group">
          <label for="username">Username</label>
          <input
            id="username"
            type="text"
            v-model="profileForm.username"
            :disabled="!isEditingProfile"
            class="form-control"
          />
        </div>

        <div class="form-group">
          <label for="email">Email</label>
          <input
            id="email"
            type="email"
            v-model="profileForm.email"
            :disabled="!isEditingProfile"
            class="form-control"
          />
        </div>

        <div class="form-group">
          <label for="role">Role</label>
          <input
            id="role"
            type="text"
            v-model="profileForm.role"
            disabled
            class="form-control"
          />
        </div>

        <div class="profile-actions">
          <button
            v-if="!isEditingProfile"
            @click="isEditingProfile = true"
            class="edit-btn"
          >
            <i class="fas fa-edit"></i>
            Edit Profile
          </button>

          <template v-else>
            <button @click="saveProfile" class="save-btn" :disabled="isSaving">
              <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
              {{ isSaving ? 'Saving...' : 'Save' }}
            </button>
            <button @click="cancelEditProfile" class="cancel-btn">
              <i class="fas fa-times"></i>
              Cancel
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- User Preferences -->
    <div v-if="userStore.isAuthenticated" class="settings-section">
      <h4>User Preferences</h4>
      <div class="preferences-settings">
        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="preferences.enableNotifications"
              @change="handlePreferenceCheckboxChange('enableNotifications')"
            />
            Enable notifications
          </label>
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="preferences.autoSaveSettings"
              @change="handlePreferenceCheckboxChange('autoSaveSettings')"
            />
            Auto-save settings
          </label>
        </div>

        <div class="form-group">
          <label for="theme">Theme</label>
          <select
            id="theme"
            v-model="preferences.theme"
            @change="handlePreferenceSelectChange('theme')"
            class="form-control"
          >
            <option value="auto">Auto (System)</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>

        <div class="form-group">
          <label for="language">Language</label>
          <select
            id="language"
            v-model="preferences.language"
            @change="handlePreferenceSelectChange('language')"
            class="form-control"
          >
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Security Settings -->
    <div v-if="userStore.isAuthenticated" class="settings-section">
      <h4>Security</h4>
      <div class="security-settings">
        <div class="form-group">
          <label for="sessionTimeout">Session Timeout (minutes)</label>
          <input
            id="sessionTimeout"
            type="number"
            v-model="securitySettings.sessionTimeout"
            @change="handleSecurityNumberInputChange('sessionTimeout')"
            class="form-control"
            min="5"
            max="1440"
          />
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="securitySettings.requireReauth"
              @change="handleSecurityCheckboxChange('requireReauth')"
            />
            Require re-authentication for sensitive operations
          </label>
        </div>

        <button @click="showChangePasswordModal = true" class="change-password-btn">
          <i class="fas fa-key"></i>
          Change Password
        </button>
      </div>
    </div>

    <!-- RBAC Management (Admin Only) - Issue #687 -->
    <div v-if="userStore.isAdmin" class="settings-section">
      <h4>Role-Based Access Control</h4>
      <div class="rbac-settings">
        <div class="rbac-status">
          <div class="status-indicator" :class="rbacStatus.initialized ? 'initialized' : 'not-initialized'">
            <i :class="rbacStatus.initialized ? 'fas fa-check-circle' : 'fas fa-exclamation-triangle'"></i>
            <span>{{ rbacStatus.initialized ? 'RBAC Initialized' : 'RBAC Not Initialized' }}</span>
          </div>
          <p class="status-message">{{ rbacStatus.message }}</p>
        </div>

        <div class="rbac-info">
          <p><strong>System Permissions:</strong> 23 permissions across 8 resources</p>
          <p><strong>System Roles:</strong> admin, user, readonly, guest</p>
        </div>

        <div class="rbac-actions">
          <button
            @click="showRbacInitModal = true"
            class="init-rbac-btn"
            :disabled="isInitializingRbac"
          >
            <i :class="isInitializingRbac ? 'fas fa-spinner fa-spin' : 'fas fa-shield-alt'"></i>
            {{ isInitializingRbac ? 'Initializing...' : 'Initialize RBAC' }}
          </button>
          <button @click="checkRbacStatus" class="check-status-btn" :disabled="isCheckingRbacStatus">
            <i :class="isCheckingRbacStatus ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
            Refresh Status
          </button>
        </div>

        <!-- Progress indicator during initialization -->
        <div v-if="rbacTaskId" class="rbac-progress">
          <div class="progress-header">
            <span>Initialization Progress</span>
            <span class="task-status" :class="rbacTaskStatus">{{ rbacTaskStatus }}</span>
          </div>
          <div v-if="rbacProgressInfo" class="progress-details">
            <p v-if="rbacProgressInfo.task_name">Current task: {{ rbacProgressInfo.task_name }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Login Modal -->
    <BaseModal
      v-model="showLoginModal"
      title="Login"
      size="medium"
    >
      <LoginForm @login-success="onLoginSuccess" @login-error="onLoginError" />
    </BaseModal>

    <!-- RBAC Initialization Modal - Issue #687 -->
    <BaseModal
      v-model="showRbacInitModal"
      title="Initialize RBAC System"
      size="medium"
      :closeOnOverlay="!isInitializingRbac"
    >
      <div class="rbac-init-modal">
        <div class="alert alert-warning">
          <i class="fas fa-exclamation-triangle"></i>
          <div>
            <strong>RBAC Initialization</strong>
            <p>This will create system permissions and roles in the database. It is safe to run multiple times - existing entries will not be duplicated.</p>
          </div>
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="rbacInitOptions.createAdmin"
              :disabled="isInitializingRbac"
            />
            Create initial admin user
          </label>
        </div>

        <div v-if="rbacInitOptions.createAdmin" class="form-group">
          <label for="adminUsername">Admin Username</label>
          <input
            id="adminUsername"
            type="text"
            v-model="rbacInitOptions.adminUsername"
            class="form-control"
            :disabled="isInitializingRbac"
          />
        </div>

        <!-- Progress indicator during initialization -->
        <div v-if="isInitializingRbac && rbacTaskId" class="progress-section">
          <div class="progress-header">
            <i class="fas fa-spinner fa-spin"></i>
            <span class="status-text">{{ rbacStatusMessage }}</span>
          </div>
          <div v-if="rbacProgressInfo" class="progress-details">
            <p v-if="rbacProgressInfo.task_name"><strong>Task:</strong> {{ rbacProgressInfo.task_name }}</p>
            <p v-if="(rbacProgressInfo as any).host"><strong>Host:</strong> {{ (rbacProgressInfo as any).host }}</p>
          </div>
          <div class="task-info">
            <span class="task-id">Task ID: {{ rbacTaskId.substring(0, 8) }}...</span>
            <span class="task-status-badge" :class="rbacTaskStatus.toLowerCase()">{{ rbacTaskStatus }}</span>
          </div>
        </div>

        <!-- Result message -->
        <div v-if="rbacInitResult" class="alert" :class="rbacInitResult.success ? 'alert-success' : 'alert-error'">
          <i :class="rbacInitResult.success ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>
          {{ rbacInitResult.message }}
        </div>
      </div>

      <template #actions>
        <button @click="showRbacInitModal = false" class="cancel-btn" :disabled="isInitializingRbac">
          Cancel
        </button>
        <button @click="initializeRbac" class="save-btn" :disabled="isInitializingRbac">
          <i :class="isInitializingRbac ? 'fas fa-spinner fa-spin' : 'fas fa-shield-alt'"></i>
          {{ isInitializingRbac ? 'Initializing...' : 'Initialize RBAC' }}
        </button>
      </template>
    </BaseModal>

    <!-- Change Password Modal -->
    <BaseModal
      v-model="showChangePasswordModal"
      title="Change Password"
      size="medium"
      :closeOnOverlay="!isChangingPassword"
    >
      <!-- Success Message -->
      <div v-if="passwordSuccess" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        {{ passwordSuccess }}
      </div>

      <!-- Error Message -->
      <div v-if="passwordError" class="alert alert-error">
        <i class="fas fa-exclamation-circle"></i>
        {{ passwordError }}
      </div>

      <div class="form-group">
        <label for="currentPassword">Current Password</label>
        <input
          id="currentPassword"
          type="password"
          v-model="passwordForm.currentPassword"
          class="form-control"
          :disabled="isChangingPassword"
        />
      </div>

      <div class="form-group">
        <label for="newPassword">New Password</label>
        <input
          id="newPassword"
          type="password"
          v-model="passwordForm.newPassword"
          class="form-control"
          :disabled="isChangingPassword"
        />
        <small class="form-hint">
          Password must be at least 8 characters with uppercase, lowercase, and a number.
        </small>
      </div>

      <div class="form-group">
        <label for="confirmPassword">Confirm New Password</label>
        <input
          id="confirmPassword"
          type="password"
          v-model="passwordForm.confirmPassword"
          class="form-control"
          :disabled="isChangingPassword"
        />
      </div>

      <template #actions>
        <button @click="showChangePasswordModal = false" class="cancel-btn" :disabled="isChangingPassword">
          Cancel
        </button>
        <button @click="changePassword" class="save-btn" :disabled="isChangingPassword || passwordSuccess !== ''">
          <i :class="isChangingPassword ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
          {{ isChangingPassword ? 'Changing...' : 'Change Password' }}
        </button>
      </template>
    </BaseModal>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useUserStore } from '../../stores/useUserStore'
import LoginForm from '../auth/LoginForm.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('UserManagementSettings')
const userStore = useUserStore()

// Props
interface Props {
  isSettingsLoaded: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'setting-changed': [key: string, value: any]
}>()

// State
const showLoginModal = ref(false)
const showChangePasswordModal = ref(false)
const isEditingProfile = ref(false)
const isSaving = ref(false)
const isChangingPassword = ref(false)
const passwordError = ref('')
const passwordSuccess = ref('')

// RBAC State (Issue #687)
const MAX_POLL_ATTEMPTS = 120 // 2 minutes max polling (120 * 1000ms)
const showRbacInitModal = ref(false)
const isInitializingRbac = ref(false)
const isCheckingRbacStatus = ref(false)
const rbacTaskId = ref<string | null>(null)
const rbacTaskStatus = ref('')
const rbacPollAttempts = ref(0)
const rbacProgressInfo = ref<{ task_name?: string } | null>(null)
const rbacInitResult = ref<{ success: boolean; message: string } | null>(null)
const rbacStatus = reactive({
  initialized: false,
  message: 'Checking RBAC status...',
})
const rbacInitOptions = reactive({
  createAdmin: false,
  adminUsername: 'admin',
})

// Computed status messages for better UX (Issue #687, #544)
const rbacStatusMessage = computed(() => {
  if (!rbacTaskId.value) return 'Preparing...'
  switch (rbacTaskStatus.value) {
    case 'PENDING':
      return 'Task queued, waiting for worker...'
    case 'PROGRESS':
      return rbacProgressInfo.value?.task_name || 'Running Ansible playbook...'
    case 'SUCCESS':
      return 'RBAC initialization complete!'
    case 'FAILURE':
      return 'RBAC initialization failed'
    default:
      return `Status: ${rbacTaskStatus.value || 'Waiting...'}`
  }
})

// Forms
const profileForm = reactive({
  username: '',
  email: '',
  role: ''
})

const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const preferences = reactive({
  enableNotifications: true,
  autoSaveSettings: true,
  theme: 'auto',
  language: 'en'
})

const securitySettings = reactive({
  sessionTimeout: 30,
  requireReauth: true
})

// Methods
const handleLogout = async () => {
  try {
    await userStore.logout()
    emit('setting-changed', 'user.logout', true)
  } catch (error) {
    logger.error('Logout failed:', error)
  }
}

const onLoginSuccess = () => {
  showLoginModal.value = false
  loadUserData()
  emit('setting-changed', 'user.login', true)
}

const onLoginError = (error: string) => {
  logger.error('Login error:', error)
}

const saveProfile = async () => {
  try {
    isSaving.value = true
    await userStore.updateProfile({
      username: profileForm.username,
      email: profileForm.email
    })
    isEditingProfile.value = false
    emit('setting-changed', 'user.profile', profileForm)
  } catch (error) {
    logger.error('Failed to save profile:', error)
  } finally {
    isSaving.value = false
  }
}

const cancelEditProfile = () => {
  isEditingProfile.value = false
  loadUserData()
}

const updatePreference = (key: string, value: any) => {
  userStore.updatePreferences({ [key]: value })
  emit('setting-changed', `user.preferences.${key}`, value)
}

const updateSecuritySetting = (key: string, value: any) => {
  emit('setting-changed', `user.security.${key}`, value)
}

// Typed event handlers
const handlePreferenceCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updatePreference(key, target.checked)
}

const handlePreferenceSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  updatePreference(key, target.value)
}

const handleSecurityNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSecuritySetting(key, target.value)
}

const handleSecurityCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSecuritySetting(key, target.checked)
}

const changePassword = async () => {
  // Validate passwords match
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    passwordError.value = 'New passwords do not match'
    return
  }

  // Clear any previous errors
  passwordError.value = ''
  passwordSuccess.value = ''

  try {
    isChangingPassword.value = true

    const result = await userStore.changePassword(
      passwordForm.currentPassword,
      passwordForm.newPassword
    )

    if (result.success) {
      passwordSuccess.value = result.message
      // Clear form and close modal after a short delay to show success message
      setTimeout(() => {
        showChangePasswordModal.value = false
        passwordForm.currentPassword = ''
        passwordForm.newPassword = ''
        passwordForm.confirmPassword = ''
        passwordSuccess.value = ''
        passwordError.value = ''
      }, 1500)
      emit('setting-changed', 'user.password', true)
    } else {
      passwordError.value = result.message
    }
  } catch (error) {
    logger.error('Failed to change password:', error)
    passwordError.value = 'An unexpected error occurred. Please try again.'
  } finally {
    isChangingPassword.value = false
  }
}

const loadUserData = () => {
  if (userStore.currentUser) {
    profileForm.username = userStore.currentUser.username
    profileForm.email = userStore.currentUser.email || ''
    profileForm.role = userStore.currentUser.role
  }

  if (userStore.currentUser?.preferences) {
    Object.assign(preferences, userStore.currentUser.preferences)
  }
}

// RBAC Methods (Issue #687)
const checkRbacStatus = async () => {
  if (!userStore.isAdmin) return

  isCheckingRbacStatus.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/settings/rbac/status`, {
      headers: {
        'Authorization': `Bearer ${userStore.authState.token}`,
      },
    })

    if (response.ok) {
      const data = await response.json()
      rbacStatus.initialized = data.initialized
      rbacStatus.message = data.message
    } else {
      rbacStatus.message = 'Failed to check RBAC status'
    }
  } catch (error) {
    logger.error('Error checking RBAC status:', error)
    rbacStatus.message = 'Error checking RBAC status'
  } finally {
    isCheckingRbacStatus.value = false
  }
}

const resetRbacState = () => {
  rbacTaskId.value = null
  rbacTaskStatus.value = ''
  rbacPollAttempts.value = 0
  rbacProgressInfo.value = null
  rbacInitResult.value = null
}

const initializeRbac = async () => {
  // Reset all RBAC state before starting new initialization
  resetRbacState()
  isInitializingRbac.value = true

  try {
    const response = await fetch(`${getBackendUrl()}/api/settings/rbac/initialize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userStore.authState.token}`,
      },
      body: JSON.stringify({
        create_admin: rbacInitOptions.createAdmin,
        admin_username: rbacInitOptions.adminUsername,
      }),
    })

    if (response.ok) {
      const data = await response.json()
      rbacTaskId.value = data.task_id
      rbacTaskStatus.value = 'PENDING'

      // Start polling for task status
      pollRbacTaskStatus()
    } else {
      const error = await response.json()
      rbacInitResult.value = {
        success: false,
        message: error.detail || 'Failed to start RBAC initialization',
      }
      isInitializingRbac.value = false
    }
  } catch (error) {
    logger.error('Error initializing RBAC:', error)
    rbacInitResult.value = {
      success: false,
      message: 'Error connecting to server',
    }
    isInitializingRbac.value = false
  }
}

const pollRbacTaskStatus = async () => {
  if (!rbacTaskId.value) return

  // Check for polling timeout
  rbacPollAttempts.value++
  if (rbacPollAttempts.value > MAX_POLL_ATTEMPTS) {
    logger.warn('RBAC polling timeout reached after %d attempts', MAX_POLL_ATTEMPTS)
    rbacInitResult.value = {
      success: false,
      message: 'Polling timeout reached. The task may still be running. Please refresh status manually.',
    }
    isInitializingRbac.value = false
    return
  }

  try {
    const response = await fetch(
      `${getBackendUrl()}/api/settings/rbac/status/${rbacTaskId.value}`,
      {
        headers: {
          'Authorization': `Bearer ${userStore.authState.token}`,
        },
      }
    )

    if (response.ok) {
      const data = await response.json()
      rbacTaskStatus.value = data.status

      if (data.status === 'PROGRESS') {
        rbacProgressInfo.value = data.progress
        // Continue polling
        setTimeout(pollRbacTaskStatus, 1000)
      } else if (data.status === 'SUCCESS') {
        rbacInitResult.value = {
          success: true,
          message: data.result?.message || 'RBAC initialized successfully',
        }
        isInitializingRbac.value = false
        // Refresh RBAC status
        await checkRbacStatus()
      } else if (data.status === 'FAILURE') {
        rbacInitResult.value = {
          success: false,
          message: data.error || 'RBAC initialization failed',
        }
        isInitializingRbac.value = false
      } else if (data.status === 'PENDING') {
        // Continue polling
        setTimeout(pollRbacTaskStatus, 1000)
      }
    } else {
      // HTTP error response
      logger.error('RBAC polling received error response: %d', response.status)
      rbacInitResult.value = {
        success: false,
        message: `Failed to get task status (HTTP ${response.status}). Please refresh status manually.`,
      }
      isInitializingRbac.value = false
    }
  } catch (error) {
    logger.error('Error polling RBAC task status:', error)
    rbacInitResult.value = {
      success: false,
      message: 'Lost connection while checking task status. Please refresh status manually.',
    }
    isInitializingRbac.value = false
  }
}

// Watch for currentUser changes to reactively update profile form
// This fixes issue #595 where profile fields were empty because
// loadUserData() ran before currentUser was populated
watch(
  () => userStore.currentUser,
  (newUser) => {
    if (newUser && !isEditingProfile.value) {
      profileForm.username = newUser.username
      profileForm.email = newUser.email || ''
      profileForm.role = newUser.role

      if (newUser.preferences) {
        Object.assign(preferences, newUser.preferences)
      }
    }
  },
  { immediate: true }
)

onMounted(async () => {
  // Check auth from backend first (handles single_user mode auto-auth)
  if (!userStore.isAuthenticated) {
    await userStore.checkAuthFromBackend()
  }
  // Note: loadUserData() is now handled by the watcher above

  // Check RBAC status if admin (Issue #687)
  if (userStore.isAdmin) {
    await checkRbacStatus()
  }
})
</script>

<style scoped>
.user-management-settings {
  padding: 24px;
}

.user-management-settings h3 {
  color: #2c3e50;
  margin-bottom: 24px;
  font-size: 24px;
  font-weight: 600;
}

.settings-section {
  margin-bottom: 32px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
}

.settings-section h4 {
  color: #495057;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 500;
}

/* Authentication Status */
.auth-status-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border-radius: 8px;
  border: 2px solid;
}

.auth-status-card.authenticated {
  background: #d4edda;
  border-color: #28a745;
  color: #155724;
}

.auth-status-card.unauthenticated {
  background: #f8d7da;
  border-color: #dc3545;
  color: #721c24;
}

.auth-status-card i {
  font-size: 24px;
}

.status-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.status-label {
  font-weight: 600;
  font-size: 16px;
}

.user-info {
  font-size: 14px;
  opacity: 0.8;
}

.login-btn, .logout-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.login-btn {
  background: #007bff;
  color: white;
}

.logout-btn {
  background: #dc3545;
  color: white;
}

/* Form Elements */
.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
  color: #495057;
}

.form-control {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.form-control:disabled {
  background: #e9ecef;
  color: #6c757d;
}

/* Action Buttons */
.profile-actions, .form-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.edit-btn, .save-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cancel-btn {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.change-password-btn {
  background: #ffc107;
  color: #212529;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Alert messages */
.alert {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-success {
  background: #d4edda;
  border: 1px solid #c3e6cb;
  color: #155724;
}

.alert-error {
  background: #f8d7da;
  border: 1px solid #f5c6cb;
  color: #721c24;
}

.alert i {
  font-size: 16px;
}

/* Form hint */
.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #6c757d;
}

/* Disabled button styles */
button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* RBAC Settings (Issue #687) */
.rbac-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rbac-status {
  padding: 16px;
  background: #e9ecef;
  border-radius: 8px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}

.status-indicator.initialized {
  color: #28a745;
}

.status-indicator.not-initialized {
  color: #ffc107;
}

.status-message {
  color: #6c757d;
  font-size: 14px;
  margin: 0;
}

.rbac-info {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  font-size: 14px;
}

.rbac-info p {
  margin: 4px 0;
}

.rbac-actions {
  display: flex;
  gap: 12px;
}

.init-rbac-btn {
  background: #6f42c1;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.init-rbac-btn:hover:not(:disabled) {
  background: #5a32a3;
}

.check-status-btn {
  background: #17a2b8;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.check-status-btn:hover:not(:disabled) {
  background: #138496;
}

.rbac-progress {
  padding: 12px;
  background: #e3f2fd;
  border-radius: 6px;
  border-left: 4px solid #2196f3;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.task-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.task-status.PENDING {
  background: #ffc107;
  color: #212529;
}

.task-status.PROGRESS {
  background: #17a2b8;
  color: white;
}

.task-status.SUCCESS {
  background: #28a745;
  color: white;
}

.task-status.FAILURE {
  background: #dc3545;
  color: white;
}

.progress-details {
  margin-top: 8px;
  font-size: 14px;
  color: #495057;
}

/* Progress section for modals (Issue #687, #544) */
.progress-section {
  margin: 16px 0;
  padding: 16px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border-radius: 8px;
  border-left: 4px solid #2196f3;
}

.progress-section .progress-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-section .status-text {
  font-weight: 500;
  color: #1565c0;
}

.progress-section .task-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(33, 150, 243, 0.2);
}

.progress-section .task-id {
  font-family: monospace;
  font-size: 12px;
  color: #546e7a;
}

.task-status-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  text-transform: uppercase;
  font-weight: 600;
}

.task-status-badge.pending {
  background: #fff3cd;
  color: #856404;
}

.task-status-badge.progress {
  background: #17a2b8;
  color: white;
}

.task-status-badge.success {
  background: #28a745;
  color: white;
}

.task-status-badge.failure {
  background: #dc3545;
  color: white;
}

.rbac-init-modal .alert {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.alert-warning {
  background: #fff3cd;
  border: 1px solid #ffc107;
  color: #856404;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .user-management-settings h3,
  .settings-section h4 {
    color: #ffffff;
  }

  .settings-section {
    background: #2d2d2d;
  }

  .form-group label {
    color: #ffffff;
  }

  .form-control {
    background: #3d3d3d;
    border-color: #555;
    color: #ffffff;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .user-management-settings {
    padding: 16px;
  }

  .auth-status-card {
    flex-direction: column;
    text-align: center;
  }

  .profile-actions, .form-actions {
    flex-direction: column;
  }

  .modal-content {
    width: 95%;
  }
}
</style>