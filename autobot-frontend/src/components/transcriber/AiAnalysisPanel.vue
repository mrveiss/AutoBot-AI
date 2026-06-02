<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AiAnalysisPanel')
const props = defineProps<{ recordingId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const streaming = ref(false)
const content = ref('')
const customQuestion = ref('')
const activeAction = ref('')

async function ask(action: string) {
  activeAction.value = action
  streaming.value = true
  content.value = ''
  const url = `${getBackendUrl()}/api/transcriber/recordings/${props.recordingId}/ai/ask`
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, custom_question: action === 'custom' ? customQuestion.value : null }),
    })
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      for (const line of text.split('\n')) {
        if (!line.startsWith('data:')) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') { streaming.value = false; return }
        try {
          const parsed = JSON.parse(data)
          if (parsed.content) content.value += parsed.content
          if (parsed.error) { content.value = `Error: ${parsed.error}`; streaming.value = false; return }
        } catch { /* ignore */ }
      }
    }
  } catch (err) {
    logger.error('AI ask failed', err)
    content.value = 'Analysis failed. Please try again.'
  } finally {
    streaming.value = false
  }
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
        <button class="btn btn-sm" @click="ask('summarize')" :disabled="streaming">Summarize</button>
        <button class="btn btn-sm" @click="ask('key_facts')" :disabled="streaming">Key Facts</button>
        <button class="btn btn-sm" @click="ask('protocol')" :disabled="streaming">Protocol</button>
      </div>
      <div class="ai-panel-custom">
        <input v-model="customQuestion" placeholder="Custom question…" class="input" />
        <button class="btn btn-sm" @click="ask('custom')" :disabled="streaming || !customQuestion.trim()">
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
