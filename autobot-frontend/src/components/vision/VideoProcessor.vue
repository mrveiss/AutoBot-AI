<template>
  <div class="video-processor">
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
          accept="video/mp4,video/webm,video/ogg,video/avi"
          @change="handleFileSelect"
          hidden
        />

        <div v-if="!selectedFile" class="drop-placeholder">
          <Icon name="video" />
          <p>{{ t('vision.videoProcessor.dropTitle') }}</p>
          <span>{{ t('vision.videoProcessor.dropOrClick') }}</span>
          <div class="supported-formats">
            {{ t('vision.videoProcessor.supportedFormats') }}
          </div>
        </div>

        <div v-else-if="previewUrl" class="file-preview">
          <video
            ref="videoPreview"
            :src="previewUrl"
            class="preview-video"
            @loadedmetadata="handleVideoLoaded"
          />
          <div class="file-info">
            <span class="filename">{{ selectedFile.name }}</span>
            <span class="filesize">{{ formatFileSize(selectedFile.size) }}</span>
            <span class="duration" v-if="videoDuration">{{ formatDuration(videoDuration) }}</span>
          </div>
          <button @click.stop="clearFile" class="btn-clear">
            <Icon name="times" />
          </button>
        </div>
      </div>
    </div>

    <!-- Processing Options -->
    <div class="options-section" v-if="selectedFile">
      <div class="option-group">
        <label>{{ t('vision.videoProcessor.frameExtractionMode') }}</label>
        <select v-model="extractionMode">
          <option value="keyframes">{{ t('vision.videoProcessor.keyFramesOnly') }}</option>
          <option value="interval">{{ t('vision.videoProcessor.fixedInterval') }}</option>
          <option value="all">{{ t('vision.videoProcessor.allFramesSlow') }}</option>
        </select>
      </div>

      <div class="option-group" v-if="extractionMode === 'interval'">
        <label>{{ t('vision.videoProcessor.frameInterval') }}</label>
        <input
          type="number"
          v-model.number="frameInterval"
          min="0.5"
          max="60"
          step="0.5"
        />
      </div>

      <div class="option-group">
        <label>{{ t('vision.videoProcessor.maxFrames') }}</label>
        <input
          type="number"
          v-model.number="maxFrames"
          min="1"
          max="100"
          step="1"
        />
      </div>

      <div class="option-group">
        <label>{{ t('vision.videoProcessor.processingIntent') }}</label>
        <select v-model="processingIntent">
          <option value="analysis">{{ t('vision.videoProcessor.generalAnalysis') }}</option>
          <option value="automation">{{ t('vision.videoProcessor.uiElementDetection') }}</option>
          <option value="content_generation">{{ t('vision.videoProcessor.contentGeneration') }}</option>
        </select>
      </div>
    </div>

    <!-- Process Button -->
    <div class="actions-section" v-if="selectedFile">
      <button
        @click="processVideo"
        class="btn-process"
        :disabled="processing"
      >
        <Icon name="spinner" class="animate-spin" v-if="processing" />
        <Icon name="cogs" v-else />
        {{ processing ? t('vision.videoProcessor.processing', { processed: processedFrames, total: totalFrames }) : t('vision.videoProcessor.processVideo') }}
      </button>
    </div>

    <!-- Progress Section -->
    <div v-if="processing" class="progress-section">
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: `${progressPercent}%` }"
        ></div>
      </div>
      <div class="progress-info">
        <span>{{ t('vision.videoProcessor.framesProcessed', { processed: processedFrames, total: totalFrames }) }}</span>
        <span>{{ progressPercent.toFixed(0) }}%</span>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="frameResults.length > 0" class="results-section">
      <div class="results-header">
        <h4><Icon name="check-circle" /> {{ t('vision.videoProcessor.processingComplete') }}</h4>
        <span class="frame-count">{{ t('vision.videoProcessor.framesAnalyzed', { count: frameResults.length }) }}</span>
      </div>

      <div class="frames-grid">
        <div
          v-for="(frame, idx) in frameResults"
          :key="idx"
          class="frame-card"
          @click="selectFrame(frame)"
        >
          <div class="frame-index">#{{ idx + 1 }}</div>
          <div class="frame-info">
            <span class="confidence">{{ (frame.confidence * 100).toFixed(0) }}%</span>
            <span class="time" v-if="frame.timestamp">{{ formatDuration(frame.timestamp) }}</span>
          </div>
        </div>
      </div>

      <!-- Selected Frame Detail -->
      <div v-if="selectedFrame" class="selected-frame">
        <h5>{{ t('vision.videoProcessor.frameDetails', { index: selectedFrameIndex + 1 }) }}</h5>
        <div class="frame-details">
          <div class="detail-item">
            <span class="label">{{ t('vision.videoProcessor.confidenceLabel') }}</span>
            <span class="value">{{ (selectedFrame.confidence * 100).toFixed(1) }}%</span>
          </div>
          <div class="detail-item">
            <span class="label">{{ t('vision.videoProcessor.processingTimeLabel') }}</span>
            <span class="value">{{ selectedFrame.processing_time.toFixed(2) }}s</span>
          </div>
          <div class="detail-item" v-if="selectedFrame.device_used">
            <span class="label">{{ t('vision.videoProcessor.deviceLabel') }}</span>
            <span class="value">{{ selectedFrame.device_used }}</span>
          </div>
        </div>

        <div class="frame-data" v-if="selectedFrame.result_data">
          <button @click="showFrameJson = !showFrameJson" class="btn-toggle">
            <Icon :name="showFrameJson ? 'chevron-up' : 'chevron-down'" />
            {{ showFrameJson ? t('vision.videoProcessor.hideAnalysisData') : t('vision.videoProcessor.showAnalysisData') }}
          </button>
          <pre v-if="showFrameJson" class="json-display">{{ JSON.stringify(selectedFrame.result_data, null, 2) }}</pre>
        </div>
      </div>

      <div class="results-actions">
        <button @click="exportAllResults" class="btn-secondary">
          <Icon name="download" />
          {{ t('vision.videoProcessor.exportAllResults') }}
        </button>
        <button @click="saveToGallery" class="btn-secondary">
          <Icon name="save" />
          {{ t('vision.videoProcessor.saveToGallery') }}
        </button>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="error" class="error-section">
      <div class="error-content">
        <Icon name="exclamation-triangle" />
        <span>{{ error }}</span>
      </div>
      <button @click="error = null" class="btn-dismiss">
        <Icon name="times" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useNotificationBus } from '@/composables/useNotificationBus';
import { useThumbnailWorker } from '@/composables/useThumbnailWorker';
import {
  visionMultimodalApiClient,
  type ProcessingIntent,
  type MultiModalResponse,
} from '@/utils/VisionMultimodalApiClient';

// Extended type for frame results that includes timestamp
interface FrameResult extends MultiModalResponse {
  timestamp?: number;
}

const { t } = useI18n();
const logger = createLogger('VideoProcessor');
const { showToast } = useNotificationBus();
const { generateThumbnail, isSupported: isWorkerSupported } = useThumbnailWorker();

// Emits
const emit = defineEmits<{
  (e: 'analysis-complete', result: Record<string, unknown>): void;
  (e: 'add-to-gallery', item: {
    id: string;
    type: 'video';
    thumbnail: string;
    filename: string;
    timestamp: number;
    analysisResult: Record<string, unknown>;
  }): void;
}>();

// State
const fileInput = ref<HTMLInputElement | null>(null);
const videoPreview = ref<HTMLVideoElement | null>(null);
const selectedFile = ref<File | null>(null);
const previewUrl = ref<string | null>(null);
const isDragging = ref(false);
const videoDuration = ref(0);

// Processing options
const extractionMode = ref<'keyframes' | 'interval' | 'all'>('interval');
const frameInterval = ref(2);
const maxFrames = ref(10);
const processingIntent = ref<ProcessingIntent>('analysis');

// Processing state
const processing = ref(false);
const processedFrames = ref(0);
const totalFrames = ref(0);
const frameResults = ref<FrameResult[]>([]);
const error = ref<string | null>(null);

// Selected frame
const selectedFrame = ref<FrameResult | null>(null);
const selectedFrameIndex = ref(0);
const showFrameJson = ref(false);

// Computed
const progressPercent = computed(() => {
  if (totalFrames.value === 0) return 0;
  return (processedFrames.value / totalFrames.value) * 100;
});

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
  if (file && file.type.startsWith('video/')) {
    selectFile(file);
  } else {
    error.value = t('vision.videoProcessor.errorInvalidFile');
  }
};

const selectFile = (file: File) => {
  selectedFile.value = file;
  frameResults.value = [];
  selectedFrame.value = null;
  error.value = null;
  videoDuration.value = 0;

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
  }
  previewUrl.value = URL.createObjectURL(file);
  logger.debug('Video selected:', file.name);
};

const handleVideoLoaded = () => {
  if (videoPreview.value) {
    videoDuration.value = videoPreview.value.duration;
    logger.debug('Video duration:', videoDuration.value);
  }
};

const clearFile = () => {
  selectedFile.value = null;
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = null;
  }
  frameResults.value = [];
  selectedFrame.value = null;
  videoDuration.value = 0;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const processVideo = async () => {
  if (!selectedFile.value || !videoPreview.value) return;

  processing.value = true;
  processedFrames.value = 0;
  frameResults.value = [];
  error.value = null;

  try {
    // Calculate frame timestamps based on extraction mode
    const timestamps = calculateFrameTimestamps();
    totalFrames.value = Math.min(timestamps.length, maxFrames.value);

    // Extract and process frames
    for (let i = 0; i < totalFrames.value; i++) {
      const timestamp = timestamps[i];
      const frameBlob = await extractFrame(timestamp);

      if (frameBlob) {
        const file = new File([frameBlob], `frame_${i}.jpg`, { type: 'image/jpeg' });
        const response = await visionMultimodalApiClient.processImage(
          file,
          processingIntent.value
        );

        if (response.success && response.data) {
          frameResults.value.push({
            ...response.data,
            timestamp,
          } as FrameResult);
        }
      }

      processedFrames.value = i + 1;
    }

    if (frameResults.value.length > 0) {
      emit('analysis-complete', {
        video: selectedFile.value.name,
        frames_processed: frameResults.value.length,
        results: frameResults.value,
      });
      showToast(t('vision.videoProcessor.toastProcessed', { count: frameResults.value.length }), 'success');
    } else {
      error.value = t('vision.videoProcessor.errorNoFrames');
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Video processing failed';
    logger.error('Video processing error:', err);
  } finally {
    processing.value = false;
  }
};

const calculateFrameTimestamps = (): number[] => {
  const timestamps: number[] = [];

  if (extractionMode.value === 'interval') {
    for (let t = 0; t < videoDuration.value; t += frameInterval.value) {
      timestamps.push(t);
    }
  } else if (extractionMode.value === 'keyframes') {
    // Simple keyframe estimation - beginning, quarters, end
    const keyPoints = [0, 0.25, 0.5, 0.75, 1];
    keyPoints.forEach(p => {
      const t = p * videoDuration.value;
      if (t < videoDuration.value) {
        timestamps.push(t);
      }
    });
  } else {
    // All frames - every 0.5 seconds
    for (let t = 0; t < videoDuration.value; t += 0.5) {
      timestamps.push(t);
    }
  }

  return timestamps.slice(0, maxFrames.value);
};

const extractFrame = async (timestamp: number): Promise<Blob | null> => {
  // Try Web Worker first if supported (Issue #4038)
  if (isWorkerSupported.value && previewUrl.value) {
    try {
      logger.debug(`Generating thumbnail with Web Worker at ${timestamp}s`);
      const dataUrl = await generateThumbnail(
        previewUrl.value,
        timestamp,
        320, // width
        180, // height
        'image/jpeg',
        0.85 // quality
      );

      if (dataUrl) {
        // Convert data URL to Blob
        const response = await fetch(dataUrl);
        const blob = await response.blob();
        logger.debug(`Thumbnail generated successfully (${blob.size} bytes)`);
        return blob;
      }
    } catch (err) {
      logger.warn('Web Worker thumbnail generation failed, falling back to canvas:', err);
      // Fall through to canvas-based approach
    }
  }

  // Fallback to canvas-based approach
  return new Promise((resolve) => {
    const video = videoPreview.value;
    if (!video) {
      resolve(null);
      return;
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      resolve(null);
      return;
    }

    video.currentTime = timestamp;

    const handleSeeked = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
      canvas.toBlob((blob) => {
        resolve(blob);
      }, 'image/jpeg', 0.85);
      video.removeEventListener('seeked', handleSeeked);
    };

    video.addEventListener('seeked', handleSeeked);
  });
};

const selectFrame = (frame: MultiModalResponse) => {
  selectedFrame.value = frame;
  selectedFrameIndex.value = frameResults.value.indexOf(frame);
  showFrameJson.value = false;
};

const exportAllResults = () => {
  const data = {
    video: selectedFile.value?.name,
    processed_at: new Date().toISOString(),
    settings: {
      extraction_mode: extractionMode.value,
      frame_interval: frameInterval.value,
      max_frames: maxFrames.value,
      processing_intent: processingIntent.value,
    },
    frames: frameResults.value,
  };

  const dataStr = JSON.stringify(data, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `video_analysis_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

const saveToGallery = () => {
  if (!selectedFile.value || frameResults.value.length === 0) return;

  emit('add-to-gallery', {
    id: `vid_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`,
    type: 'video',
    thumbnail: '', // Video thumbnails need special handling
    filename: selectedFile.value.name,
    timestamp: Date.now(),
    analysisResult: {
      frames_processed: frameResults.value.length,
      results: frameResults.value,
    },
  });

  showToast(t('vision.videoProcessor.toastSavedToGallery'), 'success');
};

// Cleanup object URLs on unmount to prevent memory leaks
onUnmounted(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
  }
});
</script>

<style scoped>
.video-processor {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Upload Section */
.upload-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-10);
  text-align: center;
  cursor: pointer;
  transition: all var(--duration-200);
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.drop-zone.has-file {
  border-style: solid;
  padding: var(--spacing-5);
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  color: var(--text-tertiary);
}

.drop-placeholder i {
  font-size: var(--text-5xl);
  color: var(--text-muted);
}

.drop-placeholder p {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.supported-formats {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--spacing-2);
}

.file-preview {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  width: 100%;
}

.preview-video {
  width: 200px;
  height: 120px;
  object-fit: cover;
  border-radius: var(--radius-lg);
  background: var(--bg-tertiary);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  text-align: left;
}

.filename {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.filesize,
.duration {
  font-size: var(--text-sm);
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

/* Options Section */
.options-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.option-group label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.option-group select,
.option-group input {
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

/* Actions */
.actions-section {
  display: flex;
  justify-content: center;
}

.btn-process {
  padding: var(--spacing-3-5) var(--spacing-8);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.btn-process:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-process:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Progress Section */
.progress-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.progress-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
  margin-bottom: var(--spacing-3);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Results Section */
.results-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  background: var(--color-success-bg);
  border-bottom: 1px solid var(--border-default);
}

.results-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.frame-count {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.frames-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: var(--spacing-3);
  padding: var(--spacing-5);
}

.frame-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3);
  cursor: pointer;
  transition: all var(--duration-150);
}

.frame-card:hover {
  border-color: var(--color-primary);
}

.frame-index {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.frame-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.frame-info .confidence,
.frame-info .time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.selected-frame {
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.selected-frame h5 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.frame-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-item .label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.detail-item .value {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.btn-toggle {
  padding: var(--spacing-2) var(--spacing-3);
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.json-display {
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
}

.results-actions {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-default);
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
  gap: var(--spacing-2);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

/* Error Section */
.error-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-lg);
}

.error-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--color-error);
}

.btn-dismiss {
  padding: var(--spacing-1) var(--spacing-2);
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
}
</style>
