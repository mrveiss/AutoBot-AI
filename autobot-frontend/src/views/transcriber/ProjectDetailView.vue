<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import UploadModal from '@/components/transcriber/UploadModal.vue'
import ProcessingProgress from '@/components/transcriber/ProcessingProgress.vue'
import {
  useTranscriberApi,
  type Project,
  type Recording,
} from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TranscriberProjectDetailView')

const route = useRoute()
const router = useRouter()
const api = useTranscriberApi()
const store = useTranscriberStore()

const projectId = computed(() => Number(route.params.projectId))

const project = ref<Project | null>(null)
const recordings = ref<Recording[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const uploadOpen = ref(false)

async function loadRecordings() {
  const list = await api.listRecordings(projectId.value)
  recordings.value = list
  store.setRecordings(list)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    project.value = await api.getProject(projectId.value)
    store.setActiveProject(project.value)
    await loadRecordings()
  } catch (err) {
    logger.error('Failed to load project', err)
    error.value = 'Failed to load this project.'
  } finally {
    loading.value = false
  }
}

function onUploaded(recording: Recording) {
  // Surface the new recording immediately; ProcessingProgress drives it to done.
  recordings.value = [recording, ...recordings.value]
  store.setRecordings(recordings.value)
}

// A recording finished (or failed) processing — refresh its row from the server.
async function onProcessingSettled(recordingId: number) {
  try {
    const fresh = await api.getRecording(recordingId)
    const idx = recordings.value.findIndex((r) => r.id === recordingId)
    if (idx !== -1) recordings.value[idx] = fresh
  } catch (err) {
    logger.warn('Failed to refresh recording after processing', err)
  }
}

async function deleteRecording(recording: Recording) {
  if (!window.confirm(`Delete recording "${recording.filename}"?`)) return
  try {
    await api.deleteRecording(recording.id)
    recordings.value = recordings.value.filter((r) => r.id !== recording.id)
    store.setRecordings(recordings.value)
  } catch (err) {
    logger.error('Failed to delete recording', err)
    error.value = 'Failed to delete recording.'
  }
}

function openTranscript(recording: Recording) {
  router.push({
    name: 'transcriber-transcript',
    params: { projectId: String(projectId.value), recordingId: String(recording.id) },
  })
}

function backToProjects() {
  router.push({ name: 'transcriber-projects' })
}

function isInProgress(r: Recording): boolean {
  return r.status === 'pending' || r.status === 'processing'
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) return '—'
  const total = Math.round(seconds)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

// Re-load when navigating directly between sibling project routes.
watch(projectId, (next, prev) => {
  if (next !== prev) load()
})

onMounted(load)
</script>

<template>
  <div class="project-detail-view">
    <header class="project-detail-header">
      <div class="project-detail-heading">
        <button type="button" class="btn btn-sm" @click="backToProjects">← Projects</button>
        <h1 class="project-detail-title">{{ project?.name ?? 'Project' }}</h1>
      </div>
      <button type="button" class="btn btn-primary" :disabled="!project" @click="uploadOpen = true">
        Upload recording
      </button>
    </header>

    <p v-if="project?.description" class="project-detail-desc">{{ project.description }}</p>

    <div v-if="loading" class="recordings-state">Loading recordings…</div>

    <div v-else-if="error" class="recordings-state recordings-error">
      <p>{{ error }}</p>
      <button type="button" class="btn btn-sm" @click="load">Retry</button>
    </div>

    <div v-else-if="!recordings.length" class="recordings-state">
      <p>No recordings yet.</p>
      <p>Upload an audio or video file to start transcribing.</p>
    </div>

    <ul v-else class="recordings-list">
      <li v-for="recording in recordings" :key="recording.id" class="recording-card">
        <div class="recording-main">
          <span class="recording-filename">{{ recording.filename }}</span>
          <span class="recording-meta">
            <span class="recording-status" :class="`recording-status-${recording.status}`">
              {{ recording.status }}
            </span>
            <span>{{ formatDuration(recording.duration) }}</span>
            <span>{{ formatDate(recording.uploaded_at) }}</span>
          </span>

          <ProcessingProgress
            v-if="isInProgress(recording)"
            :recording-id="recording.id"
            class="recording-progress"
            @complete="onProcessingSettled(recording.id)"
            @error="onProcessingSettled(recording.id)"
          />

          <span
            v-else-if="recording.status === 'error'"
            class="recording-failure"
          >
            {{ recording.failure_reason || 'Transcription failed.' }}
          </span>
        </div>

        <div class="recording-actions">
          <button
            type="button"
            class="btn btn-sm"
            :disabled="recording.status !== 'complete'"
            @click="openTranscript(recording)"
          >
            View transcript
          </button>
          <button
            type="button"
            class="btn-icon"
            :aria-label="`Delete recording ${recording.filename}`"
            @click="deleteRecording(recording)"
          >
            ✕
          </button>
        </div>
      </li>
    </ul>

    <UploadModal
      v-if="project"
      :project-id="projectId"
      :open="uploadOpen"
      @close="uploadOpen = false"
      @uploaded="onUploaded"
    />
  </div>
</template>

<style scoped>
.project-detail-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.project-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.project-detail-heading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.project-detail-title {
  margin: 0;
  font-size: var(--text-2xl, 1.5rem);
  font-weight: var(--font-medium, 600);
  color: var(--text-primary);
}

.project-detail-desc {
  margin: 0;
  color: var(--text-secondary, #6b7280);
}

.recordings-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--text-secondary, #6b7280);
  text-align: center;
}

.recordings-error {
  color: var(--color-danger-600, #dc2626);
}

.recordings-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.recording-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--bg-primary, #fff);
}

.recording-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  flex: 1;
}

.recording-filename {
  font-weight: var(--font-medium, 600);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recording-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-tertiary, #9ca3af);
}

.recording-status {
  text-transform: capitalize;
  font-weight: var(--font-medium, 600);
}

.recording-status-complete {
  color: var(--color-success-600, #16a34a);
}

.recording-status-processing,
.recording-status-pending {
  color: var(--color-warning-600, #d97706);
}

.recording-status-error {
  color: var(--color-danger-600, #dc2626);
}

.recording-progress {
  margin-top: 0.25rem;
}

.recording-failure {
  font-size: var(--text-sm, 0.875rem);
  color: var(--color-danger-600, #dc2626);
}

.recording-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}
</style>
