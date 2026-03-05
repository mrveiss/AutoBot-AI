<template>
  <div class="translation-panel">
    <div class="translation-panel-header">
      <h4 class="panel-title">
        <i class="fas fa-language" aria-hidden="true"></i>
        {{ $t('chat.translate.title') }}
      </h4>
      <BaseButton
        variant="ghost"
        size="xs"
        @click="$emit('close')"
        :aria-label="$t('chat.translate.close')"
      >
        <i class="fas fa-times" aria-hidden="true"></i>
      </BaseButton>
    </div>

    <div class="translation-panel-body">
      <!-- Language Selection -->
      <div class="language-row">
        <label for="target-language" class="language-label">
          {{ $t('chat.translate.targetLanguage') }}
        </label>
        <select
          id="target-language"
          v-model="targetLanguage"
          class="language-select"
        >
          <option
            v-for="lang in languages"
            :key="lang.code"
            :value="lang.name"
          >
            {{ lang.name }}
          </option>
        </select>
      </div>

      <!-- Text Input -->
      <div class="text-row">
        <label for="translate-text" class="sr-only">
          {{ $t('chat.translate.textToTranslate') }}
        </label>
        <textarea
          id="translate-text"
          v-model="textToTranslate"
          class="translate-textarea"
          :placeholder="$t('chat.translate.placeholder')"
          rows="3"
        ></textarea>
      </div>

      <!-- Action Buttons -->
      <div class="action-row">
        <BaseButton
          variant="ghost"
          size="sm"
          @click="detectLanguage"
          :disabled="!textToTranslate.trim() || isLoading"
          class="detect-btn"
        >
          <i class="fas fa-search" aria-hidden="true"></i>
          {{ $t('chat.translate.detectLanguage') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          @click="translateText"
          :disabled="!canTranslate"
          :loading="isLoading"
        >
          <i class="fas fa-language" aria-hidden="true"></i>
          {{ $t('chat.translate.translate') }}
        </BaseButton>
      </div>

      <!-- Result Display -->
      <div v-if="detectedLanguage" class="result-info">
        <i class="fas fa-info-circle" aria-hidden="true"></i>
        {{ $t('chat.translate.detectedAs', { language: detectedLanguage }) }}
      </div>

      <div v-if="translationError" class="result-error">
        <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
        {{ translationError }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Issue #1328: Translation shortcut panel with language picker
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
const logger = createLogger('TranslationShortcutPanel')

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'translation-result', payload: {
    originalText: string
    translatedText: string
    targetLanguage: string
    sourceLanguage?: string
  }): void
}>()

const props = defineProps<{
  initialText?: string
}>()

// State
const textToTranslate = ref(props.initialText || '')
const targetLanguage = ref('Latvian')
const isLoading = ref(false)
const detectedLanguage = ref('')
const translationError = ref('')

// Supported languages — Latvian first as default (#1328)
const languages = [
  { code: 'lv', name: 'Latvian' },
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ru', name: 'Russian' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'ar', name: 'Arabic' },
  { code: 'hi', name: 'Hindi' },
  { code: 'nl', name: 'Dutch' },
  { code: 'pl', name: 'Polish' },
  { code: 'sv', name: 'Swedish' },
  { code: 'tr', name: 'Turkish' },
  { code: 'uk', name: 'Ukrainian' },
  { code: 'lt', name: 'Lithuanian' },
  { code: 'et', name: 'Estonian' },
]

const canTranslate = computed(() => {
  return textToTranslate.value.trim().length > 0
    && targetLanguage.value.length > 0
    && !isLoading.value
})

const translateText = async () => {
  if (!canTranslate.value) return

  isLoading.value = true
  translationError.value = ''

  try {
    const result = await apiClient.post('/api/translate', {
      text: textToTranslate.value.trim(),
      target_language: targetLanguage.value,
    })

    if (result.status === 'success') {
      emit('translation-result', {
        originalText: textToTranslate.value.trim(),
        translatedText: result.response,
        targetLanguage: targetLanguage.value,
      })
    } else {
      translationError.value = result.response || t('chat.translate.error')
    }
  } catch (error) {
    logger.error('Translation failed:', error)
    translationError.value = t('chat.translate.error')
  } finally {
    isLoading.value = false
  }
}

const detectLanguage = async () => {
  if (!textToTranslate.value.trim()) return

  isLoading.value = true
  detectedLanguage.value = ''
  translationError.value = ''

  try {
    const result = await apiClient.post('/api/detect-language', {
      text: textToTranslate.value.trim(),
    })

    if (result.status === 'success') {
      detectedLanguage.value = result.response
    } else {
      translationError.value = result.response || t('chat.translate.error')
    }
  } catch (error) {
    logger.error('Language detection failed:', error)
    translationError.value = t('chat.translate.error')
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.translation-panel {
  @apply border border-autobot-border rounded-lg bg-autobot-bg-card
    shadow-lg mb-3;
}

.translation-panel-header {
  @apply flex items-center justify-between px-3 py-2
    border-b border-autobot-border;
}

.panel-title {
  @apply text-sm font-medium text-autobot-text-primary flex items-center
    gap-2;
}

.translation-panel-body {
  @apply p-3 space-y-3;
}

.language-row {
  @apply flex items-center gap-2;
}

.language-label {
  @apply text-xs font-medium text-autobot-text-secondary whitespace-nowrap;
}

.language-select {
  @apply flex-1 text-sm border border-autobot-border rounded px-2 py-1.5
    bg-autobot-bg-tertiary text-autobot-text-primary;
}

.translate-textarea {
  @apply w-full text-sm border border-autobot-border rounded px-3 py-2
    bg-autobot-bg-tertiary text-autobot-text-primary resize-none;
}

.translate-textarea:focus {
  @apply border-autobot-primary ring-1 ring-autobot-primary outline-none;
}

.action-row {
  @apply flex items-center justify-between gap-2;
}

.detect-btn {
  @apply text-xs;
}

.result-info {
  @apply text-xs text-autobot-text-secondary flex items-center gap-1
    bg-blue-50 px-2 py-1.5 rounded;
}

.result-error {
  @apply text-xs text-red-600 flex items-center gap-1
    bg-red-50 px-2 py-1.5 rounded;
}
</style>
