<script setup lang="ts">
import { BaseAvatar } from '@autobot/ui'
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


type Translate = (key: string, named: Record<string, unknown>) => string

// #14780: compact avatars are decorative, so each wrapper is named for the person and status.
const presenceLabel = (tr: Translate, p: UserPresence, isMe = false): string =>
  isMe
    ? tr('collaboration.presenceIndicator.youStatus', { status: p.status })
    : tr('collaboration.presenceIndicator.collaboratorTooltip', {
        username: p.username,
        status: p.status,
        tab: p.currentTab || tr('collaboration.presenceIndicator.unknownTab', {}),
      })

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
        :title="presenceLabel($t, myPresence, true)"
        role="img"
        :aria-label="presenceLabel($t, myPresence, true)"
      >
        <BaseAvatar :name="myPresence.username" size="md" variant="primary" :status="myPresence.status" ring decorative />
      </div>

      <!-- Other collaborators (stacked) -->
      <div class="flex -space-x-2">
        <div
          v-for="(collaborator, index) in otherCollaborators.slice(0, 3)"
          :key="collaborator.userId"
          class="relative"
          :style="{ zIndex: 3 - index }"
          :title="presenceLabel($t, collaborator)"
          role="img"
          :aria-label="presenceLabel($t, collaborator)"
        >
          <BaseAvatar :name="collaborator.username" size="sm" :status="collaborator.status" ring decorative />
        </div>
      </div>

      <!-- Overflow indicator -->
      <div
        v-if="otherCollaborators.length > 3"
        class="w-7 h-7 rounded-full bg-autobot-bg-tertiary flex items-center justify-center text-xs font-medium text-autobot-text-muted ring-2 ring-autobot-bg-secondary"
      >
        +{{ otherCollaborators.length - 3 }}
      </div>

      <!-- Connection status -->
      <span
        v-if="!isConnected"
        class="ml-2 text-xs text-red-400 flex items-center gap-1"
      >
        <i class="bi bi-exclamation-triangle" />
        {{ $t('collaboration.presence.offline') }}
      </span>
    </div>

    <!-- Expanded View -->
    <div v-else class="space-y-2">
      <div class="text-xs font-medium text-autobot-text-muted mb-2">
        {{ $t('collaboration.presence.participants', { count: sessionPresence.length }) }}
      </div>

      <!-- My entry -->
      <div
        v-if="myPresence"
        class="flex items-center gap-3 p-2 bg-blue-500/10 rounded-lg border border-blue-500/20"
      >
        <div class="relative">
          <BaseAvatar :name="myPresence.username" size="md" variant="primary" :status="myPresence.status" decorative />
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-autobot-text-primary truncate">
              {{ myPresence.username }}
            </span>
            <span class="text-xs text-blue-400">{{ $t('collaboration.presence.you') }}</span>
          </div>
          <div class="flex items-center gap-1 text-xs text-autobot-text-muted">
            <i :class="`bi bi-${getTabIcon(myPresence.currentTab)}`" />
            <span>{{ $t('collaboration.presence.tabLabel', { tab: myPresence.currentTab || $t('collaboration.presence.unknownTab') }) }}</span>
          </div>
        </div>
      </div>

      <!-- Other collaborators -->
      <div
        v-for="collaborator in otherCollaborators"
        :key="collaborator.userId"
        class="flex items-center gap-3 p-2 bg-autobot-bg-tertiary/50 rounded-lg hover:bg-autobot-bg-tertiary transition-colors"
      >
        <div class="relative">
          <BaseAvatar :name="collaborator.username" size="md" :status="collaborator.status" decorative />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-autobot-text-primary truncate">
            {{ collaborator.username }}
          </div>
          <div class="flex items-center gap-1 text-xs text-autobot-text-muted">
            <i :class="`bi bi-${getTabIcon(collaborator.currentTab)}`" />
            <span>{{ $t('collaboration.presence.tabLabel', { tab: collaborator.currentTab || $t('collaboration.presence.unknownTab') }) }}</span>
          </div>
        </div>
        <div class="text-xs text-autobot-text-muted">
          {{ collaborator.status }}
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="sessionPresence.length === 0"
        class="text-center py-4 text-autobot-text-muted"
      >
        <i class="bi bi-people text-lg mb-1" />
        <div class="text-xs">{{ $t('collaboration.presence.noParticipants') }}</div>
      </div>
    </div>
  </div>
</template>
