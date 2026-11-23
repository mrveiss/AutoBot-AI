// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useChatSidebarSessions -- the session-list state and actions of the chat sidebar (#18243),
 * moved out of ChatSidebar.vue unchanged in behaviour: title search, multi-select with bulk
 * delete, rename, share, and single delete with the file-stats and knowledge-fact preview.
 */
import { computed, ref } from 'vue'
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
    const matches = (s: ChatSession) => !q || (s.title || getSessionPreview(s)).toLowerCase().includes(q)
    return store.sessions.filter((s) => !s.unassigned && matches(s))
  })
  // #21997: chats that carry no company stay apart, in the Unassigned group, until a person assigns one.
  const unassignedSessions = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    return store.sessions.filter((s) => s.unassigned && (!q || (s.title || getSessionPreview(s)).toLowerCase().includes(q)))
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

  // The dialog's text field carries `data-autofocus`, so BaseModal's initial focus lands on it.
  function editSessionName(session: ChatSession): void {
    editingSession.value = session
    editingName.value = session.title || ''
    showEditModal.value = true
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
  /** True when the file or knowledge preview failed to load: a failure, not an empty result. */
  const deletePreviewFailed = ref(false)

  function resetDeleteDialog(): void {
    showDeleteDialog.value = false
    deleteTargetSessionId.value = null
    deleteFileStats.value = null
    deleteKBFacts.value = null
  }

  async function deleteSession(sessionId: string): Promise<void> {
    deleteTargetSessionId.value = sessionId
    kbFactsLoading.value = true
    deletePreviewFailed.value = false
    deleteKBFacts.value = null
    const [files, facts] = await Promise.allSettled([
      // #20195: the list response is adapted to the dialog's stats shape
      ApiClient.call('get', '/api/conversation-files/conversation/{session_id}/list', { path: { session_id: sessionId } }).then(
        (data) => (data ? mapFileList(data as BackendFileList, '').stats : null),
      ),
      controller.getSessionFacts(sessionId),
    ])
    // A newer deleteSession retargeted the dialog while this one loaded: its previews are not ours to publish.
    if (deleteTargetSessionId.value !== sessionId) return
    publishPreview(files, facts)
    showDeleteDialog.value = true
  }

  function publishPreview(
    files: PromiseSettledResult<FileStats | null>,
    facts: PromiseSettledResult<{ facts?: SessionFact[] } | null | undefined>,
  ): void {
    if (files.status === 'rejected') logger.warn('Failed to fetch file stats, proceeding without file info:', files.reason)
    if (facts.status === 'rejected') logger.warn('Failed to fetch KB facts:', facts.reason)
    deletePreviewFailed.value = files.status === 'rejected' || facts.status === 'rejected'
    if (deletePreviewFailed.value) showToast(t('chat.sidebar.previewFailed'), 'warning')
    deleteFileStats.value = files.status === 'fulfilled' ? files.value : null
    deleteKBFacts.value = facts.status === 'fulfilled' ? facts.value?.facts || null : null
    kbFactsLoading.value = false
  }
  function deleteCurrentSession(): void {
    if (store.currentSessionId) void deleteSession(store.currentSessionId)
  }

  /**
   * Issue #547: keep the facts the user ticked; a failure here never blocks the deletion.
   * Returns how many facts the backend confirmed as preserved (0 on failure).
   */
  async function preserveFacts(sessionId: string, factIds: string[]): Promise<number> {
    if (factIds.length === 0) return 0
    try {
      const result = await controller.preserveSessionFacts(sessionId, factIds, true)
      if (result.updated_count > 0) logger.debug(`Preserved ${result.updated_count} facts before deletion`)
      if (result.errors) logger.warn('Some facts could not be preserved:', result.errors)
      return result.updated_count ?? 0
    } catch (error) {
      logger.error('Failed to preserve facts, but continuing with deletion:', error)
      return 0
    }
  }

  /** The strings count chats (singular or plural), and this flow deletes exactly one (#21996). */
  function toastDeleted(total: number, preserved: number): void {
    const count = 1
    const deleted = total - preserved
    const say = (key: string) => showToast(t(key, { count }, count), 'success')
    if (total === 0) return say('chat.sidebar.deletedSuccess')
    if (preserved > 0 && deleted > 0) return say('chat.sidebar.deletedWithFactsMixed')
    if (deleted > 0) return say('chat.sidebar.deletedWithFactsRemoved')
    say('chat.sidebar.deletedWithFactsPreserved')
  }

  async function handleDeleteConfirm(
    fileAction: string,
    fileOptions: Record<string, unknown> | undefined,
    selectedFactIds: string[] = [],
  ): Promise<void> {
    const sessionId = deleteTargetSessionId.value
    if (!sessionId) return
    try {
      const preserved = await preserveFacts(sessionId, selectedFactIds)
      await controller.deleteChatSession(sessionId, fileAction as FileAction, fileOptions)
      // The toast reports what the backend confirmed, not what was ticked.
      toastDeleted(deleteKBFacts.value?.length || 0, preserved)
      if (preserved < selectedFactIds.length) showToast(t('chat.sidebar.preserveFailed'), 'warning')
      resetDeleteDialog()
    } catch (error) {
      logger.error('Failed to delete session:', error)
      showToast(t('chat.sidebar.deleteFailed'), 'error')
    }
  }

  return {
    getSessionPreview,
    searchQuery, filteredSessions, unassignedSessions, clearSearch,
    selectionMode, sessionSelection, enableSelectionMode, cancelSelection, deleteSelectedSessions,
    showEditModal, editingName, editSessionName, saveSessionName, cancelEdit,
    showShareDialog, shareTargetSessionId, openShareDialog, handleShareComplete,
    showDeleteDialog, deleteTargetSessionId, deleteFileStats, deleteKBFacts, kbFactsLoading, deletePreviewFailed,
    deleteSession, deleteCurrentSession, handleDeleteConfirm, handleDeleteCancel: resetDeleteDialog,
  }
}
