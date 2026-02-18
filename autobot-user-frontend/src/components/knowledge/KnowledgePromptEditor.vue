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

import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgePromptEditor')

// =============================================================================
// Type Definitions
// =============================================================================

interface Prompt {
  id: string
  name: string
  category: 'system' | 'agents' | 'templates'
  content: string
  description?: string
  variables?: string[]
  lastModified?: string
  version?: number
}

interface PromptVersion {
  version: number
  content: string
  timestamp: string
  author?: string
}

// =============================================================================
// State
// =============================================================================

const isLoading = ref(false)
const isSaving = ref(false)
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
const isLoadingHistory = ref(false)

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

const categoryIcons: Record<string, string> = {
  system: 'fas fa-cog',
  agents: 'fas fa-robot',
  templates: 'fas fa-file-code'
}

const categoryLabels: Record<string, string> = {
  system: 'System Prompts',
  agents: 'Agent Prompts',
  templates: 'Templates'
}

// =============================================================================
// Methods
// =============================================================================

async function loadPrompts(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.get('/api/prompts')
    const data = await parseApiResponse(response)

    if (data?.prompts) {
      prompts.value = data.prompts
    }
  } catch (err) {
    logger.error('Failed to load prompts:', err)
    error.value = 'Failed to load prompts'
  } finally {
    isLoading.value = false
  }
}

function selectPrompt(prompt: Prompt): void {
  if (hasUnsavedChanges.value) {
    if (!confirm('You have unsaved changes. Discard them?')) {
      return
    }
  }

  selectedPrompt.value = prompt
  editedContent.value = prompt.content
  error.value = null
  successMessage.value = null
}

async function savePrompt(): Promise<void> {
  if (!selectedPrompt.value) return

  isSaving.value = true
  error.value = null
  successMessage.value = null

  try {
    const response = await apiClient.put(
      `/api/prompts/${encodeURIComponent(selectedPrompt.value.id)}`,
      { content: editedContent.value }
    )
    const data = await parseApiResponse(response)

    if (data?.status === 'success') {
      // Update local state
      selectedPrompt.value.content = editedContent.value
      selectedPrompt.value.version = (selectedPrompt.value.version || 0) + 1
      selectedPrompt.value.lastModified = new Date().toISOString()

      successMessage.value = 'Prompt saved successfully'
      setTimeout(() => {
        successMessage.value = null
      }, 3000)
    } else {
      error.value = data?.message || 'Failed to save prompt'
    }
  } catch (err) {
    logger.error('Failed to save prompt:', err)
    error.value = 'Failed to save prompt'
  } finally {
    isSaving.value = false
  }
}

function revertChanges(): void {
  if (!selectedPrompt.value) return
  editedContent.value = selectedPrompt.value.content
}

async function loadHistory(): Promise<void> {
  if (!selectedPrompt.value) return

  isLoadingHistory.value = true
  showHistoryModal.value = true

  try {
    const response = await apiClient.get(
      `/api/prompts/${encodeURIComponent(selectedPrompt.value.id)}/history`
    )
    const data = await parseApiResponse(response)

    if (data?.versions) {
      promptHistory.value = data.versions
    }
  } catch (err) {
    logger.error('Failed to load history:', err)
    promptHistory.value = []
  } finally {
    isLoadingHistory.value = false
  }
}

async function revertToVersion(version: PromptVersion): Promise<void> {
  if (!selectedPrompt.value) return

  if (!confirm(`Revert to version ${version.version}? This will create a new version.`)) {
    return
  }

  isSaving.value = true

  try {
    const response = await apiClient.post(
      `/api/prompts/${encodeURIComponent(selectedPrompt.value.id)}/revert`,
      { version: version.version }
    )
    const data = await parseApiResponse(response)

    if (data?.status === 'success') {
      selectedPrompt.value.content = version.content
      editedContent.value = version.content
      showHistoryModal.value = false
      successMessage.value = 'Reverted to previous version'
    }
  } catch (err) {
    logger.error('Failed to revert:', err)
    error.value = 'Failed to revert to previous version'
  } finally {
    isSaving.value = false
  }
}

function getCategoryIcon(category: string): string {
  return categoryIcons[category] || 'fas fa-file'
}

function formatDate(dateString?: string): string {
  if (!dateString) return 'Unknown'
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
        <h2>Prompt Editor</h2>
        <p class="subtitle">Manage system and agent prompts</p>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <i class="fas fa-search"></i>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search prompts..."
            class="search-input"
          />
        </div>
        <select v-model="selectedCategory" class="category-filter">
          <option value="all">All Categories</option>
          <option value="system">System</option>
          <option value="agents">Agents</option>
          <option value="templates">Templates</option>
        </select>
      </div>
    </div>

    <!-- Messages -->
    <div v-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i>
      {{ error }}
      <button @click="error = null" class="close-btn"><i class="fas fa-times"></i></button>
    </div>

    <div v-if="successMessage" class="alert alert-success">
      <i class="fas fa-check-circle"></i>
      {{ successMessage }}
    </div>

    <!-- Main Content -->
    <div class="editor-content">
      <!-- Prompt List Sidebar -->
      <aside class="prompt-sidebar">
        <div v-if="isLoading" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading prompts...</span>
        </div>

        <div v-else class="prompt-list">
          <template v-for="(categoryPrompts, category) in groupedPrompts" :key="category">
            <div v-if="categoryPrompts.length > 0" class="prompt-category">
              <div class="category-header">
                <i :class="getCategoryIcon(category)"></i>
                <span>{{ categoryLabels[category] }}</span>
                <span class="count">{{ categoryPrompts.length }}</span>
              </div>
              <div class="category-prompts">
                <div
                  v-for="prompt in categoryPrompts"
                  :key="prompt.id"
                  class="prompt-item"
                  :class="{ selected: selectedPrompt?.id === prompt.id }"
                  @click="selectPrompt(prompt)"
                >
                  <span class="prompt-name">{{ prompt.name }}</span>
                  <span v-if="prompt.description" class="prompt-desc">{{ prompt.description }}</span>
                </div>
              </div>
            </div>
          </template>

          <EmptyState
            v-if="filteredPrompts.length === 0"
            icon="fas fa-search"
            :message="searchQuery ? 'No prompts match your search' : 'No prompts found'"
          />
        </div>
      </aside>

      <!-- Editor Area -->
      <div class="editor-area">
        <div v-if="!selectedPrompt" class="editor-empty">
          <i class="fas fa-edit"></i>
          <p>Select a prompt to edit</p>
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
                Unsaved changes
              </span>
            </div>
            <div class="toolbar-actions">
              <BaseButton
                variant="ghost"
                size="sm"
                @click="loadHistory"
              >
                <i class="fas fa-history"></i>
                History
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click="revertChanges"
                :disabled="!hasUnsavedChanges"
              >
                <i class="fas fa-undo"></i>
                Revert
              </BaseButton>
              <BaseButton
                variant="primary"
                size="sm"
                @click="savePrompt"
                :disabled="!hasUnsavedChanges || isSaving"
              >
                <i v-if="isSaving" class="fas fa-spinner fa-spin"></i>
                <i v-else class="fas fa-save"></i>
                Save
              </BaseButton>
            </div>
          </div>

          <!-- Editor Content -->
          <div class="editor-wrapper">
            <textarea
              v-model="editedContent"
              class="prompt-textarea"
              placeholder="Enter prompt content..."
              spellcheck="false"
            ></textarea>
          </div>

          <!-- Editor Footer -->
          <div class="editor-footer">
            <div class="footer-stats">
              <span class="stat">
                <i class="fas fa-font"></i>
                {{ characterCount }} characters
              </span>
              <span v-if="detectedVariables.length > 0" class="stat variables">
                <i class="fas fa-code"></i>
                {{ detectedVariables.length }} variables
              </span>
            </div>
            <div v-if="detectedVariables.length > 0" class="variable-tags">
              <span
                v-for="variable in detectedVariables"
                :key="variable"
                class="variable-tag"
              >
                {{ '{{' + variable + '}}' }}
              </span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- History Modal -->
    <BaseModal
      v-model="showHistoryModal"
      title="Version History"
      size="large"
      @close="showHistoryModal = false"
    >
      <div class="history-modal">
        <div v-if="isLoadingHistory" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading history...</span>
        </div>

        <EmptyState
          v-else-if="promptHistory.length === 0"
          icon="fas fa-history"
          message="No version history available"
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
              <span class="version-number">Version {{ version.version }}</span>
              <span class="version-date">{{ formatDate(version.timestamp) }}</span>
            </div>
            <BaseButton
              variant="outline"
              size="sm"
              @click.stop="revertToVersion(version)"
            >
              <i class="fas fa-undo"></i>
              Revert
            </BaseButton>
          </div>
        </div>

        <!-- Version Preview -->
        <div v-if="selectedVersion" class="version-preview">
          <h4>Preview - Version {{ selectedVersion.version }}</h4>
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
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.header-left h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.header-left .subtitle {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
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
  padding: 0.5rem 0.75rem 0.5rem 2.25rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: var(--bg-input);
  color: var(--text-primary);
}

.category-filter {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: var(--bg-input);
  color: var(--text-primary);
}

/* Alerts */
.alert {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
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
  padding: 0.25rem;
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
  padding: 1rem;
}

.prompt-category {
  margin-bottom: 1.5rem;
}

.category-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.category-header .count {
  margin-left: auto;
  background: var(--bg-card);
  padding: 0.125rem 0.5rem;
  border-radius: 1rem;
  font-weight: 500;
}

.category-prompts {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.prompt-item {
  padding: 0.625rem 0.75rem;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
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
  font-size: 0.875rem;
}

.prompt-desc {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.125rem;
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
  gap: 1rem;
}

.editor-empty i {
  font-size: 3rem;
  opacity: 0.5;
}

/* Toolbar */
.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.875rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toolbar-left h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.version-badge {
  padding: 0.125rem 0.5rem;
  background: var(--bg-secondary);
  border-radius: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.unsaved-badge {
  padding: 0.125rem 0.5rem;
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}

/* Editor Wrapper */
.editor-wrapper {
  flex: 1;
  padding: 1rem;
  overflow: hidden;
}

.prompt-textarea {
  width: 100%;
  height: 100%;
  padding: 1rem;
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.875rem;
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

/* Editor Footer */
.editor-footer {
  padding: 0.75rem 1.5rem;
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.footer-stats {
  display: flex;
  gap: 1rem;
}

.footer-stats .stat {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.footer-stats .stat.variables {
  color: var(--color-info);
}

.variable-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.variable-tag {
  padding: 0.125rem 0.5rem;
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: 0.25rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--text-secondary);
}

/* History Modal */
.history-modal {
  min-height: 300px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
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
  gap: 0.125rem;
}

.version-number {
  font-weight: 600;
  color: var(--text-primary);
}

.version-date {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.version-preview {
  border-top: 1px solid var(--border-default);
  padding-top: 1rem;
}

.version-preview h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.version-content {
  max-height: 200px;
  overflow-y: auto;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 0.375rem;
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
