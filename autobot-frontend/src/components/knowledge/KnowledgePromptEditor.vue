<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Knowledge Prompt Editor Component (Issue #747)
 *
 * Editor for system and agent prompts.
 * Features:
 * - Categorized prompt list (System, Agents, Templates)
 * - Syntax highlighting for prompt variables
 * - Version history with diff view
 * - Test prompt capability
 * - Unsaved changes warning
 */

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgePrompt } from '@/composables/knowledge/useKnowledgePrompt'
import type { Prompt, PromptVersion } from '@/composables/knowledge/useKnowledgePrompt'

const logger = createLogger('KnowledgePromptEditor')

const { t } = useI18n()

// =============================================================================
// State
// =============================================================================

const { isLoading, isSaving, isLoadingHistory, fetchPrompts, savePrompt, fetchHistory, revertPrompt } =
  useKnowledgePrompt()
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)

// Prompts
const prompts = ref<Prompt[]>([])
const selectedPrompt = ref<Prompt | null>(null)
const editedContent = ref('')
const searchQuery = ref('')
const selectedCategory = ref<'all' | 'system' | 'agents' | 'templates'>('all')

// History modal
const showHistoryModal = ref(false)
const promptHistory = ref<PromptVersion[]>([])
const selectedVersion = ref<PromptVersion | null>(null)

// Unsaved changes tracking
const hasUnsavedChanges = computed(() => {
  if (!selectedPrompt.value) return false
  return editedContent.value !== selectedPrompt.value.content
})

// =============================================================================
// Computed
// =============================================================================

const filteredPrompts = computed(() => {
  let filtered = prompts.value

  // Filter by category
  if (selectedCategory.value !== 'all') {
    filtered = filtered.filter(p => p.category === selectedCategory.value)
  }

  // Filter by search
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.description?.toLowerCase().includes(query)
    )
  }

  return filtered
})

const groupedPrompts = computed(() => {
  const groups: Record<string, Prompt[]> = {
    system: [],
    agents: [],
    templates: []
  }

  filteredPrompts.value.forEach(prompt => {
    if (groups[prompt.category]) {
      groups[prompt.category].push(prompt)
    }
  })

  return groups
})

const detectedVariables = computed(() => {
  const matches = editedContent.value.match(/\{\{([^}]+)\}\}/g)
  if (!matches) return []
  return [...new Set(matches.map(m => m.replace(/\{\{|\}\}/g, '')))]
})

const characterCount = computed(() => editedContent.value.length)

const categoryIcons: Record<string, IconName> = {
  system: 'cog',
  agents: 'robot',
  templates: 'file-code'
}

const categoryLabels = computed<Record<string, string>>(() => ({
  system: t('knowledge.promptEditor.categorySystem'),
  agents: t('knowledge.promptEditor.categoryAgents'),
  templates: t('knowledge.promptEditor.categoryTemplates')
}))

// =============================================================================
// Methods
// =============================================================================

async function loadPrompts(): Promise<void> {
  error.value = null
  try {
    prompts.value = await fetchPrompts()
  } catch (err) {
    logger.error('Failed to load prompts:', err)
    error.value = t('knowledge.promptEditor.errorLoadPrompts')
  }
}

function selectPrompt(prompt: Prompt): void {
  if (hasUnsavedChanges.value) {
    if (!confirm(t('knowledge.promptEditor.confirmDiscardChanges'))) {
      return
    }
  }

  selectedPrompt.value = prompt
  editedContent.value = prompt.content
  error.value = null
  successMessage.value = null
}

async function handleSavePrompt(): Promise<void> {
  if (!selectedPrompt.value) return

  error.value = null
  successMessage.value = null
  try {
    const data = await savePrompt(selectedPrompt.value.id, editedContent.value)

    if (data?.status === 'success') {
      // Update local state
      selectedPrompt.value.content = editedContent.value
      selectedPrompt.value.version = (selectedPrompt.value.version || 0) + 1
      selectedPrompt.value.lastModified = new Date().toISOString()

      successMessage.value = t('knowledge.promptEditor.successSaved')
      setTimeout(() => {
        successMessage.value = null
      }, 3000)
    } else {
      error.value = (data?.message as string) || t('knowledge.promptEditor.errorSavePrompt')
    }
  } catch (err) {
    logger.error('Failed to save prompt:', err)
    error.value = t('knowledge.promptEditor.errorSavePrompt')
  }
}

function revertChanges(): void {
  if (!selectedPrompt.value) return
  editedContent.value = selectedPrompt.value.content
}

async function loadHistory(): Promise<void> {
  if (!selectedPrompt.value) return

  showHistoryModal.value = true
  promptHistory.value = await fetchHistory(selectedPrompt.value.id)
}

async function revertToVersion(version: PromptVersion): Promise<void> {
  if (!selectedPrompt.value) return

  if (!confirm(t('knowledge.promptEditor.confirmRevert', { version: version.version }))) {
    return
  }

  try {
    const data = await revertPrompt(selectedPrompt.value.id, version.version)

    if (data?.status === 'success') {
      selectedPrompt.value.content = version.content
      editedContent.value = version.content
      showHistoryModal.value = false
      successMessage.value = t('knowledge.promptEditor.successReverted')
    }
  } catch (err) {
    logger.error('Failed to revert:', err)
    error.value = t('knowledge.promptEditor.errorRevert')
  }
}

function getCategoryIcon(category: string): IconName {
  return categoryIcons[category] || 'file'
}

function formatDate(dateString?: string): string {
  if (!dateString) return t('knowledge.promptEditor.unknown')
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Warn on page leave if unsaved changes
function beforeUnloadHandler(e: BeforeUnloadEvent): void {
  if (hasUnsavedChanges.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
  loadPrompts()
  window.addEventListener('beforeunload', beforeUnloadHandler)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnloadHandler)
})
</script>

<template>
  <div class="knowledge-prompt-editor">
    <!-- Header -->
    <div class="editor-header">
      <div class="header-left">
        <h2>{{ $t('knowledge.promptEditor.title') }}</h2>
        <p class="subtitle">{{ $t('knowledge.promptEditor.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Icon name="search" />
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="$t('knowledge.promptEditor.searchPlaceholder')"
            :aria-label="t('common.search')"
            class="search-input"
          />
        </div>
        <select v-model="selectedCategory" class="category-filter" :aria-label="t('common.filterByCategory')">
          <option value="all">{{ $t('knowledge.promptEditor.allCategories') }}</option>
          <option value="system">{{ $t('knowledge.promptEditor.filterSystem') }}</option>
          <option value="agents">{{ $t('knowledge.promptEditor.filterAgents') }}</option>
          <option value="templates">{{ $t('knowledge.promptEditor.filterTemplates') }}</option>
        </select>
      </div>
    </div>

    <!-- Messages -->
    <div v-if="error" class="alert alert-error">
      <Icon name="exclamation-circle" />
      {{ error }}
      <button @click="error = null" class="close-btn" :aria-label="t('common.close')"><Icon name="times" /></button>
    </div>

    <div v-if="successMessage" class="alert alert-success">
      <Icon name="check-circle" />
      {{ successMessage }}
    </div>

    <!-- Main Content -->
    <div class="editor-content">
      <!-- Prompt List Sidebar -->
      <aside class="prompt-sidebar">
        <div v-if="isLoading" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('knowledge.promptEditor.loadingPrompts') }}</span>
        </div>

        <div v-else class="prompt-list">
          <template v-for="(categoryPrompts, category) in groupedPrompts" :key="category">
            <div v-if="categoryPrompts.length > 0" class="prompt-category">
              <div class="category-header">
                <Icon :name="getCategoryIcon(category)" />
                <span>{{ categoryLabels[category] }}</span>
                <span class="count">{{ categoryPrompts.length }}</span>
              </div>
              <div class="category-prompts">
                <button
                  v-for="prompt in categoryPrompts"
                  :key="prompt.id"
                  class="prompt-item"
                  :class="{ selected: selectedPrompt?.id === prompt.id }"
                  type="button"
                  :aria-pressed="selectedPrompt?.id === prompt.id"
                  @click="selectPrompt(prompt)"
                >
                  <span class="prompt-name">{{ prompt.name }}</span>
                  <span v-if="prompt.description" class="prompt-desc">{{ prompt.description }}</span>
                </button>
              </div>
            </div>
          </template>

          <EmptyState
            v-if="filteredPrompts.length === 0"
            icon="search"
            :message="searchQuery ? $t('knowledge.promptEditor.noSearchResults') : $t('knowledge.promptEditor.noPrompts')"
          />
        </div>
      </aside>

      <!-- Editor Area -->
      <div class="editor-area">
        <div v-if="!selectedPrompt" class="editor-empty">
          <Icon name="edit" />
          <p>{{ $t('knowledge.promptEditor.selectPrompt') }}</p>
        </div>

        <template v-else>
          <!-- Editor Header -->
          <div class="editor-toolbar">
            <div class="toolbar-left">
              <h3>{{ selectedPrompt.name }}</h3>
              <span class="version-badge" v-if="selectedPrompt.version">
                v{{ selectedPrompt.version }}
              </span>
              <span v-if="hasUnsavedChanges" class="unsaved-badge">
                {{ $t('knowledge.promptEditor.unsavedChanges') }}
              </span>
            </div>
            <div class="toolbar-actions">
              <BaseButton
                variant="ghost"
                size="sm"
                @click="loadHistory"
              >
                <Icon name="history" />
                {{ $t('knowledge.promptEditor.history') }}
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click="revertChanges"
                :disabled="!hasUnsavedChanges"
              >
                <Icon name="undo" />
                {{ $t('knowledge.promptEditor.revert') }}
              </BaseButton>
              <BaseButton
                variant="primary"
                size="sm"
                @click="handleSavePrompt"
                :disabled="!hasUnsavedChanges || isSaving"
              >
                <Icon name="spinner" class="animate-spin" v-if="isSaving" />
                <Icon name="save" v-else />
                {{ $t('knowledge.promptEditor.save') }}
              </BaseButton>
            </div>
          </div>

          <!-- Editor Content -->
          <div class="editor-wrapper">
            <textarea
              v-model="editedContent"
              class="prompt-textarea"
              :placeholder="$t('knowledge.promptEditor.contentPlaceholder')"
              :aria-label="`${t('common.edit')}: ${selectedPrompt.name}`"
              spellcheck="false"
            ></textarea>
          </div>

          <!-- Editor Footer -->
          <div class="editor-footer">
            <div class="footer-stats">
              <span class="stat">
                <Icon name="font" />
                {{ $t('knowledge.promptEditor.characters', { count: characterCount }) }}
              </span>
              <span v-if="detectedVariables.length > 0" class="stat variables">
                <Icon name="code" />
                {{ $t('knowledge.promptEditor.variables', { count: detectedVariables.length }) }}
              </span>
            </div>
            <div v-if="detectedVariables.length > 0" class="variable-tags">
              <span
                v-for="variable in detectedVariables"
                :key="variable"
                class="variable-tag"
                v-text="`{{${variable}}}`"
              />
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- History Modal -->
    <BaseModal
      v-model="showHistoryModal"
      :title="$t('knowledge.promptEditor.versionHistory')"
      size="lg"
      @close="showHistoryModal = false"
    >
      <div class="history-modal">
        <div v-if="isLoadingHistory" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('knowledge.promptEditor.loadingHistory') }}</span>
        </div>

        <EmptyState
          v-else-if="promptHistory.length === 0"
          icon="history"
          :message="$t('knowledge.promptEditor.noHistory')"
        />

        <div v-else class="history-list">
          <div
            v-for="version in promptHistory"
            :key="version.version"
            class="history-item"
            :class="{ selected: selectedVersion?.version === version.version }"
            @click="selectedVersion = version"
          >
            <div class="version-info">
              <span class="version-number">{{ $t('knowledge.promptEditor.versionNumber', { version: version.version }) }}</span>
              <span class="version-date">{{ formatDate(version.timestamp) }}</span>
            </div>
            <BaseButton
              variant="outline-solid"
              size="sm"
              @click.stop="revertToVersion(version)"
            >
              <Icon name="undo" />
              {{ $t('knowledge.promptEditor.revert') }}
            </BaseButton>
          </div>
        </div>

        <!-- Version Preview -->
        <div v-if="selectedVersion" class="version-preview">
          <h4>{{ $t('knowledge.promptEditor.previewVersion', { version: selectedVersion.version }) }}</h4>
          <pre class="version-content">{{ selectedVersion.content }}</pre>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.knowledge-prompt-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 600px;
}

/* Header */
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.header-left h2 {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.header-left .subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-4);
  align-items: center;
}

.search-box {
  position: relative;
  width: 220px;
}

.search-box i {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-9);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.category-filter {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

/* Alerts */
.alert {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-sm);
}

.alert-error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border-bottom: 1px solid var(--color-error-border);
}

.alert-success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
  border-bottom: 1px solid var(--color-success-border);
}

.alert .close-btn {
  margin-left: auto;
  padding: var(--spacing-1);
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

/* Main Content */
.editor-content {
  display: grid;
  grid-template-columns: 280px 1fr;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.prompt-sidebar {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
  background: var(--bg-secondary);
}

.prompt-list {
  padding: var(--spacing-4);
}

.prompt-category {
  margin-bottom: var(--spacing-6);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-0);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.category-header .count {
  margin-left: auto;
  background: var(--bg-card);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-2xl);
  font-weight: 500;
}

.category-prompts {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.prompt-item {
  display: block;
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: all var(--duration-150);
}

.prompt-item:hover {
  background: var(--bg-card);
}

.prompt-item.selected {
  background: var(--color-info-bg);
}

.prompt-name {
  display: block;
  font-weight: 500;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.prompt-desc {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--spacing-0-5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Editor Area */
.editor-area {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  gap: var(--spacing-4);
}

.editor-empty i {
  font-size: var(--text-5xl);
  opacity: 0.5;
}

/* Toolbar */
.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3-5) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.toolbar-left h3 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.version-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.unsaved-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: 500;
}

.toolbar-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* Editor Wrapper */
.editor-wrapper {
  flex: 1;
  padding: var(--spacing-4);
  overflow: hidden;
}

.prompt-textarea {
  width: 100%;
  height: 100%;
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.6;
  resize: none;
  background: var(--bg-input);
  color: var(--text-primary);
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
.prompt-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Editor Footer */
.editor-footer {
  padding: var(--spacing-3) var(--spacing-6);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.footer-stats {
  display: flex;
  gap: var(--spacing-4);
}

.footer-stats .stat {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.footer-stats .stat.variables {
  color: var(--color-info);
}

.variable-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
}

.variable-tag {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-default);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

/* History Modal */
.history-modal {
  min-height: 300px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-6);
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150);
}

.history-item:hover {
  background: var(--bg-secondary);
}

.history-item.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.version-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.version-number {
  font-weight: 600;
  color: var(--text-primary);
}

.version-date {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.version-preview {
  border-top: 1px solid var(--border-default);
  padding-top: var(--spacing-4);
}

.version-preview h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.version-content {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  line-height: 1.5;
  white-space: pre-wrap;
}

/* Responsive */
@media (max-width: 768px) {
  .editor-content {
    grid-template-columns: 1fr;
  }

  .prompt-sidebar {
    display: none;
  }
}
</style>
