<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

LanguageSettingsPanel.vue - Language Preference Settings
Issue #1330: Language switcher component in Settings
-->

<template>
  <form class="language-panel" @submit.prevent>
    <div class="panel-header">
      <h3 class="panel-title">
        <i class="fas fa-globe" aria-hidden="true"></i>
        {{ t('settings.languageTitle') }}
      </h3>
    </div>

    <div class="panel-content">
      <fieldset class="preference-section">
        <legend class="preference-label">
          <i class="fas fa-language" aria-hidden="true"></i>
          {{ t('settings.languageSelect') }}
        </legend>
        <p class="preference-hint">
          {{ t('settings.languageHint') }}
        </p>
        <div class="language-select-wrapper">
          <select
            v-model="selectedLanguage"
            @change="handleLanguageChange"
            class="language-select"
            :aria-label="t('settings.languageSelect')"
          >
            <option
              v-for="(name, code) in languages"
              :key="code"
              :value="code"
            >
              {{ name }}
            </option>
          </select>
          <i class="fas fa-chevron-down select-icon" aria-hidden="true"></i>
        </div>
      </fieldset>

      <div v-if="statusMessage" class="status-message" :class="statusType">
        <i
          :class="statusType === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-circle'"
          aria-hidden="true"
        ></i>
        {{ statusMessage }}
      </div>
    </div>

    <!-- Screen reader announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ announcement }}
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LanguageSettingsPanel')
const { t } = useI18n()

const selectedLanguage = ref(localStorage.getItem('autobot-language') || 'en')
const languages = ref<Record<string, string>>({ en: 'English' })
const announcement = ref('')
const statusMessage = ref('')
const statusType = ref<'success' | 'error'>('success')

onMounted(async () => {
  try {
    const response = await apiClient.get('/api/personality/languages')
    if (response.data && typeof response.data === 'object') {
      languages.value = response.data
    }
  } catch (error) {
    logger.error('Failed to load supported languages', error)
  }
})

async function handleLanguageChange() {
  const locale = selectedLanguage.value
  statusMessage.value = ''

  try {
    await setLocale(locale)

    await updatePersonalityLanguage(locale)

    statusMessage.value = t('settings.languageChanged')
    statusType.value = 'success'
    announceChange(t('settings.languageChanged'))
    logger.debug(`Language changed to: ${locale}`)
  } catch (error) {
    logger.error('Failed to change language', error)
    statusMessage.value = t('settings.languageChangeFailed')
    statusType.value = 'error'
  }
}

async function updatePersonalityLanguage(languageCode: string) {
  try {
    const activeResponse = await apiClient.get('/api/personality/active')
    if (activeResponse.data && activeResponse.data.id) {
      await apiClient.put(
        `/api/personality/profiles/${activeResponse.data.id}`,
        { language_code: languageCode }
      )
    }
  } catch (error) {
    logger.warn('Could not update personality profile language', error)
  }
}

function announceChange(message: string): void {
  announcement.value = message
  setTimeout(() => {
    announcement.value = ''
  }, 1000)
}
</script>

<style scoped>
.language-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.panel-title i {
  color: var(--color-primary);
}

.panel-content {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.preference-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  border: none;
  padding: 0;
  margin: 0;
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preference-label i {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.preference-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-normal);
}

.language-select-wrapper {
  position: relative;
  max-width: 320px;
}

.language-select {
  width: 100%;
  min-height: 44px;
  padding: var(--spacing-sm) var(--spacing-xl) var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  appearance: none;
  transition: all var(--transition-fast);
}

.language-select:hover {
  border-color: var(--color-primary);
}

.language-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.select-icon {
  position: absolute;
  right: var(--spacing-md);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  pointer-events: none;
}

.status-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.status-message.success {
  background: var(--color-success-bg, rgba(16, 185, 129, 0.1));
  color: var(--color-success, #10b981);
}

.status-message.error {
  background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
  color: var(--color-error, #ef4444);
}

@media (max-width: 768px) {
  .panel-content {
    padding: var(--spacing-md);
  }

  .language-select-wrapper {
    max-width: 100%;
  }
}
</style>
