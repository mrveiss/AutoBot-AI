<script setup lang="ts">
/**
 * Secret Sharing Notifications Component
 *
 * Issue #608: User-Centric Session Tracking - Phase 5
 *
 * Displays notifications when secrets are shared or revoked in the session.
 */

import { computed } from 'vue'
import {
  useSessionCollaboration,
  type SecretSharingNotification
} from '@/composables/useSessionCollaboration'

const { secretNotifications, clearSecretNotifications } = useSessionCollaboration()

// Format timestamp
const formatTime = (date: Date): string => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)

  if (seconds < 60) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  return date.toLocaleTimeString()
}

// Get icon for secret type
const getSecretIcon = (type: string): string => {
  switch (type) {
    case 'ssh_key': return 'key'
    case 'password': return 'lock'
    case 'api_key': return 'code-slash'
    case 'token': return 'shield-check'
    case 'certificate': return 'file-earmark-lock'
    default: return 'key-fill'
  }
}

// Get action styling
const getActionStyle = (action: SecretSharingNotification['action']): string => {
  return action === 'shared'
    ? 'bg-green-500/10 text-green-400 border-green-500/20'
    : 'bg-red-500/10 text-red-400 border-red-500/20'
}

// Visible notifications
const visibleNotifications = computed(() => {
  return secretNotifications.value.slice(0, 10)
})

// Has notifications
const hasNotifications = computed(() => secretNotifications.value.length > 0)

// Dismiss a notification (for UI purposes, we just clear all for simplicity)
const dismissAll = () => {
  clearSecretNotifications()
}
</script>

<template>
  <div v-if="hasNotifications" class="secret-notifications">
    <!-- Notification container -->
    <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-2 bg-gray-750 border-b border-gray-700">
        <div class="flex items-center gap-2">
          <i class="bi bi-shield-lock text-yellow-400" />
          <span class="text-sm font-medium text-gray-200">Secret Updates</span>
          <span class="px-1.5 py-0.5 text-xs rounded-full bg-yellow-500/20 text-yellow-400">
            {{ secretNotifications.length }}
          </span>
        </div>
        <button
          class="text-xs text-gray-400 hover:text-gray-200 transition-colors"
          @click="dismissAll"
        >
          Clear all
        </button>
      </div>

      <!-- Notification list -->
      <div class="max-h-60 overflow-y-auto custom-scrollbar">
        <TransitionGroup name="notification">
          <div
            v-for="notification in visibleNotifications"
            :key="`${notification.secretId}-${notification.timestamp.getTime()}`"
            :class="[
              'flex items-start gap-3 px-4 py-3 border-b border-gray-700/50 last:border-b-0',
              getActionStyle(notification.action)
            ]"
          >
            <!-- Icon -->
            <div class="flex-shrink-0 mt-0.5">
              <i :class="`bi bi-${getSecretIcon(notification.secretType)}`" />
            </div>

            <!-- Content -->
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium truncate">
                {{ notification.secretName }}
              </div>
              <div class="text-xs opacity-75">
                {{ notification.action === 'shared' ? 'Shared by' : 'Revoked by' }}
                <span class="font-medium">{{ notification.sharedByUsername }}</span>
              </div>
            </div>

            <!-- Timestamp -->
            <div class="flex-shrink-0 text-xs opacity-50">
              {{ formatTime(notification.timestamp) }}
            </div>
          </div>
        </TransitionGroup>
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

/* Animation for notifications */
.notification-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.notification-leave-active {
  transition: all var(--duration-200) var(--ease-in);
}

.notification-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.notification-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.bg-gray-750 {
  background-color: var(--bg-tertiary);
}
</style>
