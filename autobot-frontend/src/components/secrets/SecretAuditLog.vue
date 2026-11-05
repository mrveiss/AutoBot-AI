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
import { useSecretsAuditApi } from '@/composables/useSecretsAuditApi'
import { createLogger } from '@/utils/debugUtils'
import { auditTimestampToDate } from '@/types/audit'

const logger = createLogger('SecretAuditLog')
const { t } = useI18n()

// API composable
const auditApi = useSecretsAuditApi()

/**
 * Secret action types for filtering
 */
type SecretAction =
  | 'access'
  | 'create'
  | 'list'
  | 'update'
  | 'delete'
  | 'transfer'
  | 'bulk_delete'

/** i18n label key of each action, spelled out so key-usage checks can see them. */
const ACTION_LABEL_KEYS: Record<SecretAction, string> = {
  access: 'secrets.auditLog.access',
  create: 'secrets.auditLog.create',
  list: 'secrets.auditLog.list',
  update: 'secrets.auditLog.update',
  delete: 'secrets.auditLog.delete',
  transfer: 'secrets.auditLog.transfer',
  bulk_delete: 'secrets.auditLog.bulkDelete'
}

/**
 * Transformed audit entry for display
 */
interface DisplayAuditEntry {
  id: string
  secretName: string
  action: SecretAction
  userId: string
  username: string
  timestamp: Date
  details: Record<string, unknown>
  rawOperation: string
}

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
      // The backend writes `secret.<verb>` (api/secrets_audit.py SECRET_OPERATIONS)
      return entry.operation && entry.operation.startsWith('secret.')
    })
    .map(entry => {
      // Extract action from operation (e.g., 'secret.access' -> 'access')
      const action = (entry.operation?.split('.')[1] || 'access') as SecretAction

      // The name travels in `details` (create only); `resource` is a one-way
      // hash of the id, never the id, so it is only a correlator.
      const details = entry.details || {}
      const secretName = (details.name as string) || entry.resource || t('common.unknown')

      // The backend sends a user id, never a username
      const username = entry.user_id || t('common.unknown')

      return {
        id: entry.id,
        secretName,
        action,
        userId: entry.user_id || t('common.unknown'),
        username,
        timestamp: auditTimestampToDate(entry.timestamp),
        details,
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
      return { color: 'text-blue-400 bg-blue-400/10', icon: 'key' }
    case 'list':
      return { color: 'text-blue-300 bg-blue-300/10', icon: 'list-ul' }
    case 'transfer':
      return { color: 'text-yellow-400 bg-yellow-400/10', icon: 'arrow-left-right' }
    case 'create':
      return { color: 'text-green-500 bg-green-500/10', icon: 'plus-circle' }
    case 'update':
      return { color: 'text-purple-400 bg-purple-400/10', icon: 'pencil' }
    case 'delete':
    case 'bulk_delete':
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
          <option value="list">{{ $t('secrets.auditLog.list') }}</option>
          <option value="create">{{ $t('secrets.auditLog.create') }}</option>
          <option value="update">{{ $t('secrets.auditLog.update') }}</option>
          <option value="delete">{{ $t('secrets.auditLog.delete') }}</option>
          <option value="transfer">{{ $t('secrets.auditLog.transfer') }}</option>
          <option value="bulk_delete">{{ $t('secrets.auditLog.bulkDelete') }}</option>
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
                  <span>{{ $t(ACTION_LABEL_KEYS[entry.action]) }}</span> {{ $t('secrets.auditLog.by') }}
                  <span class="font-medium">{{ entry.username }}</span>
                </div>
              </div>
              <span class="text-xs text-autobot-text-muted flex-shrink-0">
                {{ formatTime(entry.timestamp) }}
              </span>
            </div>

            <!-- Metadata -->
            <div v-if="Object.keys(entry.details).length > 0" class="text-xs text-autobot-text-muted mt-1">
              <details class="cursor-pointer">
                <summary class="hover:text-autobot-text-muted">{{ $t('secrets.auditLog.details') }}</summary>
                <pre class="mt-1 p-2 bg-autobot-bg-secondary rounded text-xs overflow-x-auto">{{ JSON.stringify(entry.details, null, 2) }}</pre>
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
