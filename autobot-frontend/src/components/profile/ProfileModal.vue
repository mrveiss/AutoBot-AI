<!-- autobot-frontend/src/components/profile/ProfileModal.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div v-if="isOpen" class="modal-overlay" @click="handleClose">
    <div
      ref="dialogRef"
      class="modal-content"
      @click.stop
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-title"
      tabindex="-1"
      @keydown="onFocusTrapKeydown"
      @keydown.escape="handleClose"
    >
      <div class="modal-header">
        <h2 id="profile-title">{{ $t('profile.title') }}</h2>
        <button @click="handleClose" class="close-button" :aria-label="$t('profile.closeAria')">&times;</button>
      </div>

      <!-- Tab Bar -->
      <div class="tab-bar" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          role="tab"
          :aria-selected="activeTab === tab.key"
          :aria-controls="`panel-${tab.key}`"
          type="button"
          @click="activeTab = tab.key"
        >
          <Icon :name="tab.icon" />
          {{ tab.label }}
        </button>
      </div>

      <div class="modal-body">
        <!-- General Tab -->
        <div v-if="activeTab === 'general'" id="panel-general" role="tabpanel">
          <div class="profile-section">
            <h3>{{ $t('profile.accountInfo') }}</h3>
            <div class="info-grid">
              <div class="info-row">
                <label>{{ $t('profile.username') }}</label>
                <span>{{ currentUser?.username || 'N/A' }}</span>
              </div>
              <div class="info-row">
                <label>{{ $t('profile.email') }}</label>
                <span>{{ currentUser?.email || 'N/A' }}</span>
              </div>
              <div class="info-row">
                <label>{{ $t('profile.role') }}</label>
                <span class="role-badge" :class="`role-${currentUser?.role}`">{{ currentUser?.role || 'N/A' }}</span>
              </div>
              <div class="info-row">
                <label>{{ $t('profile.lastLogin') }}</label>
                <span>{{ formatDate(currentUser?.lastLoginAt) }}</span>
              </div>
            </div>
          </div>

          <div class="profile-section">
            <h3>{{ $t('profile.preferences') }}</h3>

            <div class="pref-group">
              <label class="pref-label">{{ $t('profile.theme') }}</label>
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

            <div class="pref-group">
              <label class="pref-label">{{ $t('profile.notifications') }}</label>
              <div class="toggle-list">
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.notifications.email" />
                  <span>{{ $t('profile.emailNotifications') }}</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.notifications.browser" />
                  <span>{{ $t('profile.browserNotifications') }}</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.notifications.sound" />
                  <span>{{ $t('profile.soundNotifications') }}</span>
                </label>
              </div>
            </div>

            <div class="pref-group">
              <label class="pref-label">{{ $t('profile.interface') }}</label>
              <div class="toggle-list">
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.ui.compactMode" />
                  <span>{{ $t('profile.compactMode') }}</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.ui.showTooltips" />
                  <span>{{ $t('profile.showTooltips') }}</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="localPrefs.ui.animationsEnabled" />
                  <span>{{ $t('profile.enableAnimations') }}</span>
                </label>
              </div>
            </div>

            <button @click="savePreferences" class="save-btn" type="button">
              {{ $t('profile.savePreferences') }}
            </button>
          </div>
        </div>

        <!-- Appearance & Voice Tab -->
        <div v-if="activeTab === 'appearance'" id="panel-appearance" role="tabpanel">
          <div class="profile-section">
            <h3>{{ $t('profile.appearance') }}</h3>
            <PreferencesPanel />
          </div>

          <div class="profile-section">
            <h3>{{ $t('profile.voiceChatDisplay') }}</h3>
            <div class="option-row">
              <button
                @click="setVoiceDisplayMode('modal')"
                class="option-btn"
                :class="{ active: voiceDisplayMode === 'modal' }"
                type="button"
              >
                <Icon name="expand-alt" class="mr-1" />
                {{ $t('profile.fullScreen') }}
              </button>
              <button
                @click="setVoiceDisplayMode('sidepanel')"
                class="option-btn"
                :class="{ active: voiceDisplayMode === 'sidepanel' }"
                type="button"
              >
                <Icon name="columns" class="mr-1" />
                {{ $t('profile.sidePanel') }}
              </button>
            </div>
          </div>

          <div class="profile-section">
            <h3>{{ $t('profile.voiceProfiles') }}</h3>
            <VoiceSettingsPanel />
          </div>
        </div>

        <!-- Language Tab -->
        <div v-if="activeTab === 'language'" id="panel-language" role="tabpanel">
          <LanguageSettingsPanel />
        </div>

        <!-- Security Tab -->
        <div v-if="activeTab === 'security'" id="panel-security" role="tabpanel">
          <div class="profile-section">
            <h3>{{ $t('profile.changePassword') }}</h3>
            <div class="pw-form">
              <input
                v-model="passwordForm.current"
                type="password"
                :placeholder="$t('profile.currentPassword')"
                class="pw-input"
                autocomplete="current-password"
              />
              <input
                v-model="passwordForm.newPw"
                type="password"
                :placeholder="$t('profile.newPassword')"
                class="pw-input"
                autocomplete="new-password"
              />
              <input
                v-model="passwordForm.confirm"
                type="password"
                :placeholder="$t('profile.confirmNewPassword')"
                class="pw-input"
                autocomplete="new-password"
              />
              <button
                @click="changePassword"
                class="save-btn"
                type="button"
                :disabled="isChangingPassword"
              >
                {{ isChangingPassword ? $t('profile.changing') : $t('profile.changePassword') }}
              </button>
            </div>
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
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/useUserStore'
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import VoiceSettingsPanel from '@/components/settings/VoiceSettingsPanel.vue'
import LanguageSettingsPanel from '@/components/settings/LanguageSettingsPanel.vue'
import { usePreferences } from '@/composables/usePreferences'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'

const props = defineProps<{
  isOpen: boolean
}>()

const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)
useFocusRestore(toRef(props, 'isOpen'))
useBodyScrollLock(toRef(props, 'isOpen'))
const { focusFirst } = useInitialFocus(dialogRef)
watch(() => props.isOpen, (open) => { if (open) focusFirst() }, { immediate: true })

const emit = defineEmits<{
  close: []
}>()

type TabKey = 'general' | 'appearance' | 'language' | 'security'

const tabs = computed<{ key: TabKey; label: string; icon: string }[]>(() => [
  { key: 'general', label: t('profile.tabGeneral'), icon: 'user' },
  { key: 'appearance', label: t('profile.tabAppearance'), icon: 'palette' },
  { key: 'language', label: t('profile.tabLanguage'), icon: 'globe' },
  { key: 'security', label: t('profile.tabSecurity'), icon: 'shield-alt' }
])

const { t } = useI18n()
const activeTab = ref<TabKey>('general')

const userStore = useUserStore()
const { voiceDisplayMode, setVoiceDisplayMode } = usePreferences()
const currentUser = computed(() => userStore.currentUser)
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const isChangingPassword = ref(false)

const themeOptions = computed(() => [
  { value: 'light' as const, label: t('profile.themeLight') },
  { value: 'dark' as const, label: t('profile.themeDark') },
  { value: 'auto' as const, label: t('profile.themeAuto') }
])

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
  showSuccess(t('profile.preferencesSaved'))
}

async function changePassword(): Promise<void> {
  const { current, newPw, confirm } = passwordForm.value

  if (!current || !newPw || !confirm) {
    showError(t('profile.pwFillAll'))
    return
  }

  if (newPw !== confirm) {
    showError(t('profile.pwMismatch'))
    return
  }

  if (newPw.length < 8) {
    showError(t('profile.pwTooShort'))
    return
  }

  isChangingPassword.value = true
  try {
    const result = await userStore.changePassword(current, newPw)
    if (result.success) {
      passwordForm.value = { current: '', newPw: '', confirm: '' }
      showSuccess(t('profile.pwChanged'))
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
  if (!dateValue) return t('profile.never')
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
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: var(--shadow-xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h2 {
  margin: var(--spacing-0);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
}

.close-button {
  background: none;
  border: none;
  font-size: 32px;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-0);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-default);
  transition: background-color var(--duration-200);
}

.close-button:hover {
  background: var(--bg-secondary);
}

.tab-bar {
  display: flex;
  gap: var(--spacing-0);
  border-bottom: 1px solid var(--border-default);
  padding: var(--spacing-0) var(--spacing-6);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-3) var(--spacing-4);
  border: none;
  background: none;
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: var(--spacing-neg-px);
  transition: color var(--duration-150), border-color var(--duration-150);
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-primary, #6366f1);
  border-bottom-color: var(--color-primary, #6366f1);
}

.tab-btn i {
  font-size: var(--text-sm);
}

.modal-body {
  padding: var(--spacing-6);
}

.profile-section {
  margin-bottom: var(--spacing-8);
}

.profile-section:last-child {
  margin-bottom: var(--spacing-0);
}

.profile-section h3 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.info-row label {
  font-weight: 500;
  color: var(--text-muted);
}

.info-row span {
  color: var(--text-primary);
}

.role-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
}

.role-admin { background: var(--color-warning-bg); color: var(--color-warning); }
.role-user { background: var(--color-info-bg); color: var(--color-info); }
.role-viewer { background: var(--bg-tertiary); color: var(--text-secondary); }

.pref-group {
  margin-bottom: var(--spacing-5);
}

.pref-label {
  display: block;
  font-weight: 500;
  color: var(--text-muted);
  font-size: var(--text-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-2);
}

.option-row {
  display: flex;
  gap: var(--spacing-2);
}

.option-btn {
  padding: var(--spacing-1-5) var(--spacing-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-150);
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
  gap: var(--spacing-2);
}

.toggle-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.toggle-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  border-radius: var(--radius-default);
  cursor: pointer;
}

.save-btn {
  margin-top: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--color-primary, #6366f1);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--duration-150);
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
  gap: var(--spacing-2-5);
}

.pw-input {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  width: 100%;
  box-sizing: border-box;
}

.pw-input:focus {
  outline: none;
  border-color: var(--color-primary, #6366f1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}
.pw-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  font-weight: 500;
  animation: slideIn 0.3s ease-out;
  z-index: var(--z-popover);
}

.toast.success {
  background: var(--color-success);
  color: var(--text-inverse);
}

.toast.error {
  background: var(--color-error);
  color: var(--text-inverse);
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
