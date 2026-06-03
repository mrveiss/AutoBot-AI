<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import WaveformPlayer from '@/components/transcriber/WaveformPlayer.vue'
import SegmentTable from '@/components/transcriber/SegmentTable.vue'
import AiAnalysisPanel from '@/components/transcriber/AiAnalysisPanel.vue'
import ExportMenu from '@/components/transcriber/ExportMenu.vue'
import KbPushButton from '@/components/transcriber/KbPushButton.vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TranscriptView')
const route = useRoute()
const api = useTranscriberApi()
const store = useTranscriberStore()

const recordingId = Number(route.params.recordingId)
const aiOpen = ref(false)
const currentTime = ref(0)

onMounted(async () => {
  try {
    const transcript = await api.getTranscript(recordingId)
    store.setTranscript(transcript)
  } catch (err) {
    logger.error('Failed to load transcript', err)
  }
})

function audioUrl() {
  return `${getBackendUrl()}/api/transcriber/recordings/${recordingId}/audio`
}
</script>

<template>
  <div class="transcript-view">
    <div class="transcript-toolbar">
      <RouterLink
        :to="{ name: 'transcriber-project-detail', params: { projectId: route.params.projectId } }"
        class="btn-link"
      >← Project</RouterLink>
      <h2 class="transcript-title">{{ store.activeRecording?.filename }}</h2>
      <div class="transcript-actions">
        <KbPushButton :recording-id="recordingId" />
        <ExportMenu
          :recording-id="recordingId"
          :filename="store.activeRecording?.filename ?? 'transcript'"
        />
        <button class="btn btn-sm btn-outline" @click="aiOpen = !aiOpen">AI Analysis</button>
      </div>
    </div>

    <WaveformPlayer :audio-url="audioUrl()" @seek="currentTime = $event" />

    <div class="transcript-body">
      <SegmentTable
        :segments="store.segments"
        :speakers="store.speakers"
        :current-time="currentTime"
        @seek="currentTime = $event"
      />
    </div>

    <AiAnalysisPanel
      :recording-id="recordingId"
      :open="aiOpen"
      @close="aiOpen = false"
    />
  </div>
</template>
