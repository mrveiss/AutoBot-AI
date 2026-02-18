<script setup lang="ts">
/**
 * Secret Audit Log Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Displays audit trail of secret usage in the session.
 */

import { ref, computed } from 'vue'
import { useSessionActivityLogger, type SecretUsageAction } from '@/composables/useSessionActivityLogger'
import { useChatStore } from '@/stores/useChatStore'

const chatStore = useChatStore()
const { getActivities } = useSessionActivityLogger()

// Mock audit data
interface SecretAuditEntry {
  id: string
  secretId: string
  secretName: string
  action: SecretUsageAction
  userId: string
  username: string
  timestamp: Date
  metadata?: Record<string, unknown>
}

const mockAuditLog: SecretAuditEntry[] = [
  {
    id: 'audit-1',
    secretId: 'secret-1',
    secretName: 'GitHub API Token',
    action: 'access',
    userId: 'user-1',
    username: 'alice',
    timestamp: new Date(Date.now() - 300000),
    metadata: { ip: '192.168.1.100' }
  },
  {
    id: 'audit-2',
    secretId: 'secret-2',
    secretName: 'SSH Private Key',
    action: 'inject',
    userId: 'user-2',
    username: 'bob',
    timestamp: new Date(Date.now() - 600000)
  },
  {
    id: 'audit-3',
    secretId: 'secret-1',
    secretName: 'GitHub API Token',
    action: 'copy',
    userId: 'user-1',
    username: 'alice',
    timestamp: new Date(Date.now() - 1800000)
  },
  {
    id: 'audit-4',
    secretId: 'secret-3',
    secretName: 'Database Password',
    action: 'reveal',
    userId: 'user-3',
    username: 'charlie',
    timestamp: new Date(Date.now() - 3600000)
  }
]

// Props
const props = defineProps<{
  /** Filter by specific secret ID */
  secretId?: string
}>()

// Local state
const filterAction = ref<SecretUsageAction | 'all'>('all')
const filterUser = ref<string | 'all'>('all')

// Filtered audit log
const filteredLog = computed(() => {
  let log = [...mockAuditLog]

  // Filter by secret ID
  if (props.secretId) {
    log = log.filter(e => e.secretId === props.secretId)
  }

  // Filter by action
  if (filterAction.value !== 'all') {
    log = log.filter(e => e.action === filterAction.value)
  }

  // Filter by user
  if (filterUser.value !== 'all') {
    log = log.filter(e => e.userId === filterUser.value)
  }

  return log.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
})

// Unique users for filter
const uniqueUsers = computed(() => {
  const users = new Set(mockAuditLog.map(e => ({ id: e.userId, name: e.username })))
  return Array.from(users).sort((a, b) => a.name.localeCompare(b.name))
})

// Format timestamp
const formatTime = (date: Date): string => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)

  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Get action styling
const getActionStyle = (action: SecretUsageAction): { color: string; icon: string } => {
  switch (action) {
    case 'access':
      return { color: 'text-blue-400 bg-blue-400/10', icon: 'key' }
    case 'inject':
      return { color: 'text-green-400 bg-green-400/10', icon: 'arrow-down-circle' }
    case 'copy':
      return { color: 'text-yellow-400 bg-yellow-400/10', icon: 'clipboard' }
    case 'reveal':
      return { color: 'text-orange-400 bg-orange-400/10', icon: 'eye' }
  }
}
</script>

<template>
  <div class="secret-audit-log h-full flex flex-col bg-gray-800 rounded-lg">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-gray-700">
      <h3 class="text-lg font-semibold text-gray-200 flex items-center gap-2">
        <i class="bi bi-clipboard-data" />
        Secret Audit Log
      </h3>

      <!-- Filters -->
      <div class="mt-3 flex items-center gap-2">
        <select
          v-model="filterAction"
          class="px-3 py-1.5 text-xs bg-gray-700 border border-gray-600 rounded text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Actions</option>
          <option value="access">Access</option>
          <option value="inject">Inject</option>
          <option value="copy">Copy</option>
          <option value="reveal">Reveal</option>
        </select>
        <select
          v-model="filterUser"
          class="px-3 py-1.5 text-xs bg-gray-700 border border-gray-600 rounded text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Users</option>
          <option v-for="user in uniqueUsers" :key="user.id" :value="user.id">
            {{ user.name }}
          </option>
        </select>
      </div>
    </div>

    <!-- Audit log list -->
    <div class="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
      <TransitionGroup name="audit">
        <div
          v-for="entry in filteredLog"
          :key="entry.id"
          class="flex items-start gap-3 p-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
        >
          <!-- Icon -->
          <div
            :class="[
              'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
              getActionStyle(entry.action).color
            ]"
          >
            <i :class="`bi bi-${getActionStyle(entry.action).icon}`" />
          </div>

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <div class="flex items-start justify-between gap-2 mb-1">
              <div class="flex-1">
                <div class="text-sm font-medium text-gray-200">
                  {{ entry.secretName }}
                </div>
                <div class="text-xs text-gray-400">
                  <span class="capitalize">{{ entry.action }}</span> by
                  <span class="font-medium">{{ entry.username }}</span>
                </div>
              </div>
              <span class="text-xs text-gray-500 flex-shrink-0">
                {{ formatTime(entry.timestamp) }}
              </span>
            </div>

            <!-- Metadata -->
            <div v-if="entry.metadata" class="text-xs text-gray-500 mt-1">
              <details class="cursor-pointer">
                <summary class="hover:text-gray-400">Details</summary>
                <pre class="mt-1 p-2 bg-gray-800 rounded text-xs overflow-x-auto">{{ JSON.stringify(entry.metadata, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Empty state -->
      <div
        v-if="filteredLog.length === 0"
        class="flex flex-col items-center justify-center py-12 text-gray-500"
      >
        <i class="bi bi-clipboard-data text-4xl mb-3" />
        <div class="text-sm font-medium mb-1">No audit entries</div>
        <div class="text-xs text-gray-600">
          Secret usage will be logged here
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audit-enter-active {
  transition: all 0.3s ease-out;
}

.audit-leave-active {
  transition: all 0.2s ease-in;
}

.audit-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.audit-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.audit-move {
  transition: transform 0.3s ease;
}

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
</style>
