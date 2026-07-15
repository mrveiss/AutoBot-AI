<template>
  <!-- Multi-model compare panel (Issue #4414) -->
  <div class="multi-model-chat" role="region" :aria-label="$t('chat.compare.panelLabel')">

    <!-- Model picker -->
    <div class="multi-model-chat__picker">
      <span class="multi-model-chat__picker-label">{{ $t('chat.compare.selectModels') }}</span>
      <div class="multi-model-chat__checkboxes">
        <label
          v-for="model in availableModels"
          :key="model"
          class="multi-model-chat__model-checkbox"
        >
          <input
            type="checkbox"
            :value="model"
            v-model="selectedModels"
            :aria-label="model"
          />
          <span class="multi-model-chat__model-name">{{ model }}</span>
          <span
            v-if="contextWindowLabel[model]"
            class="multi-model-chat__model-ctx"
            :title="`Context window: ${contextWindowLabel[model]} tokens`"
          >{{ contextWindowLabel[model] }}</span>
        </label>
      </div>
    </div>

    <!-- Prompt input + send -->
    <div class="multi-model-chat__input-row">
      <textarea
        v-model="promptText"
        class="multi-model-chat__textarea"
        rows="3"
        :placeholder="$t('chat.compare.promptPlaceholder')"
        :disabled="isComparing"
        @keydown.ctrl.enter.prevent="onSend"
        :aria-label="$t('chat.compare.promptLabel')"
      />
      <button
        class="multi-model-chat__send-btn"
        :disabled="isComparing || !promptText.trim() || selectedModels.length === 0"
        @click="onSend"
        :aria-label="$t('chat.compare.sendLabel')"
      >
        <span v-if="isComparing">
          <Icon name="spinner" class="animate-spin" />
        </span>
        <span v-else>{{ $t('chat.compare.send') }}</span>
      </button>
    </div>

    <!-- Response columns -->
    <div
      v-if="responses.size > 0"
      class="multi-model-chat__responses"
      :class="responses.size <= 3 ? 'multi-model-chat__responses--columns' : 'multi-model-chat__responses--stacked'"
    >
      <div
        v-for="[model, state] in responses"
        :key="model"
        class="multi-model-chat__response-card"
        :class="{
          'multi-model-chat__response-card--done': state.done,
          'multi-model-chat__response-card--error': !!state.error,
        }"
      >
        <div class="multi-model-chat__response-header">
          <span class="multi-model-chat__response-model">{{ model }}</span>
          <span
            v-if="state.error"
            class="multi-model-chat__response-badge multi-model-chat__response-badge--error"
            role="status"
          >{{ $t('chat.compare.error') }}</span>
          <span
            v-else-if="state.done"
            class="multi-model-chat__response-badge multi-model-chat__response-badge--done"
            role="status"
          >{{ $t('chat.compare.done') }}</span>
          <span
            v-else
            class="multi-model-chat__response-badge multi-model-chat__response-badge--streaming"
            role="status"
            aria-live="polite"
          >{{ $t('chat.compare.streaming') }}</span>
        </div>

        <div class="multi-model-chat__response-body">
          <p v-if="state.error" class="multi-model-chat__error-msg">{{ state.error }}</p>
          <pre v-else class="multi-model-chat__response-text">{{ state.content }}<span v-if="!state.done" class="multi-model-chat__cursor" aria-hidden="true">▋</span></pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useMultiModelCompare } from '@/composables/useMultiModelCompare'
// GH#8990: show per-model context window in picker
import { useModelPicker } from '@/composables/useModelPicker'

const { responses, selectedModels, isComparing, compare, reset } = useMultiModelCompare()
// #10755/#10718: source the model list from the live /api/models endpoint (no
// hardcoded defaults) and seed the selection once it loads — shared wiring.
const { models: llmModels, availableModels } = useModelPicker(selectedModels)

const promptText = ref('')

// Map model name → formatted context window label (GH#8990)
const contextWindowLabel = computed(() => {
  const map: Record<string, string> = {}
  for (const m of llmModels.value) {
    if (!m.context_window) continue
    const cw = m.context_window
    map[m.name] = cw >= 1_000_000
      ? `${(cw / 1_000_000).toFixed(1)}M`
      : cw >= 1_000
      ? `${Math.round(cw / 1_000)}k`
      : String(cw)
  }
  return map
})

async function onSend(): Promise<void> {
  if (!promptText.value.trim() || selectedModels.value.length === 0 || isComparing.value) return
  await compare(promptText.value)
}

defineExpose({ reset })
</script>

<style scoped>
.multi-model-chat {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3, 0.75rem);
  padding: var(--spacing-4, 1rem);
  background: var(--color-bg-card, #1e1e2e);
  border-radius: var(--radius-lg, 0.5rem);
  overflow: hidden;
}

/* ---- Picker ---- */
.multi-model-chat__picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
}

.multi-model-chat__picker-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-muted, #9ca3af);
  white-space: nowrap;
}

.multi-model-chat__checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2, 0.5rem);
}

.multi-model-chat__model-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-1, 0.25rem);
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--text-primary, #e5e7eb);
}

.multi-model-chat__model-name {
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
}

.multi-model-chat__model-ctx {
  font-size: 0.6875rem;
  font-family: ui-monospace, monospace;
  color: var(--text-muted, #9ca3af);
  background: var(--color-bg-tertiary, #1a1a2e);
  border-radius: 0.25rem;
  padding: 0 0.25rem;
  cursor: default;
}

/* ---- Input row ---- */
.multi-model-chat__input-row {
  display: flex;
  gap: var(--spacing-2, 0.5rem);
}

.multi-model-chat__textarea {
  flex: 1;
  resize: vertical;
  background: var(--color-bg-input, #2a2a3e);
  color: var(--text-primary, #e5e7eb);
  border: 1px solid var(--border-default, #374151);
  border-radius: var(--radius-md, 0.375rem);
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  font-size: 0.875rem;
  line-height: 1.5;
}

.multi-model-chat__textarea:focus {
  outline: 2px solid var(--color-electric-500, #6366f1);
  outline-offset: 1px;
}

.multi-model-chat__send-btn {
  align-self: flex-end;
  padding: var(--spacing-2, 0.5rem) var(--spacing-4, 1rem);
  background: var(--color-electric-600, #4f46e5);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 0.375rem);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}

.multi-model-chat__send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.multi-model-chat__send-btn:not(:disabled):hover {
  background: var(--color-electric-500, #6366f1);
}

/* ---- Responses ---- */
.multi-model-chat__responses {
  display: grid;
  gap: var(--spacing-3, 0.75rem);
  overflow-y: auto;
  max-height: 60vh;
}

.multi-model-chat__responses--columns {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.multi-model-chat__responses--stacked {
  grid-template-columns: 1fr;
}

.multi-model-chat__response-card {
  background: var(--color-bg-secondary, #13131f);
  border: 1px solid var(--border-default, #374151);
  border-radius: var(--radius-md, 0.375rem);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.multi-model-chat__response-card--error {
  border-color: var(--color-error, #ef4444);
}

.multi-model-chat__response-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  background: var(--color-bg-tertiary, #1a1a2e);
  border-bottom: 1px solid var(--border-default, #374151);
  gap: var(--spacing-2, 0.5rem);
}

.multi-model-chat__response-model {
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
  color: var(--text-muted, #9ca3af);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.multi-model-chat__response-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-sm, 0.25rem);
  white-space: nowrap;
  flex-shrink: 0;
}

.multi-model-chat__response-badge--streaming {
  background: var(--color-electric-900, #1e1b4b);
  color: var(--color-electric-300, #a5b4fc);
}

.multi-model-chat__response-badge--done {
  background: var(--color-success-900, #14532d);
  color: var(--color-success-300, #86efac);
}

.multi-model-chat__response-badge--error {
  background: var(--color-error-900, #450a0a);
  color: var(--color-error-300, #fca5a5);
}

.multi-model-chat__response-body {
  padding: var(--spacing-3, 0.75rem);
  flex: 1;
  overflow: auto;
}

.multi-model-chat__response-text {
  margin: var(--spacing-0);
  font-family: ui-monospace, monospace;
  font-size: 0.8125rem;
  color: var(--text-primary, #e5e7eb);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.multi-model-chat__error-msg {
  font-size: 0.8125rem;
  color: var(--color-error, #ef4444);
  margin: var(--spacing-0);
}

.multi-model-chat__cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
