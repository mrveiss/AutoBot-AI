<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Bulk Actions Toolbar Component (Issue #747)
 *
 * Provides bulk operations for selected knowledge entries:
 * - Selection controls (select all page, select all matching, clear)
 * - Export options (JSON, Markdown, CSV)
 * - Category change
 * - Tag management (add/remove)
 * - Bulk delete
 */

import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()

const logger = createLogger('BulkActionsToolbar')

// =============================================================================
// Type Definitions
// =============================================================================

export type ExportFormat = 'json' | 'markdown' | 'csv'

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  selectedCount: number
  totalCount: number
  pageCount: number
  allPageSelected: boolean
  allMatchingSelected: boolean
}>()

const emit = defineEmits<{
  (e: 'selectAllPage'): void
  (e: 'selectAllMatching'): void
  (e: 'clearSelection'): void
  (e: 'export', format: ExportFormat): void
  (e: 'changeCategory'): void
  (e: 'addTags'): void
  (e: 'removeTags'): void
  (e: 'delete'): void
}>()

// =============================================================================
// State
// =============================================================================

const showExportMenu = ref(false)
const showMoreMenu = ref(false)

// =============================================================================
// Computed
// =============================================================================

const hasSelection = computed(() => props.selectedCount > 0)

const selectionText = computed(() => {
  if (props.selectedCount === 0) return t('knowledge.bulkActions.noneSelected')
  if (props.allMatchingSelected) return t('knowledge.bulkActions.allMatchingSelected', { count: props.totalCount })
  return t('knowledge.bulkActions.selectedOfTotal', { selected: props.selectedCount, total: props.totalCount })
})

// =============================================================================
// Methods
// =============================================================================

function handleSelectAction(): void {
  if (props.allPageSelected && !props.allMatchingSelected) {
    // If page is selected, offer to select all matching
    emit('selectAllMatching')
  } else if (!props.allPageSelected) {
    emit('selectAllPage')
  } else {
    emit('clearSelection')
  }
}

function handleExport(format: ExportFormat): void {
  emit('export', format)
  showExportMenu.value = false
}

function toggleExportMenu(): void {
  showExportMenu.value = !showExportMenu.value
  showMoreMenu.value = false
}

function toggleMoreMenu(): void {
  showMoreMenu.value = !showMoreMenu.value
  showExportMenu.value = false
}

function closeMenus(): void {
  showExportMenu.value = false
  showMoreMenu.value = false
}

// Close menus when clicking outside
function handleClickOutside(event: MouseEvent): void {
  const target = event.target as HTMLElement
  if (!target.closest('.dropdown-container')) {
    closeMenus()
  }
}
</script>

<template>
  <div
    class="bulk-actions-toolbar"
    :class="{ 'has-selection': hasSelection }"
    @click.capture="handleClickOutside"
  >
    <!-- Selection Info & Controls -->
    <div class="selection-section">
      <div class="selection-checkbox">
        <input
          type="checkbox"
          :checked="allPageSelected"
          :indeterminate="selectedCount > 0 && !allPageSelected"
          @change="handleSelectAction"
        />
      </div>

      <span class="selection-text">{{ selectionText }}</span>

      <template v-if="hasSelection">
        <button
          v-if="allPageSelected && !allMatchingSelected && totalCount > pageCount"
          class="select-all-btn"
          @click="emit('selectAllMatching')"
        >
          {{ $t('knowledge.bulkActions.selectAllMatching', { count: totalCount }) }}
        </button>
        <button class="clear-btn" @click="emit('clearSelection')">
          {{ $t('knowledge.bulkActions.clear') }}
        </button>
      </template>
    </div>

    <!-- Bulk Actions -->
    <Transition name="fade">
      <div v-if="hasSelection" class="actions-section">
        <!-- Export Dropdown -->
        <div class="dropdown-container">
          <BaseButton
            variant="outline"
            size="sm"
            @click="toggleExportMenu"
            class="action-btn"
          >
            <i class="fas fa-download"></i>
            {{ $t('knowledge.bulkActions.export') }}
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </BaseButton>

          <Transition name="dropdown">
            <div v-if="showExportMenu" class="dropdown-menu">
              <button class="dropdown-item" @click="handleExport('json')">
                <i class="fas fa-file-code"></i>
                {{ $t('knowledge.bulkActions.exportAsJson') }}
              </button>
              <button class="dropdown-item" @click="handleExport('markdown')">
                <i class="fas fa-file-alt"></i>
                {{ $t('knowledge.bulkActions.exportAsMarkdown') }}
              </button>
              <button class="dropdown-item" @click="handleExport('csv')">
                <i class="fas fa-file-csv"></i>
                {{ $t('knowledge.bulkActions.exportAsCsv') }}
              </button>
            </div>
          </Transition>
        </div>

        <!-- Category Change -->
        <BaseButton
          variant="outline"
          size="sm"
          @click="emit('changeCategory')"
          class="action-btn"
        >
          <i class="fas fa-folder"></i>
          {{ $t('knowledge.bulkActions.changeCategory') }}
        </BaseButton>

        <!-- More Actions Dropdown -->
        <div class="dropdown-container">
          <BaseButton
            variant="outline"
            size="sm"
            @click="toggleMoreMenu"
            class="action-btn"
          >
            <i class="fas fa-tags"></i>
            {{ $t('knowledge.bulkActions.tags') }}
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </BaseButton>

          <Transition name="dropdown">
            <div v-if="showMoreMenu" class="dropdown-menu">
              <button class="dropdown-item" @click="emit('addTags'); showMoreMenu = false">
                <i class="fas fa-plus"></i>
                {{ $t('knowledge.bulkActions.addTags') }}
              </button>
              <button class="dropdown-item" @click="emit('removeTags'); showMoreMenu = false">
                <i class="fas fa-minus"></i>
                {{ $t('knowledge.bulkActions.removeTags') }}
              </button>
            </div>
          </Transition>
        </div>

        <!-- Delete Button -->
        <BaseButton
          variant="danger"
          size="sm"
          @click="emit('delete')"
          class="action-btn danger"
        >
          <i class="fas fa-trash-alt"></i>
          {{ $t('knowledge.bulkActions.delete') }}
        </BaseButton>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bulk-actions-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  transition: all var(--duration-200);
}

.bulk-actions-toolbar.has-selection {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

/* Selection Section */
.selection-section {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.selection-checkbox {
  display: flex;
  align-items: center;
}

.selection-checkbox input {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.selection-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.has-selection .selection-text {
  color: var(--color-primary);
}

.select-all-btn,
.clear-btn {
  background: none;
  border: none;
  color: var(--color-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  transition: all var(--duration-150);
}

.select-all-btn:hover,
.clear-btn:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

/* Actions Section */
.actions-section {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.action-btn.danger {
  color: var(--color-error);
  border-color: var(--color-error);
}

.action-btn.danger:hover {
  background: var(--color-error);
  color: var(--text-on-primary);
}

.dropdown-icon {
  font-size: 0.625rem;
  margin-left: var(--spacing-1);
  transition: transform var(--duration-150);
}

/* Dropdown Container */
.dropdown-container {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + var(--spacing-1));
  right: 0;
  min-width: 180px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 50;
  overflow: hidden;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-150);
}

.dropdown-item:hover {
  background: var(--bg-hover);
}

.dropdown-item i {
  width: 1rem;
  text-align: center;
  color: var(--text-secondary);
}

.dropdown-item:hover i {
  color: var(--color-primary);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-200);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: all var(--duration-150);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}

/* Responsive */
@media (max-width: 768px) {
  .bulk-actions-toolbar {
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .actions-section {
    flex-wrap: wrap;
    justify-content: center;
  }

  .dropdown-menu {
    left: 50%;
    right: auto;
    transform: translateX(-50%);
  }
}
</style>
