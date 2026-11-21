// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useChatSidebarSessions -- the session-list state and actions of the chat sidebar (#18243),
 * moved out of ChatSidebar.vue unchanged in behaviour: title search, multi-select with bulk
 * delete, rename, share, and single delete with the file-stats and knowledge-fact preview.
 */
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useBatchSelection } from '@/composables/useBatchSelection'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { useChatStore, type ChatSession } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import type { FileStats } from '@/composables/useConversationFiles'
import { mapFileList, type BackendFileList } from '@/utils/conversationFileList'
import type { SessionFact } from '@/models/repositories/ChatRepository'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatSidebar')

type FileAction = 'delete' | 'transfer_kb' | 'transfer_shared'

export function useChatSidebarSessions() {
  const { t } = useI18n()
  const store = useChatStore()
  const controller = useChatController()
  const { confirm } = useConfirmDialog()
  const { showToast } = useNotificationBus()

  /** Title shown for a session: its title, else its first user message, else a short id. */
  function getSessionPreview(session: ChatSession): string {
    const fallback = t('chat.sidebar.untitledChat', { id: session.id.slice(-8) })
    if (session.messages.length === 0) return fallback
    const first = session.messages.find((m) => m.sender === 'user')
    if (!first) return session.title || fallback
    return first.content.slice(0, 30) + (first.content.length > 30 ? '...' : '')
  }

  // GH#8987: client-side filter by title over the loaded sessions; archived folders' chats stay searchable.
  const searchQuery = ref('')
  const filteredSessions = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return store.sessions
    return store.sessions.filter((s) => (s.title || getSessionPreview(s)).toLowerCase().includes(q))
  })
  const clearSearch = (): void => {
    searchQuery.value = ''
  }

  // Multi-select
  const selectionMode = ref(false)
  const sessionSelection = useBatchSelection<ChatSession, string>(
    () => store.sessions,
    (s) => s.id,
  )
  const enableSelectionMode = (): void => {
    selectionMode.value = true
    sessionSelection.clear()
  }
  const cancelSelection = (): void => {
    selectionMode.value = false
    sessionSelection.clear()
  }

  async function deleteSelectedSessions(): Promise<void> {
    const count = sessionSelection.selectedCount.value
    if (count === 0) return
    const confirmed = await confirm({
      title: t('common.confirm'),
      message: t('chat.sidebar.confirmDeleteSelected', { count }),
    })
    if (!confirmed) return
    // In parallel: one call per session, not N sequential round trips.
    await Promise.allSettled(
      Array.from(sessionSelection.selected.value).map((id) => controller.deleteChatSession(id)),
    )
    cancelSelection()
  }

  // Rename
  const showEditModal = ref(false)
  const editingName = ref('')
  const editingSession = ref<ChatSession | null>(null)
  const editInput = ref<{ focus: () => void }>()

  async function editSessionName(session: ChatSession): Promise<void> {
    editingSession.value = session
    editingName.value = session.title || ''
    showEditModal.value = true
    await nextTick()
    editInput.value?.focus()
  }
  function cancelEdit(): void {
    showEditModal.value = false
    editingSession.value = null
    editingName.value = ''
  }
  function saveSessionName(): void {
    if (editingSession.value) controller.updateSessionTitle(editingSession.value.id, editingName.value)
    cancelEdit()
  }

  // Share (Issue #689)
  const showShareDialog = ref(false)
  const shareTargetSessionId = ref<string | null>(null)
  function openShareDialog(sessionId: string): void {
    shareTargetSessionId.value = sessionId
    showShareDialog.value = true
  }
  function handleShareComplete(result: Record<string, unknown>): void {
    showShareDialog.value = false
    shareTargetSessionId.value = null
    const sharedWith = (result?.shared_with as string[]) || []
    showToast(t('chat.sidebar.sharedSuccess', { count: sharedWith.length }), 'success')
  }

  // Delete, with the file-stats and knowledge-fact preview (Issue #547)
  const showDeleteDialog = ref(false)
  const deleteTargetSessionId = ref<string | null>(null)
  const deleteFileStats = ref<FileStats | null>(null)
  const deleteKBFacts = ref<SessionFact[] | null>(null)
  const kbFactsLoading = ref(false)

  function resetDeleteDialog(): void {
    showDeleteDialog.value = false
    deleteTargetSessionId.value = null
    deleteFileStats.value = null
    deleteKBFacts.value = null
  }

  async function deleteSession(sessionId: string): Promise<void> {
    deleteTargetSessionId.value = sessionId
    kbFactsLoading.value = true
    deleteKBFacts.value = null
    const [files, facts] = await Promise.allSettled([
      // #20195: the list response is adapted to the dialog's stats shape
      ApiClient.call('get', '/api/conversation-files/conversation/{session_id}/list', { path: { session_id: sessionId } }).then(
        (data) => (data ? mapFileList(data as BackendFileList, '').stats : null),
      ),
      controller.getSessionFacts(sessionId),
    ])
    if (files.status === 'rejected') logger.warn('Failed to fetch file stats, proceeding without file info:', files.reason)
    if (facts.status === 'rejected') logger.warn('Failed to fetch KB facts:', facts.reason)
    deleteFileStats.value = files.status === 'fulfilled' ? files.value : null
    deleteKBFacts.value = facts.status === 'fulfilled' ? facts.value?.facts || null : null
    kbFactsLoading.value = false
    showDeleteDialog.value = true
  }
  function deleteCurrentSession(): void {
    if (store.currentSessionId) void deleteSession(store.currentSessionId)
  }

  /** Issue #547: keep the facts the user ticked; a failure here never blocks the deletion. */
  async function preserveFacts(sessionId: string, factIds: string[]): Promise<void> {
    if (factIds.length === 0) return
    try {
      const result = await controller.preserveSessionFacts(sessionId, factIds, true)
      if (result.updated_count > 0) logger.debug(`Preserved ${result.updated_count} facts before deletion`)
      if (result.errors) logger.warn('Some facts could not be preserved:', result.errors)
    } catch (error) {
      logger.error('Failed to preserve facts, but continuing with deletion:', error)
    }
  }

  function toastDeleted(total: number, preserved: number): void {
    const deleted = total - preserved
    if (total === 0) return showToast(t('chat.sidebar.deletedSuccess'), 'success')
    if (preserved > 0 && deleted > 0) {
      return showToast(t('chat.sidebar.deletedWithFactsMixed', { deleted, preserved }), 'success')
    }
    if (deleted > 0) return showToast(t('chat.sidebar.deletedWithFactsRemoved', { count: deleted }), 'success')
    showToast(t('chat.sidebar.deletedWithFactsPreserved', { count: preserved }), 'success')
  }

  async function handleDeleteConfirm(
    fileAction: string,
    fileOptions: Record<string, unknown> | undefined,
    selectedFactIds: string[] = [],
  ): Promise<void> {
    const sessionId = deleteTargetSessionId.value
    if (!sessionId) return
    try {
      await preserveFacts(sessionId, selectedFactIds)
      await controller.deleteChatSession(sessionId, fileAction as FileAction, fileOptions)
      toastDeleted(deleteKBFacts.value?.length || 0, selectedFactIds.length)
      resetDeleteDialog()
    } catch (error) {
      logger.error('Failed to delete session:', error)
      showToast(t('chat.sidebar.deleteFailed'), 'error')
    }
  }

  return {
    getSessionPreview,
    searchQuery, filteredSessions, clearSearch,
    selectionMode, sessionSelection, enableSelectionMode, cancelSelection, deleteSelectedSessions,
    showEditModal, editingName, editInput, editSessionName, saveSessionName, cancelEdit,
    showShareDialog, shareTargetSessionId, openShareDialog, handleShareComplete,
    showDeleteDialog, deleteTargetSessionId, deleteFileStats, deleteKBFacts, kbFactsLoading,
    deleteSession, deleteCurrentSession, handleDeleteConfirm, handleDeleteCancel: resetDeleteDialog,
  }
}
