<template>
  <div class="translation-panel">
    <div class="translation-panel-header">
      <h4 class="panel-title">
        <Icon name="language" />
        {{ $t('chat.translate.title') }}
      </h4>
      <BaseButton
        variant="ghost"
        size="xs"
        @click="$emit('close')"
        :aria-label="$t('chat.translate.close')"
      >
        <Icon name="times" />
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
          <Icon name="search" />
          {{ $t('chat.translate.detectLanguage') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          @click="translateText"
          :disabled="!canTranslate"
          :loading="isLoading"
        >
          <Icon name="language" />
          {{ $t('chat.translate.translate') }}
        </BaseButton>
      </div>

      <!-- Result Display -->
      <div v-if="detectedLanguage" class="result-info">
        <Icon name="info-circle" />
        {{ $t('chat.translate.detectedAs', { language: detectedLanguage }) }}
      </div>

      <div v-if="translationError" class="result-error">
        <Icon name="exclamation-triangle" />
        {{ translationError }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Issue #1328: Translation shortcut panel with language picker
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import { useLoadingState } from '@/composables/useLoadingState'
import { useChatTranslation } from '@/composables/chat/useChatTranslation'

const { t } = useI18n()
const { translateText: doTranslate, detectLanguage: doDetect } = useChatTranslation()

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
const { isLoading, wrap } = useLoadingState()
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

  translationError.value = ''
  await wrap(async () => {
    const result = await doTranslate(textToTranslate.value.trim(), targetLanguage.value)
    if ('translatedText' in result) {
      emit('translation-result', {
        originalText: textToTranslate.value.trim(),
        translatedText: result.translatedText,
        targetLanguage: targetLanguage.value,
      })
    } else {
      translationError.value = result.error || t('chat.translate.error')
    }
  })
}

const detectLanguage = async () => {
  if (!textToTranslate.value.trim()) return

  detectedLanguage.value = ''
  translationError.value = ''
  await wrap(async () => {
    const result = await doDetect(textToTranslate.value.trim())
    if ('detectedLanguage' in result) {
      detectedLanguage.value = result.detectedLanguage
    } else {
      translationError.value = result.error || t('chat.translate.error')
    }
  })
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";
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
