<template>
  <div class="analysis-results">
    <!-- Header -->
    <div class="results-header">
      <div class="header-info">
        <h4>Analysis Results</h4>
        <div class="meta-badges">
          <span class="badge confidence">
            <i class="fas fa-chart-line"></i>
            {{ (confidenceScore * 100).toFixed(1) }}% confidence
          </span>
          <span class="badge elements" v-if="elementCount > 0">
            <i class="fas fa-cube"></i>
            {{ elementCount }} elements
          </span>
          <span class="badge timestamp">
            <i class="fas fa-clock"></i>
            {{ formattedTimestamp }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <button @click="exportResults" class="btn-export">
          <i class="fas fa-download"></i>
          Export
        </button>
      </div>
    </div>

    <!-- Image with Overlays -->
    <div class="image-container" ref="imageContainer" v-if="imageSource">
      <img
        :src="imageSource"
        alt="Analysis source"
        class="source-image"
        ref="sourceImage"
        @load="handleImageLoad"
      />
      <!-- Element Bounding Boxes -->
      <div
        v-for="element in visibleElements"
        :key="element.element_id"
        class="element-overlay"
        :style="getOverlayStyle(element)"
        :class="{ selected: selectedElement?.element_id === element.element_id }"
        @click="selectElement(element)"
      >
        <div class="overlay-label" :style="{ backgroundColor: getElementColor(element.element_type) }">
          {{ element.element_type }}
        </div>
      </div>
    </div>

    <!-- Elements List -->
    <div class="elements-panel" v-if="analysisData && analysisData.ui_elements && analysisData.ui_elements.length > 0">
      <div class="panel-header">
        <h5>Detected Elements ({{ analysisData.ui_elements.length }})</h5>
        <div class="filter-controls">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search elements..."
            class="search-input"
          />
          <select v-model="typeFilter">
            <option value="">All Types</option>
            <option v-for="type in elementTypesList" :key="type" :value="type">
              {{ type }}
            </option>
          </select>
        </div>
      </div>

      <div class="elements-list">
        <div
          v-for="element in filteredElements"
          :key="element.element_id"
          class="element-row"
          :class="{ selected: selectedElement?.element_id === element.element_id }"
          @click="selectElement(element)"
        >
          <div class="element-icon" :style="{ backgroundColor: getElementColor(element.element_type) }">
            <i :class="getElementIcon(element.element_type)"></i>
          </div>
          <div class="element-details">
            <span class="element-type">{{ element.element_type }}</span>
            <span class="element-text" v-if="element.text_content">
              {{ truncateText(element.text_content, 50) }}
            </span>
            <span class="element-position">
              {{ element.bbox.x }}, {{ element.bbox.y }} ({{ element.bbox.width }}x{{ element.bbox.height }})
            </span>
          </div>
          <div class="element-confidence">
            <div class="confidence-bar" :style="{ width: `${element.confidence * 100}%` }"></div>
            <span>{{ (element.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>

        <div v-if="filteredElements.length === 0" class="no-results">
          No elements match your filters
        </div>
      </div>
    </div>

    <!-- Text Regions -->
    <div class="text-panel" v-if="analysisData && analysisData.text_regions && analysisData.text_regions.length > 0">
      <div class="panel-header">
        <h5>Text Regions ({{ analysisData.text_regions.length }})</h5>
      </div>
      <div class="text-list">
        <div
          v-for="(region, idx) in analysisData.text_regions"
          :key="idx"
          class="text-item"
        >
          <span class="text-content">{{ getTextContent(region as TextRegion) }}</span>
        </div>
      </div>
    </div>

    <!-- Automation Opportunities -->
    <div class="automation-panel" v-if="analysisData && analysisData.automation_opportunities && analysisData.automation_opportunities.length > 0">
      <div class="panel-header">
        <h5>Automation Opportunities ({{ analysisData.automation_opportunities.length }})</h5>
      </div>
      <div class="automation-list">
        <div
          v-for="(opp, idx) in analysisData.automation_opportunities"
          :key="idx"
          class="automation-item"
        >
          <i class="fas fa-magic"></i>
          <span>{{ getAutomationDescription(opp as AutomationOpportunity) }}</span>
        </div>
      </div>
    </div>

    <!-- Selected Element Detail -->
    <div v-if="selectedElement" class="selected-detail">
      <div class="detail-header">
        <h5>Element Details</h5>
        <button @click="selectedElement = null" class="btn-close">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="detail-content">
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
          <span class="label">Bounding Box</span>
          <span class="value">
            x: {{ selectedElement.bbox.x }}, y: {{ selectedElement.bbox.y }},
            w: {{ selectedElement.bbox.width }}, h: {{ selectedElement.bbox.height }}
          </span>
        </div>
        <div class="detail-row">
          <span class="label">Center</span>
          <span class="value">
            ({{ selectedElement.center_point[0] }}, {{ selectedElement.center_point[1] }})
          </span>
        </div>
        <div class="detail-row" v-if="selectedElement.possible_interactions?.length > 0">
          <span class="label">Interactions</span>
          <div class="interactions">
            <span
              v-for="action in selectedElement.possible_interactions"
              :key="action"
              class="interaction-badge"
            >
              {{ action }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import type { ScreenAnalysisResponse, UIElement, TextRegion, AutomationOpportunity } from '@/utils/VisionMultimodalApiClient';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _logger = createLogger('AnalysisResults');

// Props
const props = defineProps<{
  analysisData: ScreenAnalysisResponse | null;
  imageSource?: string;
}>();

// State
const imageContainer = ref<HTMLDivElement | null>(null);
const sourceImage = ref<HTMLImageElement | null>(null);
const selectedElement = ref<UIElement | null>(null);
const searchQuery = ref('');
const typeFilter = ref('');
const imageScale = ref(1);

// Computed
const confidenceScore = computed(() => props.analysisData?.confidence_score ?? 0);

const elementCount = computed(() => props.analysisData?.ui_elements?.length ?? 0);

const formattedTimestamp = computed(() => {
  if (!props.analysisData?.timestamp) return '';
  return new Date(props.analysisData.timestamp * 1000).toLocaleTimeString();
});

const elementTypesList = computed(() => {
  if (!props.analysisData?.ui_elements) return [];
  const types = new Set(props.analysisData.ui_elements.map(el => el.element_type));
  return Array.from(types).sort();
});

const filteredElements = computed(() => {
  if (!props.analysisData?.ui_elements) return [];

  return props.analysisData.ui_elements.filter(el => {
    if (typeFilter.value && el.element_type !== typeFilter.value) {
      return false;
    }
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase();
      return (
        el.element_type.toLowerCase().includes(query) ||
        el.text_content.toLowerCase().includes(query) ||
        el.element_id.toLowerCase().includes(query)
      );
    }
    return true;
  });
});

const visibleElements = computed(() => filteredElements.value);

// Methods
const handleImageLoad = () => {
  if (sourceImage.value && imageContainer.value) {
    const containerWidth = imageContainer.value.clientWidth;
    const imageWidth = sourceImage.value.naturalWidth;
    imageScale.value = containerWidth / imageWidth;
  }
};

const getOverlayStyle = (element: UIElement): Record<string, string> => {
  const scale = imageScale.value;
  return {
    left: `${element.bbox.x * scale}px`,
    top: `${element.bbox.y * scale}px`,
    width: `${element.bbox.width * scale}px`,
    height: `${element.bbox.height * scale}px`,
    borderColor: getElementColor(element.element_type),
  };
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

const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

const getTextContent = (region: TextRegion): string => {
  return region.text || '';
};

const getAutomationDescription = (opp: AutomationOpportunity): string => {
  if (opp.description) return opp.description;
  if (opp.action && opp.element_type) {
    return `${opp.action} on ${opp.element_type}`;
  }
  return `Automation on ${opp.element_id}`;
};

const selectElement = (element: UIElement) => {
  selectedElement.value = element;
};

const exportResults = () => {
  if (!props.analysisData) return;

  const dataStr = JSON.stringify(props.analysisData, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `analysis_results_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
};
</script>

<style scoped>
.analysis-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Header */
.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-info h4 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.meta-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.badge i {
  font-size: 10px;
}

.btn-export {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-export:hover {
  background: var(--bg-hover);
}

/* Image Container */
.image-container {
  position: relative;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.source-image {
  width: 100%;
  display: block;
}

.element-overlay {
  position: absolute;
  border: 2px solid;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.element-overlay:hover,
.element-overlay.selected {
  background: rgba(255, 255, 255, 0.1);
}

.overlay-label {
  position: absolute;
  top: -20px;
  left: -2px;
  padding: 2px 6px;
  font-size: 10px;
  color: white;
  border-radius: 3px 3px 0 0;
  white-space: nowrap;
}

/* Panels */
.elements-panel,
.text-panel,
.automation-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
  gap: 12px;
}

.panel-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.filter-controls {
  display: flex;
  gap: 8px;
}

.search-input {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-primary);
  width: 150px;
}

.filter-controls select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-primary);
}

/* Elements List */
.elements-list {
  max-height: 300px;
  overflow-y: auto;
}

.element-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.element-row:hover {
  background: var(--bg-tertiary);
}

.element-row.selected {
  background: var(--color-primary-bg);
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
  flex-shrink: 0;
}

.element-details {
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
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.element-position {
  font-size: 11px;
  color: var(--text-muted);
}

.element-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 80px;
  flex-shrink: 0;
}

.confidence-bar {
  height: 4px;
  background: var(--color-primary);
  border-radius: 2px;
}

.element-confidence span {
  font-size: 11px;
  color: var(--text-tertiary);
}

.no-results {
  padding: 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* Text List */
.text-list {
  max-height: 200px;
  overflow-y: auto;
}

.text-item {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-default);
}

.text-item:last-child {
  border-bottom: none;
}

.text-content {
  font-size: 13px;
  color: var(--text-primary);
}

/* Automation List */
.automation-list {
  max-height: 200px;
  overflow-y: auto;
}

.automation-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-default);
}

.automation-item:last-child {
  border-bottom: none;
}

.automation-item i {
  color: var(--color-primary);
}

.automation-item span {
  font-size: 13px;
  color: var(--text-primary);
}

/* Selected Detail */
.selected-detail {
  background: var(--bg-secondary);
  border: 1px solid var(--color-primary);
  border-radius: 12px;
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--color-primary-bg);
  border-bottom: 1px solid var(--border-default);
}

.detail-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

.btn-close {
  padding: 4px 8px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
}

.detail-content {
  padding: 16px;
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
  font-size: 13px;
  color: var(--text-primary);
}

.interactions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.interaction-badge {
  font-size: 11px;
  padding: 3px 8px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: 10px;
}
</style>
