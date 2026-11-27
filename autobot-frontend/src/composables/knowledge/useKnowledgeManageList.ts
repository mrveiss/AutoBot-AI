// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The Manage list (#18244, #17530): search, category and type filters, the header sort, the page
 * and the selection over the documents the server returned. The list itself is never edited
 * here; a document appears only because the store re-read it from the server.
 */
import { computed, ref, watch } from 'vue'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { useDebounce } from '@/composables/useDebounce'
import { useBatchSelection } from '@/composables/useBatchSelection'

export const MANAGE_PAGE_SIZE = 20
export type ManageSortKey = 'title' | 'category' | 'updatedAt'
export type ManageSortOrder = 'asc' | 'desc'

const SEARCH_DEBOUNCE_MS = 300

function compareBy(key: ManageSortKey, a: KnowledgeDocument, b: KnowledgeDocument): number {
  if (key === 'title') return (a.title || '').localeCompare(b.title || '')
  if (key === 'category') return a.category.localeCompare(b.category)
  return new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime()
}

function matchesQuery(doc: KnowledgeDocument, query: string): boolean {
  return (
    !!doc.title?.toLowerCase().includes(query) ||
    doc.content.toLowerCase().includes(query) ||
    doc.tags.some((tag) => tag.toLowerCase().includes(query))
  )
}

export function useKnowledgeManageList(documents: () => KnowledgeDocument[]) {
  const searchQuery = ref('')
  const debouncedSearch = useDebounce(searchQuery, SEARCH_DEBOUNCE_MS)
  const filterCategory = ref('')
  const filterType = ref('')
  const sortKey = ref<ManageSortKey>('updatedAt')
  const sortOrder = ref<ManageSortOrder>('desc')
  const currentPage = ref(1)

  const filteredDocuments = computed(() => {
    const query = debouncedSearch.value.toLowerCase()
    const docs = documents().filter(
      (doc) =>
        (!query || matchesQuery(doc, query)) &&
        (!filterCategory.value || doc.category === filterCategory.value) &&
        (!filterType.value || doc.type === filterType.value),
    )
    const direction = sortOrder.value === 'asc' ? 1 : -1
    return docs.sort((a, b) => direction * compareBy(sortKey.value, a, b))
  })

  const paginatedEntries = computed(() => {
    const start = (currentPage.value - 1) * MANAGE_PAGE_SIZE
    return filteredDocuments.value.slice(start, start + MANAGE_PAGE_SIZE)
  })
  const totalPages = computed(() => Math.max(1, Math.ceil(filteredDocuments.value.length / MANAGE_PAGE_SIZE)))

  // `items` is the current page, so selectAll / allSelected are page-level; "all matching" is setSelected below.
  const selection = useBatchSelection<{ id: string }, string>(() => paginatedEntries.value, (item) => item.id)
  const allMatchingSelected = ref(false)

  const selectAllPage = () => {
    allMatchingSelected.value = false
    selection.selectAll()
  }
  const selectAllMatching = () => {
    allMatchingSelected.value = true
    selection.setSelected(filteredDocuments.value.map((doc) => doc.id))
  }
  const clearSelection = () => {
    selection.clear()
    allMatchingSelected.value = false
  }
  const clearFilters = () => {
    searchQuery.value = ''
    filterCategory.value = ''
    filterType.value = ''
    sortKey.value = 'updatedAt'
    sortOrder.value = 'desc'
  }
  const onSort = (key: string, order: ManageSortOrder) => {
    sortKey.value = key as ManageSortKey
    sortOrder.value = order
  }

  watch([debouncedSearch, filterCategory, filterType], () => {
    currentPage.value = 1
  })

  return {
    searchQuery, filterCategory, filterType, sortKey, sortOrder, currentPage,
    filteredDocuments, paginatedEntries, totalPages, selection, allMatchingSelected,
    selectAllPage, selectAllMatching, clearSelection, clearFilters, onSort,
  }
}
