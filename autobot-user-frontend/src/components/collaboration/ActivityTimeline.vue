<script setup lang="ts">
/**
 * Activity Timeline Component
 *
 * Issue #608: User-Centric Session Tracking - Phase 7
 *
 * Displays a chronological timeline of all activities within the current session,
 * including chat messages, terminal commands, file operations, and more.
 */

import { computed, ref } from 'vue'
import { useChatStore, type SessionActivity } from '@/stores/useChatStore'
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'

const chatStore = useChatStore()
const { getActivities } = useSessionActivityLogger()

// Filter options
const filterType = ref<SessionActivity['type'] | 'all'>('all')

// Get activities with filtering
const activities = computed<SessionActivity[]>(() => {
  const allActivities = getActivities(
    filterType.value === 'all' ? undefined : { type: filterType.value }
  )
  return allActivities.slice(0, 100) // Limit to 100 most recent
})

// Group activities by date
interface ActivityGroup {
  date: string
  activities: SessionActivity[]
}

const groupedActivities = computed<ActivityGroup[]>(() => {
  const groups = new Map<string, SessionActivity[]>()

  activities.value.forEach(activity => {
    const date = activity.timestamp.toLocaleDateString()
    if (!groups.has(date)) {
      groups.set(date, [])
    }
    groups.get(date)!.push(activity)
  })

  return Array.from(groups.entries()).map(([date, acts]) => ({
    date,
    activities: acts.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
  }))
})

// Format time
const formatTime = (date: Date): string => {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Get activity type styling
const getTypeStyle = (type: SessionActivity['type']): { icon: string; color: string; label: string } => {
  switch (type) {
    case 'terminal':
      return { icon: 'terminal', color: 'text-green-400 bg-green-400/10', label: 'Terminal' }
    case 'file':
      return { icon: 'folder', color: 'text-blue-400 bg-blue-400/10', label: 'File' }
    case 'browser':
      return { icon: 'globe', color: 'text-purple-400 bg-purple-400/10', label: 'Browser' }
    case 'desktop':
      return { icon: 'display', color: 'text-orange-400 bg-orange-400/10', label: 'Desktop' }
    default:
      return { icon: 'activity', color: 'text-gray-400 bg-gray-400/10', label: 'Activity' }
  }
}

// Truncate content
const truncate = (text: string, length = 60): string => {
  if (text.length <= length) return text
  return text.substring(0, length) + '...'
}

// Current session info
const currentSession = computed(() => chatStore.currentSession)
const hasActivities = computed(() => activities.value.length > 0)

// Activity type options for filter
const typeOptions = [
  { value: 'all', label: 'All' },
  { value: 'terminal', label: 'Terminal' },
  { value: 'file', label: 'Files' },
  { value: 'browser', label: 'Browser' },
  { value: 'desktop', label: 'Desktop' }
]
</script>

<template>
  <div class="activity-timeline h-full flex flex-col bg-autobot-bg-secondary rounded-lg">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-autobot-border">
      <h3 class="text-sm font-semibold text-autobot-text-primary">Activity Timeline</h3>
      <span class="text-xs text-autobot-text-muted">{{ activities.length }} activities</span>
    </div>

    <!-- Filter -->
    <div class="px-4 py-2 border-b border-autobot-border">
      <div class="flex gap-1">
        <button
          v-for="option in typeOptions"
          :key="option.value"
          :class="[
            'px-2 py-1 text-xs rounded transition-colors',
            filterType === option.value
              ? 'bg-blue-500 text-white'
              : 'bg-autobot-bg-tertiary text-autobot-text-muted hover:bg-autobot-bg-secondary'
          ]"
          @click="filterType = option.value as SessionActivity['type'] | 'all'"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <!-- Timeline Content -->
    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <!-- No session selected -->
      <div
        v-if="!currentSession"
        class="flex flex-col items-center justify-center h-full text-autobot-text-muted p-4"
      >
        <i class="bi bi-chat-square-dots text-3xl mb-2" />
        <span class="text-sm text-center">Select a chat session to view activity timeline</span>
      </div>

      <!-- No activities -->
      <div
        v-else-if="!hasActivities"
        class="flex flex-col items-center justify-center h-full text-autobot-text-muted p-4"
      >
        <i class="bi bi-clock-history text-3xl mb-2" />
        <span class="text-sm text-center">No activities recorded yet</span>
        <span class="text-xs text-autobot-text-muted mt-1">Activities will appear here as you work</span>
      </div>

      <!-- Activity groups by date -->
      <div v-else class="p-2">
        <div
          v-for="group in groupedActivities"
          :key="group.date"
          class="mb-4"
        >
          <!-- Date header -->
          <div class="sticky top-0 bg-autobot-bg-secondary py-1 mb-2">
            <span class="text-xs font-medium text-autobot-text-muted uppercase tracking-wide">
              {{ group.date }}
            </span>
          </div>

          <!-- Activities for this date -->
          <div class="space-y-2">
            <div
              v-for="activity in group.activities"
              :key="activity.id"
              class="relative pl-6"
            >
              <!-- Timeline line -->
              <div class="absolute left-2 top-0 bottom-0 w-px bg-autobot-border" />

              <!-- Timeline dot -->
              <div
                :class="[
                  'absolute left-0 top-2 w-4 h-4 rounded-full flex items-center justify-center',
                  getTypeStyle(activity.type).color
                ]"
              >
                <i :class="`bi bi-${getTypeStyle(activity.type).icon} text-xs`" />
              </div>

              <!-- Activity card -->
              <div class="bg-autobot-bg-tertiary/50 rounded-lg p-3 hover:bg-autobot-bg-tertiary transition-colors">
                <!-- Header -->
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs font-medium text-autobot-text-muted">
                    {{ getTypeStyle(activity.type).label }}
                  </span>
                  <span class="text-xs text-autobot-text-muted">
                    {{ formatTime(activity.timestamp) }}
                  </span>
                </div>

                <!-- Content -->
                <div class="text-sm text-autobot-text-primary">
                  {{ truncate(activity.content) }}
                </div>

                <!-- User attribution -->
                <div
                  v-if="activity.userId && activity.userId !== 'anonymous'"
                  class="mt-1 text-xs text-autobot-text-muted"
                >
                  by {{ activity.userId }}
                </div>

                <!-- Secrets badge -->
                <div
                  v-if="activity.secretsUsed?.length"
                  class="mt-2"
                >
                  <span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">
                    <i class="bi bi-key mr-1" />
                    {{ activity.secretsUsed.length }} secret(s) used
                  </span>
                </div>

                <!-- Metadata (expandable in future) -->
                <div
                  v-if="activity.metadata && Object.keys(activity.metadata).length > 0"
                  class="mt-2 text-xs text-autobot-text-muted"
                >
                  <details class="cursor-pointer">
                    <summary class="hover:text-autobot-text-secondary">Details</summary>
                    <pre class="mt-1 p-2 bg-autobot-bg-secondary rounded text-xs overflow-x-auto">{{ JSON.stringify(activity.metadata, null, 2) }}</pre>
                  </details>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--text-tertiary);
  border-radius: var(--radius-sm);
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>
