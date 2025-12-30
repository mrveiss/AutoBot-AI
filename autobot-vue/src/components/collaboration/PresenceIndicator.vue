<script setup lang="ts">
/**
 * Presence Indicator Component
 *
 * Issue #608: User-Centric Session Tracking - Phase 5
 *
 * Shows who's currently active in the session with their status and current tab.
 */

import { computed } from 'vue'
import { useSessionCollaboration, type UserPresence } from '@/composables/useSessionCollaboration'

const { sessionPresence, myPresence, isConnected } = useSessionCollaboration()

// Get status color
const getStatusColor = (status: UserPresence['status']): string => {
  switch (status) {
    case 'online': return 'bg-green-500'
    case 'away': return 'bg-yellow-500'
    case 'offline': return 'bg-gray-500'
    default: return 'bg-gray-500'
  }
}

// Get tab icon
const getTabIcon = (tab?: UserPresence['currentTab']): string => {
  switch (tab) {
    case 'chat': return 'chat-dots'
    case 'terminal': return 'terminal'
    case 'files': return 'folder'
    case 'browser': return 'globe'
    case 'desktop': return 'display'
    default: return 'circle'
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

// Other collaborators (excluding myself)
const otherCollaborators = computed<UserPresence[]>(() => {
  if (!myPresence.value) return sessionPresence.value
  return sessionPresence.value.filter(p => p.userId !== myPresence.value?.userId)
})

// Show expanded or collapsed view
const props = defineProps<{
  expanded?: boolean
}>()
</script>

<template>
  <div class="presence-indicator">
    <!-- Compact View (default) -->
    <div v-if="!props.expanded" class="flex items-center gap-1">
      <!-- My avatar -->
      <div
        v-if="myPresence"
        class="relative"
        :title="`You (${myPresence.status})`"
      >
        <div class="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-xs font-medium text-white ring-2 ring-gray-800">
          {{ getInitials(myPresence.username) }}
        </div>
        <span
          :class="[
            'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-gray-800',
            getStatusColor(myPresence.status)
          ]"
        />
      </div>

      <!-- Other collaborators (stacked) -->
      <div class="flex -space-x-2">
        <div
          v-for="(collaborator, index) in otherCollaborators.slice(0, 3)"
          :key="collaborator.userId"
          class="relative"
          :style="{ zIndex: 3 - index }"
          :title="`${collaborator.username} (${collaborator.status}) - ${collaborator.currentTab || 'unknown'} tab`"
        >
          <div class="w-7 h-7 rounded-full bg-gray-600 flex items-center justify-center text-xs font-medium text-gray-200 ring-2 ring-gray-800">
            {{ getInitials(collaborator.username) }}
          </div>
          <span
            :class="[
              'absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-gray-800',
              getStatusColor(collaborator.status)
            ]"
          />
        </div>
      </div>

      <!-- Overflow indicator -->
      <div
        v-if="otherCollaborators.length > 3"
        class="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs font-medium text-gray-400 ring-2 ring-gray-800"
      >
        +{{ otherCollaborators.length - 3 }}
      </div>

      <!-- Connection status -->
      <span
        v-if="!isConnected"
        class="ml-2 text-xs text-red-400 flex items-center gap-1"
      >
        <i class="bi bi-exclamation-triangle" />
        Offline
      </span>
    </div>

    <!-- Expanded View -->
    <div v-else class="space-y-2">
      <div class="text-xs font-medium text-gray-400 mb-2">
        Participants ({{ sessionPresence.length }})
      </div>

      <!-- My entry -->
      <div
        v-if="myPresence"
        class="flex items-center gap-3 p-2 bg-blue-500/10 rounded-lg border border-blue-500/20"
      >
        <div class="relative">
          <div class="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center text-sm font-medium text-white">
            {{ getInitials(myPresence.username) }}
          </div>
          <span
            :class="[
              'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-gray-800',
              getStatusColor(myPresence.status)
            ]"
          />
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-200 truncate">
              {{ myPresence.username }}
            </span>
            <span class="text-xs text-blue-400">(you)</span>
          </div>
          <div class="flex items-center gap-1 text-xs text-gray-400">
            <i :class="`bi bi-${getTabIcon(myPresence.currentTab)}`" />
            <span>{{ myPresence.currentTab || 'unknown' }} tab</span>
          </div>
        </div>
      </div>

      <!-- Other collaborators -->
      <div
        v-for="collaborator in otherCollaborators"
        :key="collaborator.userId"
        class="flex items-center gap-3 p-2 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
      >
        <div class="relative">
          <div class="w-9 h-9 rounded-full bg-gray-600 flex items-center justify-center text-sm font-medium text-gray-200">
            {{ getInitials(collaborator.username) }}
          </div>
          <span
            :class="[
              'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-gray-800',
              getStatusColor(collaborator.status)
            ]"
          />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-200 truncate">
            {{ collaborator.username }}
          </div>
          <div class="flex items-center gap-1 text-xs text-gray-400">
            <i :class="`bi bi-${getTabIcon(collaborator.currentTab)}`" />
            <span>{{ collaborator.currentTab || 'unknown' }} tab</span>
          </div>
        </div>
        <div class="text-xs text-gray-500">
          {{ collaborator.status }}
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="sessionPresence.length === 0"
        class="text-center py-4 text-gray-500"
      >
        <i class="bi bi-people text-lg mb-1" />
        <div class="text-xs">No participants yet</div>
      </div>
    </div>
  </div>
</template>
