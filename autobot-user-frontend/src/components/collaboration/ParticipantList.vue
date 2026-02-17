<script setup lang="ts">
/**
 * Participant List Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Displays list of session participants with their roles and permissions.
 * Allows session owner to manage participant access levels.
 */

import { computed, ref } from 'vue'
import { useSessionCollaboration, type UserPresence } from '@/composables/useSessionCollaboration'
import { useChatStore } from '@/stores/useChatStore'

const chatStore = useChatStore()
const { sessionPresence, myPresence, isConnected } = useSessionCollaboration()

// Props
const props = defineProps<{
  /** Show compact view */
  compact?: boolean
  /** Allow role management (owner only) */
  allowManagement?: boolean
}>()

// Emits
const emit = defineEmits<{
  invite: []
  removeParticipant: [userId: string]
  changeRole: [userId: string, role: 'owner' | 'collaborator' | 'viewer']
}>()

// Local state
const showRoleMenu = ref<string | null>(null)
const removingUserId = ref<string | null>(null)

// Current user is owner
const isOwner = computed(() => {
  const session = chatStore.currentSession
  return session?.owner?.id === myPresence.value?.userId
})

// Participant with role data (mock for now, will come from API later)
interface ParticipantWithRole extends UserPresence {
  role: 'owner' | 'collaborator' | 'viewer'
  email?: string
  joinedAt: Date
}

// Mock role data (in real implementation, this comes from session API)
const participantsWithRoles = computed<ParticipantWithRole[]>(() => {
  return sessionPresence.value.map(p => ({
    ...p,
    role: p.userId === myPresence.value?.userId ? 'owner' : 'collaborator' as const,
    email: `${p.username}@example.com`,
    joinedAt: new Date()
  }))
})

// Get role badge styling
const getRoleBadge = (role: ParticipantWithRole['role']): { color: string; label: string } => {
  switch (role) {
    case 'owner':
      return { color: 'bg-purple-500/20 text-purple-400 border-purple-500/30', label: 'Owner' }
    case 'collaborator':
      return { color: 'bg-blue-500/20 text-blue-400 border-blue-500/30', label: 'Editor' }
    case 'viewer':
      return { color: 'bg-gray-500/20 text-gray-400 border-gray-500/30', label: 'Viewer' }
  }
}

// Get status color
const getStatusColor = (status: UserPresence['status']): string => {
  switch (status) {
    case 'online': return 'bg-green-500'
    case 'away': return 'bg-yellow-500'
    case 'offline': return 'bg-gray-500'
  }
}

// Get initials from username
const getInitials = (username: string): string => {
  return username
    .split(/[\s_-]/)
    .map(part => part[0])
    .join('')
    .toUpperCase()
    .substring(0, 2)
}

// Toggle role menu
const toggleRoleMenu = (userId: string) => {
  if (!props.allowManagement || !isOwner.value) return
  showRoleMenu.value = showRoleMenu.value === userId ? null : userId
}

// Change participant role
const changeRole = (userId: string, newRole: 'owner' | 'collaborator' | 'viewer') => {
  emit('changeRole', userId, newRole)
  showRoleMenu.value = null
}

// Remove participant
const removeParticipant = (userId: string) => {
  if (!window.confirm('Remove this participant from the session?')) return
  removingUserId.value = userId
  emit('removeParticipant', userId)
  setTimeout(() => {
    removingUserId.value = null
  }, 1000)
}

// Invite new participant
const inviteParticipant = () => {
  emit('invite')
}
</script>

<template>
  <div class="participant-list" :class="{ 'compact-mode': compact }">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <h3 class="text-sm font-semibold text-autobot-text-primary">
          Participants
        </h3>
        <span
          v-if="isConnected"
          class="px-2 py-0.5 text-xs rounded-full bg-autobot-bg-tertiary text-autobot-text-muted"
        >
          {{ participantsWithRoles.length }}
        </span>
      </div>
      <button
        v-if="isOwner && allowManagement"
        class="px-2 py-1 text-xs rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors flex items-center gap-1"
        aria-label="Invite participant"
        @click="inviteParticipant"
      >
        <i class="bi bi-person-plus" />
        <span v-if="!compact">Invite</span>
      </button>
    </div>

    <!-- Connection status banner -->
    <div
      v-if="!isConnected"
      class="mb-3 px-3 py-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2"
      role="alert"
    >
      <i class="bi bi-exclamation-triangle" />
      <span>Collaboration offline - reconnecting...</span>
    </div>

    <!-- Participant list -->
    <div class="space-y-2">
      <TransitionGroup name="participant">
        <div
          v-for="participant in participantsWithRoles"
          :key="participant.userId"
          :class="[
            'participant-item rounded-lg p-3 transition-all',
            participant.userId === myPresence?.userId
              ? 'bg-blue-500/10 border border-blue-500/20'
              : 'bg-autobot-bg-tertiary/50 hover:bg-autobot-bg-tertiary',
            removingUserId === participant.userId && 'opacity-50'
          ]"
        >
          <div class="flex items-start gap-3">
            <!-- Avatar -->
            <div class="relative flex-shrink-0">
              <div
                class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium"
                :class="participant.userId === myPresence?.userId ? 'bg-blue-600 text-white' : 'bg-autobot-bg-tertiary text-autobot-text-primary'"
              >
                {{ getInitials(participant.username) }}
              </div>
              <span
                :class="[
                  'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-autobot-bg-secondary',
                  getStatusColor(participant.status)
                ]"
                :title="participant.status"
              />
            </div>

            <!-- Info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-sm font-medium text-autobot-text-primary truncate">
                  {{ participant.username }}
                </span>
                <span
                  v-if="participant.userId === myPresence?.userId"
                  class="text-xs text-blue-400"
                >
                  (you)
                </span>
              </div>
              <div v-if="!compact" class="text-xs text-autobot-text-muted truncate mb-1">
                {{ participant.email }}
              </div>
              <div class="flex items-center gap-2 flex-wrap">
                <!-- Role badge -->
                <button
                  :class="[
                    'px-2 py-0.5 text-xs rounded border',
                    getRoleBadge(participant.role).color,
                    isOwner && allowManagement && participant.userId !== myPresence?.userId
                      ? 'cursor-pointer hover:opacity-80'
                      : 'cursor-default'
                  ]"
                  :aria-label="`Change role for ${participant.username}`"
                  @click="toggleRoleMenu(participant.userId)"
                >
                  {{ getRoleBadge(participant.role).label }}
                  <i
                    v-if="isOwner && allowManagement && participant.userId !== myPresence?.userId"
                    class="bi bi-chevron-down ml-1"
                  />
                </button>

                <!-- Status badge -->
                <span class="text-xs text-autobot-text-muted">
                  {{ participant.status }}
                </span>

                <!-- Current tab indicator -->
                <span
                  v-if="participant.currentTab"
                  class="text-xs text-autobot-text-muted flex items-center gap-1"
                >
                  <i :class="`bi bi-${participant.currentTab === 'chat' ? 'chat-dots' : participant.currentTab}`" />
                  <span v-if="!compact">{{ participant.currentTab }}</span>
                </span>
              </div>

              <!-- Role menu dropdown -->
              <div
                v-if="showRoleMenu === participant.userId"
                class="mt-2 bg-autobot-bg-secondary border border-autobot-border rounded-lg shadow-lg overflow-hidden"
                role="menu"
              >
                <button
                  v-for="role in ['collaborator', 'viewer'] as const"
                  :key="role"
                  class="w-full px-3 py-2 text-left text-xs hover:bg-autobot-bg-tertiary transition-colors text-autobot-text-primary"
                  :class="{ 'bg-autobot-bg-tertiary': participant.role === role }"
                  role="menuitem"
                  @click="changeRole(participant.userId, role)"
                >
                  {{ getRoleBadge(role).label }}
                </button>
                <hr class="border-autobot-border">
                <button
                  class="w-full px-3 py-2 text-left text-xs hover:bg-red-500/10 transition-colors text-red-400"
                  role="menuitem"
                  @click="removeParticipant(participant.userId)"
                >
                  <i class="bi bi-person-x mr-1" />
                  Remove
                </button>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Empty state -->
      <div
        v-if="participantsWithRoles.length === 0"
        class="text-center py-6 text-autobot-text-muted"
      >
        <i class="bi bi-people text-2xl mb-2" />
        <div class="text-sm">No participants yet</div>
        <div class="text-xs">Invite others to collaborate</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Participant animations */
.participant-enter-active {
  transition: all 0.3s ease-out;
}

.participant-leave-active {
  transition: all 0.2s ease-in;
}

.participant-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.participant-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.participant-move {
  transition: transform 0.3s ease;
}
</style>
