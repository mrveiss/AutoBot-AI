<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import WaveformPlayer from '@/components/transcriber/WaveformPlayer.vue'
import SegmentTable from '@/components/transcriber/SegmentTable.vue'
import {
  useTranscriberApi,
  type Recording,
  type Segment,
  type Speaker,
} from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TranscriptView')

const route = useRoute()
const api = useTranscriberApi()
const store = useTranscriberStore()

const recordingId = computed(() => Number(route.params.recordingId))

const recording = ref<Recording | null>(null)
const segments = ref<Segment[]>([])
const speakers = ref<Speaker[]>([])
const waveformPeaks = ref<number[]>([])
const currentTime = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const player = ref<InstanceType<typeof WaveformPlayer> | null>(null)

const status = computed(() => recording.value?.status ?? null)
const isInProgress = computed(
  () => status.value === 'pending' || status.value === 'processing'
)
const isFailed = computed(() => status.value === 'error')
const isComplete = computed(() => status.value === 'complete')
const audioUrl = computed(() => api.audioChunksUrl(recordingId.value))

async function load() {
  loading.value = true
  error.value = null
  try {
    recording.value = await api.getRecording(recordingId.value)
    // Segments only exist once transcription has completed.
    if (recording.value.status === 'complete') {
      const transcript = await api.getTranscript(recordingId.value)
      store.setTranscript(transcript)
      segments.value = transcript.segments
      speakers.value = transcript.speakers
      try {
        const waveform = await api.getWaveform(recordingId.value)
        waveformPeaks.value = waveform.peaks ?? []
      } catch (waveErr) {
        // Waveform peaks are an optimisation; playback still works without them.
        logger.warn('Failed to load waveform peaks', waveErr)
      }
    }
  } catch (err) {
    logger.error('Failed to load transcript', err)
    error.value = 'Failed to load this recording.'
  } finally {
    loading.value = false
  }
}

// WaveformPlayer reports playback progress; drives active-segment highlighting.
function onPlaybackProgress(seconds: number) {
  currentTime.value = seconds
}

// SegmentTable requests a seek when a row's timestamp is clicked.
function onSegmentSeek(seconds: number) {
  currentTime.value = seconds
  player.value?.seekTo(seconds)
}

onMounted(load)
</script>

<template>
  <div class="transcript-view">
    <div v-if="loading" class="transcript-state">Loading transcript…</div>

    <div v-else-if="error" class="transcript-state transcript-error">{{ error }}</div>

    <div v-else-if="isInProgress" class="transcript-state transcript-progress">
      <span class="transcript-spinner" aria-hidden="true" />
      <p>Transcription in progress… this view will populate once processing completes.</p>
    </div>

    <div v-else-if="isFailed" class="transcript-state transcript-error">
      <p>Transcription failed{{ recording?.failure_reason ? `: ${recording.failure_reason}` : '.' }}</p>
    </div>

    <template v-else-if="isComplete">
      <WaveformPlayer
        ref="player"
        class="transcript-player"
        :audio-url="audioUrl"
        :peaks="waveformPeaks"
        @seek="onPlaybackProgress"
      />
      <SegmentTable
        v-if="segments.length"
        :segments="segments"
        :speakers="speakers"
        :current-time="currentTime"
        @seek="onSegmentSeek"
      />
      <div v-else class="transcript-state">No transcript segments were produced for this recording.</div>
    </template>
  </div>
</template>

<style scoped>
.transcript-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.transcript-player {
  margin-bottom: 0.5rem;
}

.transcript-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--color-text-secondary, #6b7280);
  text-align: center;
}

.transcript-error {
  color: var(--color-danger-600, #dc2626);
}

.transcript-spinner {
  width: 1.5rem;
  height: 1.5rem;
  border: 2px solid var(--color-primary-300, #93c5fd);
  border-top-color: var(--color-primary-600, #2563eb);
  border-radius: 50%;
  animation: transcript-spin 0.8s linear infinite;
}

@keyframes transcript-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
