<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeBrowser — Refined UI "Knowledge · Browser" and "Knowledge · AI documents" (#18244).
  One header with one search box (typing filters the tree, Enter runs the unified search), the
  three category cards, the health strip (advanced), and a files card — the filter chip, the
  selection bar, the document tree and the AI documents — beside the reading pane. The state
  lives in the three useKnowledgeBrowser* composables; this file only composes.
-->
<template>
  <div class="knowledge-file-browser">
    <div v-if="docBranchError" class="error-toast" role="alert">{{ docBranchError }}</div>

    <KnowledgeBrowserHeader
      :query="searchQuery"
      :search="search"
      @filter="handleSearch"
      @submit="runSearch"
      @clear="clearAllSearch"
    />

    <KnowledgeMainCategories
      :categories="mainCategories"
      :population-states="populationStates"
      :selected-id="selectedMainCategory"
      :kb-connected="kbConnected"
      :kb-fetch-error="kbFetchError"
      @select="selectMainCategory"
      @populate="handlePopulate"
      @import="goToImport"
      @edit="handleEditCategory"
    />

    <KnowledgeHealthSummary />

    <Breadcrumb v-if="selectedFile" class="breadcrumb" :items="crumbs" :label="$t('common.breadcrumb')" @select="clearSelection">
      <template #item="{ item, index }">
        <Icon v-if="index === 0" name="home" aria-hidden="true" /> {{ item.label }}
      </template>
      <template #separator><Icon name="chevron-right" aria-hidden="true" /></template>
    </Breadcrumb>

    <section class="split-pane" :aria-label="$t('knowledge.browser.filesLabel')">
      <BaseCard class="tree-card">
        <KnowledgeBrowserFilterBar
          :filter-label="activeFilterLabel"
          :refreshing="isRefreshingStatus"
          @clear-filter="clearFilters"
          @refresh="refreshVectorizationStatus"
        />
        <KnowledgeBatchToolbar
          :has-selection="hasSelection"
          :selection-count="selectionCount"
          :eligible-count="eligibleCount"
          :can-vectorize="canVectorizeSelection"
          :is-vectorizing="isVectorizing"
          @vectorize="vectorizeSelected"
          @deselect-all="deselectAll"
        />
        <KnowledgeTreePane
          :is-loading="isLoading"
          :error="error"
          :nodes="filteredTree"
          :expanded-nodes="expandedNodes"
          :selected-id="selectedFile?.id"
          :selected-documents="selectedDocuments"
          :vectorization-states="documentStates"
          :has-more="hasMoreCategoryFacts"
          :is-loading-more="isLoadingMoreCategoryFacts"
          :selected-doc-id="selectedDocId"
          @retry="loadTree"
          @toggle="toggleNode"
          @select="selectNode"
          @toggle-select="toggleDocumentSelection"
          @vectorize="handleVectorizeDocument"
          @vectorize-folder="handleVectorizeFolder"
          @load-more="loadMoreCategoryFacts"
          @doc-select="onDocSelect"
          @doc-deleted="onDocDeleted"
          @doc-error="showDocBranchError"
        />
      </BaseCard>

      <AIDocumentEditor
        v-if="rightPane === 'editor'"
        :doc-id="selectedDocId!"
        class="content-pane"
        @error="showDocBranchError($event)"
        @load-error="onEditorLoadError"
      />
      <KnowledgeSearchResults v-else-if="rightPane === 'results'" :search="search" class="content-pane" @close="search.clearResults()" />
      <KnowledgeContentViewer
        v-else
        :selected-file="selectedFile"
        :content="fileContent"
        :is-loading="isLoadingContent"
        :error="contentError instanceof Error ? contentError.message : (contentError as string | null)"
        class="content-pane"
        @close="clearSelection"
      />
    </section>

    <VectorizationProgressModal
      :show="showProgressModal"
      :document-states="documentStates"
      @close="showProgressModal = false"
      @retry-failed="handleRetryFailed"
      @cancel="handleCancelVectorization"
    />

    <CategoryEditModal
      v-model="showCategoryEditModal"
      :category="categoryToEdit"
      @updated="handleCategoryUpdated"
      @deleted="handleCategoryDeleted"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { BaseCard, Breadcrumb, type BreadcrumbItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import AIDocumentEditor from '@/components/documents/AIDocumentEditor.vue'
import { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'
import { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'
import { useKnowledgeBrowserTree } from '@/composables/knowledge/useKnowledgeBrowserTree'
import { useKnowledgeBrowserCategories } from '@/composables/knowledge/useKnowledgeBrowserCategories'
import { useKnowledgeBrowserSelection } from '@/composables/knowledge/useKnowledgeBrowserSelection'
import { useTransientError } from '@/composables/useTransientError'
import { formatCategoryName } from '@/utils/formatHelpers'
import KnowledgeBrowserHeader from './KnowledgeBrowserHeader.vue'
import KnowledgeMainCategories from './KnowledgeMainCategories.vue'
import KnowledgeHealthSummary from './KnowledgeHealthSummary.vue'
import KnowledgeBrowserFilterBar from './KnowledgeBrowserFilterBar.vue'
import KnowledgeBatchToolbar from './KnowledgeBatchToolbar.vue'
import KnowledgeTreePane from './KnowledgeTreePane.vue'
import KnowledgeContentViewer from './KnowledgeContentViewer.vue'
import KnowledgeSearchResults from './KnowledgeSearchResults.vue'
import VectorizationProgressModal from './VectorizationProgressModal.vue'
import CategoryEditModal from './modals/CategoryEditModal.vue'

const props = withDefaults(
  defineProps<{
    mode?: 'user' | 'autobot' | 'autobot-documentation' | 'system-knowledge' | 'user-knowledge'
    preselectedCategory?: string | null
  }>(),
  { mode: 'user', preselectedCategory: null },
)

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

// Selection and vectorization state is one instance, shared by the tree and the actions.
const vec = useKnowledgeVectorization()
const { documentStates, selectedDocuments, hasSelection, selectionCount, canVectorizeSelection } = vec
const { toggleDocumentSelection, deselectAll } = vec

const categories = useKnowledgeBrowserCategories(() => tree.loadTree(), (message) => showDocBranchError(message))
const {
  mainCategories, selectedMainCategory, selectedCategory, kbConnected, kbFetchError, populationStates,
  showCategoryEditModal, categoryToEdit, selectMainCategory, handleEditCategory, handleCategoryUpdated,
  handleCategoryDeleted, handlePopulate,
} = categories

const selectedDocId = ref<string | null>(null)
const { message: docBranchError, show: showDocBranchError } = useTransientError()
const search = useKnowledgeSearch(selectedCategory)

const tree = useKnowledgeBrowserTree({
  selectedMainCategory,
  selectedCategory,
  fetchBatchStatus: vec.fetchBatchStatus,
  onError: (message) => showDocBranchError(message),
  onFilePicked: () => {
    selectedDocId.value = null // picking a fact leaves the AI document editor
  },
})
const {
  searchQuery, filteredTree, expandedNodes, isLoading, error, hasMoreCategoryFacts, isLoadingMoreCategoryFacts,
  isRefreshingStatus, selectedFile, fileContent, isLoadingContent, contentError, loadTree, loadMoreCategoryFacts,
  refreshVectorizationStatus, toggleNode, selectNode, clearSelection, handleSearch, clearSearch,
} = tree

const {
  isVectorizing, showProgressModal, eligibleCount, handleVectorizeDocument, handleVectorizeFolder,
  vectorizeSelected, handleRetryFailed, handleCancelVectorization,
} = useKnowledgeBrowserSelection(vec, (message) => showDocBranchError(message))

// Right pane priority: document editor > search results > reading pane.
const rightPane = computed<'editor' | 'results' | 'viewer'>(() => {
  if (selectedDocId.value) return 'editor'
  if (search.searchPerformed.value) return 'results'
  return 'viewer'
})

// The kit trail (#17563): the root returns to the tree; the file's path parts are not links.
const crumbs = computed<BreadcrumbItem[]>(() => {
  if (!selectedFile.value) return []
  const parts = selectedFile.value.path.split('/').filter((p) => p)
  return [{ label: t('knowledge.browser.root'), selectable: true }, ...parts.map((label) => ({ label }))]
})

// One chip names whichever category filter is on (a card's main category, or ?category=).
const activeFilterLabel = computed(() => {
  if (selectedMainCategory.value) {
    return mainCategories.value.find((c) => c.id === selectedMainCategory.value)?.name ?? selectedMainCategory.value
  }
  return selectedCategory.value ? formatCategoryName(selectedCategory.value) : null
})

function clearFilters() {
  selectedMainCategory.value = null
  selectedCategory.value = null
}

/** Enter in the one search box: run the unified search with the box's text. */
async function runSearch() {
  search.searchQuery.value = searchQuery.value
  // Leave the editor first: a document picked while the search is pending must stay open.
  selectedDocId.value = null
  await search.handleSearch()
}

function clearAllSearch() {
  clearSearch()
  search.clearResults()
}

function onDocSelect(id: string) {
  selectedDocId.value = id
  clearSelection()
}

function onDocDeleted(id: string) {
  if (selectedDocId.value === id) selectedDocId.value = null
}

function onEditorLoadError(message: string) {
  showDocBranchError(message)
  selectedDocId.value = null
}

const goToImport = () => router.push('/knowledge/upload')

/** ?doc= opens the editor, ?category= filters, ?view=system picks the system card, ?q= searches. */
function applyDeepLinks() {
  if (props.preselectedCategory) selectedMainCategory.value = props.preselectedCategory
  const { doc, category, view, q } = route.query
  if (typeof doc === 'string') selectedDocId.value = doc
  if (typeof category === 'string') selectedCategory.value = category
  if (view === 'system') selectedMainCategory.value = 'system-knowledge'
  if (typeof q === 'string' && q.trim()) {
    searchQuery.value = q
    search.searchQuery.value = q
    search.handleSearch()
  }
}

onMounted(() => {
  categories.loadMainCategories()
  loadTree()
  applyDeepLinks()
})

onUnmounted(() => vec.cleanup())

watch(
  () => props.mode,
  () => {
    tree.resetPagination()
    loadTree()
    clearSelection()
    selectedDocId.value = null
    tree.nodeExpansion.collapseAll()
  },
)
</script>

<style scoped>
.knowledge-file-browser {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
  min-block-size: 100%;
  padding: var(--spacing-6) var(--page-margin) var(--spacing-8);
  background: var(--bg);
}

.error-toast {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  background: var(--bad-bg);
  color: var(--bad-fg);
  font-size: var(--text-sm);
}

.split-pane {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  align-items: stretch;
}

.tree-card {
  flex: 1 1 340px;
  min-inline-size: 0;
}

.tree-card :deep(.aui-card__body) {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.content-pane {
  flex: 999 1 380px;
  min-inline-size: 0;
}
</style>
