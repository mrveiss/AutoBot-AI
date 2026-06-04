<template>
  <div class="screen-capture-viewer">
    <!-- Controls Bar -->
    <div class="controls-bar">
      <div class="controls-left">
        <button @click="captureAndAnalyze" class="btn-capture" :disabled="analyzing">
          <Icon name="spinner" class="animate-spin" v-if="analyzing" />
          <Icon name="camera" v-else />
          {{ analyzing ? t('vision.screenCapture.analyzing') : t('vision.screenCapture.captureAndAnalyze') }}
        </button>

        <div class="auto-refresh-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="autoRefresh" />
            <span class="toggle-switch"></span>
            {{ t('vision.screenCapture.autoRefresh') }}
          </label>
          <select v-model="refreshInterval" :disabled="!autoRefresh" class="interval-select">
            <option :value="5000">5s</option>
            <option :value="10000">10s</option>
            <option :value="30000">30s</option>
            <option :value="60000">1m</option>
          </select>
        </div>
      </div>

      <div class="controls-right">
        <div class="filter-group">
          <label>{{ t('vision.screenCapture.elementTypeLabel') }}</label>
          <select v-model="elementTypeFilter">
            <option value="">{{ t('vision.screenCapture.allTypes') }}</option>
            <option v-for="type in elementTypes" :key="type.value" :value="type.value">
              {{ type.name }}
            </option>
          </select>
        </div>

        <div class="filter-group">
          <label>{{ t('vision.screenCapture.minConfidence') }}</label>
          <input
            type="range"
            v-model.number="confidenceThreshold"
            min="0"
            max="100"
            step="5"
          />
          <span class="confidence-value">{{ confidenceThreshold }}%</span>
        </div>
      </div>
    </div>

    <!-- Capture Error -->
    <BaseAlert
      v-if="analyzeError"
      variant="error"
      :message="analyzeError"
      dismissible
      @dismiss="analyzeError = null"
    />

    <!-- Main Content -->
    <div class="viewer-content">
      <!-- Analysis View -->
      <div class="analysis-panel" v-if="analysisResult">
        <div class="panel-header">
          <h4>{{ t('vision.screenCapture.screenAnalysis') }}</h4>
          <div class="analysis-meta">
            <span class="element-count">
              <Icon name="cube" />
              {{ t('vision.screenCapture.elements', { count: filteredElements.length }) }}
            </span>
            <span class="confidence">
              <Icon name="chart-line" />
              {{ t('vision.screenCapture.confidenceScore', { score: (analysisResult.confidence_score * 100).toFixed(1) }) }}
            </span>
            <span class="timestamp">
              <Icon name="clock" />
              {{ formatTimestamp(analysisResult.timestamp) }}
            </span>
          </div>
        </div>

        <!-- Elements List -->
        <div class="elements-section">
          <h5>{{ t('vision.screenCapture.detectedElements') }}</h5>
          <div class="elements-list">
            <div
              v-for="element in filteredElements"
              :key="element.element_id"
              class="element-item"
              :class="{ selected: selectedElement?.element_id === element.element_id }"
              @click="selectElement(element)"
            >
              <div class="element-icon" :style="{ backgroundColor: getElementColor(element.element_type) }">
                <Icon :name="getElementIcon(element.element_type)" />
              </div>
              <div class="element-info">
                <span class="element-type">{{ element.element_type }}</span>
                <span class="element-text" v-if="element.text_content">
                  {{ truncateText(element.text_content, 40) }}
                </span>
              </div>
              <div class="element-confidence">
                {{ (element.confidence * 100).toFixed(0) }}%
              </div>
            </div>

            <div v-if="filteredElements.length === 0" class="no-elements">
              <Icon name="search" />
              <span>{{ t('vision.screenCapture.noElementsMatch') }}</span>
            </div>
          </div>
        </div>

        <!-- Text Regions -->
        <div class="text-section" v-if="analysisResult.text_regions.length > 0">
          <h5>{{ t('vision.screenCapture.textRegionsOcr') }}</h5>
          <div class="text-regions">
            <div
              v-for="(region, idx) in analysisResult.text_regions"
              :key="idx"
              class="text-region"
            >
              <span class="text-content">{{ region.text || region }}</span>
            </div>
          </div>
        </div>

        <!-- Layout Info -->
        <div class="layout-section" v-if="analysisResult.layout_structure">
          <h5>{{ t('vision.screenCapture.layoutStructure') }}</h5>
          <div class="layout-info">
            <pre>{{ JSON.stringify(analysisResult.layout_structure, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="empty-icon">
          <Icon name="desktop" />
        </div>
        <h3>{{ t('vision.screenCapture.noScreenAnalysis') }}</h3>
        <p>{{ t('vision.screenCapture.noScreenAnalysisHint') }}</p>
      </div>
    </div>

    <!-- Selected Element Detail Modal -->
    <div v-if="selectedElement" class="element-detail-overlay" @click.self="selectedElement = null">
      <div class="element-detail-modal">
        <div class="modal-header">
          <h4>{{ t('vision.screenCapture.elementDetails') }}</h4>
          <button @click="selectedElement = null" class="btn-close">
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-content">
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.id') }}</span>
            <span class="value">{{ selectedElement.element_id }}</span>
          </div>
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.type') }}</span>
            <span class="value">{{ selectedElement.element_type }}</span>
          </div>
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.confidence') }}</span>
            <span class="value">{{ (selectedElement.confidence * 100).toFixed(1) }}%</span>
          </div>
          <div class="detail-row" v-if="selectedElement.text_content">
            <span class="label">{{ t('vision.screenCapture.text') }}</span>
            <span class="value">{{ selectedElement.text_content }}</span>
          </div>
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.position') }}</span>
            <span class="value">
              x: {{ selectedElement.bbox.x }}, y: {{ selectedElement.bbox.y }}
            </span>
          </div>
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.size') }}</span>
            <span class="value">
              {{ selectedElement.bbox.width }} x {{ selectedElement.bbox.height }}
            </span>
          </div>
          <div class="detail-row">
            <span class="label">{{ t('vision.screenCapture.center') }}</span>
            <span class="value">
              ({{ selectedElement.center_point[0] }}, {{ selectedElement.center_point[1] }})
            </span>
          </div>
          <div class="detail-row" v-if="selectedElement.possible_interactions.length > 0">
            <span class="label">{{ t('vision.screenCapture.interactions') }}</span>
            <div class="interactions-list">
              <span
                v-for="interaction in selectedElement.possible_interactions"
                :key="interaction"
                class="interaction-tag"
              >
                {{ interaction }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { usePollingJob } from '@/composables/usePollingJob';
import {
  visionMultimodalApiClient,
  type ScreenAnalysisResponse,
  type UIElement,
  type ElementTypeInfo,
} from '@/utils/VisionMultimodalApiClient';

const { t } = useI18n();
const logger = createLogger('ScreenCaptureViewer');

// Emits
const emit = defineEmits<{
  (e: 'analysis-complete', result: ScreenAnalysisResponse): void;
  (e: 'add-to-gallery', item: {
    id: string;
    type: 'screen';
    thumbnail: string;
    filename: string;
    timestamp: number;
    analysisResult: Record<string, unknown>;
  }): void;
}>();

// State
const analyzing = ref(false);
const analyzeError = ref<string | null>(null);
const analysisResult = ref<ScreenAnalysisResponse | null>(null);
const selectedElement = ref<UIElement | null>(null);
const elementTypes = ref<ElementTypeInfo[]>([]);

// Filters
const elementTypeFilter = ref('');
const confidenceThreshold = ref(50);

// Auto-refresh
const autoRefresh = ref(false);
const refreshInterval = ref(10000);
// Computed
const filteredElements = computed(() => {
  if (!analysisResult.value) return [];

  return analysisResult.value.ui_elements.filter((el) => {
    // Filter by type
    if (elementTypeFilter.value && el.element_type !== elementTypeFilter.value) {
      return false;
    }
    // Filter by confidence
    if (el.confidence * 100 < confidenceThreshold.value) {
      return false;
    }
    return true;
  });
});

// Methods
const captureAndAnalyze = async () => {
  analyzing.value = true;

  try {
    const response = await visionMultimodalApiClient.analyzeScreen({
      include_multimodal: true,
    });

    if (response.success && response.data) {
      analyzeError.value = null;
      analysisResult.value = response.data;
      emit('analysis-complete', response.data);
      logger.debug('Screen analysis complete:', response.data);
    } else {
      analyzeError.value = response.error || t('vision.screenCapture.toastAnalysisFailed');
      logger.error('Analysis failed:', response.error);
    }
  } catch (err) {
    analyzeError.value = t('vision.screenCapture.toastFailedToAnalyze');
    logger.error('Analysis error:', err);
  } finally {
    analyzing.value = false;
  }
};

const loadElementTypes = async () => {
  try {
    const response = await visionMultimodalApiClient.getElementTypes();
    if (response.success && response.data) {
      elementTypes.value = response.data.element_types;
    }
  } catch (err) {
    logger.error('Failed to load element types:', err);
  }
};

const selectElement = (element: UIElement) => {
  selectedElement.value = element;
};

const formatTimestamp = (timestamp: number): string => {
  return new Date(timestamp * 1000).toLocaleTimeString();
};

const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

const getElementColor = (elementType: string): string => {
  const colors: Record<string, string> = {
    button: '#3498db',
    input: '#2ecc71',
    text: '#9b59b6',
    image: '#e74c3c',
    link: '#f39c12',
    checkbox: '#1abc9c',
    dropdown: '#34495e',
    menu: '#e67e22',
    icon: '#95a5a6',
    window: '#2c3e50',
  };
  return colors[elementType.toLowerCase()] || '#7f8c8d';
};

const getElementIcon = (elementType: string): string => {
  const icons: Record<string, string> = {
    button: 'square',
    input: 'i-cursor',
    text: 'font',
    image: 'image',
    link: 'link',
    checkbox: 'check-square',
    dropdown: 'caret-down',
    menu: 'bars',
    icon: 'icons',
    window: 'window-maximize',
  };
  return icons[elementType.toLowerCase()] || 'cube';
};

// Auto-refresh watcher
const { start: _startAutoRefresh, stop: _stopAutoRefresh } = usePollingJob(
  async () => {
    if (!analyzing.value) {
      await captureAndAnalyze();
    }
    return null;
  },
  { intervalMs: refreshInterval, maxAttempts: Number.MAX_SAFE_INTEGER }
);

watch(autoRefresh, (enabled) => {
  if (enabled) {
    _startAutoRefresh('');
  } else {
    _stopAutoRefresh();
  }
});

watch(refreshInterval, () => {
  if (autoRefresh.value) {
    _stopAutoRefresh();
    _startAutoRefresh('');
  }
});

// Lifecycle
onMounted(() => {
  loadElementTypes();
});

onUnmounted(() => {
  _stopAutoRefresh();
});
</script>

<style scoped>
.screen-capture-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--spacing-4);
}

/* Controls Bar */
.controls-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.controls-left,
.controls-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.btn-capture {
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-capture:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-capture:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auto-refresh-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.toggle-label input {
  display: none;
}

.toggle-switch {
  width: 36px;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xl);
  position: relative;
  transition: all var(--duration-200);
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--text-tertiary);
  border-radius: 50%;
  transition: all var(--duration-200);
}

.toggle-label input:checked + .toggle-switch {
  background: var(--color-primary);
}

.toggle-label input:checked + .toggle-switch::after {
  left: 18px;
  background: white;
}

.interval-select {
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.filter-group label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.filter-group select {
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.filter-group input[type="range"] {
  width: 80px;
}

.confidence-value {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  min-width: 35px;
}

/* Viewer Content */
.viewer-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Analysis Panel */
.analysis-panel {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.panel-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.analysis-meta {
  display: flex;
  gap: var(--spacing-4);
}

.analysis-meta span {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

/* Elements Section */
.elements-section,
.text-section,
.layout-section {
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.elements-section h5,
.text-section h5,
.layout-section h5 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.elements-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  max-height: 300px;
  overflow-y: auto;
}

.element-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-150);
}

.element-item:hover {
  background: var(--bg-hover);
}

.element-item.selected {
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary);
}

.element-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: var(--text-sm);
}

.element-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
  min-width: 0;
}

.element-type {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.element-text {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.element-confidence {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
}

.no-elements {
  text-align: center;
  padding: var(--spacing-6);
  color: var(--text-tertiary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
}

.no-elements i {
  font-size: var(--text-2xl);
}

/* Text Regions */
.text-regions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.text-region {
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.text-content {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

/* Layout Section */
.layout-info pre {
  margin: var(--spacing-0);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
}

/* Empty State */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.empty-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: var(--text-muted);
}

.empty-state h3 {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  color: var(--text-primary);
}

.empty-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Element Detail Modal */
.element-detail-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.element-detail-modal {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
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
}

.btn-close:hover {
  color: var(--text-primary);
}

.modal-content {
  padding: var(--spacing-5);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-row .label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-row .value {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.interactions-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
}

.interaction-tag {
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2-5);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-xl);
}
</style>
