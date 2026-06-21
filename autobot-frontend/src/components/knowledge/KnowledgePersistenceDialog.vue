<template>
  <div v-if="visible" class="dialog-overlay" @click="closeDialog" tabindex="0" @keyup.enter="($event.target as HTMLElement | null)?.click()" @keyup.space="($event.target as HTMLElement | null)?.click()">
    <div class="knowledge-dialog" @click.stop tabindex="0" @keyup.enter="($event.target as HTMLElement | null)?.click()" @keyup.space="($event.target as HTMLElement | null)?.click()">
      <!-- Header -->
      <div class="dialog-header">
        <h3 class="dialog-title">{{ $t('knowledge.persistence.title') }}</h3>
        <BaseButton
          variant="ghost"
          size="sm"
          @click="closeDialog"
          class="close-button"
          :aria-label="$t('knowledge.persistence.closeDialog')"
        >
          ×
        </BaseButton>
      </div>

      <!-- Load Error -->
      <BaseAlert v-if="loadError" variant="error" :message="loadError" dismissible @dismiss="loadError = null" class="dialog-load-error" />

      <!-- Chat Context Info -->
      <div v-if="chatContext" class="context-info">
        <div class="context-topic">
          <span class="label">{{ $t('knowledge.persistence.topicLabel') }}</span>
          <span class="value">{{ chatContext.topic || $t('knowledge.persistence.defaultTopic') }}</span>
        </div>
        <div class="context-keywords" v-if="chatContext.keywords?.length">
          <span class="label">{{ $t('knowledge.persistence.keywordsLabel') }}</span>
          <div class="keywords-list">
            <span v-for="keyword in chatContext.keywords" :key="keyword" class="keyword-tag">
              {{ keyword }}
            </span>
          </div>
        </div>
        <div class="context-stats">
          <div class="stat">
            <span class="stat-value">{{ pendingItems.length }}</span>
            <span class="stat-label">{{ $t('knowledge.persistence.knowledgeItems') }}</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ chatContext.file_count || 0 }}</span>
            <span class="stat-label">{{ $t('knowledge.persistence.associatedFiles') }}</span>
          </div>
        </div>
      </div>

      <!-- Pending Knowledge Items -->
      <div class="knowledge-items">
        <h4 class="section-title">{{ $t('knowledge.persistence.reviewTitle') }}</h4>
        <div class="items-list">
          <div
            v-for="item in pendingItems"
            :key="item.id"
            class="knowledge-item"
            :class="{ 'selected': isSelected(item) }"
          >
            <div class="item-header">
              <div class="item-selection">
                <input
                  type="checkbox"
                  :id="`item-${item.id}`"
                  :checked="isSelected(item)"
                  @change="handleItemToggle(item)"
                >
                <label :for="`item-${item.id}`" class="item-preview">
                  {{ truncateContent(item.content, 100) }}
                </label>
              </div>
              <div class="item-suggestion" :class="item.suggested_action">
                {{ getSuggestionText(item.suggested_action) }}
              </div>
            </div>

            <div v-if="isSelected(item)" class="item-details">
              <div class="content-preview">
                <pre>{{ item.content }}</pre>
              </div>

              <div class="decision-options">
                <label class="decision-option">
                  <input
                    type="radio"
                    :name="`decision-${item.id}`"
                    value="add_to_kb"
                    v-model="itemDecisions[item.id]"
                  >
                  <span class="option-label">
                    <span class="option-icon">💾</span>
                    {{ $t('knowledge.persistence.addToKbLabel') }}
                  </span>
                  <span class="option-description">
                    {{ $t('knowledge.persistence.addToKbDescription') }}
                  </span>
                </label>

                <label class="decision-option">
                  <input
                    type="radio"
                    :name="`decision-${item.id}`"
                    value="keep_temporary"
                    v-model="itemDecisions[item.id]"
                  >
                  <span class="option-label">
                    <span class="option-icon">⏰</span>
                    {{ $t('knowledge.persistence.keepTemporaryLabel') }}
                  </span>
                  <span class="option-description">
                    {{ $t('knowledge.persistence.keepTemporaryDescription') }}
                  </span>
                </label>

                <label class="decision-option">
                  <input
                    type="radio"
                    :name="`decision-${item.id}`"
                    value="delete"
                    v-model="itemDecisions[item.id]"
                  >
                  <span class="option-label">
                    <span class="option-icon">🗑️</span>
                    {{ $t('knowledge.persistence.deleteLabel') }}
                  </span>
                  <span class="option-description">
                    {{ $t('knowledge.persistence.deleteDescription') }}
                  </span>
                </label>
              </div>

              <div class="item-metadata" v-if="item.metadata">
                <span class="metadata-label">{{ $t('knowledge.persistence.createdLabel') }}</span>
                <span class="metadata-value">{{ formatDate(item.created_at) }}</span>
                <span v-if="item.metadata.source" class="metadata-label">{{ $t('knowledge.persistence.sourceLabel') }}</span>
                <span v-if="item.metadata.source" class="metadata-value">{{ item.metadata.source }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bulk Actions -->
      <div class="bulk-actions" v-if="pendingItems.length > 1">
        <h4 class="section-title">{{ $t('knowledge.persistence.bulkActionsTitle') }}</h4>
        <div class="bulk-buttons">
          <BaseButton
            variant="outline-solid"
            @click="selectAll"
            class="bulk-button"
            :aria-label="$t('knowledge.persistence.selectAllAria')"
          >
            {{ $t('knowledge.persistence.selectAll') }}
          </BaseButton>
          <BaseButton
            variant="outline-solid"
            @click="deselectAll"
            class="bulk-button"
            :aria-label="$t('knowledge.persistence.deselectAllAria')"
          >
            {{ $t('knowledge.persistence.deselectAll') }}
          </BaseButton>
          <BaseButton
            variant="success"
            @click="applyBulkDecision('add_to_kb')"
            :disabled="!hasSelectedItems"
            class="bulk-button add"
            :aria-label="$t('knowledge.persistence.addSelectedToKbAria')"
          >
            {{ $t('knowledge.persistence.addSelectedToKb') }}
          </BaseButton>
          <BaseButton
            variant="warning"
            @click="applyBulkDecision('keep_temporary')"
            :disabled="!hasSelectedItems"
            class="bulk-button temp"
            :aria-label="$t('knowledge.persistence.keepSelectedTemporarilyAria')"
          >
            {{ $t('knowledge.persistence.keepSelectedTemporarily') }}
          </BaseButton>
          <BaseButton
            variant="error"
            @click="applyBulkDecision('delete')"
            :disabled="!hasSelectedItems"
            class="bulk-button delete"
            :aria-label="$t('knowledge.persistence.deleteSelectedAria')"
          >
            {{ $t('knowledge.persistence.deleteSelected') }}
          </BaseButton>
        </div>
      </div>

      <!-- Compile Chat Option -->
      <div class="compile-section">
        <h4 class="section-title">{{ $t('knowledge.persistence.compileTitle') }}</h4>
        <div class="compile-description">
          {{ $t('knowledge.persistence.compileDescription') }}
        </div>
        <div class="compile-options">
          <label class="compile-option">
            <input type="checkbox" v-model="compileOptions.includeSystemMessages">
            {{ $t('knowledge.persistence.includeSystemMessages') }}
          </label>
          <div class="compile-title">
            <label>{{ $t('knowledge.persistence.compileTitleLabel') }}</label>
            <input
              type="text"
              v-model="compileOptions.title"
              :placeholder="$t('knowledge.persistence.compileTitlePlaceholder')"
              class="title-input"
            >
          </div>
        </div>
        <BaseButton
          variant="primary"
          @click="compileChat"
          class="compile-button"
          :aria-label="$t('knowledge.persistence.compileChatAria')"
        >
          {{ $t('knowledge.persistence.compileButton') }}
        </BaseButton>
      </div>

      <!-- Submit Error -->
      <BaseAlert
        v-if="submitError"
        variant="error"
        :message="submitError"
        dismissible
        @dismiss="submitError = null"
      />

      <!-- Dialog Actions -->
      <div class="dialog-actions">
        <div class="action-summary">
          <span v-if="decisionsCount.add_to_kb > 0" class="summary-item add">
            {{ $t('knowledge.persistence.toKbCount', { count: decisionsCount.add_to_kb }) }}
          </span>
          <span v-if="decisionsCount.keep_temporary > 0" class="summary-item temp">
            {{ $t('knowledge.persistence.temporaryCount', { count: decisionsCount.keep_temporary }) }}
          </span>
          <span v-if="decisionsCount.delete > 0" class="summary-item delete">
            {{ $t('knowledge.persistence.toDeleteCount', { count: decisionsCount.delete }) }}
          </span>
        </div>

        <div class="action-buttons">
          <BaseButton
            variant="success"
            @click="applyAllDecisions"
            :disabled="!hasDecisions"
            class="primary-button"
            :aria-label="$t('knowledge.persistence.applyDecisionsAria')"
          >
            {{ $t('knowledge.persistence.applyDecisions') }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="closeDialog"
            class="secondary-button"
            :aria-label="$t('knowledge.persistence.cancelAria')"
          >
            {{ $t('knowledge.persistence.cancel') }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useNotificationBus } from '@/composables/useNotificationBus';
import { useBatchSelection } from '@/composables/useBatchSelection';
import { apiService } from '@/services/api';
import { getApiBase } from '@/config/ssot-config';
import { formatDateTime as formatDate } from '@/utils/formatHelpers';
import BaseButton from '@/components/base/BaseButton.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';
import { createLogger } from '@/utils/debugUtils';

type KnowledgeDecision = 'add_to_kb' | 'keep_temporary' | 'delete';

interface PendingKnowledgeItem {
  id: string;
  content: string;
  suggested_action: KnowledgeDecision;
  created_at: string;
  metadata?: {
    source?: string;
    [key: string]: unknown;
  };
}

interface ChatContext {
  topic?: string;
  keywords?: string[];
  file_count?: number;
}

interface Props {
  visible?: boolean;
  chatId?: string | null;
  chatContext?: ChatContext | null;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  chatId: null,
  chatContext: null,
});

const emit = defineEmits<{
  close: [];
  'decisions-applied': [decisions: Array<{ chat_id: string; knowledge_id: string; decision: KnowledgeDecision }>];
  'chat-compiled': [compiled: unknown];
}>();

const logger = createLogger('KnowledgePersistenceDialog');

const { t } = useI18n();
const { showToast } = useNotificationBus();

const pendingItems = ref<PendingKnowledgeItem[]>([]);
const itemDecisions = ref<Record<string, KnowledgeDecision>>({});

const {
  isSelected,
  toggle: toggleItemSelection,
  selectAll,
  clear: deselectAllItems,
  selectedItems: selectedPendingItems,
  selectedCount,
  selected: selectedKeys,
} = useBatchSelection<PendingKnowledgeItem, string>(pendingItems, item => item.id);

// someSelected is false when ALL items are selected — use selectedCount > 0 so
// bulk-action buttons remain enabled when the user selects all (GH#8395).
const hasSelectedItems = computed(() => selectedCount.value > 0);

const compileOptions = ref({
  includeSystemMessages: false,
  title: '',
});
const loading = ref(false);
const submitError = ref<string | null>(null);
const loadError = ref<string | null>(null);

const hasDecisions = computed(() => Object.keys(itemDecisions.value).length > 0);

const decisionsCount = computed(() => {
  const counts: Record<KnowledgeDecision, number> = {
    add_to_kb: 0,
    keep_temporary: 0,
    delete: 0,
  };

  const selectedIds = new Set(selectedPendingItems.value.map((item: PendingKnowledgeItem) => item.id));
  (Object.entries(itemDecisions.value) as [string, KnowledgeDecision][]).forEach(([itemId, decision]) => {
    if (selectedIds.has(itemId) && decision) {
      counts[decision]++;
    }
  });
  return counts;
});

const loadPendingItems = async (): Promise<void> => {
  try {
    loading.value = true;
    loadError.value = null;
    // Issue #552: Fixed path to match backend (hyphen instead of underscore)
    const response = await apiService.get(`${getApiBase()}/chat-knowledge/knowledge/pending/${props.chatId}`) as { success: boolean; pending_items: PendingKnowledgeItem[] };

    if (response.success) {
      pendingItems.value = response.pending_items ?? [];

      // Initialize decisions (useBatchSelection handles selection state)
      pendingItems.value.forEach((item: PendingKnowledgeItem) => {
        itemDecisions.value[item.id] = item.suggested_action || 'keep_temporary';
      });
    }
  } catch (error) {
    logger.error('Failed to load pending knowledge:', error);
    loadError.value = error instanceof Error ? error.message : t('knowledge.persistence.failedToLoad');
  } finally {
    loading.value = false;
  }
};

const truncateContent = (content: string, maxLength: number): string => {
  if (content.length <= maxLength) return content;
  return content.substring(0, maxLength) + '...';
};

const getSuggestionText = (action: KnowledgeDecision): string => {
  const suggestions: Record<KnowledgeDecision, string> = {
    'add_to_kb': t('knowledge.persistence.suggestionAddToKb'),
    'keep_temporary': t('knowledge.persistence.suggestionKeepTemporary'),
    'delete': t('knowledge.persistence.suggestionDelete'),
  };
  return suggestions[action] || '';
};

const handleItemToggle = (item: PendingKnowledgeItem): void => {
  const wasSelected = isSelected(item);
  toggleItemSelection(item);
  if (wasSelected) {
    delete itemDecisions.value[item.id];
  }
};

const deselectAll = (): void => {
  deselectAllItems();
  itemDecisions.value = {};
};

const applyBulkDecision = (decision: KnowledgeDecision): void => {
  selectedPendingItems.value.forEach((item: PendingKnowledgeItem) => {
    itemDecisions.value[item.id] = decision;
  });
};

const applyAllDecisions = async (): Promise<void> => {
  try {
    loading.value = true;
    const decisions: Array<{ chat_id: string; knowledge_id: string; decision: KnowledgeDecision }> =
      selectedPendingItems.value
        .filter((item: PendingKnowledgeItem) => itemDecisions.value[item.id])
        .map((item: PendingKnowledgeItem) => ({
          chat_id: props.chatId as string,
          knowledge_id: item.id,
          decision: itemDecisions.value[item.id],
        }));

    // Apply decisions in parallel - eliminates N+1 sequential API calls
    // Issue #552: Fixed path to match backend (hyphen instead of underscore)
    await Promise.all(
      decisions.map(decision =>
        apiService.post(`${getApiBase()}/chat-knowledge/knowledge/decide`, decision)
      )
    );

    showToast(t('knowledge.persistence.decisionsApplied', { count: decisions.length }), 'success');
    submitError.value = null;
    emit('decisions-applied', decisions);
    closeDialog();
  } catch (error) {
    logger.error('Failed to apply decisions:', error);
    submitError.value = t('knowledge.persistence.decisionsApplyFailed');
  } finally {
    loading.value = false;
  }
};

const compileChat = async (): Promise<void> => {
  try {
    loading.value = true;

    // Issue #552: Fixed path to match backend (hyphen instead of underscore)
    const response = await apiService.post(`${getApiBase()}/chat-knowledge/compile`, {
      chat_id: props.chatId,
      title: compileOptions.value.title || null,
      include_system_messages: compileOptions.value.includeSystemMessages,
    }) as { success: boolean; compiled: unknown };

    if (response.success) {
      showToast(t('knowledge.persistence.compiledSuccess'), 'success');
      submitError.value = null;
      emit('chat-compiled', response.compiled);
      closeDialog();
    }
  } catch (error) {
    logger.error('Failed to compile chat:', error);
    submitError.value = t('knowledge.persistence.compileFailed');
  } finally {
    loading.value = false;
  }
};

const closeDialog = (): void => {
  emit('close');
};

onMounted(() => {
  if (props.visible && props.chatId) {
    loadPendingItems();
  }
});

watch(() => props.visible, (newVal: boolean) => {
  if (newVal && props.chatId) {
    loadPendingItems();
  }
});
</script>

<style scoped>
/**
 * KnowledgePersistenceDialog - Design Token Migration
 * Issue #704: Migrated hardcoded colors to CSS design tokens
 */

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-backdrop);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: var(--z-modal);
  backdrop-filter: blur(4px);
}

.knowledge-dialog {
  background: var(--bg-surface);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-xl);
  max-width: 900px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--color-info);
}

.dialog-title {
  margin: var(--spacing-0);
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
}

/* Button styling handled by BaseButton component */

.context-info {
  padding: var(--spacing-5);
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-default);
}

.context-topic,
.context-keywords {
  margin-bottom: var(--spacing-3);
}

.label {
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin-right: var(--spacing-2);
}

.value {
  color: var(--text-primary);
}

.keywords-list {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
}

.keyword-tag {
  background: var(--color-info);
  color: var(--text-on-primary);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
}

.context-stats {
  display: flex;
  gap: var(--spacing-8);
  margin-top: var(--spacing-4);
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--color-info);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.knowledge-items {
  padding: var(--spacing-5);
}

.section-title {
  margin: 0 0 var(--spacing-4) 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.items-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.knowledge-item {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  transition: var(--transition-all);
}

.knowledge-item.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
}

.item-selection {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  flex: 1;
}

.item-selection input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.item-preview {
  cursor: pointer;
  font-size: var(--text-base);
  flex: 1;
}

.item-suggestion {
  font-size: var(--text-sm);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.item-suggestion.add_to_kb {
  background: var(--color-success-bg);
  color: var(--chart-green);
}

.item-suggestion.keep_temporary {
  background: var(--color-warning-bg);
  color: var(--color-warning-light);
}

.item-suggestion.delete {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.item-details {
  padding: 0 var(--spacing-4) var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.content-preview {
  margin: var(--spacing-4) 0;
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
}

.content-preview pre {
  margin: var(--spacing-0);
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.decision-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin: var(--spacing-4) 0;
}

.decision-option {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-all);
}

.decision-option:hover {
  border-color: var(--border-strong);
  background: var(--bg-hover);
}

.decision-option input[type="radio"] {
  margin-right: var(--spacing-2);
}

.option-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-1);
}

.option-icon {
  font-size: var(--text-lg);
}

.option-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-left: var(--spacing-7);
}

.item-metadata {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.metadata-label {
  font-weight: var(--font-semibold);
}

.bulk-actions {
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
}

.bulk-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

/* Button styling handled by BaseButton component */

.compile-section {
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.compile-description {
  color: var(--text-secondary);
  font-size: var(--text-base);
  margin-bottom: var(--spacing-4);
}

.compile-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.compile-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.compile-title {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.compile-title label {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

.title-input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-md);
  font-family: inherit;
}

.title-input:focus {
  outline: none;
  border-color: var(--color-info);
}
.title-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Button styling handled by BaseButton component */

.dialog-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
}

.action-summary {
  display: flex;
  gap: var(--spacing-4);
}

.summary-item {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.summary-item.add {
  background: var(--color-success-bg);
  color: var(--chart-green);
}

.summary-item.temp {
  background: var(--color-warning-bg);
  color: var(--color-warning-light);
}

.summary-item.delete {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-3);
}

/* Button styling handled by BaseButton component */

/* Responsive design */
@media (max-width: 768px) {
  .knowledge-dialog {
    width: 95%;
    margin: var(--spacing-2-5);
  }

  .bulk-buttons {
    flex-direction: column;
  }

  .dialog-actions {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .action-summary {
    order: 2;
  }

  .action-buttons {
    order: 1;
    width: 100%;
  }
}
</style>
