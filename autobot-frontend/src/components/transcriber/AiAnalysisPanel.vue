<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { useAiAnalysis, type AiAnalysisAction } from '@/composables/transcriber/useAiAnalysis'

const props = defineProps<{ recordingId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const customQuestion = ref('')
const { streaming, content, ask } = useAiAnalysis(props.recordingId)

function handleAsk(action: AiAnalysisAction) {
  ask({ action, customQuestion: action === 'custom' ? customQuestion.value : undefined })
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
        <button class="btn btn-sm" @click="handleAsk('summarize')" :disabled="streaming">Summarize</button>
        <button class="btn btn-sm" @click="handleAsk('key_facts')" :disabled="streaming">Key Facts</button>
        <button class="btn btn-sm" @click="handleAsk('protocol')" :disabled="streaming">Protocol</button>
      </div>
      <div class="ai-panel-custom">
        <input v-model="customQuestion" placeholder="Custom question…" class="input" />
        <button class="btn btn-sm" @click="handleAsk('custom')" :disabled="streaming || !customQuestion.trim()">
          Ask
        </button>
      </div>
      <div class="ai-panel-content">
        <span v-if="streaming" class="ai-streaming-cursor">▌</span>
        <pre v-if="content" class="ai-result">{{ content }}</pre>
        <span v-else-if="!streaming" class="ai-empty">Choose an action above to analyze the transcript.</span>
      </div>
    </div>
  </Transition>
</template>
