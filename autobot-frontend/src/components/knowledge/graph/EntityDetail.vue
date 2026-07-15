<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div
    class="entity-detail-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="$t('knowledge.graph.entity.ariaLabel', { name: entity.name })"
    @click.self="$emit('close')"
    @keydown.escape="$emit('close')"
  >
    <div
      ref="panelRef"
      class="entity-detail"
      tabindex="-1"
      @keydown="onFocusTrapKeydown"
    >
      <!-- Header -->
      <div class="detail-header">
        <div class="header-left">
          <span
            class="type-indicator"
            :style="{ backgroundColor: getTypeColor(entity.type) }"
          />
          <h4>{{ entity.name }}</h4>
          <span
            class="type-badge"
            :style="{
              backgroundColor: getTypeColor(entity.type),
              color: 'white',
            }"
          >
            {{ entity.type }}
          </span>
        </div>
        <button
          class="close-btn"
          :aria-label="$t('knowledge.graph.entity.closeAriaLabel')"
          @click="$emit('close')"
        >
          <Icon name="times" />
        </button>
      </div>

      <!-- Confidence -->
      <div class="confidence-bar">
        <span class="confidence-label">{{ $t('knowledge.graph.entity.confidence') }}</span>
        <div class="confidence-track">
          <div
            class="confidence-fill"
            :style="{ width: `${entity.confidence * 100}%` }"
          />
        </div>
        <span class="confidence-value">
          {{ (entity.confidence * 100).toFixed(0) }}%
        </span>
      </div>

      <!-- Description -->
      <div class="detail-section">
        <h5><Icon name="list" /> {{ $t('knowledge.graph.entity.description') }}</h5>
        <p class="description-text">
          {{ entity.description || $t('knowledge.graph.entity.noDescription') }}
        </p>
      </div>

      <!-- Properties Table -->
      <div
        v-if="propertyEntries.length > 0"
        class="detail-section"
      >
        <h5><Icon name="list" /> {{ $t('knowledge.graph.entity.properties') }}</h5>
        <table class="properties-table">
          <tbody>
            <tr
              v-for="[key, value] in propertyEntries"
              :key="key"
            >
              <td class="prop-key">{{ key }}</td>
              <td class="prop-value">{{ formatValue(value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Relationships -->
      <RelationshipViewer :entity-id="entity.id" />

      <!-- Source Documents -->
      <div
        v-if="entity.source_document_ids.length > 0"
        class="detail-section"
      >
        <h5>
          <Icon name="file-alt" />
          {{ $t('knowledge.graph.entity.sourceDocuments', { count: entity.source_document_ids.length }) }}
        </h5>
        <div class="source-list">
          <span
            v-for="docId in entity.source_document_ids"
            :key="docId"
            class="source-badge"
          >
            {{ docId }}
          </span>
        </div>
      </div>

      <!-- Actions -->
      <div class="detail-actions">
        <button
          class="action-btn"
          @click="$emit('view-timeline', entity.name)"
        >
          <Icon name="clock" />
          {{ $t('knowledge.graph.entity.viewTimeline') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import Icon from '@/components/ui/Icon.vue'
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import {
  type Entity,
} from '@/composables/useKnowledgeGraph'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'
import { getEntityTypeColor as getTypeColor } from '../constants'
import RelationshipViewer from './RelationshipViewer.vue'

const props = defineProps<{
  entity: Entity
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'view-timeline', entityName: string): void
}>()

const panelRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(panelRef)
useFocusRestore()
// Mount-lifecycle = always-active. Component is v-if'd by parent on open/close.
useBodyScrollLock(ref(true))
const { focusFirst } = useInitialFocus(panelRef)

const propertyEntries = computed(() => {
  return Object.entries(props.entity.properties || {})
})

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

onMounted(focusFirst)
</script>

<style scoped>
.entity-detail-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-end;
  z-index: var(--z-modal-backdrop);
}

.entity-detail {
  width: 480px;
  max-width: 100%;
  height: 100%;
  background: var(--bg-primary);
  overflow-y: auto;
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  box-shadow: var(--shadow-lg);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  min-width: 0;
}

.type-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.detail-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin: var(--spacing-0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-xs);
  font-size: var(--text-lg);
}

.close-btn:hover {
  color: var(--text-primary);
}

/* Confidence */
.confidence-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.confidence-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.confidence-track {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.confidence-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-full);
  transition: width var(--duration-300);
}

.confidence-value {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  flex-shrink: 0;
}

/* Sections */
.detail-section {
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}

.detail-section h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.detail-section h5 i {
  color: var(--color-primary);
  font-size: var(--text-xs);
}

.section-loading {
  color: var(--text-tertiary);
}

.section-error {
  font-size: var(--text-sm);
  color: var(--color-error);
  padding: var(--spacing-sm);
  background: var(--color-error-bg);
  border-radius: var(--radius-md);
}

.description-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: var(--spacing-0);
}

/* Properties */
.properties-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.properties-table td {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: 1px solid var(--border-subtle);
}

.prop-key {
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  width: 40%;
}

.prop-value {
  color: var(--text-primary);
  word-break: break-word;
}

/* Source Documents */
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.source-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-family: 'Fira Code', monospace;
}

/* Actions */
.detail-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: auto;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

@media (max-width: 768px) {
  .entity-detail {
    width: 100%;
  }

  .detail-actions {
    flex-direction: column;
  }
}
</style>
