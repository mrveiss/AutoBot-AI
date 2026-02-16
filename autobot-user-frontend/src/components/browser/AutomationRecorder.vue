<template>
  <div class="automation-recorder">
    <!-- Header -->
    <div class="recorder-header">
      <div class="flex items-center space-x-3">
        <i class="fas fa-record-vinyl text-red-600 text-xl"></i>
        <div>
          <h3 class="text-lg font-semibold text-gray-800">Automation Recorder</h3>
          <p class="text-sm text-gray-500">Record, playback, and export browser actions</p>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <BaseButton
          v-if="!isRecording && !currentRecording"
          variant="primary"
          size="sm"
          @click="showNewRecordingModal = true"
        >
          <i class="fas fa-circle mr-1"></i>
          Start Recording
        </BaseButton>

        <BaseButton
          v-if="isRecording"
          variant="danger"
          size="sm"
          @click="stopRecording"
        >
          <i class="fas fa-stop mr-1"></i>
          Stop Recording
        </BaseButton>

        <BaseButton
          v-if="currentRecording && !isRecording"
          variant="outline"
          size="sm"
          @click="discardRecording"
        >
          <i class="fas fa-times mr-1"></i>
          Discard
        </BaseButton>

        <BaseButton
          v-if="currentRecording && !isRecording"
          variant="success"
          size="sm"
          @click="saveRecording"
        >
          <i class="fas fa-save mr-1"></i>
          Save Recording
        </BaseButton>
      </div>
    </div>

    <!-- Recording Status -->
    <div v-if="isRecording" class="recording-status">
      <div class="status-indicator recording-pulse">
        <i class="fas fa-circle text-red-600"></i>
      </div>
      <div class="flex-1">
        <h4 class="text-lg font-semibold text-gray-800">{{ currentRecording?.name }}</h4>
        <p class="text-sm text-gray-500">Recording in progress...</p>
      </div>
      <div class="recording-timer">
        <i class="fas fa-clock mr-2"></i>
        {{ formatDuration(recordingDuration) }}
      </div>
      <div class="action-count">
        <i class="fas fa-list mr-2"></i>
        {{ currentRecording?.actions.length || 0 }} actions
      </div>
    </div>

    <!-- Current Recording Editor -->
    <div v-if="currentRecording && !isRecording" class="recording-editor">
      <div class="editor-header">
        <h4 class="text-lg font-semibold">Edit Recording</h4>
        <div class="flex items-center space-x-2">
          <BaseButton
            variant="outline"
            size="sm"
            @click="playbackRecording(currentRecording)"
            :disabled="currentRecording.actions.length === 0"
          >
            <i class="fas fa-play mr-1"></i>
            Test Playback
          </BaseButton>
        </div>
      </div>

      <div class="actions-list">
        <div
          v-for="(action, index) in currentRecording.actions"
          :key="action.id"
          class="action-item"
        >
          <div class="action-number">{{ index + 1 }}</div>
          <div class="action-icon" :class="getActionIconClass(action.type)">
            <i :class="getActionIcon(action.type)"></i>
          </div>
          <div class="action-details flex-1">
            <h5 class="action-description">{{ action.description }}</h5>
            <div class="action-meta">
              <span v-if="action.url">URL: {{ action.url }}</span>
              <span v-if="action.selector">Selector: {{ action.selector }}</span>
              <span v-if="action.value">Value: "{{ action.value }}"</span>
            </div>
          </div>
          <button
            @click="removeAction(index)"
            class="remove-action-btn"
            title="Remove Action"
          >
            <i class="fas fa-trash"></i>
          </button>
        </div>

        <div v-if="currentRecording.actions.length === 0" class="empty-actions">
          <i class="fas fa-info-circle text-gray-400 text-2xl mb-2"></i>
          <p class="text-gray-500">No actions recorded yet</p>
        </div>
      </div>
    </div>

    <!-- Saved Recordings List -->
    <div class="recordings-list">
      <div class="list-header">
        <h4 class="text-lg font-semibold">Saved Recordings</h4>
        <span class="text-sm text-gray-500">{{ recordings.length }} recordings</span>
      </div>

      <div v-if="recordings.length === 0" class="empty-state">
        <EmptyState
          icon="fas fa-record-vinyl"
          title="No Recordings Yet"
          message="Start recording browser actions to automate repetitive tasks"
        >
          <template #actions>
            <BaseButton variant="primary" @click="showNewRecordingModal = true">
              <i class="fas fa-circle mr-2"></i>
              Start Recording
            </BaseButton>
          </template>
        </EmptyState>
      </div>

      <div v-else class="recordings-grid">
        <div
          v-for="recording in recordings"
          :key="recording.id"
          class="recording-card"
        >
          <div class="recording-header">
            <div class="flex-1">
              <h4 class="recording-name">{{ recording.name }}</h4>
              <p v-if="recording.description" class="recording-description">
                {{ recording.description }}
              </p>
            </div>
            <div class="recording-badge">
              {{ recording.actions.length }} actions
            </div>
          </div>

          <div class="recording-meta">
            <div class="meta-item">
              <i class="fas fa-clock"></i>
              <span>{{ formatDuration(recording.duration) }}</span>
            </div>
            <div class="meta-item">
              <i class="fas fa-calendar"></i>
              <span>{{ formatDate(recording.createdAt) }}</span>
            </div>
          </div>

          <div class="recording-actions">
            <BaseButton
              variant="primary"
              size="sm"
              @click="playbackRecording(recording)"
            >
              <i class="fas fa-play mr-1"></i>
              Play
            </BaseButton>
            <BaseButton
              variant="outline"
              size="sm"
              @click="exportRecording(recording)"
            >
              <i class="fas fa-download mr-1"></i>
              Export
            </BaseButton>
            <button
              @click="deleteRecording(recording.id)"
              class="delete-btn"
              title="Delete Recording"
            >
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- New Recording Modal -->
    <div v-if="showNewRecordingModal" class="modal-overlay" @click.self="showNewRecordingModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="text-lg font-semibold">New Recording</h3>
          <button @click="showNewRecordingModal = false" class="text-gray-400 hover:text-gray-600">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Recording Name</label>
            <input
              v-model="newRecordingName"
              type="text"
              class="form-input"
              placeholder="e.g., Login Flow, Search Products"
              @keyup.enter="startNewRecording"
            />
          </div>

          <div class="form-group">
            <label class="form-label">Description (Optional)</label>
            <textarea
              v-model="newRecordingDescription"
              class="form-textarea"
              rows="3"
              placeholder="Describe what this recording automates..."
            ></textarea>
          </div>
        </div>

        <div class="modal-footer">
          <BaseButton variant="outline" @click="showNewRecordingModal = false">
            Cancel
          </BaseButton>
          <BaseButton
            variant="primary"
            @click="startNewRecording"
            :disabled="!newRecordingName.trim()"
          >
            <i class="fas fa-circle mr-1"></i>
            Start Recording
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, onUnmounted } from 'vue'
import { useBrowserAutomation } from '@/composables/useBrowserAutomation'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { AutomationRecording } from '@/types/browser'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AutomationRecorder')

export default {
  name: 'AutomationRecorder',
  components: {
    BaseButton,
    EmptyState
  },
  setup() {
    const {
      recordings,
      currentRecording,
      isRecording,
      startRecording,
      stopRecording: stopRecordingHandler,
      playbackRecording: playbackRecordingHandler,
      deleteRecording: deleteRecordingHandler
    } = useBrowserAutomation()

    const showNewRecordingModal = ref(false)
    const newRecordingName = ref('')
    const newRecordingDescription = ref('')
    const recordingDuration = ref(0)
    let durationInterval: number | null = null

    // Methods
    const startNewRecording = () => {
      if (!newRecordingName.value.trim()) return

      startRecording(newRecordingName.value, newRecordingDescription.value || undefined)

      // Start duration timer
      recordingDuration.value = 0
      durationInterval = window.setInterval(() => {
        recordingDuration.value++
      }, 1000)

      // Reset form
      newRecordingName.value = ''
      newRecordingDescription.value = ''
      showNewRecordingModal.value = false

      logger.info('Started new recording')
    }

    const stopRecording = () => {
      stopRecordingHandler()

      // Stop duration timer
      if (durationInterval) {
        clearInterval(durationInterval)
        durationInterval = null
      }

      logger.info('Stopped recording')
    }

    const discardRecording = () => {
      if (confirm('Are you sure you want to discard this recording?')) {
        currentRecording.value = null
        logger.info('Discarded recording')
      }
    }

    const saveRecording = () => {
      stopRecording()
      logger.info('Saved recording')
    }

    const removeAction = (index: number) => {
      if (currentRecording.value) {
        currentRecording.value.actions.splice(index, 1)
      }
    }

    const playbackRecording = async (recording: AutomationRecording) => {
      try {
        await playbackRecordingHandler(recording.id)
        logger.info('Started playback', { id: recording.id })
      } catch (error: unknown) {
        logger.error('Playback failed', error)
        alert(`Playback failed: ${(error as Error).message}`)
      }
    }

    const exportRecording = (recording: AutomationRecording) => {
      const exportData = {
        name: recording.name,
        description: recording.description,
        actions: recording.actions,
        version: '1.0'
      }

      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${recording.name.replace(/[^a-z0-9]/gi, '-').toLowerCase()}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      logger.info('Exported recording', { id: recording.id })
    }

    const deleteRecording = (recordingId: string) => {
      if (confirm('Are you sure you want to delete this recording?')) {
        deleteRecordingHandler(recordingId)
        logger.info('Deleted recording', { id: recordingId })
      }
    }

    const getActionIcon = (type: string): string => {
      switch (type) {
        case 'navigate': return 'fas fa-compass'
        case 'click': return 'fas fa-hand-pointer'
        case 'type': return 'fas fa-keyboard'
        case 'scroll': return 'fas fa-arrows-alt-v'
        case 'wait': return 'fas fa-clock'
        case 'screenshot': return 'fas fa-camera'
        default: return 'fas fa-cog'
      }
    }

    const getActionIconClass = (type: string): string => {
      switch (type) {
        case 'navigate': return 'bg-blue-100 text-blue-600'
        case 'click': return 'bg-green-100 text-green-600'
        case 'type': return 'bg-purple-100 text-purple-600'
        case 'scroll': return 'bg-yellow-100 text-yellow-600'
        case 'wait': return 'bg-gray-100 text-gray-600'
        case 'screenshot': return 'bg-indigo-100 text-indigo-600'
        default: return 'bg-gray-100 text-gray-600'
      }
    }

    const formatDuration = (seconds: number): string => {
      const hrs = Math.floor(seconds / 3600)
      const mins = Math.floor((seconds % 3600) / 60)
      const secs = seconds % 60

      if (hrs > 0) {
        return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
      }
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    const formatDate = (date: Date): string => {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      }).format(date)
    }

    // Cleanup on unmount
    onUnmounted(() => {
      if (durationInterval) {
        clearInterval(durationInterval)
      }
    })

    return {
      recordings,
      currentRecording,
      isRecording,
      showNewRecordingModal,
      newRecordingName,
      newRecordingDescription,
      recordingDuration,
      startNewRecording,
      stopRecording,
      discardRecording,
      saveRecording,
      removeAction,
      playbackRecording,
      exportRecording,
      deleteRecording,
      getActionIcon,
      getActionIconClass,
      formatDuration,
      formatDate
    }
  }
}
</script>

<style scoped>
.automation-recorder {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.recorder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
}

.recording-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: linear-gradient(135deg, #fee2e2 0%, #fef3c7 100%);
  border-bottom: 2px solid #ef4444;
}

.status-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: white;
  border-radius: var(--radius-full);
}

.recording-pulse {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

.recording-timer,
.action-count {
  display: flex;
  align-items: center;
  padding: var(--spacing-2) var(--spacing-3);
  background: white;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 14px;
}

.recording-editor {
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-light);
}

.actions-list {
  padding: var(--spacing-4);
  max-height: 300px;
  overflow-y: auto;
}

.action-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
}

.action-number {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-weight: 700;
  font-size: 14px;
  color: var(--text-secondary);
}

.action-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 18px;
}

.action-details {
  flex: 1;
}

.action-description {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.action-meta {
  display: flex;
  gap: var(--spacing-3);
  font-size: 12px;
  color: var(--text-secondary);
}

.remove-action-btn {
  padding: var(--spacing-2);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color var(--duration-200);
}

.remove-action-btn:hover {
  color: #ef4444;
}

.empty-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
}

.recordings-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.recordings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-4);
}

.recording-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  transition: all var(--duration-200);
}

.recording-card:hover {
  box-shadow: var(--shadow-md);
}

.recording-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-3);
}

.recording-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.recording-description {
  font-size: 14px;
  color: var(--text-secondary);
}

.recording-badge {
  padding: 4px 12px;
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.recording-meta {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--border-light);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 12px;
  color: var(--text-secondary);
}

.recording-actions {
  display: flex;
  gap: var(--spacing-2);
}

.delete-btn {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-200);
}

.delete-btn:hover {
  color: #ef4444;
  border-color: #ef4444;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-4);
}

.modal-content {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 500px;
  box-shadow: var(--shadow-2xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-light);
}

.modal-body {
  padding: var(--spacing-5);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-light);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}
</style>
