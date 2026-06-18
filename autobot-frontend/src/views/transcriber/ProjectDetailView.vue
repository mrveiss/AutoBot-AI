<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  useTranscriberApi,
  type Project,
  type Recording,
  type RecordingStatus,
} from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectDetailView')

const route = useRoute()
const router = useRouter()
const api = useTranscriberApi()

const ACCEPTED_TYPES = '.wav,.mp3,.mp4,.m4a,.ogg,.flac,.webm'

const projectId = computed(() => Number(route.params.projectId))

const project = ref<Project | null>(null)
const recordings = ref<Recording[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadError = ref<string | null>(null)

const STATUS_LABELS: Record<RecordingStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  complete: 'Complete',
  error: 'Failed',
}

async function load() {
  loading.value = true
  error.value = null
  try {
    project.value = await api.getProject(projectId.value)
    recordings.value = await api.listRecordings(projectId.value)
  } catch (err) {
    logger.error('Failed to load project', err)
    error.value = 'Failed to load this project.'
  } finally {
    loading.value = false
  }
}

async function refreshRecordings() {
  try {
    recordings.value = await api.listRecordings(projectId.value)
  } catch (err) {
    logger.error('Failed to refresh recordings', err)
    error.value = 'Failed to refresh recordings.'
  }
}

function pickFile() {
  fileInput.value?.click()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  uploadError.value = null
  try {
    const recording = await api.uploadRecording(projectId.value, file)
    recordings.value = [recording, ...recordings.value]
  } catch (err) {
    logger.error('Failed to upload recording', err)
    uploadError.value = 'Failed to upload recording.'
  } finally {
    uploading.value = false
    // Reset so re-selecting the same file fires the change event again.
    input.value = ''
  }
}

function isComplete(recording: Recording): boolean {
  return recording.status === 'complete'
}

function isInProgress(recording: Recording): boolean {
  return recording.status === 'pending' || recording.status === 'processing'
}

function openRecording(recording: Recording) {
  if (!isComplete(recording)) return
  router.push({
    name: 'transcriber-transcript',
    params: { projectId: projectId.value, recordingId: recording.id },
  })
}

async function removeRecording(recording: Recording) {
  if (!window.confirm(`Delete recording "${recording.filename}"? This cannot be undone.`)) return
  try {
    await api.deleteRecording(recording.id)
    recordings.value = recordings.value.filter((r) => r.id !== recording.id)
  } catch (err) {
    logger.error('Failed to delete recording', err)
    error.value = 'Failed to delete recording.'
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) return '—'
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(load)
</script>

<template>
  <div class="project-detail-view">
    <router-link class="back-link" :to="{ name: 'transcriber-projects' }">
      ← Back to projects
    </router-link>

    <div v-if="loading" class="detail-state">Loading project…</div>

    <div v-else-if="error" class="detail-state detail-error">{{ error }}</div>

    <template v-else>
      <header class="detail-header">
        <h1 class="detail-title">{{ project?.name }}</h1>
        <p v-if="project?.description" class="detail-description">{{ project.description }}</p>
      </header>

      <section class="upload-section">
        <input
          ref="fileInput"
          class="upload-input"
          type="file"
          :accept="ACCEPTED_TYPES"
          @change="onFileSelected"
        />
        <button class="btn-primary" type="button" :disabled="uploading" @click="pickFile">
          {{ uploading ? 'Uploading…' : 'Upload recording' }}
        </button>
        <button class="btn-secondary" type="button" @click="refreshRecordings">Refresh</button>
        <p v-if="uploadError" class="detail-error">{{ uploadError }}</p>
      </section>

      <div v-if="!recordings.length" class="detail-state">
        No recordings yet — upload an audio file to begin transcription.
      </div>

      <ul v-else class="recordings-list">
        <li v-for="recording in recordings" :key="recording.id" class="recording-card">
          <component
            :is="isComplete(recording) ? 'button' : 'div'"
            class="recording-main"
            :class="{ 'recording-clickable': isComplete(recording) }"
            :type="isComplete(recording) ? 'button' : undefined"
            @click="openRecording(recording)"
          >
            <span class="recording-filename">{{ recording.filename }}</span>
            <span class="recording-meta">
              <span class="status-badge" :class="`status-${recording.status}`">
                {{ STATUS_LABELS[recording.status] }}
              </span>
              <span>{{ formatDuration(recording.duration) }}</span>
              <span v-if="recording.speaker_count">{{ recording.speaker_count }} speakers</span>
              <span v-if="recording.language_detected">{{ recording.language_detected }}</span>
            </span>
            <span v-if="isInProgress(recording)" class="recording-note">
              Transcription in progress…
            </span>
            <span v-else-if="recording.status === 'error'" class="recording-note detail-error">
              {{ recording.failure_reason || 'Transcription failed.' }}
            </span>
          </component>
          <button
            class="btn-danger"
            type="button"
            :aria-label="`Delete ${recording.filename}`"
            @click="removeRecording(recording)"
          >
            Delete
          </button>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.project-detail-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.back-link {
  font-size: 0.875rem;
  color: var(--color-primary-600, #2563eb);
  text-decoration: none;
}

.detail-header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text, #111827);
}

.detail-description {
  color: var(--color-text-secondary, #6b7280);
}

.upload-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.upload-input {
  display: none;
}

.recordings-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.recording-card {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--color-bg, #fff);
}

.recording-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  text-align: left;
  background: transparent;
  border: none;
  color: inherit;
  font: inherit;
}

.recording-clickable {
  cursor: pointer;
}

.recording-clickable:hover {
  background: var(--color-surface, #f3f4f6);
}

.recording-filename {
  font-weight: 600;
  color: var(--color-text, #111827);
}

.recording-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #6b7280);
}

.recording-note {
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #6b7280);
}

.status-badge {
  padding: 0.0625rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--color-surface, #f3f4f6);
  color: var(--color-text-secondary, #6b7280);
}

.status-complete {
  background: var(--color-success-100, #dcfce7);
  color: var(--color-success-700, #15803d);
}

.status-processing,
.status-pending {
  background: var(--color-primary-100, #dbeafe);
  color: var(--color-primary-700, #1d4ed8);
}

.status-error {
  background: var(--color-danger-100, #fee2e2);
  color: var(--color-danger-700, #b91c1c);
}

.detail-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--color-text-secondary, #6b7280);
  text-align: center;
}

.detail-error {
  color: var(--color-danger-600, #dc2626);
}

.btn-primary,
.btn-secondary,
.btn-danger {
  padding: 0.5rem 0.875rem;
  border-radius: 0.375rem;
  border: 1px solid transparent;
  font-size: 0.875rem;
  cursor: pointer;
}

.btn-primary {
  background: var(--color-primary-600, #2563eb);
  color: #fff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  border-color: var(--color-border, #d1d5db);
  color: var(--color-text, #111827);
}

.btn-danger {
  margin: 0.75rem;
  align-self: center;
  background: transparent;
  border-color: var(--color-danger-600, #dc2626);
  color: var(--color-danger-600, #dc2626);
}
</style>
