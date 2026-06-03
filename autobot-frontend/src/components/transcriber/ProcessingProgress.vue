<!-- autobot-frontend/src/components/transcriber/ProcessingProgress.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useSseProgress } from '@/composables/transcriber/useSseProgress'

const props = defineProps<{ recordingId: number }>()
const emit = defineEmits<{ (e: 'complete'): void; (e: 'error'): void }>()

const { percent, step, status, connect } = useSseProgress(props.recordingId)

onMounted(() => {
  connect()
})

watch(status, (val) => {
  if (val === 'complete') emit('complete')
  if (val === 'error') emit('error')
})
</script>

<template>
  <div class="processing-progress">
    <div class="progress-bar-track">
      <div class="progress-bar-fill" :style="{ width: `${percent}%` }" />
    </div>
    <span class="progress-step">{{ step || 'Processing…' }} {{ percent }}%</span>
  </div>
</template>
