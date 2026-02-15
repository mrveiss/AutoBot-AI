<script setup lang="ts">
/**
 * Invite User Dialog Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Modal dialog for inviting users to collaborate on a session.
 * Supports role selection and email-based invitations.
 */

import { ref, computed } from 'vue'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
import { useChatStore } from '@/stores/useChatStore'

const chatStore = useChatStore()
const { inviteCollaborator, sessionPresence } = useSessionCollaboration()

// Props
const props = defineProps<{
  /** Whether the dialog is visible */
  modelValue: boolean
}>()

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  invited: [userId: string, username: string, role: string]
}>()

// Local state
const searchQuery = ref('')
const selectedRole = ref<'collaborator' | 'viewer'>('collaborator')
const selectedUserId = ref<string | null>(null)
const inviting = ref(false)
const errorMessage = ref<string | null>(null)

// Mock user list (in real implementation, comes from API)
const mockUsers = [
  { id: 'user-1', username: 'alice', email: 'alice@example.com', avatar: null },
  { id: 'user-2', username: 'bob', email: 'bob@example.com', avatar: null },
  { id: 'user-3', username: 'charlie', email: 'charlie@example.com', avatar: null },
  { id: 'user-4', username: 'diana', email: 'diana@example.com', avatar: null },
  { id: 'user-5', username: 'eve', email: 'eve@example.com', avatar: null }
]

// Filter users by search query
const filteredUsers = computed(() => {
  if (!searchQuery.value) return mockUsers

  const query = searchQuery.value.toLowerCase()
  return mockUsers.filter(user =>
    user.username.toLowerCase().includes(query) ||
    user.email.toLowerCase().includes(query)
  )
})

// Already in session
const alreadyInSession = computed(() => {
  const participantIds = new Set(sessionPresence.value.map(p => p.userId))
  return filteredUsers.value.filter(user => participantIds.has(user.id))
})

// Available to invite
const availableUsers = computed(() => {
  const participantIds = new Set(sessionPresence.value.map(p => p.userId))
  return filteredUsers.value.filter(user => !participantIds.has(user.id))
})

// Get initials
const getInitials = (username: string): string => {
  return username
    .split(/[\s_-]/)
    .map(part => part[0])
    .join('')
    .toUpperCase()
    .substring(0, 2)
}

// Select user
const selectUser = (userId: string) => {
  selectedUserId.value = userId
  errorMessage.value = null
}

// Send invitation
const sendInvitation = async () => {
  if (!selectedUserId.value) {
    errorMessage.value = 'Please select a user to invite'
    return
  }

  inviting.value = true
  errorMessage.value = null

  try {
    // Call composable to send invitation
    const success = inviteCollaborator(selectedUserId.value, selectedRole.value)

    if (success) {
      const user = mockUsers.find(u => u.id === selectedUserId.value)
      if (user) {
        emit('invited', user.id, user.username, selectedRole.value)
      }

      // Close dialog and reset
      closeDialog()
    } else {
      errorMessage.value = 'Failed to send invitation'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'An error occurred'
  } finally {
    inviting.value = false
  }
}

// Close dialog
const closeDialog = () => {
  emit('update:modelValue', false)
  // Reset state after animation
  setTimeout(() => {
    searchQuery.value = ''
    selectedUserId.value = null
    selectedRole.value = 'collaborator'
    errorMessage.value = null
  }, 300)
}

// Role options
const roleOptions = [
  {
    value: 'collaborator' as const,
    label: 'Editor',
    description: 'Can view and edit session content',
    icon: 'pencil-square'
  },
  {
    value: 'viewer' as const,
    label: 'Viewer',
    description: 'Can only view session content',
    icon: 'eye'
  }
]
</script>

<template>
  <!-- Modal backdrop -->
  <Transition name="modal-backdrop">
    <div
      v-if="props.modelValue"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      @click.self="closeDialog"
    >
      <!-- Modal content -->
      <Transition name="modal-content">
        <div
          v-if="props.modelValue"
          class="bg-gray-800 rounded-lg shadow-2xl w-full max-w-md border border-gray-700"
          role="dialog"
          aria-labelledby="invite-dialog-title"
          aria-modal="true"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-700">
            <h2 id="invite-dialog-title" class="text-lg font-semibold text-gray-100">
              Invite to Session
            </h2>
            <button
              class="text-gray-400 hover:text-gray-200 transition-colors"
              aria-label="Close dialog"
              @click="closeDialog"
            >
              <i class="bi bi-x-lg" />
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-4 space-y-4">
            <!-- Search input -->
            <div>
              <label for="user-search" class="block text-sm font-medium text-gray-300 mb-2">
                Search users
              </label>
              <div class="relative">
                <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  id="user-search"
                  v-model="searchQuery"
                  type="text"
                  placeholder="Search by username or email..."
                  class="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  autocomplete="off"
                >
              </div>
            </div>

            <!-- User list -->
            <div class="max-h-60 overflow-y-auto custom-scrollbar space-y-1">
              <!-- Available users -->
              <div v-if="availableUsers.length > 0">
                <div class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Available ({{ availableUsers.length }})
                </div>
                <button
                  v-for="user in availableUsers"
                  :key="user.id"
                  :class="[
                    'w-full flex items-center gap-3 p-3 rounded-lg transition-colors text-left',
                    selectedUserId === user.id
                      ? 'bg-blue-500/20 border border-blue-500/30'
                      : 'bg-gray-700/50 hover:bg-gray-700 border border-transparent'
                  ]"
                  @click="selectUser(user.id)"
                >
                  <div class="w-10 h-10 rounded-full bg-gray-600 flex items-center justify-center text-sm font-medium text-gray-200">
                    {{ getInitials(user.username) }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-200 truncate">
                      {{ user.username }}
                    </div>
                    <div class="text-xs text-gray-400 truncate">
                      {{ user.email }}
                    </div>
                  </div>
                  <i
                    v-if="selectedUserId === user.id"
                    class="bi bi-check-circle-fill text-blue-400"
                  />
                </button>
              </div>

              <!-- Already in session -->
              <div v-if="alreadyInSession.length > 0" class="mt-3">
                <div class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Already in session ({{ alreadyInSession.length }})
                </div>
                <div
                  v-for="user in alreadyInSession"
                  :key="user.id"
                  class="w-full flex items-center gap-3 p-3 rounded-lg bg-gray-700/30 opacity-50 cursor-not-allowed"
                >
                  <div class="w-10 h-10 rounded-full bg-gray-600 flex items-center justify-center text-sm font-medium text-gray-200">
                    {{ getInitials(user.username) }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-200 truncate">
                      {{ user.username }}
                    </div>
                    <div class="text-xs text-gray-400 truncate">
                      {{ user.email }}
                    </div>
                  </div>
                  <span class="text-xs text-gray-500">
                    In session
                  </span>
                </div>
              </div>

              <!-- No results -->
              <div
                v-if="filteredUsers.length === 0"
                class="text-center py-8 text-gray-500"
              >
                <i class="bi bi-search text-2xl mb-2" />
                <div class="text-sm">No users found</div>
              </div>
            </div>

            <!-- Role selection -->
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-2">
                Permission level
              </label>
              <div class="space-y-2">
                <button
                  v-for="role in roleOptions"
                  :key="role.value"
                  :class="[
                    'w-full flex items-start gap-3 p-3 rounded-lg border transition-all text-left',
                    selectedRole === role.value
                      ? 'bg-blue-500/20 border-blue-500/50'
                      : 'bg-gray-700/50 border-gray-600 hover:bg-gray-700'
                  ]"
                  @click="selectedRole = role.value"
                >
                  <div
                    :class="[
                      'w-5 h-5 rounded-full border-2 flex items-center justify-center mt-0.5',
                      selectedRole === role.value
                        ? 'border-blue-500 bg-blue-500'
                        : 'border-gray-500 bg-transparent'
                    ]"
                  >
                    <i
                      v-if="selectedRole === role.value"
                      class="bi bi-check text-xs text-white"
                    />
                  </div>
                  <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                      <i :class="`bi bi-${role.icon} text-gray-400`" />
                      <span class="text-sm font-medium text-gray-200">
                        {{ role.label }}
                      </span>
                    </div>
                    <div class="text-xs text-gray-400">
                      {{ role.description }}
                    </div>
                  </div>
                </button>
              </div>
            </div>

            <!-- Error message -->
            <div
              v-if="errorMessage"
              class="px-3 py-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"
              role="alert"
            >
              <i class="bi bi-exclamation-triangle" />
              <span>{{ errorMessage }}</span>
            </div>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-700">
            <button
              class="px-4 py-2 text-sm rounded bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
              @click="closeDialog"
            >
              Cancel
            </button>
            <button
              class="px-4 py-2 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              :disabled="!selectedUserId || inviting"
              @click="sendInvitation"
            >
              <i v-if="inviting" class="bi bi-arrow-repeat animate-spin" />
              <span>{{ inviting ? 'Sending...' : 'Send Invitation' }}</span>
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
</template>

<style scoped>
/* Modal animations */
.modal-backdrop-enter-active,
.modal-backdrop-leave-active {
  transition: opacity 0.3s ease;
}

.modal-backdrop-enter-from,
.modal-backdrop-leave-to {
  opacity: 0;
}

.modal-content-enter-active {
  transition: all 0.3s ease-out;
}

.modal-content-leave-active {
  transition: all 0.2s ease-in;
}

.modal-content-enter-from {
  opacity: 0;
  transform: scale(0.95) translateY(-10px);
}

.modal-content-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(10px);
}

/* Custom scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.5);
}
</style>
