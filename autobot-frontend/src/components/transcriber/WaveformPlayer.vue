<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useWaveform } from '@/composables/transcriber/useWaveform'

const props = defineProps<{ audioUrl: string }>()
const emit = defineEmits<{ (e: 'seek', seconds: number): void }>()

const container = ref<HTMLElement | null>(null)
const { currentTime, duration, isPlaying, init, togglePlay } = useWaveform(container)

onMounted(() => init(props.audioUrl))
watch(() => props.audioUrl, (url) => init(url))

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="waveform-player">
    <div ref="container" class="waveform-container" />
    <div class="waveform-controls">
      <button class="btn btn-icon" @click="togglePlay" :aria-label="isPlaying ? 'Pause' : 'Play'">
        <span v-if="isPlaying">⏸</span>
        <span v-else>▶</span>
      </button>
      <span class="waveform-time">{{ fmt(currentTime) }} / {{ fmt(duration) }}</span>
    </div>
  </div>
</template>
