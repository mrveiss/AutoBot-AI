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
        <Icon name="globe" aria-hidden="true" />
        {{ t('settings.languageTitle') }}
      </h3>
    </div>

    <div class="panel-content">
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="language" aria-hidden="true" />
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
          <Icon name="chevron-down" class="select-icon" aria-hidden="true" />
        </div>
      </fieldset>
    </div>

    <!-- Screen reader announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ announcement }}
    </div>
  </form>
</template>

<script setup lang="ts">
// Issue #1331: Use usePreferences for language persistence
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferences } from '@/composables/usePreferences'
import { useAvailableLanguages } from '@/composables/useAvailableLanguages'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('LanguageSettingsPanel')
const { t } = useI18n()
const { language, setLanguage } = usePreferences()
const { languages: availableLanguages } = useAvailableLanguages()
const { showToast } = useNotificationBus()

const selectedLanguage = ref(language.value)
// Convert to Record<string,string> for the existing template's v-for="(name, code) in languages"
const languages = computed<Record<string, string>>(() =>
  Object.fromEntries(availableLanguages.value.map(l => [l.code, l.name]))
)
const announcement = ref('')

async function handleLanguageChange() {
  const locale = selectedLanguage.value

  try {
    await setLanguage(locale)

    showToast(t('settings.languageChanged'), 'success')
    announceChange(t('settings.languageChanged'))
    logger.debug(`Language changed to: ${locale}`)
  } catch (error) {
    logger.error('Failed to change language', error)
    showToast(t('settings.languageChangeFailed'), 'error')
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
  padding: var(--spacing-0);
  margin: var(--spacing-neg-px);
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
  margin: var(--spacing-0);
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
  padding: var(--spacing-0);
  margin: var(--spacing-0);
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
  margin: var(--spacing-0);
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

@media (max-width: 768px) {
  .panel-content {
    padding: var(--spacing-md);
  }

  .language-select-wrapper {
    max-width: 100%;
  }
}
</style>
