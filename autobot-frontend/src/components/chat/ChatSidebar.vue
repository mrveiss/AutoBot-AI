<template>
  <div
    class="bg-autobot-bg-secondary border-r border-autobot-border flex flex-col h-full overflow-hidden transition-all duration-300 shrink-0"
    :class="{ 'w-12': store.sidebarCollapsed, 'w-80': !store.sidebarCollapsed }"
  >
    <!-- Toggle Button row: desktop collapse toggle + mobile close button (#1804) -->
    <div class="flex items-center border-b border-autobot-border shrink-0">
      <BaseButton
        variant="ghost"
        class="flex-1 p-3 text-autobot-text-secondary hidden lg:flex"
        @click="controller.toggleSidebar()"
        :aria-label="store.sidebarCollapsed ? $t('chat.sidebar.expandSidebar') : $t('chat.sidebar.collapseSidebar')"
      >
        <Icon :name="store.sidebarCollapsed ? 'chevron-right' : 'chevron-left'" />
      </BaseButton>
      <!--
        Mobile header: close button only.

        #5456: previously also rendered a `<span>{{ chatHistory }}</span>`
        title which duplicated the `<h3>` below on L36 — in the DOM at
        all viewports (CSS media queries don't hide the subtree from
        jsdom / a11y readers in every case). The `<h3>` serves as the
        single accessible section heading; the mobile header keeps just
        the close button, which already has an `aria-label`.
      -->
      <div class="lg:hidden flex items-center justify-end w-full px-3 py-2">
        <BaseButton
          variant="ghost"
          class="p-2 text-autobot-text-secondary"
          @click="emit('close-mobile')"
          :aria-label="$t('common.close')"
        >
          <Icon name="times" />
        </BaseButton>
      </div>
    </div>

    <!-- Sidebar Content - FIXED: Better scroll behavior -->
    <div v-if="!store.sidebarCollapsed" class="flex-1 flex flex-col min-h-0 overflow-hidden">

      <!-- Folders Section (GH#8987) -->
      <section v-if="folderStore.folders.length > 0" class="border-b border-autobot-border p-3 pb-2 shrink-0 max-h-56 overflow-y-auto" style="scrollbar-width: thin;">
        <div class="flex items-center justify-between mb-1">
          <button
            class="flex items-center gap-1 text-xs font-semibold text-autobot-text-secondary hover:text-autobot-text-primary transition-colors"
            @click="showFolders = !showFolders"
          >
            <Icon :name="showFolders ? 'chevron-down' : 'chevron-right'" class="text-xs" />
            {{ $t('chat.folders.folders') }}
            <span v-if="folderStore.folders.length" class="text-autobot-text-muted font-normal">({{ folderStore.folders.length }})</span>
          </button>
        </div>
        <ChatFolderTree
          v-if="showFolders"
          :sessions="filteredSessions"
          :current-session-id="store.currentSessionId"
          @session-click="(id) => controller.switchToSession(id)"
        />

        <!-- GH#8987: Archived folders (hidden by default, chats remain searchable) -->
        <div v-if="folderStore.archivedFolders.length > 0" class="mt-2 pt-2 border-t border-autobot-border">
          <button
            class="flex items-center gap-1 text-xs font-semibold text-autobot-text-muted hover:text-autobot-text-secondary transition-colors"
            @click="showArchived = !showArchived"
          >
            <Icon :name="showArchived ? 'chevron-down' : 'chevron-right'" class="text-xs" />
            {{ $t('chat.folders.archived') }}
            <span class="font-normal">({{ folderStore.archivedFolders.length }})</span>
          </button>
          <FolderNode
            v-for="folder in folderStore.archivedFolders"
            v-show="showArchived"
            :key="folder.id"
            :folder="folder"
            :depth="0"
            :sessions="filteredSessions"
            :current-session-id="store.currentSessionId"
            @session-click="(id) => controller.switchToSession(id)"
          />
        </div>
      </section>

      <!-- Chat History Section - FIXED: Scrollable area with multi-select -->
      <section class="flex-1 flex flex-col min-h-0 overflow-hidden p-4 pb-0">
        <div class="flex items-center justify-between mb-3 shrink-0">
          <h3 class="text-base font-semibold text-autobot-text-primary">{{ $t('chat.sidebar.chatHistory') }}</h3>
          <BaseButton
            v-if="!selectionMode"
            @click="enableSelectionMode"
            variant="ghost"
            size="xs"
            class="text-autobot-text-secondary"
            :title="$t('chat.sidebar.selectMultiple')"
          >
            <Icon name="check-square" class="me-1" />{{ $t('common.select') }}
          </BaseButton>
          <div v-else class="flex items-center gap-2">
            <span class="text-xs text-autobot-text-secondary">{{ $t('chat.sidebar.nSelected', { count: sessionSelection.selectedCount.value }) }}</span>
            <BaseButton
              @click="cancelSelection"
              variant="ghost"
              size="xs"
              class="text-autobot-text-secondary"
            >
              {{ $t('common.cancel') }}
            </BaseButton>
          </div>
        </div>

        <!-- GH#8987: Search / filter chats by title (across folders) -->
        <div class="relative mb-2 shrink-0">
          <Icon name="search" class="absolute start-2 top-1/2 -translate-y-1/2 text-xs text-autobot-text-muted pointer-events-none" />
          <input
            id="chat-search"
            v-model="searchQuery"
            type="search"
            class="w-full text-xs ps-7 pe-7 py-1.5 border border-autobot-border rounded bg-autobot-bg-card focus:outline-none focus:ring-1 focus:ring-electric-500"
            :placeholder="$t('chat.sidebar.searchChats')"
            :aria-label="$t('chat.sidebar.searchChats')"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="absolute end-2 top-1/2 -translate-y-1/2 text-autobot-text-muted hover:text-autobot-text-primary"
            :aria-label="$t('common.clear')"
            @click="clearSearch"
          >
            <Icon name="times" class="text-xs" />
          </button>
        </div>

        <!-- FIXED: Scrollable chat history container -->
        <div class="flex-1 overflow-y-auto space-y-1.5 pe-1 mb-3" style="scrollbar-width: thin;">
          <div
            v-for="(session, index) in filteredSessions"
            :key="session.id"
            :ref="el => setSessionRef(el as HTMLElement | null, index)"
            class="p-2.5 rounded-lg transition-all duration-150 group relative"
            :class="[
              selectionMode ? 'cursor-default' : 'cursor-pointer',
              store.currentSessionId === session.id && !selectionMode
                ? 'bg-electric-100 border border-electric-200'
                : sessionSelection.isSelected(session)
                ? 'bg-red-50 border border-red-200'
                : 'bg-autobot-bg-card hover:bg-autobot-bg-secondary border border-autobot-border'
            ]"
            :tabindex="index === focusedIndex ? 0 : -1"
            :aria-selected="index === focusedIndex"
            role="button"
            @click="handleSessionClick(session, index)"
            @keydown="handleSessionKeydown($event, session, index)"
            @focus="focusedIndex = index"
          >
            <!-- Selection checkbox -->
            <div v-if="selectionMode" class="absolute inset-s-1 top-1">
              <input
                type="checkbox"
                :checked="sessionSelection.isSelected(session)"
                @click.stop="sessionSelection.toggle(session)"
                class="w-4 h-4 rounded border-autobot-border text-red-600 focus:ring-red-500"
              />
            </div>

            <div class="flex items-start justify-between gap-2" :class="{ 'ms-6': selectionMode }">
              <span class="text-sm text-autobot-text-primary truncate flex-1 leading-tight">
                {{ session.title || getSessionPreview(session) }}
              </span>
              <div v-if="!selectionMode" class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <!-- GH#8987: Assign to folder -->
                <div class="relative" @click.stop>
                  <BaseButton
                    variant="ghost"
                    size="xs"
                    class="text-autobot-text-muted p-1"
                    :title="$t('chat.folders.assignToFolder')"
                    tabindex="-1"
                    @click.stop="folderAssignTarget = folderAssignTarget === session.id ? null : session.id"
                  >
                    <Icon name="folder" class="text-xs" />
                  </BaseButton>
                  <div
                    v-if="folderAssignTarget === session.id"
                    class="absolute end-0 top-6 z-50 min-w-36 bg-autobot-bg-card border border-autobot-border rounded shadow-lg p-1 text-xs"
                  >
                    <button
                      class="w-full text-start px-2 py-1 rounded hover:bg-autobot-bg-secondary text-autobot-text-muted"
                      @click="folderStore.assignSessionToFolder(session.id, null); folderAssignTarget = null"
                    >
                      {{ $t('chat.folders.removeFromFolder') }}
                    </button>
                    <hr class="border-autobot-border my-0.5" />
                    <button
                      v-for="f in folderStore.folders"
                      :key="f.id"
                      class="w-full text-start px-2 py-1 rounded hover:bg-autobot-bg-secondary text-autobot-text-primary"
                      @click="folderStore.assignSessionToFolder(session.id, f.id); folderAssignTarget = null"
                    >
                      <Icon name="folder" class="text-xs me-1" />{{ f.name }}
                    </button>
                  </div>
                </div>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-autobot-primary p-1"
                  @click.stop="openShareDialog(session.id)"
                  :title="$t('common.share')"
                  tabindex="-1"
                >
                  <Icon name="share-alt" class="text-xs" />
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-autobot-text-muted p-1"
                  @click.stop="editSessionName(session)"
                  :title="$t('chat.editName')"
                  tabindex="-1"
                >
                  <Icon name="edit" class="text-xs" />
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-red-400 p-1"
                  @click.stop="deleteSession(session.id)"
                  :title="$t('common.delete')"
                  tabindex="-1"
                >
                  <Icon name="trash" class="text-xs" />
                </BaseButton>
              </div>
            </div>

            <!-- Session metadata - FIXED: Smaller, more compact -->
            <div class="text-xs text-autobot-text-secondary mt-1 flex justify-between leading-tight" :class="{ 'ms-6': selectionMode }">
              <span>{{ $t('chat.sidebar.nMsgs', { count: session.messages.length }) }}</span>
              <span>{{ formatDate(session.updatedAt) }}</span>
            </div>
          </div>

          <!-- Empty state -->
          <EmptyState
            v-if="store.sessions.length === 0"
            icon="comments"
            :message="$t('chat.sidebar.noSessions')"
          />
          <!-- GH#8987: No search results -->
          <EmptyState
            v-else-if="filteredSessions.length === 0"
            icon="search"
            :message="$t('chat.sidebar.noSearchResults')"
          />
        </div>

        <!-- Chat Actions - FIXED: More compact, stays at bottom of scrollable area -->
        <div v-if="!selectionMode" class="grid grid-cols-2 gap-1.5 pt-2 border-t border-autobot-border shrink-0">
          <BaseButton
            variant="primary"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.createNewSession()"
            :aria-label="$t('chat.sidebar.createNew')"
          >
            <Icon name="plus" class="me-1" />
            {{ $t('chat.sidebar.new') }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.resetCurrentChat()"
            :disabled="!store.currentSessionId"
            :aria-label="$t('chat.sidebar.resetChat')"
          >
            <Icon name="redo" class="me-1" />
            {{ $t('common.reset') }}
          </BaseButton>
          <BaseButton
            variant="error"
            size="xs"
            class="py-1.5 px-2"
            @click="deleteCurrentSession()"
            :disabled="!store.currentSessionId"
            :aria-label="$t('chat.sidebar.deleteChat')"
          >
            <Icon name="trash" class="me-1" />
            {{ $t('common.delete') }}
          </BaseButton>
          <BaseButton
            variant="outline-solid"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.loadChatSessions()"
            :aria-label="$t('chat.sidebar.refreshList')"
          >
            <Icon name="sync" class="me-1" />
            {{ $t('common.refresh') }}
          </BaseButton>
        </div>

        <!-- Selection Mode Actions -->
        <div v-else class="pt-2 border-t border-autobot-border shrink-0">
          <BaseButton
            variant="error"
            size="xs"
            class="w-full py-2"
            @click="deleteSelectedSessions()"
            :disabled="sessionSelection.selectedCount.value === 0"
            :aria-label="$t('chat.sidebar.deleteSelected')"
          >
            <Icon name="trash" class="me-1.5" />
            {{ $t('chat.sidebar.deleteNSelected', { count: sessionSelection.selectedCount.value }) }}
          </BaseButton>
        </div>
      </section>

      <!-- TASK 10: "Message Display" settings moved to the chat header's
           settings panel (gear icon → ChatSettingsModal). -->

      <!-- System Control Section - FIXED: More compact -->
      <section class="border-t border-autobot-border p-4 pb-4 shrink-0">
        <h3 class="text-base font-semibold text-autobot-text-primary mb-2">{{ $t('chat.sidebar.systemControl') }}</h3>
        <div class="space-y-1.5">
          <BaseButton
            variant="primary"
            size="xs"
            class="w-full py-1.5"
            @click="reloadSystem"
            :loading="isSystemReloading"
            :aria-label="$t('chat.sidebar.reloadSystem')"
          >
            <Icon name="sync" class="me-1.5" />
            {{ isSystemReloading ? $t('chat.sidebar.reloading') : $t('chat.sidebar.reloadSystem') }}
          </BaseButton>

          <!-- System Status -->
          <div class="text-xs text-center text-autobot-text-secondary mt-1">
            {{ $t('chat.sidebar.system') }}: {{ systemStatus }}
          </div>
        </div>
      </section>
    </div>
  </div>

  <!-- Delete Conversation Dialog (Issue #547: Added KB facts preview) -->
  <DeleteConversationDialog
    :visible="showDeleteDialog"
    :session-id="deleteTargetSessionId || ''"
    :session-name="store.sessions.find(s => s.id === deleteTargetSessionId)?.title"
    :file-stats="deleteFileStats"
    :kb-facts="deleteKBFacts"
    :kb-facts-loading="kbFactsLoading"
    @confirm="handleDeleteConfirm"
    @cancel="handleDeleteCancel"
  />

  <!-- Share Conversation Dialog (Issue #689) -->
  <ShareConversationDialog
    :visible="showShareDialog"
    :session-id="shareTargetSessionId || ''"
    @update:visible="showShareDialog = $event"
    @shared="handleShareComplete"
    @cancel="showShareDialog = false"
  />

  <!-- Edit Session Name Modal -->
  <BaseModal
    v-model="showEditModal"
    :title="$t('chat.sidebar.editChatName')"
    size="md"
  >
    <input
      v-model="editingName"
      type="text"
      class="w-full px-3 py-2 border border-autobot-border rounded-md focus:outline-none focus:ring-2 focus:ring-electric-500"
      :placeholder="$t('chat.sidebar.enterChatName')"
      @keyup.enter="saveSessionName"
      @keyup.escape="cancelEdit"
      ref="editInput"
    />

    <template #actions>
      <BaseButton
        variant="secondary"
        @click="cancelEdit"
      >
        {{ $t('common.cancel') }}
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="saveSessionName"
      >
        {{ $t('common.save') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

// #1804: emit close-mobile so ChatInterface can close the mobile overlay
const emit = defineEmits<{ 'close-mobile': [] }>()
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import ChatFolderTree from './ChatFolderTree.vue'
import FolderNode from './ChatFolderNode.vue'
import { useFolderStore } from '@/stores/useFolderStore'
import { useBatchSelection } from '@/composables/useBatchSelection'
import type { ChatSession } from '@/stores/useChatStore'
import DeleteConversationDialog from './DeleteConversationDialog.vue'
import ShareConversationDialog from './ShareConversationDialog.vue'
import type { FileStats } from '@/composables/useConversationFiles'
import type { SessionFact } from '@/models/repositories/ChatRepository'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { formatDate } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { BaseModal } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import { useNotificationBus } from '@/composables/useNotificationBus'

const logger = createLogger('ChatSidebar')

const { t } = useI18n()
const store = useChatStore()
const controller = useChatController()
const folderStore = useFolderStore()

// GH#8987: state for folder section
const showFolders = ref(true)
const showArchived = ref(false)
const folderAssignTarget = ref<string | null>(null)

// GH#8987: in-folder / chat-list search. Client-side filter by title over
// the already-loaded sessions; archived folders' chats stay searchable.
const searchQuery = ref('')
const filteredSessions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return store.sessions
  return store.sessions.filter((s) =>
    (s.title || getSessionPreview(s)).toLowerCase().includes(q)
  )
})
const clearSearch = () => {
  searchQuery.value = ''
}

onMounted(() => {
  folderStore.fetchFolders()
})

// Local state
const showEditModal = ref(false)
const editingName = ref('')
const editingSession = ref<ChatSession | null>(null)
const editInput = ref<HTMLInputElement>()
const isSystemReloading = ref(false)
const systemStatus = ref(t('status.ready'))

// Multi-select state
const selectionMode = ref(false)
const sessionSelection = useBatchSelection<ChatSession, string>(
  () => store.sessions,
  (s) => s.id
)

// Keyboard navigation state
const focusedIndex = ref(0)
const sessionRefs = ref<(HTMLElement | null)[]>([])

// Set session reference for keyboard navigation
const setSessionRef = (el: HTMLElement | null, index: number) => {
  if (el) {
    sessionRefs.value[index] = el
  }
}

// Handle session click (mouse or keyboard activation)
const handleSessionClick = (session: ChatSession, index: number) => {
  focusedIndex.value = index

  if (selectionMode.value) {
    sessionSelection.toggle(session)
  } else {
    controller.switchToSession(session.id)
    // #1804: close mobile overlay after selecting a session
    emit('close-mobile')
  }
}

// Handle keyboard navigation
const handleSessionKeydown = (event: KeyboardEvent, session: ChatSession, index: number) => {
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      if (index < filteredSessions.value.length - 1) {
        focusedIndex.value = index + 1
        nextTick(() => {
          sessionRefs.value[index + 1]?.focus()
        })
      }
      break

    case 'ArrowUp':
      event.preventDefault()
      if (index > 0) {
        focusedIndex.value = index - 1
        nextTick(() => {
          sessionRefs.value[index - 1]?.focus()
        })
      }
      break

    case 'Home':
      event.preventDefault()
      focusedIndex.value = 0
      nextTick(() => {
        sessionRefs.value[0]?.focus()
      })
      break

    case 'End':
      event.preventDefault()
      focusedIndex.value = filteredSessions.value.length - 1
      nextTick(() => {
        sessionRefs.value[filteredSessions.value.length - 1]?.focus()
      })
      break

    case 'Enter':
    case ' ':
      event.preventDefault()
      handleSessionClick(session, index)
      break
  }
}

// Delete dialog state
const showDeleteDialog = ref(false)
const deleteTargetSessionId = ref<string | null>(null)
const deleteFileStats = ref<FileStats | null>(null)
const deleteKBFacts = ref<SessionFact[] | null>(null)
const kbFactsLoading = ref(false)

// Share dialog state (Issue #689)
const showShareDialog = ref(false)
const shareTargetSessionId = ref<string | null>(null)

// Toast for notifications (Issue #547)
const { showToast } = useNotificationBus()

// Methods
const getSessionPreview = (session: ChatSession): string => {
  if (session.messages.length === 0) {
    return `Chat ${session.id.slice(-8)}...`
  }

  const firstUserMessage = session.messages.find(m => m.sender === 'user')
  if (firstUserMessage) {
    return firstUserMessage.content.slice(0, 30) + (firstUserMessage.content.length > 30 ? '...' : '')
  }

  return session.title || `Chat ${session.id.slice(-8)}...`
}

const editSessionName = async (session: ChatSession) => {
  editingSession.value = session
  editingName.value = session.title || ''
  showEditModal.value = true

  await nextTick()
  editInput.value?.focus()
}

const saveSessionName = () => {
  if (editingSession.value) {
    controller.updateSessionTitle(editingSession.value.id, editingName.value)
  }
  cancelEdit()
}

const cancelEdit = () => {
  showEditModal.value = false
  editingSession.value = null
  editingName.value = ''
}

const deleteSession = async (sessionId: string) => {
  // Fetch file stats for the session
  deleteTargetSessionId.value = sessionId
  kbFactsLoading.value = true
  deleteKBFacts.value = null

  // Fetch file stats and KB facts in parallel (Issue #547)
  const [fileStatsResult, kbFactsResult] = await Promise.allSettled([
    // Fetch file stats
    (async () => {
      const data = await ApiClient.get<{ stats?: FileStats }>(`${getApiBase()}/conversation-files/conversation/${sessionId}/list`)
      return data?.stats || null
    })(),
    // Fetch KB facts (Issue #547)
    controller.getSessionFacts(sessionId)
  ])

  // Handle file stats result
  if (fileStatsResult.status === 'fulfilled') {
    deleteFileStats.value = fileStatsResult.value
  } else {
    logger.warn('Failed to fetch file stats, proceeding without file info:', fileStatsResult.reason)
    deleteFileStats.value = null
  }

  // Handle KB facts result (Issue #547)
  if (kbFactsResult.status === 'fulfilled') {
    deleteKBFacts.value = kbFactsResult.value?.facts || null
    logger.debug(`Found ${deleteKBFacts.value?.length || 0} KB facts for session ${sessionId}`)
  } else {
    logger.warn('Failed to fetch KB facts:', kbFactsResult.reason)
    deleteKBFacts.value = null
  }

  kbFactsLoading.value = false

  // Show delete dialog
  showDeleteDialog.value = true
}

const deleteCurrentSession = () => {
  if (store.currentSessionId) {
    deleteSession(store.currentSessionId)
  }
}

const handleDeleteConfirm = async (fileAction: string, fileOptions: Record<string, unknown>, selectedFactIds: string[] = []) => {
  if (!deleteTargetSessionId.value) return
  const sessionId = deleteTargetSessionId.value

  try {
    // Issue #547: Preserve selected facts before deletion
    if (selectedFactIds.length > 0) {
      try {
        const preserveResult = await controller.preserveSessionFacts(sessionId, selectedFactIds, true)
        if (preserveResult.updated_count > 0) {
          logger.debug(`Preserved ${preserveResult.updated_count} facts before deletion`)
        }
        if (preserveResult.errors) {
          logger.warn('Some facts could not be preserved:', preserveResult.errors)
        }
      } catch (preserveError) {
        logger.error('Failed to preserve facts, but continuing with deletion:', preserveError)
        // Continue with deletion even if preservation fails
      }
    }

    // Delete the session
    await controller.deleteChatSession(sessionId, fileAction as 'delete' | 'transfer_kb' | 'transfer_shared', fileOptions)

    // Issue #547: Show toast with KB cleanup results
    const totalFacts = deleteKBFacts.value?.length || 0
    const preservedCount = selectedFactIds.length
    const deletedCount = totalFacts - preservedCount

    if (totalFacts > 0) {
      if (preservedCount > 0 && deletedCount > 0) {
        showToast(t('chat.sidebar.deletedWithFactsMixed', { deleted: deletedCount, preserved: preservedCount }), 'success')
      } else if (deletedCount > 0) {
        showToast(t('chat.sidebar.deletedWithFactsRemoved', { count: deletedCount }), 'success')
      } else {
        showToast(t('chat.sidebar.deletedWithFactsPreserved', { count: preservedCount }), 'success')
      }
    } else {
      showToast(t('chat.sidebar.deletedSuccess'), 'success')
    }

    showDeleteDialog.value = false
    deleteTargetSessionId.value = null
    deleteFileStats.value = null
    deleteKBFacts.value = null
  } catch (error) {
    logger.error('Failed to delete session:', error)
    showToast(t('chat.sidebar.deleteFailed'), 'error')
  }
}

const handleDeleteCancel = () => {
  showDeleteDialog.value = false
  deleteTargetSessionId.value = null
  deleteFileStats.value = null
  deleteKBFacts.value = null  // Issue #547
}

// Share session handlers (Issue #689)
const openShareDialog = (sessionId: string) => {
  shareTargetSessionId.value = sessionId
  showShareDialog.value = true
}

const handleShareComplete = (result: Record<string, unknown>) => {
  showShareDialog.value = false
  shareTargetSessionId.value = null
  const sharedWith = (result?.shared_with as string[]) || []
  showToast(t('chat.sidebar.sharedSuccess', { count: sharedWith.length }), 'success')
}

const reloadSystem = async () => {
  isSystemReloading.value = true
  systemStatus.value = t('chat.sidebar.reloading')

  try {
    // Call real system reload API
    const response = await ApiClient.post<unknown>(`${getApiBase()}/system/reload_config`)
    const data = await (response as { json: () => Promise<Record<string, unknown>> }).json()

    if (data && data.success) {
      systemStatus.value = t('status.ready')

      // Log reloaded components for debugging
      if (data.reloaded_components) {
        logger.debug('Reloaded components:', data.reloaded_components)
      }
    } else {
      systemStatus.value = t('common.error')
      logger.error('System reload failed:', data?.message || 'Unknown error')
    }
  } catch (error) {
    systemStatus.value = t('common.error')
    logger.error('System reload failed:', error)
  } finally {
    isSystemReloading.value = false
  }
}

// NOTE: formatDate removed - now using shared utility from @/utils/formatHelpers

// Multi-select functions
const enableSelectionMode = () => {
  selectionMode.value = true
  sessionSelection.clear()
}

const cancelSelection = () => {
  selectionMode.value = false
  sessionSelection.clear()
}

const toggleSelection = (sessionId: string) => {
  sessionSelection.toggleByKey(sessionId)
}

const deleteSelectedSessions = async () => {
  if (sessionSelection.selectedCount.value === 0) return

  const confirmed = confirm(t('chat.sidebar.confirmDeleteSelected', { count: sessionSelection.selectedCount.value }))
  if (!confirmed) return

  // Delete all selected sessions in parallel - eliminates N+1 sequential API calls
  await Promise.allSettled(
    Array.from(sessionSelection.selected.value).map(sessionId =>
      controller.deleteChatSession(sessionId)
    )
  )

  // Clear selection mode
  cancelSelection()
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: var(--bg-secondary);
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-sm);
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* Keyboard focus indicator for chat sessions */
.group:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--color-primary-transparent);
}

.group:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  box-shadow: 0 0 0 2px var(--color-primary-transparent);
}
</style>
