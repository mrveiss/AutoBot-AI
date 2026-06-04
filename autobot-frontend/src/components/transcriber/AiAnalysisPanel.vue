<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, toRef, computed } from 'vue'
import { useAiAnalysis, type AiAction } from '@/composables/transcriber/useAiAnalysis'

const props = defineProps<{ recordingId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const customQuestion = ref('')

const { result, loading, error, ask } = useAiAnalysis(toRef(props, 'recordingId'))

const displayContent = computed(() => {
  if (error.value) return `Error: ${error.value}`
  return result.value
})

async function handleAsk(action: AiAction) {
  await ask(action, action === 'custom' ? customQuestion.value : undefined)
}
</script>

<template>
  <Transition name="slide">
    <div v-if="open" class="ai-panel">
      <div class="ai-panel-header">
        <span>AI Analysis</span>
        <button class="btn-icon" @click="emit('close')">✕</button>
      </div>
      <div class="ai-panel-actions">
        <button class="btn btn-sm" @click="handleAsk('summarize')" :disabled="loading">Summarize</button>
        <button class="btn btn-sm" @click="handleAsk('key_facts')" :disabled="loading">Key Facts</button>
        <button class="btn btn-sm" @click="handleAsk('protocol')" :disabled="loading">Protocol</button>
      </div>
      <div class="ai-panel-custom">
        <input v-model="customQuestion" placeholder="Custom question…" class="input" />
        <button class="btn btn-sm" @click="handleAsk('custom')" :disabled="loading || !customQuestion.trim()">
          Ask
        </button>
      </div>
      <div class="ai-panel-content">
        <span v-if="loading" class="ai-streaming-cursor">▌</span>
        <pre v-if="displayContent" class="ai-result">{{ displayContent }}</pre>
        <span v-else-if="!loading" class="ai-empty">Choose an action above to analyze the transcript.</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ai-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: var(--color-background);
  border-left: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
  font-weight: 600;
}

.ai-panel-actions {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.ai-panel-custom {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.ai-panel-custom .input {
  flex: 1;
}

.ai-panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.ai-result {
  white-space: pre-wrap;
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1.5;
}

.ai-empty {
  color: var(--color-text-secondary);
  font-style: italic;
}

.ai-streaming-cursor {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
