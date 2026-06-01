<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import type { Recording } from '@/composables/transcriber/useTranscriberApi'
import UploadModal from '@/components/transcriber/UploadModal.vue'
import ProcessingProgress from '@/components/transcriber/ProcessingProgress.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectDetailView')
const route = useRoute()
const router = useRouter()
const api = useTranscriberApi()
const store = useTranscriberStore()

const projectId = Number(route.params.projectId)
const showUpload = ref(false)
const processingIds = ref<Set<number>>(new Set())

onMounted(async () => {
  try {
    const [project, recordings] = await Promise.all([
      api.getProject(projectId),
      api.listRecordings(projectId),
    ])
    store.setActiveProject(project)
    store.setRecordings(recordings)
    recordings.filter(r => r.status === 'processing' || r.status === 'pending')
      .forEach(r => processingIds.value.add(r.id))
  } catch (err) {
    logger.error('Failed to load project', err)
  }
})

function onUploaded(rec: Recording) {
  store.setRecordings([rec, ...store.recordings])
  processingIds.value.add(rec.id)
}

function onProcessingComplete(recId: number) {
  processingIds.value.delete(recId)
  api.getRecording(recId).then(r => store.updateRecordingStatus(r.id, r.status))
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Queued',
  processing: 'Processing',
  complete: 'Ready',
  error: 'Failed',
}
</script>

<template>
  <div class="project-detail-view">
    <div class="detail-header">
      <RouterLink :to="{ name: 'transcriber-projects' }" class="btn-link">← Projects</RouterLink>
      <h2>{{ store.activeProject?.name }}</h2>
      <button class="btn btn-primary" @click="showUpload = true">Upload Recording</button>
    </div>

    <UploadModal
      :project-id="projectId"
      :open="showUpload"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />

    <div class="recordings-list">
      <div v-for="rec in store.recordings" :key="rec.id" class="recording-row card">
        <div class="recording-info">
          <span class="recording-name">{{ rec.filename }}</span>
          <span class="recording-status" :class="`status-${rec.status}`">
            {{ STATUS_LABEL[rec.status] }}
          </span>
          <span v-if="rec.language_detected" class="recording-lang">{{ rec.language_detected }}</span>
          <span v-if="rec.speaker_count" class="recording-speakers">{{ rec.speaker_count }} speakers</span>
        </div>
        <ProcessingProgress
          v-if="processingIds.has(rec.id)"
          :recording-id="rec.id"
          @complete="onProcessingComplete(rec.id)"
          @error="onProcessingComplete(rec.id)"
        />
        <RouterLink
          v-if="rec.status === 'complete'"
          :to="{ name: 'transcriber-transcript', params: { projectId, recordingId: rec.id } }"
          class="btn btn-sm"
        >Open Transcript</RouterLink>
      </div>
    </div>
  </div>
</template>
