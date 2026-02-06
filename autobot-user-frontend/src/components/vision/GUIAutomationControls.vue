<template>
  <div class="gui-automation-controls">
    <!-- Header Section -->
    <div class="automation-header">
      <div class="header-info">
        <h3>GUI Automation Opportunities</h3>
        <p>Discover and interact with UI elements on the current screen</p>
      </div>
      <div class="header-actions">
        <button @click="$emit('refresh')" class="btn-refresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Analyzing screen for automation opportunities...</span>
    </div>

    <!-- Opportunities List -->
    <div v-else-if="opportunities.length > 0" class="opportunities-section">
      <div class="opportunities-grid">
        <div
          v-for="opportunity in opportunities"
          :key="opportunity.element_id"
          class="opportunity-card"
          @click="selectOpportunity(opportunity)"
        >
          <div class="card-header">
            <div class="element-type-badge" :style="{ backgroundColor: getTypeColor(opportunity.element_type) }">
              <i :class="getTypeIcon(opportunity.element_type)"></i>
            </div>
            <div class="card-info">
              <span class="action-name">{{ opportunity.action }}</span>
              <span class="element-type">{{ opportunity.element_type }}</span>
            </div>
            <div class="confidence-badge" :class="getConfidenceClass(opportunity.confidence)">
              {{ (opportunity.confidence * 100).toFixed(0) }}%
            </div>
          </div>
          <div class="card-description">
            {{ opportunity.description }}
          </div>
          <div class="card-actions">
            <button @click.stop="executeAction(opportunity)" class="btn-execute">
              <i class="fas fa-play"></i>
              Execute
            </button>
            <button @click.stop="viewDetails(opportunity)" class="btn-details">
              <i class="fas fa-info-circle"></i>
              Details
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-robot"></i>
      </div>
      <h4>No Automation Opportunities Found</h4>
      <p>Click "Refresh" to analyze the current screen for interactive elements</p>
    </div>

    <!-- Element Types Reference -->
    <div class="reference-section">
      <div class="reference-header" @click="showElementTypes = !showElementTypes">
        <h4><i class="fas fa-cube"></i> Element Types Reference</h4>
        <i :class="showElementTypes ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
      </div>
      <div v-if="showElementTypes" class="reference-content">
        <div class="types-grid">
          <div
            v-for="type in elementTypesList"
            :key="type.value"
            class="type-item"
          >
            <div class="type-icon" :style="{ backgroundColor: getTypeColor(type.value) }">
              <i :class="getTypeIcon(type.value)"></i>
            </div>
            <div class="type-info">
              <span class="type-name">{{ type.name }}</span>
              <span class="type-desc">{{ type.description }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Interaction Types Reference -->
    <div class="reference-section">
      <div class="reference-header" @click="showInteractionTypes = !showInteractionTypes">
        <h4><i class="fas fa-mouse-pointer"></i> Interaction Types Reference</h4>
        <i :class="showInteractionTypes ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
      </div>
      <div v-if="showInteractionTypes" class="reference-content">
        <div class="interactions-grid">
          <div
            v-for="interaction in interactionTypesList"
            :key="interaction.value"
            class="interaction-item"
          >
            <i :class="getInteractionIcon(interaction.value)"></i>
            <span class="interaction-name">{{ interaction.name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedOpportunity" class="detail-overlay" @click.self="selectedOpportunity = null">
      <div class="detail-modal">
        <div class="modal-header">
          <h4>Automation Details</h4>
          <button @click="selectedOpportunity = null" class="btn-close">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-content">
          <div class="detail-section">
            <label>Element ID</label>
            <span>{{ selectedOpportunity.element_id }}</span>
          </div>
          <div class="detail-section">
            <label>Element Type</label>
            <span>{{ selectedOpportunity.element_type }}</span>
          </div>
          <div class="detail-section">
            <label>Action</label>
            <span>{{ selectedOpportunity.action }}</span>
          </div>
          <div class="detail-section">
            <label>Confidence</label>
            <span>{{ (selectedOpportunity.confidence * 100).toFixed(1) }}%</span>
          </div>
          <div class="detail-section">
            <label>Description</label>
            <span>{{ selectedOpportunity.description }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button @click="executeAction(selectedOpportunity)" class="btn-primary">
            <i class="fas fa-play"></i>
            Execute Action
          </button>
          <button @click="selectedOpportunity = null" class="btn-secondary">
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
  type ElementTypeInfo,
  type InteractionTypeInfo,
} from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('GUIAutomationControls');
const { showToast } = useToast();

// Props
const props = defineProps<{
  opportunities: AutomationOpportunity[];
  loading: boolean;
}>();

// Emits
const emit = defineEmits<{
  (e: 'refresh'): void;
}>();

// State
const selectedOpportunity = ref<AutomationOpportunity | null>(null);
const showElementTypes = ref(false);
const showInteractionTypes = ref(false);
const elementTypesList = ref<ElementTypeInfo[]>([]);
const interactionTypesList = ref<InteractionTypeInfo[]>([]);

// Methods
const loadReferenceData = async () => {
  try {
    const [elementsRes, interactionsRes] = await Promise.all([
      visionMultimodalApiClient.getElementTypes(),
      visionMultimodalApiClient.getInteractionTypes(),
    ]);

    if (elementsRes.success && elementsRes.data) {
      elementTypesList.value = elementsRes.data.element_types;
    }
    if (interactionsRes.success && interactionsRes.data) {
      interactionTypesList.value = interactionsRes.data.interaction_types;
    }
  } catch (err) {
    logger.error('Failed to load reference data:', err);
  }
};

const selectOpportunity = (opportunity: AutomationOpportunity) => {
  selectedOpportunity.value = opportunity;
};

const viewDetails = (opportunity: AutomationOpportunity) => {
  selectedOpportunity.value = opportunity;
};

const executeAction = (opportunity: AutomationOpportunity) => {
  // TODO: Implement actual action execution via backend
  showToast(`Action "${opportunity.action}" would be executed on element ${opportunity.element_id}`, 'info');
  logger.debug('Execute action:', opportunity);
};

const getTypeColor = (elementType: string): string => {
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

const getTypeIcon = (elementType: string): string => {
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

const getInteractionIcon = (interactionType: string): string => {
  const icons: Record<string, string> = {
    click: 'fas fa-mouse-pointer',
    double_click: 'fas fa-hand-pointer',
    right_click: 'fas fa-hand-point-right',
    type: 'fas fa-keyboard',
    scroll: 'fas fa-arrows-alt-v',
    hover: 'fas fa-hand-paper',
    drag: 'fas fa-arrows-alt',
    select: 'fas fa-check',
  };
  return icons[interactionType.toLowerCase()] || 'fas fa-hand-point-up';
};

const getConfidenceClass = (confidence: number): string => {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.5) return 'medium';
  return 'low';
};

// Lifecycle
onMounted(() => {
  loadReferenceData();
});
</script>

<style scoped>
.gui-automation-controls {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Header Section */
.automation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.header-info h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-info p {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.btn-refresh {
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

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  color: var(--text-tertiary);
}

/* Opportunities Section */
.opportunities-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.opportunities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.opportunity-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.opportunity-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.element-type-badge {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 16px;
}

.card-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.element-type {
  font-size: 12px;
  color: var(--text-tertiary);
}

.confidence-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.confidence-badge.high {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.confidence-badge.medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.confidence-badge.low {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.card-description {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  line-height: 1.4;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.btn-execute,
.btn-details {
  flex: 1;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-execute {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
}

.btn-execute:hover {
  background: var(--color-primary-hover);
}

.btn-details {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-details:hover {
  background: var(--bg-hover);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 60px 20px;
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

.empty-state h4 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Reference Sections */
.reference-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.reference-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  transition: background 0.2s;
}

.reference-header:hover {
  background: var(--bg-tertiary);
}

.reference-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.reference-header i:last-child {
  color: var(--text-tertiary);
}

.reference-content {
  padding: 0 20px 20px;
}

.types-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.type-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.type-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
}

.type-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.type-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.type-desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

.interactions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.interaction-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.interaction-item i {
  color: var(--color-primary);
}

.interaction-name {
  font-size: 13px;
  color: var(--text-primary);
}

/* Detail Modal */
.detail-overlay {
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

.detail-modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  overflow: hidden;
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
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-section label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-section span {
  font-size: 14px;
  color: var(--text-primary);
}

.modal-actions {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  flex: 1;
  padding: 12px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: 12px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}
</style>
