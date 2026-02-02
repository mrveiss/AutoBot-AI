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

import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeSystemDocs')

// =============================================================================
// Type Definitions
// =============================================================================

interface SystemDoc {
  id: string
  title: string
  path: string
  content: string
  type: string
  category: string
  metadata?: {
    wordCount?: number
    lastModified?: string
    author?: string
  }
}

interface DocCategory {
  id: string
  name: string
  path: string
  icon: string
  children: DocCategory[]
  docs: SystemDoc[]
  docCount: number
}

// =============================================================================
// State
// =============================================================================

const route = useRoute()

const isLoading = ref(false)
const error = ref<string | null>(null)
const searchQuery = ref('')
const categories = ref<DocCategory[]>([])
const selectedCategory = ref<DocCategory | null>(null)
const selectedDoc = ref<SystemDoc | null>(null)
const expandedCategories = ref<Set<string>>(new Set())

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
  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.get('/api/knowledge_base/system-docs/categories')
    const data = await parseApiResponse(response)

    if (data?.categories) {
      categories.value = data.categories
      // Auto-select first category if exists
      if (categories.value.length > 0 && !selectedCategory.value) {
        selectCategory(categories.value[0])
      }
    }
  } catch (err) {
    logger.error('Failed to load doc categories:', err)
    error.value = 'Failed to load documentation categories'
  } finally {
    isLoading.value = false
  }
}

async function loadCategoryDocs(category: DocCategory): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.get(
      `/api/knowledge_base/system-docs/category/${encodeURIComponent(category.path)}`
    )
    const data = await parseApiResponse(response)

    if (data?.docs) {
      category.docs = data.docs
    }
  } catch (err) {
    logger.error('Failed to load category docs:', err)
    error.value = 'Failed to load documents'
  } finally {
    isLoading.value = false
  }
}

async function loadDocContent(doc: SystemDoc): Promise<void> {
  if (doc.content) {
    selectedDoc.value = doc
    return
  }

  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.get(
      `/api/knowledge_base/system-docs/${encodeURIComponent(doc.id)}`
    )
    const data = await parseApiResponse(response)

    if (data?.doc) {
      doc.content = data.doc.content
      selectedDoc.value = doc
    }
  } catch (err) {
    logger.error('Failed to load doc content:', err)
    error.value = 'Failed to load document content'
  } finally {
    isLoading.value = false
  }
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
  if (expandedCategories.value.has(categoryId)) {
    expandedCategories.value.delete(categoryId)
  } else {
    expandedCategories.value.add(categoryId)
  }
}

function isCategoryExpanded(categoryId: string): boolean {
  return expandedCategories.value.has(categoryId)
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
    error.value = 'Failed to copy to clipboard'
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
    error.value = 'Failed to export document'
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
    error.value = 'Failed to export documents'
  } finally {
    isExporting.value = false
  }
}

function getDocIcon(type: string): string {
  const icons: Record<string, string> = {
    'markdown': 'fas fa-file-alt',
    'api': 'fas fa-code',
    'guide': 'fas fa-book',
    'reference': 'fas fa-book-open',
    'tutorial': 'fas fa-graduation-cap',
    'default': 'fas fa-file'
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
        <h2>System Documentation</h2>
        <p class="subtitle">Browse and export AutoBot documentation</p>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <i class="fas fa-search"></i>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search documentation..."
            class="search-input"
          />
        </div>
        <div class="export-dropdown" v-if="selectedCategory">
          <BaseButton variant="outline" class="export-btn">
            <i class="fas fa-download"></i>
            Export All
          </BaseButton>
          <div class="dropdown-menu">
            <button @click="exportAllDocs('markdown')">
              <i class="fas fa-file-alt"></i> Markdown
            </button>
            <button @click="exportAllDocs('json')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-circle"></i>
      {{ error }}
      <button @click="error = null" class="close-btn">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Main Content -->
    <div class="docs-content">
      <!-- Category Sidebar -->
      <aside class="docs-sidebar">
        <div v-if="isLoading && categories.length === 0" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading categories...</span>
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
                <i :class="isCategoryExpanded(category.id) ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              </button>
              <i :class="category.icon || 'fas fa-folder'" class="category-icon"></i>
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
                <i :class="child.icon || 'fas fa-folder'" class="category-icon"></i>
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
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading documents...</span>
        </div>

        <EmptyState
          v-else-if="!selectedCategory"
          icon="fas fa-folder-open"
          message="Select a category to browse documents"
        />

        <EmptyState
          v-else-if="filteredDocs.length === 0"
          icon="fas fa-file-alt"
          :message="searchQuery ? 'No documents match your search' : 'No documents in this category'"
        />

        <div v-else class="doc-items">
          <div
            v-for="doc in filteredDocs"
            :key="doc.id"
            class="doc-item"
            :class="{ selected: selectedDoc?.id === doc.id }"
            @click="selectDoc(doc)"
          >
            <i :class="getDocIcon(doc.type)" class="doc-icon"></i>
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
          <i class="fas fa-file-alt"></i>
          <p>Select a document to preview</p>
        </div>

        <div v-else class="preview-content">
          <div class="preview-header">
            <h3>{{ selectedDoc?.title }}</h3>
            <div class="preview-actions">
              <BaseButton
                variant="ghost"
                size="small"
                :class="{ success: copySuccess }"
                @click="copyToClipboard"
              >
                <i :class="copySuccess ? 'fas fa-check' : 'fas fa-copy'"></i>
                {{ copySuccess ? 'Copied!' : 'Copy' }}
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="small"
                @click="exportDoc('markdown')"
                :disabled="isExporting"
              >
                <i class="fas fa-download"></i>
                Export
              </BaseButton>
            </div>
          </div>

          <div class="preview-meta">
            <span v-if="selectedDoc?.path" class="meta-item">
              <i class="fas fa-folder"></i>
              {{ selectedDoc.path }}
            </span>
            <span class="meta-item">
              <i class="fas fa-file-word"></i>
              {{ docWordCount }} words
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
  padding: 0.5rem 0.875rem 0.5rem 2.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: var(--bg-input);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
}

/* Export Dropdown */
.export-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.25rem;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  box-shadow: var(--shadow-lg);
  z-index: 100;
  display: none;
  min-width: 150px;
}

.export-dropdown:hover .dropdown-menu {
  display: block;
}

.dropdown-menu button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.625rem 1rem;
  border: none;
  background: none;
  color: var(--text-primary);
  font-size: 0.875rem;
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
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border-bottom: 1px solid var(--color-error-border);
}

.error-banner .close-btn {
  margin-left: auto;
  padding: 0.25rem;
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
  padding: 1rem 0;
}

.category-tree {
  padding: 0 0.5rem;
}

.category-item {
  margin-bottom: 0.25rem;
}

.category-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background 0.15s;
}

.category-header:hover {
  background: var(--bg-secondary);
}

.category-header.selected {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.category-header.child {
  padding-left: 2rem;
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.75rem;
}

.category-icon {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.category-name {
  flex: 1;
  font-size: 0.875rem;
  font-weight: 500;
}

.doc-count {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-secondary);
  padding: 0.125rem 0.5rem;
  border-radius: 1rem;
}

.category-children {
  margin-top: 0.25rem;
}

/* Document List */
.docs-list {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
  padding: 1rem;
}

.doc-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
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
  border-radius: 0.375rem;
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
  margin-bottom: 0.125rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-path {
  display: block;
  font-size: 0.75rem;
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
  gap: 1rem;
}

.preview-empty i {
  font-size: 3rem;
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
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.preview-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.preview-actions {
  display: flex;
  gap: 0.5rem;
}

.preview-actions .success {
  color: var(--color-success);
}

.preview-meta {
  display: flex;
  gap: 1.5rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-card);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.preview-body {
  flex: 1;
  padding: 1.5rem;
  overflow-y: auto;
}

.doc-content {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  color: var(--text-primary);
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
