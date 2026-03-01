<!-- autobot-frontend/src/components/profile/ProfileModal.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div v-if="isOpen" class="modal-overlay" @click="handleClose">
    <div class="modal-content" @click.stop role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <div class="modal-header">
        <h2 id="profile-title">Profile Settings</h2>
        <button @click="handleClose" class="close-button" aria-label="Close profile settings">&times;</button>
      </div>

      <div class="modal-body">
        <!-- Account Information -->
        <div class="profile-section">
          <h3>Account Information</h3>
          <div class="info-grid">
            <div class="info-row">
              <label>Username:</label>
              <span>{{ currentUser?.username || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Email:</label>
              <span>{{ currentUser?.email || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Role:</label>
              <span class="role-badge" :class="`role-${currentUser?.role}`">{{ currentUser?.role || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Last Login:</label>
              <span>{{ formatDate(currentUser?.lastLoginAt) }}</span>
            </div>
          </div>
        </div>

        <!-- Preferences Section -->
        <div class="profile-section">
          <h3>Preferences</h3>

          <!-- Theme -->
          <div class="pref-group">
            <label class="pref-label">Theme</label>
            <div class="option-row">
              <button
                v-for="opt in themeOptions"
                :key="opt.value"
                @click="localPrefs.theme = opt.value"
                class="option-btn"
                :class="{ active: localPrefs.theme === opt.value }"
                type="button"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <!-- Notifications -->
          <div class="pref-group">
            <label class="pref-label">Notifications</label>
            <div class="toggle-list">
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.notifications.email" />
                <span>Email notifications</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.notifications.browser" />
                <span>Browser notifications</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.notifications.sound" />
                <span>Sound notifications</span>
              </label>
            </div>
          </div>

          <!-- UI Settings -->
          <div class="pref-group">
            <label class="pref-label">Interface</label>
            <div class="toggle-list">
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.ui.compactMode" />
                <span>Compact mode</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.ui.showTooltips" />
                <span>Show tooltips</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="localPrefs.ui.animationsEnabled" />
                <span>Enable animations</span>
              </label>
            </div>
          </div>

          <button @click="savePreferences" class="save-btn" type="button">
            Save Preferences
          </button>
        </div>

        <!-- Appearance Settings (Issue #753) -->
        <div class="profile-section">
          <h3>Appearance</h3>
          <PreferencesPanel />
        </div>

        <!-- Voice Settings -->
        <div class="profile-section">
          <h3>Voice</h3>
          <VoiceSettingsPanel />
        </div>

        <!-- Change Password Section -->
        <div class="profile-section">
          <h3>Change Password</h3>
          <div class="pw-form">
            <input
              v-model="passwordForm.current"
              type="password"
              placeholder="Current password"
              class="pw-input"
              autocomplete="current-password"
            />
            <input
              v-model="passwordForm.newPw"
              type="password"
              placeholder="New password"
              class="pw-input"
              autocomplete="new-password"
            />
            <input
              v-model="passwordForm.confirm"
              type="password"
              placeholder="Confirm new password"
              class="pw-input"
              autocomplete="new-password"
            />
            <button
              @click="changePassword"
              class="save-btn"
              type="button"
              :disabled="isChangingPassword"
            >
              {{ isChangingPassword ? 'Changing...' : 'Change Password' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Success Toast -->
      <div v-if="successMessage" class="toast success" role="status">
        {{ successMessage }}
      </div>

      <!-- Error Toast -->
      <div v-if="errorMessage" class="toast error" role="alert">
        {{ errorMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useUserStore } from '@/stores/useUserStore'
import type { UserPreferences } from '@/stores/useUserStore'
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import VoiceSettingsPanel from '@/components/settings/VoiceSettingsPanel.vue'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const userStore = useUserStore()
const currentUser = computed(() => userStore.currentUser)
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const isChangingPassword = ref(false)

const themeOptions = [
  { value: 'light' as const, label: 'Light' },
  { value: 'dark' as const, label: 'Dark' },
  { value: 'auto' as const, label: 'Auto' }
]

const localPrefs = ref({
  theme: userStore.preferences.theme,
  notifications: { ...userStore.preferences.notifications },
  ui: { ...userStore.preferences.ui }
})

// Sync localPrefs when the modal opens
watch(
  () => userStore.preferences,
  (prefs) => {
    localPrefs.value = {
      theme: prefs.theme,
      notifications: { ...prefs.notifications },
      ui: { ...prefs.ui }
    }
  },
  { deep: true }
)

const passwordForm = ref({ current: '', newPw: '', confirm: '' })

function handleClose(): void {
  emit('close')
}

function savePreferences(): void {
  userStore.updateTheme(localPrefs.value.theme)
  userStore.updateNotificationSettings(localPrefs.value.notifications)
  userStore.updateUISettings(localPrefs.value.ui)
  userStore.persistToStorage()
  showSuccess('Preferences saved.')
}

async function changePassword(): Promise<void> {
  const { current, newPw, confirm } = passwordForm.value

  if (!current || !newPw || !confirm) {
    showError('Please fill in all password fields.')
    return
  }

  if (newPw !== confirm) {
    showError('New passwords do not match.')
    return
  }

  if (newPw.length < 8) {
    showError('New password must be at least 8 characters.')
    return
  }

  isChangingPassword.value = true
  try {
    const result = await userStore.changePassword(current, newPw)
    if (result.success) {
      passwordForm.value = { current: '', newPw: '', confirm: '' }
      showSuccess('Password changed successfully.')
    } else {
      showError(result.message)
    }
  } finally {
    isChangingPassword.value = false
  }
}

function showSuccess(msg: string): void {
  errorMessage.value = null
  successMessage.value = msg
  setTimeout(() => { successMessage.value = null }, 5000)
}

function showError(msg: string): void {
  successMessage.value = null
  errorMessage.value = msg
  setTimeout(() => { errorMessage.value = null }, 5000)
}

function formatDate(dateValue: Date | string | undefined | null): string {
  if (!dateValue) return 'Never'
  const date = dateValue instanceof Date ? dateValue : new Date(dateValue)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}
</script>

<style scoped>
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
  background: var(--bg-card);
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-button {
  background: none;
  border: none;
  font-size: 32px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-button:hover {
  background: var(--bg-secondary);
}

.modal-body {
  padding: 24px;
}

.profile-section {
  margin-bottom: 32px;
}

.profile-section:last-child {
  margin-bottom: 0;
}

.profile-section h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.info-row label {
  font-weight: 500;
  color: var(--text-muted);
}

.info-row span {
  color: var(--text-primary);
}

.role-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.role-admin { background: #fbbf24; color: #78350f; }
.role-user { background: #60a5fa; color: #1e3a8a; }
.role-viewer { background: #94a3b8; color: #1e293b; }

.pref-group {
  margin-bottom: 20px;
}

.pref-label {
  display: block;
  font-weight: 500;
  color: var(--text-muted);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.option-row {
  display: flex;
  gap: 8px;
}

.option-btn {
  padding: 6px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}

.option-btn:hover {
  background: var(--bg-tertiary);
}

.option-btn.active {
  background: var(--color-primary, #6366f1);
  color: white;
  border-color: var(--color-primary, #6366f1);
}

.toggle-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.toggle-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
}

.toggle-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  cursor: pointer;
}

.save-btn {
  margin-top: 16px;
  padding: 8px 20px;
  background: var(--color-primary, #6366f1);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.save-btn:hover {
  opacity: 0.9;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pw-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pw-input {
  padding: 8px 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 14px;
  width: 100%;
  box-sizing: border-box;
}

.pw-input:focus {
  outline: none;
  border-color: var(--color-primary, #6366f1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  font-weight: 500;
  animation: slideIn 0.3s ease-out;
  z-index: 1100;
}

.toast.success {
  background: #10b981;
  color: white;
}

.toast.error {
  background: #ef4444;
  color: white;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
