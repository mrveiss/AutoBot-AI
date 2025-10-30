<template>
  <div
    class="bg-blueGray-100 border-r border-blueGray-200 flex flex-col h-full overflow-hidden transition-all duration-300 flex-shrink-0"
    :class="{ 'w-12': store.sidebarCollapsed, 'w-80': !store.sidebarCollapsed }"
  >
    <!-- Toggle Button -->
    <button
      class="p-3 border-b border-blueGray-200 text-blueGray-600 hover:bg-blueGray-200 transition-colors flex-shrink-0"
      @click="controller.toggleSidebar()"
      :aria-label="store.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
    >
      <i :class="store.sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left'"></i>
    </button>

    <!-- Sidebar Content - FIXED: Better scroll behavior -->
    <div v-if="!store.sidebarCollapsed" class="flex-1 flex flex-col min-h-0 overflow-hidden">

      <!-- Chat History Section - FIXED: Scrollable area with multi-select -->
      <section class="flex-1 flex flex-col min-h-0 overflow-hidden p-4 pb-0">
        <div class="flex items-center justify-between mb-3 flex-shrink-0">
          <h3 class="text-base font-semibold text-blueGray-700">Chat History</h3>
          <button
            v-if="!selectionMode"
            @click="enableSelectionMode"
            class="text-xs text-blueGray-600 hover:text-indigo-600 transition-colors"
            title="Select multiple"
          >
            <i class="fas fa-check-square mr-1"></i>Select
          </button>
          <div v-else class="flex items-center gap-2">
            <span class="text-xs text-blueGray-600">{{ selectedSessions.size }} selected</span>
            <button
              @click="cancelSelection"
              class="text-xs text-blueGray-600 hover:text-blueGray-800"
            >
              Cancel
            </button>
          </div>
        </div>

        <!-- FIXED: Scrollable chat history container -->
        <div class="flex-1 overflow-y-auto space-y-1.5 pr-1 mb-3" style="scrollbar-width: thin;">
          <div
            v-for="session in store.sessions"
            :key="session.id"
            class="p-2.5 rounded-lg transition-all duration-150 group relative"
            :class="[
              selectionMode ? 'cursor-default' : 'cursor-pointer',
              store.currentSessionId === session.id && !selectionMode
                ? 'bg-indigo-100 border border-indigo-200'
                : selectedSessions.has(session.id)
                ? 'bg-red-50 border border-red-200'
                : 'bg-white hover:bg-blueGray-50 border border-blueGray-200'
            ]"
            @click="selectionMode ? toggleSelection(session.id) : controller.switchToSession(session.id)"
            tabindex="0"
            @keyup.enter="selectionMode ? toggleSelection(session.id) : controller.switchToSession(session.id)"
            @keyup.space="selectionMode ? toggleSelection(session.id) : controller.switchToSession(session.id)"
          >
            <!-- Selection checkbox -->
            <div v-if="selectionMode" class="absolute left-1 top-1">
              <input
                type="checkbox"
                :checked="selectedSessions.has(session.id)"
                @click.stop="toggleSelection(session.id)"
                class="w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
              />
            </div>

            <div class="flex items-start justify-between gap-2" :class="{ 'ml-6': selectionMode }">
              <span class="text-sm text-blueGray-700 truncate flex-1 leading-tight">
                {{ session.title || getSessionPreview(session) }}
              </span>
              <div v-if="!selectionMode" class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                <button
                  class="text-blueGray-400 hover:text-blueGray-600 p-1 rounded"
                  @click.stop="editSessionName(session)"
                  title="Edit Name"
                  tabindex="-1"
                >
                  <i class="fas fa-edit text-xs"></i>
                </button>
                <button
                  class="text-red-400 hover:text-red-600 p-1 rounded"
                  @click.stop="deleteSession(session.id)"
                  title="Delete"
                  tabindex="-1"
                >
                  <i class="fas fa-trash text-xs"></i>
                </button>
              </div>
            </div>

            <!-- Session metadata - FIXED: Smaller, more compact -->
            <div class="text-xs text-blueGray-500 mt-1 flex justify-between leading-tight" :class="{ 'ml-6': selectionMode }">
              <span>{{ session.messages.length }} msgs</span>
              <span>{{ formatDate(session.updatedAt) }}</span>
            </div>
          </div>

          <!-- Empty state -->
          <div v-if="store.sessions.length === 0" class="text-center py-3 text-blueGray-500">
            <i class="fas fa-comments text-xl mb-1 opacity-50"></i>
            <p class="text-xs">No chat sessions yet</p>
          </div>
        </div>

        <!-- Chat Actions - FIXED: More compact, stays at bottom of scrollable area -->
        <div v-if="!selectionMode" class="grid grid-cols-2 gap-1.5 pt-2 border-t border-blueGray-200 flex-shrink-0">
          <button
            class="btn btn-primary text-xs py-1.5 px-2"
            @click="controller.createNewSession()"
            aria-label="Create new chat"
          >
            <i class="fas fa-plus mr-1"></i>
            New
          </button>
          <button
            class="btn btn-secondary text-xs py-1.5 px-2"
            @click="controller.resetCurrentChat()"
            :disabled="!store.currentSessionId"
            aria-label="Reset current chat"
          >
            <i class="fas fa-redo mr-1"></i>
            Reset
          </button>
          <button
            class="btn btn-danger text-xs py-1.5 px-2"
            @click="deleteCurrentSession()"
            :disabled="!store.currentSessionId"
            aria-label="Delete current chat"
          >
            <i class="fas fa-trash mr-1"></i>
            Delete
          </button>
          <button
            class="btn btn-outline text-xs py-1.5 px-2"
            @click="controller.loadChatSessions()"
            aria-label="Refresh chat list"
          >
            <i class="fas fa-sync mr-1"></i>
            Refresh
          </button>
        </div>

        <!-- Selection Mode Actions -->
        <div v-else class="pt-2 border-t border-blueGray-200 flex-shrink-0">
          <button
            class="btn btn-danger w-full text-xs py-2"
            @click="deleteSelectedSessions()"
            :disabled="selectedSessions.size === 0"
            aria-label="Delete selected conversations"
          >
            <i class="fas fa-trash mr-1.5"></i>
            Delete {{ selectedSessions.size }} Selected
          </button>
        </div>
      </section>

      <!-- Display Settings Section - FIXED: More compact -->
      <section class="border-t border-blueGray-200 p-4 pb-3 flex-shrink-0">
        <h3 class="text-base font-semibold text-blueGray-700 mb-2">Message Display</h3>
        <div class="space-y-2">
          <label v-for="setting in displaySettingsConfig" :key="setting.key" class="flex items-center">
            <input
              type="checkbox"
              :checked="getSetting(setting.key)"
              @change="toggleSetting(setting.key, $event.target.checked)"
              class="mr-2 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span class="text-xs text-blueGray-600">{{ setting.label }}</span>
          </label>
        </div>
      </section>

      <!-- System Control Section - FIXED: More compact -->
      <section class="border-t border-blueGray-200 p-4 pb-4 flex-shrink-0">
        <h3 class="text-base font-semibold text-blueGray-700 mb-2">System Control</h3>
        <div class="space-y-1.5">
          <button
            class="btn btn-primary w-full text-xs py-1.5"
            @click="reloadSystem"
            :disabled="isSystemReloading"
            aria-label="Reload system"
          >
            <i class="fas fa-sync mr-1.5" :class="{ 'fa-spin': isSystemReloading }"></i>
            {{ isSystemReloading ? 'Reloading...' : 'Reload System' }}
          </button>

          <!-- System Status -->
          <div class="text-xs text-center text-blueGray-500 mt-1">
            System: {{ systemStatus }}
          </div>
        </div>
      </section>
    </div>
  </div>

  <!-- Delete Conversation Dialog -->
  <DeleteConversationDialog
    :visible="showDeleteDialog"
    :session-id="deleteTargetSessionId || ''"
    :session-name="store.sessions.find(s => s.id === deleteTargetSessionId)?.title"
    :file-stats="deleteFileStats"
    @confirm="handleDeleteConfirm"
    @cancel="handleDeleteCancel"
  />

  <!-- Edit Session Name Modal -->
  <div v-if="showEditModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
    <div class="bg-white rounded-lg p-6 w-96 max-w-90vw">
      <h3 class="text-lg font-semibold mb-4">Edit Chat Name</h3>
      <input
        v-model="editingName"
        type="text"
        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder="Enter chat name..."
        @keyup.enter="saveSessionName"
        @keyup.escape="cancelEdit"
        ref="editInput"
      />
      <div class="flex justify-end gap-2 mt-4">
        <button
          class="px-4 py-2 text-gray-600 hover:text-gray-800"
          @click="cancelEdit"
        >
          Cancel
        </button>
        <button
          class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
          @click="saveSessionName"
        >
          Save
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import type { ChatSession } from '@/stores/useChatStore'
import DeleteConversationDialog from './DeleteConversationDialog.vue'
import type { FileStats } from '@/composables/useConversationFiles'
import ApiClient from '@/utils/ApiClient.js'
import { formatDate } from '@/utils/formatHelpers'

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

// Delete dialog state
const showDeleteDialog = ref(false)
const deleteTargetSessionId = ref<string | null>(null)
const deleteFileStats = ref<FileStats | null>(null)

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

  try {
    const response = await ApiClient.get(`/api/conversation-files/conversation/${sessionId}/list`)
    deleteFileStats.value = response.data?.stats || null
  } catch (error) {
    console.warn('Failed to fetch file stats, proceeding without file info:', error)
    deleteFileStats.value = null
  }

  // Show delete dialog
  showDeleteDialog.value = true
}

const deleteCurrentSession = () => {
  if (store.currentSessionId) {
    deleteSession(store.currentSessionId)
  }
}

const handleDeleteConfirm = async (fileAction: string, fileOptions: any) => {
  if (!deleteTargetSessionId.value) return
  
  try {
    await controller.deleteChatSession(deleteTargetSessionId.value, fileAction as any, fileOptions)
    showDeleteDialog.value = false
    deleteTargetSessionId.value = null
    deleteFileStats.value = null
  } catch (error) {
    console.error('Failed to delete session:', error)
  }
}

const handleDeleteCancel = () => {
  showDeleteDialog.value = false
  deleteTargetSessionId.value = null
  deleteFileStats.value = null
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
    // This would call system reload API
    await new Promise(resolve => setTimeout(resolve, 2000)) // Simulate reload
    systemStatus.value = 'Ready'
  } catch (error) {
    systemStatus.value = 'Error'
    console.error('System reload failed:', error)
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

  // Delete all selected sessions
  for (const sessionId of selectedSessions.value) {
    await controller.deleteChatSession(sessionId)
  }

  // Clear selection mode
  cancelSelection()
}
</script>

<style scoped>
.btn {
  @apply px-3 py-2 rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2;
}

.btn-primary {
  @apply bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500;
}

.btn-secondary {
  @apply bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-500;
}

.btn-danger {
  @apply bg-red-600 text-white hover:bg-red-700 focus:ring-red-500;
}

.btn-outline {
  @apply border border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500;
}

.btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f5f9;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
