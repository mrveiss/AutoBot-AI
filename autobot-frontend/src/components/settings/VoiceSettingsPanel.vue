<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

VoiceSettingsPanel.vue - Voice profile selection and management (#1054)
-->

<template>
  <div class="voice-settings">
    <div class="voice-list" v-if="!loading">
      <!-- Default (no profile) -->
      <label
        class="voice-item"
        :class="{ active: selectedVoiceId === '' }"
      >
        <input
          type="radio"
          name="voice"
          value=""
          :checked="selectedVoiceId === ''"
          @change="selectVoice('')"
        />
        <span class="voice-name">Default</span>
        <span class="voice-badge builtin">built-in</span>
      </label>

      <!-- Voice profiles -->
      <label
        v-for="voice in voices"
        :key="voice.id"
        class="voice-item"
        :class="{ active: selectedVoiceId === voice.id }"
      >
        <input
          type="radio"
          name="voice"
          :value="voice.id"
          :checked="selectedVoiceId === voice.id"
          @change="selectVoice(voice.id)"
        />
        <span class="voice-name">{{ voice.name }}</span>
        <span
          class="voice-badge"
          :class="voice.builtin ? 'builtin' : 'custom'"
        >
          {{ voice.builtin ? 'built-in' : 'custom' }}
        </span>
        <button
          v-if="!voice.builtin"
          class="delete-btn"
          title="Delete voice"
          @click.prevent="handleDelete(voice.id, voice.name)"
        >
          <i class="fas fa-trash"></i>
        </button>
      </label>
    </div>

    <div v-if="loading" class="loading-indicator">
      <i class="fas fa-spinner fa-spin"></i> Loading voices...
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- Add Voice -->
    <div class="add-voice-section">
      <button class="add-voice-btn" @click="showAddDialog = true">
        <i class="fas fa-plus"></i> Add Voice Profile
      </button>
    </div>

    <!-- Add Voice Dialog -->
    <div v-if="showAddDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog">
        <h3>Add Voice Profile</h3>
        <div class="form-group">
          <label>Name</label>
          <input
            v-model="newVoiceName"
            type="text"
            placeholder="Voice name"
            class="form-input"
          />
        </div>
        <div class="form-group">
          <label>Audio Sample</label>
          <div class="audio-options">
            <button class="option-btn" @click="triggerFileUpload">
              <i class="fas fa-upload"></i> Upload File
            </button>
            <button
              class="option-btn"
              :class="{ recording: isRecording }"
              @click="toggleRecording"
            >
              <i :class="isRecording ? 'fas fa-stop' : 'fas fa-microphone'"></i>
              {{ isRecording ? 'Stop' : 'Record' }}
            </button>
          </div>
          <input
            ref="fileInput"
            type="file"
            accept="audio/*"
            style="display: none"
            @change="handleFileSelect"
          />
          <div v-if="audioFile" class="audio-preview">
            <i class="fas fa-file-audio"></i> {{ audioFileName }}
          </div>
        </div>
        <div class="dialog-actions">
          <button class="cancel-btn" @click="closeDialog">Cancel</button>
          <button
            class="submit-btn"
            :disabled="!newVoiceName || !audioFile || creating"
            @click="handleCreate"
          >
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useVoiceProfiles } from '@/composables/useVoiceProfiles'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('VoiceSettingsPanel')

const {
  voices,
  selectedVoiceId,
  loading,
  error,
  fetchVoices,
  selectVoice,
  createVoice,
  deleteVoice,
} = useVoiceProfiles()

const showAddDialog = ref(false)
const newVoiceName = ref('')
const audioFile = ref<Blob | null>(null)
const audioFileName = ref('')
const creating = ref(false)
const isRecording = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

let mediaRecorder: MediaRecorder | null = null
let recordedChunks: Blob[] = []

onMounted(() => {
  fetchVoices()
})

function triggerFileUpload() {
  fileInput.value?.click()
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    audioFile.value = input.files[0]
    audioFileName.value = input.files[0].name
  }
}

async function toggleRecording() {
  if (isRecording.value) {
    mediaRecorder?.stop()
    isRecording.value = false
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    recordedChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordedChunks.push(e.data)
    }
    mediaRecorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: 'audio/webm' })
      audioFile.value = blob
      audioFileName.value = 'recording.webm'
      stream.getTracks().forEach((t) => t.stop())
    }
    mediaRecorder.start()
    isRecording.value = true
  } catch (e) {
    logger.error('Mic access error:', e)
  }
}

async function handleCreate() {
  if (!newVoiceName.value || !audioFile.value) return
  creating.value = true
  const ok = await createVoice(
    newVoiceName.value,
    audioFile.value,
    audioFileName.value,
  )
  creating.value = false
  if (ok) closeDialog()
}

function closeDialog() {
  showAddDialog.value = false
  newVoiceName.value = ''
  audioFile.value = null
  audioFileName.value = ''
}

async function handleDelete(voiceId: string, name: string) {
  if (!confirm(`Delete voice "${name}"?`)) return
  await deleteVoice(voiceId)
}
</script>

<style scoped>
.voice-settings {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md, 12px);
}

.voice-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 6px);
}

.voice-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: background 0.15s;
  border: 1px solid transparent;
}

.voice-item:hover {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
}

.voice-item.active {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
  border-color: var(--color-primary, #60a5fa);
}

.voice-name {
  flex: 1;
  color: var(--text-primary, #e2e8f0);
  font-size: var(--text-sm, 14px);
}

.voice-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
  font-weight: 500;
}

.voice-badge.builtin {
  background: var(--color-primary-bg, rgba(96, 165, 250, 0.15));
  color: var(--color-primary, #60a5fa);
}

.voice-badge.custom {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}

.delete-btn {
  background: none;
  border: none;
  color: var(--text-tertiary, #64748b);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm, 4px);
}

.delete-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.loading-indicator {
  color: var(--text-secondary, #94a3b8);
  padding: var(--spacing-md, 12px);
}

.error-msg {
  color: #ef4444;
  font-size: var(--text-sm, 14px);
  padding: var(--spacing-sm, 8px);
}

.add-voice-section {
  padding-top: var(--spacing-sm, 8px);
}

.add-voice-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 6px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
  color: var(--text-secondary, #94a3b8);
  border: 1px dashed var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  font-size: var(--text-sm, 14px);
  transition: all 0.15s;
}

.add-voice-btn:hover {
  color: var(--color-primary, #60a5fa);
  border-color: var(--color-primary, #60a5fa);
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-lg, 8px);
  padding: var(--spacing-xl, 24px);
  width: 400px;
  max-width: 90vw;
}

.dialog h3 {
  margin: 0 0 var(--spacing-lg, 16px);
  color: var(--text-primary, #e2e8f0);
}

.form-group {
  margin-bottom: var(--spacing-md, 12px);
}

.form-group label {
  display: block;
  font-size: var(--text-sm, 14px);
  color: var(--text-secondary, #94a3b8);
  margin-bottom: var(--spacing-xs, 6px);
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm, 8px);
  background: var(--bg-primary, #0f172a);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-md, 6px);
  color: var(--text-primary, #e2e8f0);
  font-size: var(--text-sm, 14px);
  box-sizing: border-box;
}

.audio-options {
  display: flex;
  gap: var(--spacing-sm, 8px);
}

.option-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs, 6px);
  padding: var(--spacing-sm, 8px);
  background: var(--bg-primary, #0f172a);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-md, 6px);
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  font-size: var(--text-sm, 14px);
}

.option-btn:hover {
  border-color: var(--color-primary, #60a5fa);
  color: var(--color-primary, #60a5fa);
}

.option-btn.recording {
  border-color: #ef4444;
  color: #ef4444;
}

.audio-preview {
  margin-top: var(--spacing-xs, 6px);
  font-size: 12px;
  color: var(--text-tertiary, #64748b);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm, 8px);
  margin-top: var(--spacing-lg, 16px);
}

.cancel-btn,
.submit-btn {
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  border-radius: var(--radius-md, 6px);
  font-size: var(--text-sm, 14px);
  cursor: pointer;
  border: none;
}

.cancel-btn {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
  color: var(--text-secondary, #94a3b8);
}

.submit-btn {
  background: var(--color-primary, #60a5fa);
  color: white;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
