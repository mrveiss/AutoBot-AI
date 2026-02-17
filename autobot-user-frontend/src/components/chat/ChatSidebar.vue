<template>
  <div
    class="bg-blueGray-100 border-r border-blueGray-200 flex flex-col h-full overflow-hidden transition-all duration-300 flex-shrink-0"
    :class="{ 'w-12': store.sidebarCollapsed, 'w-80': !store.sidebarCollapsed }"
  >
    <!-- Toggle Button -->
    <BaseButton
      variant="ghost"
      class="p-3 border-b border-blueGray-200 text-blueGray-600 flex-shrink-0"
      @click="controller.toggleSidebar()"
      :aria-label="store.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
    >
      <i :class="store.sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left'"></i>
    </BaseButton>

    <!-- Sidebar Content - FIXED: Better scroll behavior -->
    <div v-if="!store.sidebarCollapsed" class="flex-1 flex flex-col min-h-0 overflow-hidden">

      <!-- Chat History Section - FIXED: Scrollable area with multi-select -->
      <section class="flex-1 flex flex-col min-h-0 overflow-hidden p-4 pb-0">
        <div class="flex items-center justify-between mb-3 flex-shrink-0">
          <h3 class="text-base font-semibold text-blueGray-700">Chat History</h3>
          <BaseButton
            v-if="!selectionMode"
            @click="enableSelectionMode"
            variant="ghost"
            size="xs"
            class="text-blueGray-600"
            title="Select multiple"
          >
            <i class="fas fa-check-square mr-1"></i>Select
          </BaseButton>
          <div v-else class="flex items-center gap-2">
            <span class="text-xs text-blueGray-600">{{ selectedSessions.size }} selected</span>
            <BaseButton
              @click="cancelSelection"
              variant="ghost"
              size="xs"
              class="text-blueGray-600"
            >
              Cancel
            </BaseButton>
          </div>
        </div>

        <!-- FIXED: Scrollable chat history container -->
        <div class="flex-1 overflow-y-auto space-y-1.5 pr-1 mb-3" style="scrollbar-width: thin;">
          <div
            v-for="(session, index) in store.sessions"
            :key="session.id"
            :ref="el => setSessionRef(el as HTMLElement | null, index)"
            class="p-2.5 rounded-lg transition-all duration-150 group relative"
            :class="[
              selectionMode ? 'cursor-default' : 'cursor-pointer',
              store.currentSessionId === session.id && !selectionMode
                ? 'bg-electric-100 border border-electric-200'
                : selectedSessions.has(session.id)
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
            <div v-if="selectionMode" class="absolute left-1 top-1">
              <input
                type="checkbox"
                :checked="selectedSessions.has(session.id)"
                @click.stop="toggleSelection(session.id)"
                class="w-4 h-4 rounded border-autobot-border text-red-600 focus:ring-red-500"
              />
            </div>

            <div class="flex items-start justify-between gap-2" :class="{ 'ml-6': selectionMode }">
              <span class="text-sm text-blueGray-700 truncate flex-1 leading-tight">
                {{ session.title || getSessionPreview(session) }}
              </span>
              <div v-if="!selectionMode" class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-autobot-primary p-1"
                  @click.stop="openShareDialog(session.id)"
                  title="Share"
                  tabindex="-1"
                >
                  <i class="fas fa-share-alt text-xs"></i>
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-blueGray-400 p-1"
                  @click.stop="editSessionName(session)"
                  title="Edit Name"
                  tabindex="-1"
                >
                  <i class="fas fa-edit text-xs"></i>
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  class="text-red-400 p-1"
                  @click.stop="deleteSession(session.id)"
                  title="Delete"
                  tabindex="-1"
                >
                  <i class="fas fa-trash text-xs"></i>
                </BaseButton>
              </div>
            </div>

            <!-- Session metadata - FIXED: Smaller, more compact -->
            <div class="text-xs text-blueGray-500 mt-1 flex justify-between leading-tight" :class="{ 'ml-6': selectionMode }">
              <span>{{ session.messages.length }} msgs</span>
              <span>{{ formatDate(session.updatedAt) }}</span>
            </div>
          </div>

          <!-- Empty state -->
          <EmptyState
            v-if="store.sessions.length === 0"
            icon="fas fa-comments"
            message="No chat sessions yet"
          />
        </div>

        <!-- Chat Actions - FIXED: More compact, stays at bottom of scrollable area -->
        <div v-if="!selectionMode" class="grid grid-cols-2 gap-1.5 pt-2 border-t border-blueGray-200 flex-shrink-0">
          <BaseButton
            variant="primary"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.createNewSession()"
            aria-label="Create new chat"
          >
            <i class="fas fa-plus mr-1"></i>
            New
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.resetCurrentChat()"
            :disabled="!store.currentSessionId"
            aria-label="Reset current chat"
          >
            <i class="fas fa-redo mr-1"></i>
            Reset
          </BaseButton>
          <BaseButton
            variant="danger"
            size="xs"
            class="py-1.5 px-2"
            @click="deleteCurrentSession()"
            :disabled="!store.currentSessionId"
            aria-label="Delete current chat"
          >
            <i class="fas fa-trash mr-1"></i>
            Delete
          </BaseButton>
          <BaseButton
            variant="outline"
            size="xs"
            class="py-1.5 px-2"
            @click="controller.loadChatSessions()"
            aria-label="Refresh chat list"
          >
            <i class="fas fa-sync mr-1"></i>
            Refresh
          </BaseButton>
        </div>

        <!-- Selection Mode Actions -->
        <div v-else class="pt-2 border-t border-blueGray-200 flex-shrink-0">
          <BaseButton
            variant="danger"
            size="xs"
            class="w-full py-2"
            @click="deleteSelectedSessions()"
            :disabled="selectedSessions.size === 0"
            aria-label="Delete selected conversations"
          >
            <i class="fas fa-trash mr-1.5"></i>
            Delete {{ selectedSessions.size }} Selected
          </BaseButton>
        </div>
      </section>

      <!-- Display Settings Section - FIXED: More compact -->
      <section class="border-t border-blueGray-200 p-4 pb-3 flex-shrink-0">
        <h3 class="text-base font-semibold text-blueGray-700 mb-2">Message Display</h3>
        <div class="space-y-2">
          <label v-for="setting in displaySettingsConfig" :key="setting.key" class="flex items-center">
            <input
              type="checkbox"
              :checked="getSetting(setting.key as keyof DisplaySettings)"
              @change="toggleSetting(setting.key as keyof DisplaySettings, ($event.target as HTMLInputElement)?.checked)"
              class="mr-2 rounded border-autobot-border text-electric-600 focus:ring-electric-500"
            />
            <span class="text-xs text-blueGray-600">{{ setting.label }}</span>
          </label>
        </div>
      </section>

      <!-- System Control Section - FIXED: More compact -->
      <section class="border-t border-blueGray-200 p-4 pb-4 flex-shrink-0">
        <h3 class="text-base font-semibold text-blueGray-700 mb-2">System Control</h3>
        <div class="space-y-1.5">
          <BaseButton
            variant="primary"
            size="xs"
            class="w-full py-1.5"
            @click="reloadSystem"
            :loading="isSystemReloading"
            aria-label="Reload system"
          >
            <i class="fas fa-sync mr-1.5"></i>
            {{ isSystemReloading ? 'Reloading...' : 'Reload System' }}
          </BaseButton>

          <!-- System Status -->
          <div class="text-xs text-center text-blueGray-500 mt-1">
            System: {{ systemStatus }}
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
    title="Edit Chat Name"
    size="medium"
  >
    <input
      v-model="editingName"
      type="text"
      class="w-full px-3 py-2 border border-autobot-border rounded-md focus:outline-none focus:ring-2 focus:ring-electric-500"
      placeholder="Enter chat name..."
      @keyup.enter="saveSessionName"
      @keyup.escape="cancelEdit"
      ref="editInput"
    />

    <template #actions>
      <BaseButton
        variant="secondary"
        @click="cancelEdit"
      >
        Cancel
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="saveSessionName"
      >
        Save
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useDisplaySettings, type DisplaySettings } from '@/composables/useDisplaySettings'
import type { ChatSession } from '@/stores/useChatStore'
import DeleteConversationDialog from './DeleteConversationDialog.vue'
import ShareConversationDialog from './ShareConversationDialog.vue'
import type { FileStats } from '@/composables/useConversationFiles'
import type { SessionFact } from '@/models/repositories/ChatRepository'
import ApiClient from '@/utils/ApiClient'
import { formatDate } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'
import { useToast } from '@/composables/useToast'

const logger = createLogger('ChatSidebar')

const store = useChatStore()
const controller = useChatController()
const { getSetting, setSetting } = useDisplaySettings()

// Local state
const showEditModal = ref(false)
const editingName = ref('')
const editingSession = ref<ChatSession | null>(null)
const editInput = ref<HTMLInputElement>()
const isSystemReloading = ref(false)
const systemStatus = ref('Ready')

// Multi-select state
const selectionMode = ref(false)
const selectedSessions = ref(new Set<string>())

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
    toggleSelection(session.id)
  } else {
    controller.switchToSession(session.id)
  }
}

// Handle keyboard navigation
const handleSessionKeydown = (event: KeyboardEvent, session: ChatSession, index: number) => {
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      if (index < store.sessions.length - 1) {
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
      focusedIndex.value = store.sessions.length - 1
      nextTick(() => {
        sessionRefs.value[store.sessions.length - 1]?.focus()
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
const { showToast } = useToast()

// Display settings configuration (UI labels)
const displaySettingsConfig = [
  { key: 'showThoughts', label: 'Show Thoughts' },
  { key: 'showJson', label: 'Show JSON Output' },
  { key: 'showUtility', label: 'Show Utility Messages' },
  { key: 'showPlanning', label: 'Show Planning Messages' },
  { key: 'showDebug', label: 'Show Debug Messages' },
  { key: 'showSources', label: 'Show Sources' },
  { key: 'autoScroll', label: 'Auto Scroll' }
]

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
      const response = await ApiClient.get(`/api/conversation-files/conversation/${sessionId}/list`)
      const data = await (response as any).json()
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

const handleDeleteConfirm = async (fileAction: string, fileOptions: any, selectedFactIds: string[] = []) => {
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
    await controller.deleteChatSession(sessionId, fileAction as any, fileOptions)

    // Issue #547: Show toast with KB cleanup results
    const totalFacts = deleteKBFacts.value?.length || 0
    const preservedCount = selectedFactIds.length
    const deletedCount = totalFacts - preservedCount

    if (totalFacts > 0) {
      if (preservedCount > 0 && deletedCount > 0) {
        showToast(`Conversation deleted. ${deletedCount} KB fact${deletedCount > 1 ? 's' : ''} removed, ${preservedCount} preserved.`, 'success')
      } else if (deletedCount > 0) {
        showToast(`Conversation deleted. ${deletedCount} KB fact${deletedCount > 1 ? 's' : ''} removed.`, 'success')
      } else {
        showToast(`Conversation deleted. All ${preservedCount} KB fact${preservedCount > 1 ? 's' : ''} preserved.`, 'success')
      }
    } else {
      showToast('Conversation deleted successfully.', 'success')
    }

    showDeleteDialog.value = false
    deleteTargetSessionId.value = null
    deleteFileStats.value = null
    deleteKBFacts.value = null
  } catch (error) {
    logger.error('Failed to delete session:', error)
    showToast('Failed to delete conversation. Please try again.', 'error')
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
  showToast(`Conversation shared with ${sharedWith.length} user${sharedWith.length > 1 ? 's' : ''}.`, 'success')
}

// Toggle setting handler
const toggleSetting = (key: string, value: boolean) => {
  setSetting(key as any, value)

  // Also update chat store settings for autoScroll
  if (key === 'autoScroll') {
    controller.updateChatSettings({ autoSave: value })
  }
}

const reloadSystem = async () => {
  isSystemReloading.value = true
  systemStatus.value = 'Reloading...'

  try {
    // Call real system reload API
    const response = await ApiClient.post('/api/system/reload_config')
    const data = await (response as any).json()

    if (data && data.success) {
      systemStatus.value = 'Ready'

      // Log reloaded components for debugging
      if (data.reloaded_components) {
        logger.debug('Reloaded components:', data.reloaded_components)
      }
    } else {
      systemStatus.value = 'Error'
      logger.error('System reload failed:', data?.message || 'Unknown error')
    }
  } catch (error) {
    systemStatus.value = 'Error'
    logger.error('System reload failed:', error)
  } finally {
    isSystemReloading.value = false
  }
}

// NOTE: formatDate removed - now using shared utility from @/utils/formatHelpers

// Multi-select functions
const enableSelectionMode = () => {
  selectionMode.value = true
  selectedSessions.value = new Set()
}

const cancelSelection = () => {
  selectionMode.value = false
  selectedSessions.value = new Set()
}

const toggleSelection = (sessionId: string) => {
  if (selectedSessions.value.has(sessionId)) {
    selectedSessions.value.delete(sessionId)
  } else {
    selectedSessions.value.add(sessionId)
  }
  // Force reactivity update
  selectedSessions.value = new Set(selectedSessions.value)
}

const deleteSelectedSessions = async () => {
  if (selectedSessions.value.size === 0) return

  const confirmed = confirm(`Delete ${selectedSessions.value.size} conversation(s)? This action cannot be undone.`)
  if (!confirmed) return

  // Delete all selected sessions in parallel - eliminates N+1 sequential API calls
  await Promise.allSettled(
    Array.from(selectedSessions.value).map(sessionId =>
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
  outline: none;
  box-shadow: 0 0 0 2px var(--color-primary-transparent);
}
</style>
