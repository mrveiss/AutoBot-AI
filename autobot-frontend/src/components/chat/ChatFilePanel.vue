<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatFilePanel -- the Chat files aside (#22349, on the Refined UI Chat mockup): header with New file, list/grid and
  Close, then the toolbar, the upload target, the file cards, the create / edit dialog and the preview pane. It owns
  the dialog state and the delete confirmations; the data comes from `useConversationFiles`.
-->
<template>
  <aside
    class="chat-file-panel w-80 min-w-80 max-w-80 h-full flex flex-col bg-autobot-bg-card border-l border-autobot-border"
    :aria-label="$t('chat.filePanel.title')"
    tabindex="-1"
    @keydown.escape.self="$emit('close')"
  >
    <div class="flex items-center justify-between p-3 border-b border-autobot-border shrink-0">
      <div class="flex items-center gap-2">
        <Icon name="folder" class="text-autobot-text-secondary" />
        <h2 class="text-sm font-semibold text-autobot-text-primary">{{ $t('chat.filePanel.title') }}</h2>
      </div>
      <div class="flex items-center gap-1">
        <ChatHeaderIconButton :label="$t('chat.filePanel.newFile')" icon="plus" data-testid="new-file" @click="showCreateDialog = true" />
        <ChatHeaderIconButton
          :label="viewMode === 'list' ? $t('chat.filePanel.gridView') : $t('chat.filePanel.listView')"
          :icon="viewMode === 'list' ? 'th' : 'list'"
          data-testid="view-toggle"
          @click="viewMode = viewMode === 'list' ? 'grid' : 'list'"
        />
        <ChatHeaderIconButton :label="$t('chat.filePanel.closePanel')" icon="times" data-testid="close-panel" @click="$emit('close')" />
      </div>
    </div>

    <ChatFilePanelToolbar
      v-model:search="searchQuery"
      :total-files="stats.total_files"
      :total-size-label="totalSizeFormatted"
      :sort-field="sortField"
      :sort-direction="sortDirection"
      :selected-count="selectedCount"
      :all-selected="allSelected"
      @sort="setSort"
      @bulk-delete="handleBulkDelete"
      @select-all="selectAllFiles"
    />
    <ChatFilePanelUpload :loading="loading" :progress="uploadProgress" @files="uploadFiles" />

    <BaseAlert
      v-if="error"
      variant="error"
      size="compact"
      class="shrink-0"
      :message="error"
      dismissible
      :dismiss-label="$t('common.dismiss')"
      @dismiss="clearError"
    />

    <div class="flex-1 overflow-y-auto p-3 file-list [scrollbar-width:thin]" :class="viewMode === 'grid' ? 'grid grid-cols-1 gap-2' : 'space-y-2'">
      <EmptyState
        v-if="!hasFiles && !loading"
        compact
        :description="searchQuery.trim() ? $t('chat.filePanel.noMatches') : $t('chat.filePanel.noFiles')"
      >
        <template #icon><Icon name="folder-open" size="xl" /></template>
      </EmptyState>
      <div v-if="loading && !hasFiles" class="text-center py-8 text-autobot-text-muted">
        <BaseSpinner :label="$t('chat.filePanel.loadingFiles')" />
      </div>
      <ChatFilePanelItem
        v-for="file in sortedFiles"
        :key="file.file_id"
        :file="file"
        :selected="selectedFileIds.has(file.file_id)"
        :icon="getFileIcon(file.mime_type)"
        :size-label="formatFileSize(file.size_bytes)"
        :previewable="isPreviewable(file.mime_type)"
        :editable="isEditable(file.mime_type)"
        @select="toggleFileSelection(file.file_id)"
        @preview="previewFile(file.file_id)"
        @download="downloadFile(file.file_id, file.filename)"
        @delete="handleDelete(file.file_id, file.filename)"
        @edit="startEdit(file.file_id, file.filename)"
        @rename="renameFile(file.file_id, $event)"
        @duplicate="copyFile(file.file_id)"
      />
    </div>

    <ChatFileEditorDialog v-model:open="showCreateDialog" mode="create" @submit="handleCreateFile" />
    <ChatFileEditorDialog
      :open="editingFileId !== null"
      mode="edit"
      :filename="editingFileName"
      :content="editingContent"
      @update:open="closeEdit"
      @submit="handleSaveEdit"
    />
    <!-- Preview Pane: the server-built preview of a listed text attachment (#20906) -->
    <FilePreviewPane v-if="preview || previewLoading" :preview="preview" @close="closePreview" />
  </aside>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseSpinner, EmptyState } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from '@/components/chat/ChatHeaderIconButton.vue'
import ChatFileEditorDialog from '@/components/chat/ChatFileEditorDialog.vue'
import ChatFilePanelItem from '@/components/chat/ChatFilePanelItem.vue'
import ChatFilePanelToolbar from '@/components/chat/ChatFilePanelToolbar.vue'
import ChatFilePanelUpload from '@/components/chat/ChatFilePanelUpload.vue'
import FilePreviewPane from '@/components/chat/FilePreviewPane.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useConversationFiles } from '@/composables/useConversationFiles'
import { useLatestRequest } from '@/composables/useLatestRequest'

const props = defineProps<{ sessionId: string }>()
defineEmits<{ close: [] }>()

const { t } = useI18n()
const { confirm } = useConfirmDialog()

const {
  stats, loading, error, preview, previewLoading, closePreview, resetForSession, uploadProgress,
  hasFiles, totalSizeFormatted, sortedFiles, searchQuery, sortField, sortDirection, selectedCount,
  allSelected, selectedFileIds, loadFiles, uploadFiles, deleteFile, downloadFile, previewFile, createFile,
  renameFile, getFileContent, updateFileContent, copyFile, toggleFileSelection, selectAllFiles,
  deleteSelectedFiles, setSort, getFileIcon, formatFileSize, isPreviewable, isEditable, clearError,
} = useConversationFiles(() => props.sessionId)

const viewMode = ref<'list' | 'grid'>('list')
const showCreateDialog = ref(false)
const editingFileId = ref<string | null>(null)
const editingContent = ref('')
const editingFileName = ref('')

async function handleDelete(fileId: string, filename: string): Promise<void> {
  if (await confirm({ title: t('common.confirm'), message: t('chat.filePanel.confirmDelete', { name: filename }) })) {
    await deleteFile(fileId)
  }
}

async function handleBulkDelete(): Promise<void> {
  if (await confirm({ title: t('common.confirm'), message: t('chat.filePanel.confirmBulkDelete', { count: selectedCount.value }) })) {
    await deleteSelectedFiles()
  }
}

async function handleCreateFile(draft: { name: string; content: string }): Promise<void> {
  if (!draft.name) return
  await createFile(draft.name, draft.content)
  showCreateDialog.value = false
}

/** Only the latest edit-open may fill the editor; a session switch or a newer open revokes the one in flight (#21337). */
const editOpen = useLatestRequest()

async function startEdit(fileId: string, filename: string): Promise<void> {
  const token = editOpen.begin()
  const content = await getFileContent(fileId)
  if (content !== null && editOpen.isCurrent(token)) {
    editingContent.value = content
    editingFileName.value = filename
    editingFileId.value = fileId
  }
}

function closeEdit(): void {
  editingFileId.value = null
  editingContent.value = ''
  editingFileName.value = ''
}

async function handleSaveEdit(draft: { content: string }): Promise<void> {
  if (!editingFileId.value) return
  await updateFileContent(editingFileId.value, draft.content)
  closeEdit()
}

// Keyboard shortcuts: Ctrl+N opens the create dialog, Delete removes the selection.
/** True while the user is typing: Delete there edits text, it must never delete files. */
function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.ctrlKey && event.key === 'n') {
    event.preventDefault()
    showCreateDialog.value = true
  }
  if (event.key === 'Delete' && selectedCount.value > 0 && !isTypingTarget(event.target)) handleBulkDelete()
}

onMounted(() => {
  if (props.sessionId) loadFiles()
  document.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))

watch(() => props.sessionId, (newSessionId) => {
  resetForSession()
  // A draft belongs to the file of the previous conversation; saving it here would write into the new one (#21337).
  editOpen.invalidate()
  closeEdit()
  if (newSessionId) loadFiles()
})
</script>
