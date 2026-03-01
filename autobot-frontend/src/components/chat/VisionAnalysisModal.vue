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

import { ref, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import {
  visionMultimodalApiClient,
  type ProcessingIntent,
  type MultiModalResponse,
} from '@/utils/VisionMultimodalApiClient'

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

const intentLabels: Record<string, string> = {
  analysis: 'General Analysis',
  visual_qa: 'Visual Q&A',
  automation: 'Automation Detection',
  content_generation: 'Content Generation',
}

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
    error.value = 'Please drop a valid image file'
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
      error.value = response.error || 'Analysis failed'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error'
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
          <i class="fas fa-eye"></i>
          <h3>Image Analysis</h3>
        </div>
        <button @click="emit('close')" class="btn-close">
          <i class="fas fa-times"></i>
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
            <i class="fas fa-cloud-upload-alt"></i>
            <p>Drag & drop an image or click to browse</p>
            <span class="formats">PNG, JPG, WebP, GIF</span>
          </div>
          <div v-else-if="previewUrl" class="file-preview">
            <img :src="previewUrl" alt="Preview" class="preview-image" />
            <div class="file-info">
              <span class="filename">{{ selectedFile.name }}</span>
              <span class="filesize">{{ formatFileSize(selectedFile.size) }}</span>
            </div>
            <button @click.stop="clearFile" class="btn-clear">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <!-- Options -->
        <div class="options-row">
          <div class="option-group">
            <label>Intent</label>
            <select v-model="selectedIntent">
              <option value="analysis">General Analysis</option>
              <option value="visual_qa">Visual Q&A</option>
              <option value="automation">Automation Detection</option>
              <option value="content_generation">Content Generation</option>
            </select>
          </div>
          <div v-if="selectedIntent === 'visual_qa'" class="option-group flex-1">
            <label>Question</label>
            <input
              v-model="question"
              type="text"
              placeholder="What would you like to know about this image?"
            />
          </div>
        </div>

        <!-- Analyze Button -->
        <button
          @click="analyzeImage"
          class="btn-analyze"
          :disabled="!selectedFile || processing"
        >
          <i :class="processing ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          {{ processing ? 'Analyzing...' : 'Analyze Image' }}
        </button>

        <!-- Error -->
        <div v-if="error" class="error-banner">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ error }}</span>
          <button @click="error = null" class="error-dismiss">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- Results -->
        <div v-if="analysisResult" class="results-section">
          <div class="results-header">
            <h4><i class="fas fa-check-circle"></i> Results</h4>
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
              <span class="result-label">Description</span>
              <p class="result-value">
                {{ (analysisResult.result_data as any).description }}
              </p>
            </div>

            <!-- Labels -->
            <div
              v-if="(analysisResult.result_data as any)?.labels?.length"
              class="result-item"
            >
              <span class="result-label">Labels</span>
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
              <span class="result-label">Detected Objects</span>
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
              <i :class="showRawJson ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
              {{ showRawJson ? 'Hide' : 'Show' }} Raw JSON
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
          <i class="fas fa-download"></i> Export JSON
        </button>
        <div class="footer-right">
          <button @click="emit('close')" class="btn-secondary">Cancel</button>
          <button
            @click="sendToChat"
            class="btn-primary"
            :disabled="!analysisResult"
          >
            <i class="fas fa-paper-plane"></i> Send to Chat
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
  z-index: 1000;
}

.vision-modal {
  background: var(--bg-secondary, #fff);
  border-radius: 12px;
  width: 90%;
  max-width: 640px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

/* Header */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title i {
  color: var(--color-primary);
  font-size: 18px;
}

.header-title h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  padding: 8px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}

.btn-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Body */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: 10px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
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
  padding: 16px;
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-tertiary);
}

.drop-placeholder i {
  font-size: 36px;
  color: var(--text-muted);
}

.drop-placeholder p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.formats {
  font-size: 12px;
  color: var(--text-muted);
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}

.preview-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: left;
}

.filename {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}

.filesize {
  font-size: 12px;
  color: var(--text-tertiary);
}

.btn-clear {
  padding: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-clear:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Options */
.options-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
}

.option-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.option-group select,
.option-group input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.option-group select:focus,
.option-group input:focus {
  outline: none;
  border-color: var(--color-primary);
}

/* Analyze button */
.btn-analyze {
  padding: 10px 24px;
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
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
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border, var(--color-error));
  border-radius: 8px;
  color: var(--color-error);
  font-size: 13px;
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
  border-radius: 10px;
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--color-success-bg);
}

.results-header h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: 6px;
}

.results-meta {
  display: flex;
  gap: 8px;
}

.meta-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.results-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-value {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag {
  font-size: 11px;
  padding: 3px 8px;
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.1));
  color: var(--color-primary);
  border-radius: 10px;
}

.objects-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.object-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-primary);
}

.obj-confidence {
  font-size: 12px;
  color: var(--text-tertiary);
}

.btn-toggle-json {
  padding: 6px 10px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-toggle-json:hover {
  color: var(--text-secondary);
}

.json-display {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
}

/* Footer */
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--border-default);
}

.footer-right {
  display: flex;
  gap: 8px;
}

.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
