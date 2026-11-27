<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeEntries — "Knowledge · Manage" (#18244): the Upload, Manage, Watch Folders and
  Connectors tabs. The Manage list is a server read (#17530): it is loaded from the entries
  endpoint every time the screen opens, never accumulated from this session's uploads.
-->
<template>
  <div class="knowledge-entries flex flex-col gap-4 p-4">
    <BaseTabs v-model="manageTab" :items="tabItems" :label="$t('knowledge.entries.tabsLabel')" class="manage-tabs">
      <template #icon="{ item }"><Icon :name="TAB_ICONS[item.value as ManageTab]" aria-hidden="true" /></template>
      <template #panel-upload><KnowledgeUploadTab /></template>
      <template #panel-watchFolders><WatchFoldersPanel /></template>
      <template #panel-connectors><ConnectorManager /></template>
      <template #panel-manage>
        <div class="flex flex-col gap-4">
          <KnowledgeEntriesFilters
            v-model:search="list.searchQuery.value"
            v-model:category="list.filterCategory.value"
            v-model:type="list.filterType.value"
            :categories="store.categories"
            :total="list.filteredDocuments.value.length"
            @clear="list.clearFilters"
          />

          <BulkActionsToolbar
            :selected-count="selection.selectedCount.value"
            :total-count="list.filteredDocuments.value.length"
            :page-count="list.paginatedEntries.value.length"
            :all-page-selected="selection.allSelected.value"
            :all-matching-selected="list.allMatchingSelected.value"
            @select-all-page="list.selectAllPage"
            @select-all-matching="list.selectAllMatching"
            @clear-selection="list.clearSelection"
            @export="onBulkExport"
            @change-category="openBulkEdit('category')"
            @add-tags="openBulkEdit('tags-add')"
            @remove-tags="openBulkEdit('tags-remove')"
            @delete="deleteSelected"
          />

          <KnowledgeEntriesTable
            v-model:page="list.currentPage.value"
            :documents="list.filteredDocuments.value"
            :loading="store.isLoading"
            :page-size="MANAGE_PAGE_SIZE"
            :sort-key="list.sortKey.value"
            :sort-order="list.sortOrder.value"
            :total="list.filteredDocuments.value.length"
            :empty-description="filtersActive ? $t('knowledge.entries.adjustFilters') : $t('knowledge.entries.addFirstEntry')"
            :is-selected="selection.isSelected"
            @sort="list.onSort"
            @toggle="selection.toggle"
            @preview="openPreview"
            @view="dialog.viewEntry"
            @edit="dialog.editEntry"
            @delete="deleteEntry"
          />
        </div>
      </template>
    </BaseTabs>

    <KnowledgeEntryDialog
      v-model="dialog.showDialog.value"
      :mode="dialog.dialogMode.value"
      :entry="dialog.currentEntry.value"
      :categories="store.categories"
      :can-save="dialog.canSaveEdit.value"
      @edit="dialog.currentEntry.value && dialog.editEntry(dialog.currentEntry.value)"
      @cancel="dialog.cancelEdit"
      @export="openDocumentExport"
      @save="dialog.saveEdit"
    />

    <BulkEditModal
      v-model="showBulkEditModal"
      :mode="bulkEditMode"
      :selected-entries="selectedBulkEditEntries"
      @confirm="handleBulkEditConfirm"
    />

    <SourcePreviewPanel v-model="showPreview" :document="previewDocument" hide-open-in-manager />
    <DocumentExportModal v-model="showDocumentExport" :documents="exportDocuments" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BaseTabs } from '@autobot/ui'
import type { TabItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { MANAGE_PAGE_SIZE, useKnowledgeManageList } from '@/composables/knowledge/useKnowledgeManageList'
import { useKnowledgeEntryDialog } from '@/composables/knowledge/useKnowledgeEntryDialog'
import { exportEntries } from '@/composables/knowledge/knowledgeEntryExport'
import type { ExportFormat } from '@/composables/knowledge/knowledgeEntryExport'
import { formatManPageTitle } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import KnowledgeUploadTab from './KnowledgeUploadTab.vue'
import WatchFoldersPanel from './WatchFoldersPanel.vue'
import ConnectorManager from './connectors/ConnectorManager.vue'
import BulkActionsToolbar from './BulkActionsToolbar.vue'
import KnowledgeEntriesFilters from './KnowledgeEntriesFilters.vue'
import KnowledgeEntriesTable from './KnowledgeEntriesTable.vue'
import KnowledgeEntryDialog from './KnowledgeEntryDialog.vue'
import BulkEditModal from './modals/BulkEditModal.vue'
import type { BulkEditMode, BulkEditEntry } from './modals/BulkEditModal.vue'
import DocumentExportModal from './modals/DocumentExportModal.vue'
import type { ExportDocument } from './modals/DocumentExportModal.vue'
import SourcePreviewPanel from './panels/SourcePreviewPanel.vue'
import type { SourceDocument } from './panels/SourcePreviewPanel.vue'

const logger = createLogger('KnowledgeEntries')
const { t } = useI18n()
const { confirm } = useConfirmDialog()
const store = useKnowledgeStore()
const controller = useKnowledgeController()
const route = useRoute()

// The tab starts from ?tab= so /knowledge/manage?tab=watchFolders (the redirect target of the retired
// watch-folders route) opens on the right tab. Connectors joined the same surface (#16897).
type ManageTab = 'upload' | 'manage' | 'watchFolders' | 'connectors'
const TAB_ICONS: Record<ManageTab, IconName> = { upload: 'upload', manage: 'edit', watchFolders: 'folder', connectors: 'plug' }
const tabItems = computed<TabItem[]>(() =>
  (Object.keys(TAB_ICONS) as ManageTab[]).map((value) => ({ value, label: t(`knowledge.entries.${value}Tab`) })),
)
const manageTab = ref<ManageTab>(
  (Object.keys(TAB_ICONS) as string[]).includes(route.query.tab as string) ? (route.query.tab as ManageTab) : 'upload',
)

const list = useKnowledgeManageList(() => store.documents)
const selection = list.selection
const filtersActive = computed(() => !!(list.searchQuery.value || list.filterCategory.value || list.filterType.value))
const dialog = useKnowledgeEntryDialog((id, updates) => controller.updateDocument(id, updates))

// Bulk edit (#747)
const showBulkEditModal = ref(false)
const bulkEditMode = ref<BulkEditMode>('category')
const openBulkEdit = (mode: BulkEditMode) => {
  bulkEditMode.value = mode
  showBulkEditModal.value = true
}
const selectedBulkEditEntries = computed<BulkEditEntry[]>(() =>
  store.documents
    .filter((doc) => selection.isSelected(doc))
    .map((doc) => ({
      id: doc.id,
      title: formatManPageTitle(doc.title, doc.metadata?.factType, t) || t('knowledge.entries.untitled'),
      category: doc.category,
      tags: doc.tags,
    })),
)

type BulkEditPayload = { mode: BulkEditMode; value: string | string[] | { scope: string; groupIds: string[] } }
async function handleBulkEditConfirm(payload: BulkEditPayload) {
  try {
    const ids = [...selection.selected.value]
    if (payload.mode === 'category') await controller.bulkUpdateCategory(ids, payload.value as string)
    else if (payload.mode === 'tags-add') await controller.bulkAddTags(ids, payload.value as string[])
    else if (payload.mode === 'tags-remove') await controller.bulkRemoveTags(ids, payload.value as string[])
    list.clearSelection()
  } catch (error) {
    logger.error('Bulk edit failed:', error)
  }
}

async function deleteEntry(entry: KnowledgeDocument) {
  const message = t('knowledge.entries.confirmDelete', { title: entry.title || t('knowledge.entries.untitled') })
  if (!(await confirm({ title: t('common.confirm'), message }))) return
  try {
    await controller.deleteDocument(entry.id)
  } catch (error) {
    logger.error('Failed to delete entry:', error)
  }
}

async function deleteSelected() {
  const message = t('knowledge.entries.confirmDeleteSelected', { count: selection.selectedCount.value })
  if (selection.selectedCount.value && !(await confirm({ title: t('common.confirm'), message }))) return
  try {
    await controller.bulkDeleteDocuments([...selection.selected.value])
    selection.clear()
  } catch (error) {
    logger.error('Failed to delete entries:', error)
  }
}

const onBulkExport = (format: ExportFormat) =>
  exportEntries(store.documents.filter((doc) => selection.selected.value.has(doc.id)), format)

// Quick preview (SourcePreviewPanel) and single-document export (DocumentExportModal)
const showPreview = ref(false)
const previewDocument = ref<SourceDocument | null>(null)
const openPreview = (entry: KnowledgeDocument) => {
  previewDocument.value = {
    id: entry.id,
    title: formatManPageTitle(entry.title, entry.metadata?.factType, t) || t('knowledge.entries.untitled'),
    content: entry.content,
    path: entry.source,
    type: entry.type,
    category: entry.category,
    metadata: { wordCount: entry.metadata?.wordCount, source: entry.source },
  }
  showPreview.value = true
}

const showDocumentExport = ref(false)
const exportDocuments = computed<ExportDocument[]>(() => {
  const entry = dialog.currentEntry.value
  return entry ? [{ id: entry.id, title: entry.title || t('knowledge.entries.untitled'), content: entry.content, path: entry.source }] : []
})
const openDocumentExport = () => {
  showDocumentExport.value = true
}

// Always re-read: the list is a projection of the server, not of this session's uploads (#17530).
onMounted(() => controller.loadAllDocuments())
</script>
