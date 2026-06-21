<template>
  <div class="gui-automation-controls">
    <!-- Header Section -->
    <div class="automation-header">
      <div class="header-info">
        <h3>{{ t('vision.guiAutomation.title') }}</h3>
        <p>{{ t('vision.guiAutomation.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button @click="$emit('refresh')" class="btn-refresh" :disabled="loading">
          <Icon name="sync-alt" />
          {{ t('vision.guiAutomation.refresh') }}
        </button>
      </div>
    </div>

    <!-- Action Error -->
    <BaseAlert
      v-if="actionError"
      variant="error"
      :message="actionError"
      dismissible
      @dismiss="actionError = null"
    />

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      <span>{{ t('vision.guiAutomation.analyzingScreen') }}</span>
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
              <Icon :name="getTypeIcon(opportunity.element_type)" />
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
            <button @click.stop="executeAction(opportunity)" class="btn-execute" :disabled="executing">
              <i :class="executing ? 'fas fa-spinner fa-spin' : 'play'"></i>
              {{ executing ? t('vision.guiAutomation.verifying') : t('vision.guiAutomation.execute') }}
            </button>
            <button @click.stop="viewDetails(opportunity)" class="btn-details">
              <Icon name="info-circle" />
              {{ t('vision.guiAutomation.details') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <Icon name="robot" />
      </div>
      <h4>{{ t('vision.guiAutomation.noOpportunities') }}</h4>
      <p>{{ t('vision.guiAutomation.noOpportunitiesHint') }}</p>
    </div>

    <!-- Element Types Reference -->
    <div class="reference-section">
      <div class="reference-header" @click="showElementTypes = !showElementTypes">
        <h4><Icon name="cube" /> {{ t('vision.guiAutomation.elementTypesRef') }}</h4>
        <Icon :name="showElementTypes ? 'chevron-up' : 'chevron-down'" />
      </div>
      <div v-if="showElementTypes" class="reference-content">
        <div class="types-grid">
          <div
            v-for="type in elementTypesList"
            :key="type.value"
            class="type-item"
          >
            <div class="type-icon" :style="{ backgroundColor: getTypeColor(type.value) }">
              <Icon :name="getTypeIcon(type.value)" />
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
        <h4><Icon name="mouse-pointer" /> {{ t('vision.guiAutomation.interactionTypesRef') }}</h4>
        <Icon :name="showInteractionTypes ? 'chevron-up' : 'chevron-down'" />
      </div>
      <div v-if="showInteractionTypes" class="reference-content">
        <div class="interactions-grid">
          <div
            v-for="interaction in interactionTypesList"
            :key="interaction.value"
            class="interaction-item"
          >
            <Icon :name="getInteractionIcon(interaction.value)" />
            <span class="interaction-name">{{ interaction.name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedOpportunity" class="detail-overlay" @click.self="selectedOpportunity = null">
      <div class="detail-modal">
        <div class="modal-header">
          <h4>{{ t('vision.guiAutomation.automationDetails') }}</h4>
          <button @click="selectedOpportunity = null" class="btn-close">
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-content">
          <div class="detail-section">
            <label>{{ t('vision.guiAutomation.elementId') }}</label>
            <span>{{ selectedOpportunity.element_id }}</span>
          </div>
          <div class="detail-section">
            <label>{{ t('vision.guiAutomation.elementType') }}</label>
            <span>{{ selectedOpportunity.element_type }}</span>
          </div>
          <div class="detail-section">
            <label>{{ t('vision.guiAutomation.action') }}</label>
            <span>{{ selectedOpportunity.action }}</span>
          </div>
          <div class="detail-section">
            <label>{{ t('vision.guiAutomation.confidence') }}</label>
            <span>{{ (selectedOpportunity.confidence * 100).toFixed(1) }}%</span>
          </div>
          <div class="detail-section">
            <label>{{ t('vision.guiAutomation.descriptionLabel') }}</label>
            <span>{{ selectedOpportunity.description }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button @click="executeAction(selectedOpportunity)" class="btn-primary" :disabled="executing">
            <i :class="executing ? 'fas fa-spinner fa-spin' : 'play'"></i>
            {{ executing ? t('vision.guiAutomation.verifying') : t('vision.guiAutomation.executeAction') }}
          </button>
          <button @click="selectedOpportunity = null" class="btn-secondary">
            {{ t('vision.guiAutomation.close') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useNotificationBus } from '@/composables/useNotificationBus';
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
  type ElementTypeInfo,
  type InteractionTypeInfo,
} from '@/utils/VisionMultimodalApiClient';

const { t } = useI18n();
const logger = createLogger('GUIAutomationControls');
const { showToast } = useNotificationBus();

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
const actionError = ref<string | null>(null);
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

const executing = ref(false);

const executeAction = async (opportunity: AutomationOpportunity) => {
  if (executing.value) return;
  executing.value = true;
  actionError.value = null;
  try {
    const res = await visionMultimodalApiClient.detectElements({
      element_type: opportunity.element_type,
      min_confidence: opportunity.confidence * 0.8,
    });
    if (!res.success || !res.data) {
      actionError.value = t('vision.guiAutomation.toastVerifyFailed', { error: res.error || 'Unknown error' });
      return;
    }
    const found = res.data.elements?.some(
      (el: { element_id: string }) => el.element_id === opportunity.element_id
    );
    if (found) {
      showToast(
        t('vision.guiAutomation.toastElementVerified', { elementId: opportunity.element_id, action: opportunity.action }),
        'success',
      );
    } else {
      showToast(
        t('vision.guiAutomation.toastElementGone', { elementId: opportunity.element_id }),
        'warning',
      );
    }
    emit('refresh');
  } catch (err) {
    logger.error('Execute action failed:', err);
    actionError.value = t('vision.guiAutomation.toastExecutionFailed');
  } finally {
    executing.value = false;
  }
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

const getTypeIcon = (elementType: string): IconName => {
  const icons: Record<string, IconName> = {
    button: 'square',
    input: 'i-cursor',
    text: 'font',
    image: 'image',
    link: 'link',
    checkbox: 'check-square',
    dropdown: 'caret-down',
    menu: 'bars',
    // #9724: 'icons' is not an SVG IconName (rendered empty)
    icon: 'th-large',
    window: 'window-maximize',
  };
  return icons[elementType.toLowerCase()] || 'cube';
};

// #9724: hand-pointer/hand-point-right/arrows-alt-v/arrows-alt/hand-point-up
// are not SVG IconNames (rendered empty) — mapped to registry icons.
const getInteractionIcon = (interactionType: string): IconName => {
  const icons: Record<string, IconName> = {
    click: 'mouse-pointer',
    double_click: 'mouse-pointer',
    right_click: 'mouse-pointer',
    type: 'keyboard',
    scroll: 'sort',
    hover: 'hand-paper',
    drag: 'expand-arrows-alt',
    select: 'check',
  };
  return icons[interactionType.toLowerCase()] || 'hand-paper';
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
  gap: var(--spacing-5);
}

/* Header Section */
.automation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.header-info h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.header-info p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.btn-refresh {
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
  transition: all var(--duration-200);
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
  gap: var(--spacing-3);
  padding: 60px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  color: var(--text-tertiary);
}

/* Opportunities Section */
.opportunities-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.opportunities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-4);
}

.opportunity-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-4);
  cursor: pointer;
  transition: all var(--duration-200);
}

.opportunity-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-3);
}

.element-type-badge {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: var(--text-base);
}

.card-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.action-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.element-type {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.confidence-badge {
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-xl);
  font-size: var(--text-xs);
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
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-3);
  line-height: 1.4;
}

.card-actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn-execute,
.btn-details {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
  transition: all var(--duration-200);
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
  gap: var(--spacing-4);
  padding: 60px 20px;
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

.empty-state h4 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.empty-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Reference Sections */
.reference-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.reference-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  cursor: pointer;
  transition: background var(--duration-200);
}

.reference-header:hover {
  background: var(--bg-tertiary);
}

.reference-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.reference-header i:last-child {
  color: var(--text-tertiary);
}

.reference-content {
  padding: var(--spacing-0) var(--spacing-5) var(--spacing-5);
}

.types-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--spacing-3);
}

.type-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.type-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: var(--text-sm);
}

.type-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.type-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.type-desc {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.interactions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--spacing-2-5);
}

.interaction-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.interaction-item i {
  color: var(--color-primary);
}

.interaction-name {
  font-size: var(--text-sm);
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
  z-index: var(--z-modal);
}

.detail-modal {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 480px;
  overflow: hidden;
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
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-section label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-section span {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.modal-actions {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  flex: 1;
  padding: var(--spacing-3);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: var(--spacing-3) var(--spacing-5);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}
</style>
