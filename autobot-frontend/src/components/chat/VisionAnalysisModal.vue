// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * VisionAnalysisModal — Modal dialog for image analysis from the chat input.
 *
 * Provides upload, intent selection, analysis results, and "Send to Chat"
 * to insert results into the conversation. Issue #1242.
 */

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import {
  visionMultimodalApiClient,
  type ProcessingIntent,
  type MultiModalResponse,
} from '@/utils/VisionMultimodalApiClient'

const { t } = useI18n()
const logger = createLogger('VisionAnalysisModal')

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'send-to-chat', payload: {
    filename: string
    intent: ProcessingIntent
    question?: string
    result: MultiModalResponse
  }): void
}>()

// File state
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
const isDragging = ref(false)

// Options
const selectedIntent = ref<ProcessingIntent>('analysis')
const question = ref('')

// Processing state
const processing = ref(false)
const analysisResult = ref<MultiModalResponse | null>(null)
const error = ref<string | null>(null)
const showRawJson = ref(false)

const intentLabels = computed<Record<string, string>>(() => ({
  analysis: t('chat.vision.intentAnalysis'),
  visual_qa: t('chat.vision.intentVisualQA'),
  automation: t('chat.vision.intentAutomation'),
  content_generation: t('chat.vision.intentContentGeneration'),
}))

function triggerFileInput(): void {
  fileInput.value?.click()
}

function handleFileSelect(event: Event): void {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) selectFile(file)
}

function handleDrop(event: DragEvent): void {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    selectFile(file)
  } else {
    error.value = t('chat.vision.invalidImageFile')
  }
}

function selectFile(file: File): void {
  selectedFile.value = file
  analysisResult.value = null
  error.value = null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
  logger.debug('File selected:', file.name)
}

function clearFile(): void {
  selectedFile.value = null
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  analysisResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function analyzeImage(): Promise<void> {
  if (!selectedFile.value) return
  processing.value = true
  error.value = null
  try {
    const q = selectedIntent.value === 'visual_qa'
      ? question.value
      : undefined
    const response = await visionMultimodalApiClient.processImage(
      selectedFile.value,
      selectedIntent.value,
      q,
    )
    if (response.success && response.data) {
      analysisResult.value = response.data
      logger.debug('Analysis complete:', response.data)
    } else {
      error.value = response.error || t('chat.vision.analysisFailed')
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('common.unknownError')
    logger.error('Analysis error:', err)
  } finally {
    processing.value = false
  }
}

function sendToChat(): void {
  if (!analysisResult.value || !selectedFile.value) return
  emit('send-to-chat', {
    filename: selectedFile.value.name,
    intent: selectedIntent.value,
    question: selectedIntent.value === 'visual_qa'
      ? question.value
      : undefined,
    result: analysisResult.value,
  })
  emit('close')
}

function exportResults(): void {
  if (!analysisResult.value) return
  const blob = new Blob(
    [JSON.stringify(analysisResult.value, null, 2)],
    { type: 'application/json' },
  )
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

onUnmounted(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="vision-modal-overlay" @click.self="emit('close')">
    <div class="vision-modal">
      <!-- Header -->
      <div class="modal-header">
        <div class="header-title">
          <Icon name="eye" />
          <h3>{{ $t('chat.vision.title') }}</h3>
        </div>
        <button @click="emit('close')" class="btn-close">
          <Icon name="times" />
        </button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <!-- Upload Zone -->
        <div
          class="drop-zone"
          :class="{ dragging: isDragging, 'has-file': selectedFile }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="triggerFileInput"
        >
          <input
            ref="fileInput"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            @change="handleFileSelect"
            hidden
          />
          <div v-if="!selectedFile" class="drop-placeholder">
            <Icon name="cloud-upload-alt" />
            <p>{{ $t('chat.vision.dropPrompt') }}</p>
            <span class="formats">{{ $t('chat.vision.formats') }}</span>
          </div>
          <div v-else-if="previewUrl" class="file-preview">
            <img :src="previewUrl" :alt="$t('chat.vision.preview')" class="preview-image" loading="lazy" />
            <div class="file-info">
              <span class="filename">{{ selectedFile.name }}</span>
              <span class="filesize">{{ formatFileSize(selectedFile.size) }}</span>
            </div>
            <button @click.stop="clearFile" class="btn-clear">
              <Icon name="times" />
            </button>
          </div>
        </div>

        <!-- Options -->
        <div class="options-row">
          <div class="option-group">
            <label>{{ $t('chat.vision.intent') }}</label>
            <select v-model="selectedIntent">
              <option v-for="(label, value) in intentLabels" :key="value" :value="value">{{ label }}</option>
            </select>
          </div>
          <div v-if="selectedIntent === 'visual_qa'" class="option-group flex-1">
            <label>{{ $t('chat.vision.question') }}</label>
            <input
              v-model="question"
              type="text"
              :placeholder="$t('chat.vision.questionPlaceholder')"
            />
          </div>
        </div>

        <!-- Analyze Button -->
        <button
          @click="analyzeImage"
          class="btn-analyze"
          :disabled="!selectedFile || processing"
        >
          <i :class="processing ? 'fas fa-spinner fa-spin' : 'search'"></i>
          {{ processing ? $t('chat.vision.analyzing') : $t('chat.vision.analyzeImage') }}
        </button>

        <!-- Error -->
        <div v-if="error" class="error-banner">
          <Icon name="exclamation-triangle" />
          <span>{{ error }}</span>
          <button @click="error = null" class="error-dismiss">
            <Icon name="times" />
          </button>
        </div>

        <!-- Results -->
        <div v-if="analysisResult" class="results-section">
          <div class="results-header">
            <h4><Icon name="check-circle" /> {{ $t('chat.vision.results') }}</h4>
            <div class="results-meta">
              <span class="meta-badge">
                {{ (analysisResult.confidence * 100).toFixed(1) }}%
              </span>
              <span class="meta-badge">
                {{ analysisResult.processing_time.toFixed(2) }}s
              </span>
              <span v-if="analysisResult.device_used" class="meta-badge">
                {{ analysisResult.device_used }}
              </span>
            </div>
          </div>

          <div class="results-content">
            <!-- Description -->
            <div
              v-if="(analysisResult.result_data as any)?.description"
              class="result-item"
            >
              <span class="result-label">{{ $t('chat.vision.description') }}</span>
              <p class="result-value">
                {{ (analysisResult.result_data as any).description }}
              </p>
            </div>

            <!-- Labels -->
            <div
              v-if="(analysisResult.result_data as any)?.labels?.length"
              class="result-item"
            >
              <span class="result-label">{{ $t('chat.vision.labels') }}</span>
              <div class="tags">
                <span
                  v-for="label in (analysisResult.result_data as any).labels"
                  :key="label"
                  class="tag"
                >{{ label }}</span>
              </div>
            </div>

            <!-- Objects -->
            <div
              v-if="(analysisResult.result_data as any)?.objects?.length"
              class="result-item"
            >
              <span class="result-label">{{ $t('chat.vision.detectedObjects') }}</span>
              <div class="objects-list">
                <div
                  v-for="(obj, idx) in (analysisResult.result_data as any).objects"
                  :key="idx"
                  class="object-row"
                >
                  <span>{{ obj.name || obj.label }}</span>
                  <span v-if="obj.confidence" class="obj-confidence">
                    {{ (obj.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>

            <!-- Raw JSON toggle -->
            <button @click="showRawJson = !showRawJson" class="btn-toggle-json">
              <Icon :name="showRawJson ? 'chevron-up' : 'chevron-down'" />
              {{ showRawJson ? $t('chat.vision.hideRawJson') : $t('chat.vision.showRawJson') }}
            </button>
            <pre v-if="showRawJson" class="json-display">{{
              JSON.stringify(analysisResult, null, 2)
            }}</pre>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button @click="exportResults" class="btn-secondary" :disabled="!analysisResult">
          <Icon name="download" /> {{ $t('chat.vision.exportJson') }}
        </button>
        <div class="footer-right">
          <button @click="emit('close')" class="btn-secondary">{{ $t('common.cancel') }}</button>
          <button
            @click="sendToChat"
            class="btn-primary"
            :disabled="!analysisResult"
          >
            <Icon name="paper-plane" /> {{ $t('chat.vision.sendToChat') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vision-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.vision-modal {
  background: var(--bg-secondary, #fff);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 640px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-2xl);
}

/* Header */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.header-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-title i {
  color: var(--color-primary);
  font-size: var(--text-lg);
}

.header-title h3 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  padding: var(--spacing-2);
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--duration-150);
}

.btn-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Body */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-8);
  text-align: center;
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  justify-content: center;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.05));
}

.drop-zone.has-file {
  border-style: solid;
  padding: var(--spacing-4);
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-tertiary);
}

.drop-placeholder i {
  font-size: var(--text-4xl);
  color: var(--text-muted);
}

.drop-placeholder p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.formats {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.file-preview {
  display: flex;
  align-items: center;
  gap: var(--spacing-3-5);
  width: 100%;
}

.preview-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
  text-align: left;
}

.filename {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}

.filesize {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.btn-clear {
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
}

.btn-clear:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Options */
.options-row {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
  min-width: 160px;
}

.option-group label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-secondary);
}

.option-group select,
.option-group input {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.option-group select:focus,
.option-group input:focus {
  outline: none;
  border-color: var(--color-primary);
}
.option-group select:focus-visible,
.option-group input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Analyze button */
.btn-analyze {
  padding: var(--spacing-2-5) var(--spacing-6);
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  align-self: center;
}

.btn-analyze:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-analyze:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border, var(--color-error));
  border-radius: var(--radius-lg);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.error-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

/* Results */
.results-section {
  background: var(--bg-tertiary);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-success-bg);
}

.results-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.results-meta {
  display: flex;
  gap: var(--spacing-2);
}

.meta-badge {
  font-size: var(--text-xs);
  padding: 3px 8px;
  border-radius: var(--radius-default);
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.results-content {
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.result-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-value {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.tag {
  font-size: var(--text-xs);
  padding: 3px 8px;
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.1));
  color: var(--color-primary);
  border-radius: var(--radius-xl);
}

.objects-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.object-row {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.obj-confidence {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.btn-toggle-json {
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.btn-toggle-json:hover {
  color: var(--text-secondary);
}

.json-display {
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
  margin: var(--spacing-0);
}

/* Footer */
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3-5) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.footer-right {
  display: flex;
  gap: var(--spacing-2);
}

.btn-primary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
