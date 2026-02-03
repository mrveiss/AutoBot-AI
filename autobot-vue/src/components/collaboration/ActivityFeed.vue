<script setup lang="ts">
/**
 * Activity Feed Component
 *
 * Issue #608: User-Centric Session Tracking - Phase 5
 *
 * Displays real-time activity stream from session collaborators.
 * Shows terminal commands, file operations, browser actions, etc.
 */

import { computed } from 'vue'
import { useSessionCollaboration, type CollaboratorActivity } from '@/composables/useSessionCollaboration'

const { recentCollaboratorActivities, sessionPresence, isConnected } = useSessionCollaboration()

// Format timestamp relative to now
const formatTime = (date: Date): string => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (seconds < 60) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return date.toLocaleDateString()
}

// Get icon for activity type
const getActivityIcon = (type: string): string => {
  switch (type) {
    case 'terminal': return 'terminal'
    case 'file': return 'folder'
    case 'browser': return 'globe'
    case 'desktop': return 'monitor'
    default: return 'activity'
  }
}

// Get color class for activity type
const getActivityColor = (type: string): string => {
  switch (type) {
    case 'terminal': return 'text-green-400'
    case 'file': return 'text-blue-400'
    case 'browser': return 'text-purple-400'
    case 'desktop': return 'text-orange-400'
    default: return 'text-gray-400'
  }
}

// Truncate long content
const truncateContent = (content: string, maxLength = 50): string => {
  if (content.length <= maxLength) return content
  return content.substring(0, maxLength) + '...'
}

// Visible activities (limit to 20 most recent)
const visibleActivities = computed<CollaboratorActivity[]>(() => {
  return recentCollaboratorActivities.value.slice(0, 20)
})

// Online collaborator count
const onlineCount = computed(() => {
  return sessionPresence.value.filter(p => p.status === 'online').length
})
</script>

<template>
  <div class="activity-feed bg-gray-800 rounded-lg p-4 h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-200">Activity Feed</h3>
      <div class="flex items-center gap-2">
        <span
          :class="[
            'w-2 h-2 rounded-full',
            isConnected ? 'bg-green-500' : 'bg-red-500'
          ]"
        />
        <span class="text-xs text-gray-400">
          {{ onlineCount }} online
        </span>
      </div>
    </div>

    <!-- Activity List -->
    <div class="flex-1 overflow-y-auto space-y-2 custom-scrollbar">
      <TransitionGroup name="activity">
        <div
          v-for="activity in visibleActivities"
          :key="activity.activity.id"
          class="activity-item bg-gray-700/50 rounded px-3 py-2 hover:bg-gray-700 transition-colors"
        >
          <!-- User and Time -->
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-gray-300">
              {{ activity.username }}
            </span>
            <span class="text-xs text-gray-500">
              {{ formatTime(activity.timestamp) }}
            </span>
          </div>

          <!-- Activity Content -->
          <div class="flex items-start gap-2">
            <span :class="['text-sm', getActivityColor(activity.activity.type)]">
              <i :class="`bi bi-${getActivityIcon(activity.activity.type)}`" />
            </span>
            <span class="text-xs text-gray-400 break-all">
              {{ truncateContent(activity.activity.content) }}
            </span>
          </div>

          <!-- Secrets Used Badge -->
          <div
            v-if="activity.activity.secretsUsed?.length"
            class="mt-1"
          >
            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">
              <i class="bi bi-key mr-1" />
              {{ activity.activity.secretsUsed.length }} secret(s)
            </span>
          </div>
        </div>
      </TransitionGroup>

      <!-- Empty State -->
      <div
        v-if="visibleActivities.length === 0"
        class="flex flex-col items-center justify-center py-8 text-gray-500"
      >
        <i class="bi bi-activity text-2xl mb-2" />
        <span class="text-sm">No recent activity</span>
        <span class="text-xs">Activities from collaborators will appear here</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--text-tertiary);
  border-radius: var(--radius-xs);
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

/* Activity list animations */
.activity-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.activity-leave-active {
  transition: all var(--duration-200) var(--ease-in);
}

.activity-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.activity-leave-to {
  opacity: 0;
  transform: translateX(10px);
}

.activity-move {
  transition: transform var(--duration-300) var(--ease-in-out);
}
</style>
