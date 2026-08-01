<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

VoiceSettingsPanel.vue - Voice profile selection and management (#1054)
-->

<template>
  <div class="voice-settings">
    <!-- Active voice toolset bundle (GH#7422) -->
    <div class="voice-bundle-section">
      <VoiceBundleInfo />
    </div>

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
        <span class="voice-name">{{ $t('voice.default') }}</span>
        <span class="voice-badge builtin">{{ $t('voice.builtIn') }}</span>
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
          {{ voice.builtin ? $t('voice.builtIn') : $t('voice.custom') }}
        </span>
        <button
          v-if="!voice.builtin"
          class="delete-btn"
          :title="$t('voice.deleteVoice')"
          @click.prevent="handleDelete(voice.id, voice.name)"
        >
          <Icon name="trash" />
        </button>
      </label>
    </div>

    <div v-if="loading" class="loading-indicator">
      <Icon name="spinner" class="animate-spin" /> {{ $t('voice.loadingVoices') }}
    </div>

    <div v-if="personalityVoiceId || hasLanguageVoices" class="personality-voice-hint">
      <Icon name="user-circle" />
      <div class="personality-voice-details">
        <div v-if="personalityVoiceId">
          {{ $t('voice.personalityOverride') }}
          <strong>{{ voices.find(v => v.id === personalityVoiceId)?.name ?? personalityVoiceId }}</strong>
        </div>
        <div v-if="hasLanguageVoices">
          {{ $t('voice.languageVoicesActive', { count: Object.keys(personalityVoiceIds).length }) }}
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- Add Voice -->
    <div class="add-voice-section">
      <button class="add-voice-btn" @click="showAddDialog = true">
        <Icon name="plus" /> {{ $t('voice.addVoiceProfile') }}
      </button>
    </div>

    <!-- Add Voice Dialog -->
    <div v-if="showAddDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog">
        <h3>{{ $t('voice.addVoiceProfile') }}</h3>
        <div class="form-group">
          <label>{{ $t('common.name') }}</label>
          <input
            v-model="newVoiceName"
            type="text"
            :placeholder="$t('voice.voiceName')"
            class="form-input"
          />
        </div>
        <div class="form-group">
          <label>{{ $t('voice.audioSample') }}</label>
          <div class="audio-options">
            <button class="option-btn" @click="triggerFileUpload">
              <Icon name="upload" /> {{ $t('voice.uploadFile') }}
            </button>
            <button
              class="option-btn"
              :class="{ recording: isRecording }"
              @click="toggleRecording"
            >
              <Icon :name="isRecording ? 'stop' : 'microphone'" />
              {{ isRecording ? $t('voice.stop') : $t('voice.record') }}
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
            <Icon name="microphone" /> {{ audioFileName }}
          </div>
        </div>
        <div class="dialog-actions">
          <button class="cancel-btn" @click="closeDialog">{{ $t('common.cancel') }}</button>
          <button
            class="submit-btn"
            :disabled="!newVoiceName || !audioFile || creating"
            @click="handleCreate"
          >
            {{ creating ? $t('voice.creating') : $t('common.create') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import VoiceBundleInfo from '@/views/voice/VoiceBundleInfo.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useVoiceProfiles } from '@/composables/useVoiceProfiles'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('VoiceSettingsPanel')
const { t } = useI18n()
const { confirm } = useConfirmDialog()

const {
  voices,
  selectedVoiceId,
  personalityVoiceId,
  personalityVoiceIds,
  loading,
  error,
  fetchVoices,
  selectVoice,
  createVoice,
  deleteVoice,
  fetchPersonalityVoice,
} = useVoiceProfiles()

const hasLanguageVoices = computed(() =>
  Object.keys(personalityVoiceIds.value).length > 0
)

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
  fetchPersonalityVoice()
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
  const ok = await confirm({
    title: t('voice.confirmDeleteVoiceTitle'),
    message: t('voice.confirmDeleteVoice', { name }),
  })
  if (!ok) return
  await deleteVoice(voiceId)
}
</script>

<style scoped>
.voice-settings {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.voice-bundle-section {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.voice-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.voice-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-150);
  border: 1px solid transparent;
}

.voice-item:hover {
  background: var(--bg-tertiary);
}

.voice-item.active {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.voice-name {
  flex: 1;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.voice-badge {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.voice-badge.builtin {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.voice-badge.custom {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.delete-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: var(--spacing-1);
  border-radius: var(--radius-sm);
}

.delete-btn:hover {
  color: var(--color-error);
  background: rgba(239, 68, 68, 0.1);
}

.loading-indicator {
  color: var(--text-secondary);
  padding: var(--spacing-md);
}

.error-msg {
  color: var(--color-error);
  font-size: var(--text-sm);
  padding: var(--spacing-sm);
}

.add-voice-section {
  padding-top: var(--spacing-sm);
}

.add-voice-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-150);
}

.add-voice-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl);
  width: 400px;
  max-width: 90vw;
}

.dialog h3 {
  margin: 0 0 var(--spacing-lg);
  color: var(--text-primary);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xs);
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  box-sizing: border-box;
}

.audio-options {
  display: flex;
  gap: var(--spacing-sm);
}

.option-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
}

.option-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.option-btn.recording {
  border-color: var(--color-error);
  color: var(--color-error);
}

.audio-preview {
  margin-top: var(--spacing-xs);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
}

.cancel-btn,
.submit-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  border: none;
}

.cancel-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.submit-btn {
  background: var(--color-primary);
  color: white;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.personality-voice-hint {
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.personality-voice-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.personality-voice-hint strong {
  color: var(--color-primary);
}
</style>
