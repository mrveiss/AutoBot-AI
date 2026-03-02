<template>
  <div class="screen-capture-viewer">
    <!-- Controls Bar -->
    <div class="controls-bar">
      <div class="controls-left">
        <button @click="captureAndAnalyze" class="btn-capture" :disabled="analyzing">
          <i v-if="analyzing" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-camera"></i>
          {{ analyzing ? 'Analyzing...' : 'Capture & Analyze' }}
        </button>

        <div class="auto-refresh-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="autoRefresh" />
            <span class="toggle-switch"></span>
            Auto-refresh
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
          <label>Element Type</label>
          <select v-model="elementTypeFilter">
            <option value="">All Types</option>
            <option v-for="type in elementTypes" :key="type.value" :value="type.value">
              {{ type.name }}
            </option>
          </select>
        </div>

        <div class="filter-group">
          <label>Min Confidence</label>
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

    <!-- Main Content -->
    <div class="viewer-content">
      <!-- Analysis View -->
      <div class="analysis-panel" v-if="analysisResult">
        <div class="panel-header">
          <h4>Screen Analysis</h4>
          <div class="analysis-meta">
            <span class="element-count">
              <i class="fas fa-cube"></i>
              {{ filteredElements.length }} elements
            </span>
            <span class="confidence">
              <i class="fas fa-chart-line"></i>
              {{ (analysisResult.confidence_score * 100).toFixed(1) }}% confidence
            </span>
            <span class="timestamp">
              <i class="fas fa-clock"></i>
              {{ formatTimestamp(analysisResult.timestamp) }}
            </span>
          </div>
        </div>

        <!-- Elements List -->
        <div class="elements-section">
          <h5>Detected Elements</h5>
          <div class="elements-list">
            <div
              v-for="element in filteredElements"
              :key="element.element_id"
              class="element-item"
              :class="{ selected: selectedElement?.element_id === element.element_id }"
              @click="selectElement(element)"
            >
              <div class="element-icon" :style="{ backgroundColor: getElementColor(element.element_type) }">
                <i :class="getElementIcon(element.element_type)"></i>
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
              <i class="fas fa-search"></i>
              <span>No elements match current filters</span>
            </div>
          </div>
        </div>

        <!-- Text Regions -->
        <div class="text-section" v-if="analysisResult.text_regions.length > 0">
          <h5>Text Regions (OCR)</h5>
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
          <h5>Layout Structure</h5>
          <div class="layout-info">
            <pre>{{ JSON.stringify(analysisResult.layout_structure, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="empty-icon">
          <i class="fas fa-desktop"></i>
        </div>
        <h3>No Screen Analysis</h3>
        <p>Click "Capture & Analyze" to analyze the current screen</p>
      </div>
    </div>

    <!-- Selected Element Detail Modal -->
    <div v-if="selectedElement" class="element-detail-overlay" @click.self="selectedElement = null">
      <div class="element-detail-modal">
        <div class="modal-header">
          <h4>Element Details</h4>
          <button @click="selectedElement = null" class="btn-close">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-content">
          <div class="detail-row">
            <span class="label">ID</span>
            <span class="value">{{ selectedElement.element_id }}</span>
          </div>
          <div class="detail-row">
            <span class="label">Type</span>
            <span class="value">{{ selectedElement.element_type }}</span>
          </div>
          <div class="detail-row">
            <span class="label">Confidence</span>
            <span class="value">{{ (selectedElement.confidence * 100).toFixed(1) }}%</span>
          </div>
          <div class="detail-row" v-if="selectedElement.text_content">
            <span class="label">Text</span>
            <span class="value">{{ selectedElement.text_content }}</span>
          </div>
          <div class="detail-row">
            <span class="label">Position</span>
            <span class="value">
              x: {{ selectedElement.bbox.x }}, y: {{ selectedElement.bbox.y }}
            </span>
          </div>
          <div class="detail-row">
            <span class="label">Size</span>
            <span class="value">
              {{ selectedElement.bbox.width }} x {{ selectedElement.bbox.height }}
            </span>
          </div>
          <div class="detail-row">
            <span class="label">Center</span>
            <span class="value">
              ({{ selectedElement.center_point[0] }}, {{ selectedElement.center_point[1] }})
            </span>
          </div>
          <div class="detail-row" v-if="selectedElement.possible_interactions.length > 0">
            <span class="label">Interactions</span>
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  visionMultimodalApiClient,
  type ScreenAnalysisResponse,
  type UIElement,
  type ElementTypeInfo,
} from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('ScreenCaptureViewer');
const { showToast } = useToast();

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
const analysisResult = ref<ScreenAnalysisResponse | null>(null);
const selectedElement = ref<UIElement | null>(null);
const elementTypes = ref<ElementTypeInfo[]>([]);

// Filters
const elementTypeFilter = ref('');
const confidenceThreshold = ref(50);

// Auto-refresh
const autoRefresh = ref(false);
const refreshInterval = ref(10000);
let refreshTimer: ReturnType<typeof setInterval> | null = null;

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
      analysisResult.value = response.data;
      emit('analysis-complete', response.data);
      logger.debug('Screen analysis complete:', response.data);
    } else {
      showToast(response.error || 'Analysis failed', 'error');
      logger.error('Analysis failed:', response.error);
    }
  } catch (err) {
    showToast('Failed to analyze screen', 'error');
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
    button: 'fas fa-square',
    input: 'fas fa-i-cursor',
    text: 'fas fa-font',
    image: 'fas fa-image',
    link: 'fas fa-link',
    checkbox: 'fas fa-check-square',
    dropdown: 'fas fa-caret-down',
    menu: 'fas fa-bars',
    icon: 'fas fa-icons',
    window: 'fas fa-window-maximize',
  };
  return icons[elementType.toLowerCase()] || 'fas fa-cube';
};

// Auto-refresh watcher
watch(autoRefresh, (enabled) => {
  if (enabled) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

watch(refreshInterval, () => {
  if (autoRefresh.value) {
    stopAutoRefresh();
    startAutoRefresh();
  }
});

const startAutoRefresh = () => {
  if (refreshTimer) return;
  refreshTimer = setInterval(() => {
    if (!analyzing.value) {
      captureAndAnalyze();
    }
  }, refreshInterval.value);
  logger.debug('Auto-refresh started:', refreshInterval.value);
};

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
    logger.debug('Auto-refresh stopped');
  }
};

// Lifecycle
onMounted(() => {
  loadElementTypes();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
.screen-capture-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

/* Controls Bar */
.controls-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  flex-wrap: wrap;
  gap: 16px;
}

.controls-left,
.controls-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.btn-capture {
  padding: 12px 24px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
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
  gap: 12px;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
}

.toggle-label input {
  display: none;
}

.toggle-switch {
  width: 36px;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  position: relative;
  transition: all 0.2s;
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
  transition: all 0.2s;
}

.toggle-label input:checked + .toggle-switch {
  background: var(--color-primary);
}

.toggle-label input:checked + .toggle-switch::after {
  left: 18px;
  background: white;
}

.interval-select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.filter-group select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.filter-group input[type="range"] {
  width: 80px;
}

.confidence-value {
  font-size: 12px;
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
  border-radius: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
  gap: 12px;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.analysis-meta {
  display: flex;
  gap: 16px;
}

.analysis-meta span {
  font-size: 12px;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Elements Section */
.elements-section,
.text-section,
.layout-section {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.elements-section h5,
.text-section h5,
.layout-section h5 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.elements-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.element-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
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
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
}

.element-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.element-type {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.element-text {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.element-confidence {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 2px 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.no-elements {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.no-elements i {
  font-size: 24px;
}

/* Text Regions */
.text-regions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.text-region {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.text-content {
  font-size: 13px;
  color: var(--text-primary);
}

/* Layout Section */
.layout-info pre {
  margin: 0;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  font-size: 12px;
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
  gap: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
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
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
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
  z-index: 1000;
}

.element-detail-modal {
  background: var(--bg-secondary);
  border-radius: 12px;
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
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
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
}

.btn-close:hover {
  color: var(--text-primary);
}

.modal-content {
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-row .label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-row .value {
  font-size: 14px;
  color: var(--text-primary);
}

.interactions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.interaction-tag {
  font-size: 12px;
  padding: 4px 10px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: 12px;
}
</style>
