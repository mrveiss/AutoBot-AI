<script setup lang="ts">
/**
 * Secret Audit Log Component
 *
 * Issue #3988: Display real audit logs from backend API instead of hardcoded mock data
 *
 * Displays audit trail of secret usage in the session with real backend data.
 * Supports filtering by action type and user, with pagination support.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSecretsAuditApi, type AuditLogEntry } from '@/composables/useSecretsAuditApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SecretAuditLog')
const { t } = useI18n()

// API composable
const auditApi = useSecretsAuditApi()

/**
 * Secret action types for filtering
 */
type SecretAction = 'access' | 'inject' | 'copy' | 'reveal' | 'create' | 'read' | 'update' | 'delete'

/**
 * Transformed audit entry for display
 */
interface DisplayAuditEntry {
  id: string
  secretId: string
  secretName: string
  action: SecretAction
  userId: string
  username: string
  timestamp: Date
  metadata?: Record<string, unknown>
  rawOperation: string
}

// Props
const props = defineProps<{
  /** Filter by specific secret ID */
  secretId?: string
}>()

// Local state
const filterAction = ref<SecretAction | 'all'>('all')
const filterUser = ref<string | 'all'>('all')
const currentPage = ref(0)
const pageSize = 50
const isLoadingInitial = ref(true)

// Fetch audit logs on mount
onMounted(async () => {
  await loadAuditLogs()
})

// Watch for filter changes and reload
watch([filterAction, filterUser], async () => {
  currentPage.value = 0
  await loadAuditLogs()
})

/**
 * Load audit logs from backend
 */
const loadAuditLogs = async () => {
  isLoadingInitial.value = true
  try {
    const offset = currentPage.value * pageSize

    await auditApi.fetchAuditLogs({
      operationFilter: filterAction.value,
      userIdFilter: filterUser.value,
      limit: pageSize,
      offset
    })

    logger.info(`Loaded ${auditApi.entries.value.length} audit log entries`)
  } catch (error) {
    logger.error('Failed to load audit logs:', error)
  } finally {
    isLoadingInitial.value = false
  }
}

/**
 * Transform backend audit entries to display format
 * Filters and extracts secret-specific information from audit entries
 */
const transformedEntries = computed((): DisplayAuditEntry[] => {
  return auditApi.entries.value
    .filter(entry => {
      // Only include secret-related operations
      return entry.operation && entry.operation.startsWith('secrets.')
    })
    .map(entry => {
      // Extract action from operation (e.g., 'secrets.access' -> 'access')
      const action = (entry.operation?.split('.')[1] || 'access') as SecretAction

      // Extract secret name and ID from metadata or resource
      const secretName = (entry.metadata?.secret_name as string) || 'Unknown Secret'
      const secretId = (entry.metadata?.secret_id as string) || entry.resource || 'unknown'

      // Extract username from user_id or metadata
      const username = (entry.metadata?.username as string) || entry.user_id || 'Unknown'

      return {
        id: entry.id,
        secretId,
        secretName,
        action,
        userId: entry.user_id || 'unknown',
        username,
        timestamp: new Date(entry.timestamp),
        metadata: entry.metadata || {},
        rawOperation: entry.operation
      }
    })
    .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
})

/**
 * Filtered audit log based on current filters
 */
const filteredLog = computed(() => {
  let log = [...transformedEntries.value]

  // Filter by secret ID if provided
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

  return log
})

/**
 * Get unique users from the audit log for filter dropdown
 */
const uniqueUsers = computed(() => {
  const users = new Set<{ id: string; name: string }>()

  transformedEntries.value.forEach(entry => {
    users.add({ id: entry.userId, name: entry.username })
  })

  return Array.from(users).sort((a, b) => a.name.localeCompare(b.name))
})

/**
 * Format timestamp to relative or absolute format
 */
const formatTime = (date: Date): string => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)

  if (minutes < 1) return t('secrets.auditLog.justNow')
  if (minutes < 60) return t('secrets.auditLog.minutesAgo', { minutes })
  if (hours < 24) return t('secrets.auditLog.hoursAgo', { hours })
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/**
 * Get styling for action type
 */
const getActionStyle = (action: SecretAction): { color: string; icon: string } => {
  switch (action) {
    case 'access':
    case 'read':
      return { color: 'text-blue-400 bg-blue-400/10', icon: 'key' }
    case 'inject':
      return { color: 'text-green-400 bg-green-400/10', icon: 'arrow-down-circle' }
    case 'copy':
      return { color: 'text-yellow-400 bg-yellow-400/10', icon: 'clipboard' }
    case 'reveal':
      return { color: 'text-orange-400 bg-orange-400/10', icon: 'eye' }
    case 'create':
      return { color: 'text-green-500 bg-green-500/10', icon: 'plus-circle' }
    case 'update':
      return { color: 'text-purple-400 bg-purple-400/10', icon: 'pencil' }
    case 'delete':
      return { color: 'text-red-400 bg-red-400/10', icon: 'trash' }
    default:
      return { color: 'text-autobot-text-muted bg-gray-400/10', icon: 'info-circle' }
  }
}

/**
 * Move to next page
 */
const nextPage = async () => {
  if (auditApi.hasMore.value) {
    currentPage.value++
    await loadAuditLogs()
  }
}

/**
 * Move to previous page
 */
const prevPage = async () => {
  if (currentPage.value > 0) {
    currentPage.value--
    await loadAuditLogs()
  }
}
</script>

<template>
  <div class="secret-audit-log h-full flex flex-col bg-autobot-bg-secondary rounded-lg">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-autobot-border-strong">
      <h3 class="text-lg font-semibold text-autobot-text-primary flex items-center gap-2">
        <i class="bi bi-clipboard-data" />
        {{ $t('secrets.auditLog.title') }}
      </h3>

      <!-- Filters -->
      <div class="mt-3 flex items-center gap-2">
        <select
          v-model="filterAction"
          class="px-3 py-1.5 text-xs bg-autobot-bg-secondary border border-autobot-border-strong rounded text-autobot-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">{{ $t('secrets.auditLog.allActions') }}</option>
          <option value="access">{{ $t('secrets.auditLog.access') }}</option>
          <option value="read">{{ $t('secrets.auditLog.read') }}</option>
          <option value="inject">{{ $t('secrets.auditLog.inject') }}</option>
          <option value="copy">{{ $t('secrets.auditLog.copy') }}</option>
          <option value="reveal">{{ $t('secrets.auditLog.reveal') }}</option>
          <option value="create">{{ $t('secrets.auditLog.create') }}</option>
          <option value="update">{{ $t('secrets.auditLog.update') }}</option>
          <option value="delete">{{ $t('secrets.auditLog.delete') }}</option>
        </select>
        <select
          v-model="filterUser"
          class="px-3 py-1.5 text-xs bg-autobot-bg-secondary border border-autobot-border-strong rounded text-autobot-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">{{ $t('secrets.auditLog.allUsers') }}</option>
          <option v-for="user in uniqueUsers" :key="user.id" :value="user.id">
            {{ user.name }}
          </option>
        </select>
      </div>
    </div>

    <!-- Loading State -->
    <div
      v-if="isLoadingInitial || auditApi.loading.value"
      class="flex-1 flex items-center justify-center"
    >
      <div class="text-center">
        <div class="inline-block">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
        <div class="mt-2 text-sm text-autobot-text-muted">{{ $t('common.loading') }}</div>
      </div>
    </div>

    <!-- Error State -->
    <div
      v-else-if="auditApi.error.value"
      class="flex-1 flex items-center justify-center p-4"
    >
      <div class="text-center text-red-400">
        <i class="bi bi-exclamation-triangle text-2xl mb-2" />
        <div class="text-sm">{{ auditApi.error.value }}</div>
        <button
          @click="loadAuditLogs"
          class="mt-3 px-3 py-1.5 text-xs bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 rounded text-red-300 transition-colors"
        >
          {{ $t('common.retry') }}
        </button>
      </div>
    </div>

    <!-- Audit Log Entries -->
    <div
      v-else
      class="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar"
    >
      <TransitionGroup name="audit">
        <div
          v-for="entry in filteredLog"
          :key="entry.id"
          class="flex items-start gap-3 p-3 bg-autobot-bg-secondary/50 rounded-lg hover:bg-autobot-bg-hover transition-colors"
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
                <div class="text-sm font-medium text-autobot-text-primary">
                  {{ entry.secretName }}
                </div>
                <div class="text-xs text-autobot-text-muted">
                  <span class="capitalize">{{ entry.action }}</span> {{ $t('secrets.auditLog.by') }}
                  <span class="font-medium">{{ entry.username }}</span>
                </div>
              </div>
              <span class="text-xs text-autobot-text-muted flex-shrink-0">
                {{ formatTime(entry.timestamp) }}
              </span>
            </div>

            <!-- Metadata -->
            <div v-if="entry.metadata && Object.keys(entry.metadata).length > 0" class="text-xs text-autobot-text-muted mt-1">
              <details class="cursor-pointer">
                <summary class="hover:text-autobot-text-muted">{{ $t('secrets.auditLog.details') }}</summary>
                <pre class="mt-1 p-2 bg-autobot-bg-secondary rounded text-xs overflow-x-auto">{{ JSON.stringify(entry.metadata, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Empty state -->
      <div
        v-if="filteredLog.length === 0"
        class="flex flex-col items-center justify-center py-12 text-autobot-text-muted"
      >
        <i class="bi bi-clipboard-data text-4xl mb-3" />
        <div class="text-sm font-medium mb-1">{{ $t('secrets.auditLog.noEntries') }}</div>
        <div class="text-xs text-autobot-text-secondary">
          {{ $t('secrets.auditLog.noEntriesHint') }}
        </div>
      </div>
    </div>

    <!-- Pagination Controls -->
    <div
      v-if="!auditApi.loading.value && !auditApi.error.value && auditApi.entries.value.length > 0"
      class="px-4 py-3 border-t border-autobot-border-strong flex items-center justify-between"
    >
      <div class="text-xs text-autobot-text-muted">
        {{ $t('common.page') }}: {{ currentPage + 1 }}
        <span v-if="auditApi.hasMore.value"> ({{ $t('common.hasMore') }})</span>
      </div>
      <div class="flex gap-2">
        <button
          :disabled="currentPage === 0"
          @click="prevPage"
          class="px-3 py-1.5 text-xs bg-autobot-bg-secondary hover:bg-autobot-bg-hover disabled:opacity-50 disabled:cursor-not-allowed border border-autobot-border-strong rounded text-autobot-text-muted transition-colors"
        >
          {{ $t('common.previous') }}
        </button>
        <button
          :disabled="!auditApi.hasMore.value"
          @click="nextPage"
          class="px-3 py-1.5 text-xs bg-autobot-bg-secondary hover:bg-autobot-bg-hover disabled:opacity-50 disabled:cursor-not-allowed border border-autobot-border-strong rounded text-autobot-text-muted transition-colors"
        >
          {{ $t('common.next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audit-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.audit-leave-active {
  transition: all var(--duration-200) var(--ease-in);
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
  transition: transform var(--duration-300) var(--ease-out);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.3);
  border-radius: var(--radius-default);
}
</style>
