<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Knowledge System Docs Component (Issue #747)
 *
 * System documentation viewer and exporter.
 * Features:
 * - Tree view of documentation categories
 * - Markdown preview with syntax highlighting
 * - Export single doc or bulk export (JSON, Markdown)
 * - Search within documents
 * - Copy to clipboard
 */

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, watch } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useLoadingState } from '@/composables/useLoadingState'
import { fetchDocCategories, fetchCategoryDocs, fetchDocContent } from '@/composables/knowledge/useKnowledgeSystemDocs'
import type { SystemDoc, DocCategory } from '@/composables/knowledge/useKnowledgeSystemDocs'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeSystemDocs')

const { t } = useI18n()

// =============================================================================
// State
// =============================================================================

const route = useRoute()

const { isLoading, wrap } = useLoadingState()
const error = ref<string | null>(null)
const searchQuery = ref('')
const categories = ref<DocCategory[]>([])
const selectedCategory = ref<DocCategory | null>(null)
const selectedDoc = ref<SystemDoc | null>(null)
const categoryExpansion = useExpansion<string>()
const expandedCategories = categoryExpansion.expanded

// Export state
const isExporting = ref(false)
const copySuccess = ref(false)

// =============================================================================
// Computed
// =============================================================================

const filteredDocs = computed(() => {
  if (!selectedCategory.value) return []
  if (!searchQuery.value.trim()) return selectedCategory.value.docs

  const query = searchQuery.value.toLowerCase()
  return selectedCategory.value.docs.filter(doc =>
    doc.title.toLowerCase().includes(query) ||
    doc.content.toLowerCase().includes(query)
  )
})

const hasSelectedDoc = computed(() => selectedDoc.value !== null)

const docWordCount = computed(() => {
  if (!selectedDoc.value?.content) return 0
  return selectedDoc.value.content.split(/\s+/).filter(Boolean).length
})

// =============================================================================
// Methods
// =============================================================================

async function loadDocCategories(): Promise<void> {
  error.value = null
  await wrap(async () => {
    try {
      const data = await fetchDocCategories()
      if (data?.categories) {
        categories.value = data.categories
        // Auto-select first category if exists
        if (categories.value.length > 0 && !selectedCategory.value) {
          selectCategory(categories.value[0])
        }
      }
    } catch (err) {
      logger.error('Failed to load doc categories:', err)
      error.value = t('knowledge.systemDocs.errorLoadCategories')
    }
  })
}

async function loadCategoryDocs(category: DocCategory): Promise<void> {
  error.value = null
  await wrap(async () => {
    try {
      const data = await fetchCategoryDocs(category.path)
      if (data?.docs) {
        category.docs = data.docs
      }
    } catch (err) {
      logger.error('Failed to load category docs:', err)
      error.value = t('knowledge.systemDocs.errorLoadDocs')
    }
  })
}

async function loadDocContent(doc: SystemDoc): Promise<void> {
  if (doc.content) {
    selectedDoc.value = doc
    return
  }

  error.value = null
  await wrap(async () => {
    try {
      const data = await fetchDocContent(doc.id)
      if (data?.doc) {
        doc.content = data.doc.content
        selectedDoc.value = doc
      }
    } catch (err) {
      logger.error('Failed to load doc content:', err)
      error.value = t('knowledge.systemDocs.errorLoadContent')
    }
  })
}

function selectCategory(category: DocCategory): void {
  selectedCategory.value = category
  selectedDoc.value = null

  // Load docs if not already loaded
  if (!category.docs || category.docs.length === 0) {
    loadCategoryDocs(category)
  }
}

function selectDoc(doc: SystemDoc): void {
  loadDocContent(doc)
}

function toggleCategory(categoryId: string): void {
  categoryExpansion.toggle(categoryId)
}

function isCategoryExpanded(categoryId: string): boolean {
  return categoryExpansion.isExpanded(categoryId)
}

async function copyToClipboard(): Promise<void> {
  if (!selectedDoc.value?.content) return

  try {
    await navigator.clipboard.writeText(selectedDoc.value.content)
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 2000)
  } catch (err) {
    logger.error('Failed to copy to clipboard:', err)
    error.value = t('knowledge.systemDocs.errorCopy')
  }
}

async function exportDoc(format: 'json' | 'markdown'): Promise<void> {
  if (!selectedDoc.value) return

  isExporting.value = true

  try {
    let content: string
    let filename: string
    let mimeType: string

    if (format === 'json') {
      content = JSON.stringify(selectedDoc.value, null, 2)
      filename = `${selectedDoc.value.title.replace(/\s+/g, '-')}.json`
      mimeType = 'application/json'
    } else {
      content = `# ${selectedDoc.value.title}\n\n${selectedDoc.value.content}`
      filename = `${selectedDoc.value.title.replace(/\s+/g, '-')}.md`
      mimeType = 'text/markdown'
    }

    // Create and trigger download
    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (err) {
    logger.error('Failed to export document:', err)
    error.value = t('knowledge.systemDocs.errorExport')
  } finally {
    isExporting.value = false
  }
}

async function exportAllDocs(format: 'json' | 'markdown'): Promise<void> {
  if (!selectedCategory.value?.docs) return

  isExporting.value = true

  try {
    let content: string
    let filename: string
    let mimeType: string

    if (format === 'json') {
      content = JSON.stringify(selectedCategory.value.docs, null, 2)
      filename = `${selectedCategory.value.name.replace(/\s+/g, '-')}-docs.json`
      mimeType = 'application/json'
    } else {
      content = selectedCategory.value.docs
        .map(doc => `# ${doc.title}\n\n${doc.content || '[Content not loaded]'}\n\n---\n`)
        .join('\n')
      filename = `${selectedCategory.value.name.replace(/\s+/g, '-')}-docs.md`
      mimeType = 'text/markdown'
    }

    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (err) {
    logger.error('Failed to export all documents:', err)
    error.value = t('knowledge.systemDocs.errorExportAll')
  } finally {
    isExporting.value = false
  }
}

function getDocIcon(type: string): IconName {
  const icons: Record<string, IconName> = {
    'markdown': 'file-alt',
    'api': 'code',
    'guide': 'book',
    'reference': 'book-open',
    'tutorial': 'graduation-cap',
    'default': 'file'
  }
  return icons[type] || icons.default
}

// Handle deep-link from route query
watch(() => route.query.doc, (docId) => {
  if (docId && typeof docId === 'string') {
    // Find and select the document
    for (const category of categories.value) {
      const doc = category.docs?.find(d => d.id === docId)
      if (doc) {
        selectCategory(category)
        selectDoc(doc)
        break
      }
    }
  }
}, { immediate: true })

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
  loadDocCategories()
})
</script>

<template>
  <div class="knowledge-system-docs">
    <!-- Header -->
    <div class="docs-header">
      <div class="header-left">
        <h2>{{ $t('knowledge.systemDocs.title') }}</h2>
        <p class="subtitle">{{ $t('knowledge.systemDocs.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Icon name="search" />
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="$t('knowledge.systemDocs.searchPlaceholder')"
            class="search-input"
          />
        </div>
        <div class="export-dropdown" v-if="selectedCategory">
          <BaseButton variant="outline-solid" class="export-btn">
            <Icon name="download" />
            {{ $t('knowledge.systemDocs.exportAll') }}
          </BaseButton>
          <div class="dropdown-menu">
            <button @click="exportAllDocs('markdown')">
              <Icon name="file-alt" /> Markdown
            </button>
            <button @click="exportAllDocs('json')">
              <Icon name="file-code" /> JSON
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      {{ error }}
      <button @click="error = null" class="close-btn">
        <Icon name="times" />
      </button>
    </div>

    <!-- Main Content -->
    <div class="docs-content">
      <!-- Category Sidebar -->
      <aside class="docs-sidebar">
        <div v-if="isLoading && categories.length === 0" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('knowledge.systemDocs.loadingCategories') }}</span>
        </div>

        <div v-else class="category-tree">
          <div
            v-for="category in categories"
            :key="category.id"
            class="category-item"
          >
            <div
              class="category-header"
              :class="{ selected: selectedCategory?.id === category.id }"
              @click="selectCategory(category)"
            >
              <button
                v-if="category.children?.length"
                class="expand-btn"
                @click.stop="toggleCategory(category.id)"
              >
                <Icon :name="isCategoryExpanded(category.id) ? 'chevron-down' : 'chevron-right'" />
              </button>
              <i :class="category.icon || 'folder'" class="category-icon"></i>
              <span class="category-name">{{ category.name }}</span>
              <span class="doc-count">{{ category.docCount || 0 }}</span>
            </div>

            <!-- Children -->
            <div
              v-if="category.children?.length && isCategoryExpanded(category.id)"
              class="category-children"
            >
              <div
                v-for="child in category.children"
                :key="child.id"
                class="category-header child"
                :class="{ selected: selectedCategory?.id === child.id }"
                @click="selectCategory(child)"
              >
                <i :class="child.icon || 'folder'" class="category-icon"></i>
                <span class="category-name">{{ child.name }}</span>
                <span class="doc-count">{{ child.docCount || 0 }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Document List -->
      <div class="docs-list">
        <div v-if="isLoading" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('knowledge.systemDocs.loadingDocs') }}</span>
        </div>

        <EmptyState
          v-else-if="!selectedCategory"
          icon="folder-open"
          :message="$t('knowledge.systemDocs.selectCategory')"
        />

        <EmptyState
          v-else-if="filteredDocs.length === 0"
          icon="file-alt"
          :message="searchQuery ? $t('knowledge.systemDocs.noSearchResults') : $t('knowledge.systemDocs.noDocs')"
        />

        <div v-else class="doc-items">
          <div
            v-for="doc in filteredDocs"
            :key="doc.id"
            class="doc-item"
            :class="{ selected: selectedDoc?.id === doc.id }"
            @click="selectDoc(doc)"
          >
            <Icon :name="getDocIcon(doc.type)" />
            <div class="doc-info">
              <span class="doc-title">{{ doc.title }}</span>
              <span class="doc-path">{{ doc.path }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Document Preview -->
      <div class="docs-preview">
        <div v-if="!hasSelectedDoc" class="preview-empty">
          <Icon name="file-alt" />
          <p>{{ $t('knowledge.systemDocs.selectDocument') }}</p>
        </div>

        <div v-else class="preview-content">
          <div class="preview-header">
            <h3>{{ selectedDoc?.title }}</h3>
            <div class="preview-actions">
              <BaseButton
                variant="ghost"
                size="sm"
                :class="{ success: copySuccess }"
                @click="copyToClipboard"
              >
                <Icon :name="copySuccess ? 'check' : 'copy'" />
                {{ copySuccess ? $t('knowledge.systemDocs.copied') : $t('knowledge.systemDocs.copy') }}
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click="exportDoc('markdown')"
                :disabled="isExporting"
              >
                <Icon name="download" />
                {{ $t('knowledge.systemDocs.export') }}
              </BaseButton>
            </div>
          </div>

          <div class="preview-meta">
            <span v-if="selectedDoc?.path" class="meta-item">
              <Icon name="folder" />
              {{ selectedDoc.path }}
            </span>
            <span class="meta-item">
              <Icon name="file-word" />
              {{ $t('knowledge.systemDocs.words', { count: docWordCount }) }}
            </span>
          </div>

          <div class="preview-body">
            <pre class="doc-content">{{ selectedDoc?.content }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-system-docs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 600px;
}

/* Header */
.docs-header {
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
  width: 280px;
}

.search-box i {
  position: absolute;
  left: 0.875rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3-5) var(--spacing-2) var(--spacing-10);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
}
.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Export Dropdown */
.export-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-1);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-popover);
  display: none;
  min-width: 150px;
}

.export-dropdown:hover .dropdown-menu {
  display: block;
}

.dropdown-menu button {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-4);
  border: none;
  background: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  text-align: left;
}

.dropdown-menu button:hover {
  background: var(--bg-secondary);
}

/* Error Banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border-bottom: 1px solid var(--color-error-border);
}

.error-banner .close-btn {
  margin-left: auto;
  padding: var(--spacing-1);
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

/* Main Content */
.docs-content {
  display: grid;
  grid-template-columns: 220px 280px 1fr;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.docs-sidebar {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
  padding: var(--spacing-4) var(--spacing-0);
}

.category-tree {
  padding: var(--spacing-0) var(--spacing-2);
}

.category-item {
  margin-bottom: var(--spacing-1);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-150);
}

.category-header:hover {
  background: var(--bg-secondary);
}

.category-header.selected {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.category-header.child {
  padding-left: var(--spacing-8);
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-0);
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-xs);
}

.category-icon {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.category-name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 500;
}

.doc-count {
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: var(--bg-secondary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-2xl);
}

.category-children {
  margin-top: var(--spacing-1);
}

/* Document List */
.docs-list {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
  padding: var(--spacing-4);
}

.doc-items {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.doc-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150);
}

.doc-item:hover {
  border-color: var(--color-info);
  background: var(--bg-secondary);
}

.doc-item.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.doc-icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  color: var(--color-info);
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-title {
  display: block;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-0-5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-path {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Preview */
.docs-preview {
  overflow-y: auto;
  background: var(--bg-secondary);
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--spacing-4);
}

.preview-empty i {
  font-size: var(--text-5xl);
  opacity: 0.5;
}

.preview-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.preview-header h3 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.preview-actions {
  display: flex;
  gap: var(--spacing-2);
}

.preview-actions .success {
  color: var(--color-success);
}

.preview-meta {
  display: flex;
  gap: var(--spacing-6);
  padding: var(--spacing-3) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.preview-body {
  flex: 1;
  padding: var(--spacing-6);
  overflow-y: auto;
}

.doc-content {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: var(--spacing-0);
  color: var(--text-primary);
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

/* Responsive */
@media (max-width: 1200px) {
  .docs-content {
    grid-template-columns: 200px 1fr;
  }

  .docs-list {
    display: none;
  }
}

@media (max-width: 768px) {
  .docs-content {
    grid-template-columns: 1fr;
  }

  .docs-sidebar {
    display: none;
  }
}
</style>
