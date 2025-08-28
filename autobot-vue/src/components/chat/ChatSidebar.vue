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

    <!-- Sidebar Content -->
    <div v-if="!store.sidebarCollapsed" class="flex-1 overflow-y-auto p-4">

      <!-- Chat History Section -->
      <section class="mb-6">
        <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Chat History</h3>

        <div class="space-y-2 mb-4">
          <div
            v-for="session in store.sessions"
            :key="session.id"
            class="p-3 rounded-lg cursor-pointer transition-all duration-150 group"
            :class="store.currentSessionId === session.id
              ? 'bg-indigo-100 border border-indigo-200'
              : 'bg-white hover:bg-blueGray-50 border border-blueGray-200'"
            @click="controller.switchToSession(session.id)"
            tabindex="0"
            @keyup.enter="controller.switchToSession(session.id)"
            @keyup.space="controller.switchToSession(session.id)"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm text-blueGray-700 truncate flex-1 mr-2">
                {{ session.title || getSessionPreview(session) }}
              </span>
              <div class="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
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

            <!-- Session metadata -->
            <div class="text-xs text-blueGray-500 mt-1 flex justify-between">
              <span>{{ session.messages.length }} messages</span>
              <span>{{ formatDate(session.updatedAt) }}</span>
            </div>
          </div>

          <!-- Empty state -->
          <div v-if="store.sessions.length === 0" class="text-center py-4 text-blueGray-500">
            <i class="fas fa-comments text-2xl mb-2 opacity-50"></i>
            <p class="text-sm">No chat sessions yet</p>
          </div>
        </div>

        <!-- Chat Actions -->
        <div class="grid grid-cols-2 gap-2 pt-4 border-t border-blueGray-200">
          <button
            class="btn btn-primary text-xs"
            @click="controller.createNewSession()"
            aria-label="Create new chat"
          >
            <i class="fas fa-plus mr-1"></i>
            New
          </button>
          <button
            class="btn btn-secondary text-xs"
            @click="controller.resetCurrentChat()"
            :disabled="!store.currentSessionId"
            aria-label="Reset current chat"
          >
            <i class="fas fa-redo mr-1"></i>
            Reset
          </button>
          <button
            class="btn btn-danger text-xs"
            @click="deleteCurrentSession()"
            :disabled="!store.currentSessionId"
            aria-label="Delete current chat"
          >
            <i class="fas fa-trash mr-1"></i>
            Delete
          </button>
          <button
            class="btn btn-outline text-xs"
            @click="controller.loadChatSessions()"
            aria-label="Refresh chat list"
          >
            <i class="fas fa-sync mr-1"></i>
            Refresh
          </button>
        </div>
      </section>

      <!-- Display Settings Section -->
      <section class="mb-6">
        <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Message Display</h3>
        <div class="space-y-3">
          <label v-for="setting in displaySettings" :key="setting.key" class="flex items-center">
            <input
              type="checkbox"
              :checked="getSetting(setting.key)"
              @change="toggleSetting(setting.key, $event.target.checked)"
              class="mr-2 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span class="text-sm text-blueGray-600">{{ setting.label }}</span>
          </label>
        </div>
      </section>

      <!-- System Control Section -->
      <section>
        <h3 class="text-lg font-semibold text-blueGray-700 mb-4">System Control</h3>
        <div class="space-y-2">
          <button
            class="btn btn-primary w-full text-sm"
            @click="reloadSystem"
            :disabled="isSystemReloading"
            aria-label="Reload system"
          >
            <i class="fas fa-sync mr-2" :class="{ 'fa-spin': isSystemReloading }"></i>
            {{ isSystemReloading ? 'Reloading...' : 'Reload System' }}
          </button>

          <!-- System Status -->
          <div class="text-xs text-center text-blueGray-500 mt-2">
            System: {{ systemStatus }}
          </div>
        </div>
      </section>
    </div>
  </div>

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
import type { ChatSession } from '@/stores/useChatStore'

const store = useChatStore()
const controller = useChatController()

// Local state
const showEditModal = ref(false)
const editingName = ref('')
const editingSession = ref<ChatSession | null>(null)
const editInput = ref<HTMLInputElement>()
const isSystemReloading = ref(false)
const systemStatus = ref('Ready')

// Display settings configuration
const displaySettings = [
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
  const session = store.sessions.find(s => s.id === sessionId)
  const sessionName = session?.title || `Chat ${sessionId.slice(-8)}...`

  if (confirm(`Delete "${sessionName}"? This action cannot be undone.`)) {
    await controller.deleteChatSession(sessionId)
  }
}

const deleteCurrentSession = () => {
  if (store.currentSessionId) {
    deleteSession(store.currentSessionId)
  }
}

const getSetting = (key: string): boolean => {
  // This would need to be connected to actual settings
  // For now, return from store settings
  const settingMap: Record<string, keyof typeof store.settings> = {
    showThoughts: 'persistHistory', // Placeholder mappings
    showJson: 'persistHistory',
    autoScroll: 'autoSave'
  }

  return store.settings[settingMap[key]] ?? false
}

const toggleSetting = (key: string, value: boolean) => {
  // This would update the actual display settings
  controller.updateChatSettings({ [key]: value })
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

const formatDate = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString()
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
