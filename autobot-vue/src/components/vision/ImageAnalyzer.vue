<template>
  <div class="image-analyzer">
    <!-- Upload Section -->
    <div class="upload-section">
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
          <p>Drag & drop an image here</p>
          <span>or click to browse</span>
          <div class="supported-formats">
            PNG, JPG, WebP, GIF
          </div>
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
    </div>

    <!-- Options Section -->
    <div class="options-section">
      <div class="option-group">
        <label>Processing Intent</label>
        <select v-model="selectedIntent">
          <option value="analysis">General Analysis</option>
          <option value="visual_qa">Visual Q&A</option>
          <option value="automation">Automation Detection</option>
          <option value="content_generation">Content Generation</option>
        </select>
      </div>

      <div class="option-group" v-if="selectedIntent === 'visual_qa'">
        <label>Question</label>
        <input
          v-model="question"
          type="text"
          placeholder="What would you like to know about this image?"
        />
      </div>
    </div>

    <!-- Analyze Button -->
    <div class="actions-section">
      <button
        @click="analyzeImage"
        class="btn-analyze"
        :disabled="!selectedFile || processing"
      >
        <i v-if="processing" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-search"></i>
        {{ processing ? 'Analyzing...' : 'Analyze Image' }}
      </button>
    </div>

    <!-- Results Section -->
    <div v-if="analysisResult" class="results-section">
      <div class="results-header">
        <h4><i class="fas fa-check-circle"></i> Analysis Results</h4>
        <div class="results-meta">
          <span class="confidence">
            Confidence: {{ (analysisResult.confidence * 100).toFixed(1) }}%
          </span>
          <span class="processing-time">
            {{ analysisResult.processing_time.toFixed(2) }}s
          </span>
          <span class="device" v-if="analysisResult.device_used">
            {{ analysisResult.device_used }}
          </span>
        </div>
      </div>

      <div class="results-content">
        <!-- Result Data Display -->
        <div class="result-card" v-if="analysisResult.result_data">
          <h5>Analysis Data</h5>
          <div class="result-data">
            <template v-if="analysisResult.result_data.description">
              <div class="data-item">
                <span class="label">Description</span>
                <span class="value">{{ analysisResult.result_data.description }}</span>
              </div>
            </template>
            <template v-if="analysisResult.result_data.labels">
              <div class="data-item">
                <span class="label">Labels</span>
                <div class="tags">
                  <span
                    v-for="label in analysisResult.result_data.labels"
                    :key="label"
                    class="tag"
                  >
                    {{ label }}
                  </span>
                </div>
              </div>
            </template>
            <template v-if="analysisResult.result_data.objects">
              <div class="data-item">
                <span class="label">Detected Objects</span>
                <div class="objects-list">
                  <div
                    v-for="(obj, idx) in (analysisResult.result_data.objects as Array<{name?: string; label?: string; confidence?: number}>)"
                    :key="idx"
                    class="object-item"
                  >
                    <span class="object-name">{{ obj.name || obj.label }}</span>
                    <span class="object-confidence" v-if="obj.confidence">
                      {{ (obj.confidence * 100).toFixed(0) }}%
                    </span>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Raw JSON Toggle -->
        <div class="raw-json-section">
          <button @click="showRawJson = !showRawJson" class="btn-toggle">
            <i :class="showRawJson ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
            {{ showRawJson ? 'Hide' : 'Show' }} Raw JSON
          </button>
          <pre v-if="showRawJson" class="json-display">{{ JSON.stringify(analysisResult, null, 2) }}</pre>
        </div>
      </div>

      <!-- Result Actions -->
      <div class="results-actions">
        <button @click="saveToGallery" class="btn-secondary">
          <i class="fas fa-save"></i>
          Save to Gallery
        </button>
        <button @click="exportResults" class="btn-secondary">
          <i class="fas fa-download"></i>
          Export JSON
        </button>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="error" class="error-section">
      <div class="error-content">
        <i class="fas fa-exclamation-triangle"></i>
        <span>{{ error }}</span>
      </div>
      <button @click="error = null" class="btn-dismiss">
        <i class="fas fa-times"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import {
  visionMultimodalApiClient,
  type ProcessingIntent,
  type MultiModalResponse,
} from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('ImageAnalyzer');

// Emits
const emit = defineEmits<{
  (e: 'analysis-complete', result: MultiModalResponse): void;
  (e: 'add-to-gallery', item: {
    id: string;
    type: 'image';
    thumbnail: string;
    filename: string;
    timestamp: number;
    analysisResult: Record<string, unknown>;
  }): void;
}>();

// State
const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const previewUrl = ref<string | null>(null);
const isDragging = ref(false);
const selectedIntent = ref<ProcessingIntent>('analysis');
const question = ref('');
const processing = ref(false);
const analysisResult = ref<MultiModalResponse | null>(null);
const error = ref<string | null>(null);
const showRawJson = ref(false);

// Methods
const triggerFileInput = () => {
  fileInput.value?.click();
};

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (file) {
    selectFile(file);
  }
};

const handleDrop = (event: DragEvent) => {
  isDragging.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file && file.type.startsWith('image/')) {
    selectFile(file);
  } else {
    error.value = 'Please drop a valid image file';
  }
};

const selectFile = (file: File) => {
  selectedFile.value = file;
  analysisResult.value = null;
  error.value = null;

  // Create preview URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
  }
  previewUrl.value = URL.createObjectURL(file);
  logger.debug('File selected:', file.name);
};

const clearFile = () => {
  selectedFile.value = null;
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = null;
  }
  analysisResult.value = null;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

const analyzeImage = async () => {
  if (!selectedFile.value) return;

  processing.value = true;
  error.value = null;

  try {
    const questionText = selectedIntent.value === 'visual_qa' ? question.value : undefined;
    const response = await visionMultimodalApiClient.processImage(
      selectedFile.value,
      selectedIntent.value,
      questionText
    );

    if (response.success && response.data) {
      analysisResult.value = response.data;
      emit('analysis-complete', response.data);
      logger.debug('Analysis complete:', response.data);
    } else {
      error.value = response.error || 'Analysis failed';
      logger.error('Analysis failed:', response.error);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error occurred';
    logger.error('Analysis error:', err);
  } finally {
    processing.value = false;
  }
};

const saveToGallery = () => {
  if (!selectedFile.value || !previewUrl.value || !analysisResult.value) return;

  emit('add-to-gallery', {
    id: `img_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`,
    type: 'image',
    thumbnail: previewUrl.value,
    filename: selectedFile.value.name,
    timestamp: Date.now(),
    analysisResult: analysisResult.value as Record<string, unknown>,
  });
};

const exportResults = () => {
  if (!analysisResult.value) return;

  const dataStr = JSON.stringify(analysisResult.value, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `analysis_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

// Cleanup object URLs on unmount to prevent memory leaks
onUnmounted(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
  }
});
</script>

<style scoped>
.image-analyzer {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Upload Section */
.upload-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drop-zone:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.drop-zone.has-file {
  border-style: solid;
  padding: 20px;
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-tertiary);
}

.drop-placeholder i {
  font-size: 48px;
  color: var(--text-muted);
}

.drop-placeholder p {
  margin: 0;
  font-size: 16px;
  color: var(--text-secondary);
}

.drop-placeholder span {
  font-size: 13px;
}

.supported-formats {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 8px;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.preview-image {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
}

.filename {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}

.filesize {
  font-size: 13px;
  color: var(--text-tertiary);
}

.btn-clear {
  padding: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-clear:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Options Section */
.options-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.option-group select,
.option-group input {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary);
}

.option-group select:focus,
.option-group input:focus {
  outline: none;
  border-color: var(--color-primary);
}

/* Actions Section */
.actions-section {
  display: flex;
  justify-content: center;
}

.btn-analyze {
  padding: 14px 32px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all 0.2s;
}

.btn-analyze:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-analyze:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Results Section */
.results-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--color-success-bg);
  border-bottom: 1px solid var(--border-default);
}

.results-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: 8px;
}

.results-meta {
  display: flex;
  gap: 16px;
}

.results-meta span {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.results-content {
  padding: 20px;
}

.result-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.result-card h5 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.result-data {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.data-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.data-item .label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-item .value {
  font-size: 14px;
  color: var(--text-primary);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  font-size: 12px;
  padding: 4px 10px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: 12px;
}

.objects-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.object-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.object-name {
  font-size: 13px;
  color: var(--text-primary);
}

.object-confidence {
  font-size: 12px;
  color: var(--text-tertiary);
}

.raw-json-section {
  margin-top: 16px;
}

.btn-toggle {
  padding: 8px 12px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-toggle:hover {
  color: var(--text-secondary);
}

.json-display {
  margin-top: 12px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 300px;
}

.results-actions {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

/* Error Section */
.error-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: 8px;
}

.error-content {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-error);
}

.btn-dismiss {
  padding: 4px 8px;
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
}

/* Buttons */
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
  gap: 8px;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}
</style>
