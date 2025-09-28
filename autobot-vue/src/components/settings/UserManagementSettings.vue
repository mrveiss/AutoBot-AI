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
            <span class="user-info">{{ userStore.user?.username }} ({{ userStore.user?.role }})</span>
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
              @change="updatePreference('enableNotifications', $event.target.checked)"
            />
            Enable notifications
          </label>
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="preferences.autoSaveSettings"
              @change="updatePreference('autoSaveSettings', $event.target.checked)"
            />
            Auto-save settings
          </label>
        </div>

        <div class="form-group">
          <label for="theme">Theme</label>
          <select
            id="theme"
            v-model="preferences.theme"
            @change="updatePreference('theme', $event.target.value)"
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
            @change="updatePreference('language', $event.target.value)"
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
            @change="updateSecuritySetting('sessionTimeout', $event.target.value)"
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
              @change="updateSecuritySetting('requireReauth', $event.target.checked)"
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

    <!-- Login Modal -->
    <teleport to="body">
      <div v-if="showLoginModal" class="modal-overlay" @click="showLoginModal = false">
        <div class="modal-content" @click.stop>
          <div class="modal-header">
            <h3>Login</h3>
            <button @click="showLoginModal = false" class="close-btn">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <LoginForm @login-success="onLoginSuccess" @login-error="onLoginError" />
        </div>
      </div>
    </teleport>

    <!-- Change Password Modal -->
    <teleport to="body">
      <div v-if="showChangePasswordModal" class="modal-overlay" @click="showChangePasswordModal = false">
        <div class="modal-content" @click.stop>
          <div class="modal-header">
            <h3>Change Password</h3>
            <button @click="showChangePasswordModal = false" class="close-btn">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="change-password-form">
            <div class="form-group">
              <label for="currentPassword">Current Password</label>
              <input
                id="currentPassword"
                type="password"
                v-model="passwordForm.currentPassword"
                class="form-control"
              />
            </div>

            <div class="form-group">
              <label for="newPassword">New Password</label>
              <input
                id="newPassword"
                type="password"
                v-model="passwordForm.newPassword"
                class="form-control"
              />
            </div>

            <div class="form-group">
              <label for="confirmPassword">Confirm New Password</label>
              <input
                id="confirmPassword"
                type="password"
                v-model="passwordForm.confirmPassword"
                class="form-control"
              />
            </div>

            <div class="form-actions">
              <button @click="changePassword" class="save-btn" :disabled="isChangingPassword">
                <i :class="isChangingPassword ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
                {{ isChangingPassword ? 'Changing...' : 'Change Password' }}
              </button>
              <button @click="showChangePasswordModal = false" class="cancel-btn">
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useUserStore } from '../../stores/useUserStore'
import LoginForm from '../auth/LoginForm.vue'

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
    console.error('Logout failed:', error)
  }
}

const onLoginSuccess = () => {
  showLoginModal.value = false
  loadUserData()
  emit('setting-changed', 'user.login', true)
}

const onLoginError = (error: string) => {
  console.error('Login error:', error)
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
    console.error('Failed to save profile:', error)
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

const changePassword = async () => {
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    alert('New passwords do not match')
    return
  }

  try {
    isChangingPassword.value = true
    await userStore.changePassword(passwordForm.currentPassword, passwordForm.newPassword)
    showChangePasswordModal.value = false
    passwordForm.currentPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
    emit('setting-changed', 'user.password', true)
  } catch (error) {
    console.error('Failed to change password:', error)
    alert('Failed to change password')
  } finally {
    isChangingPassword.value = false
  }
}

const loadUserData = () => {
  if (userStore.user) {
    profileForm.username = userStore.user.username
    profileForm.email = userStore.user.email || ''
    profileForm.role = userStore.user.role
  }

  if (userStore.user?.preferences) {
    Object.assign(preferences, userStore.user.preferences)
  }
}

onMounted(() => {
  loadUserData()
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

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  max-width: 500px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #dee2e6;
}

.modal-header h3 {
  margin: 0;
  color: #2c3e50;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #6c757d;
  font-size: 18px;
}

.change-password-form {
  padding: 20px;
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

  .modal-content {
    background: #2d2d2d;
  }

  .modal-header {
    border-bottom-color: #555;
  }

  .modal-header h3 {
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