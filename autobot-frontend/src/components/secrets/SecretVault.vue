<script setup lang="ts">
/**
 * Secret Vault Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 * Issue #4037: Virtual scrolling for large secret lists (100+ items)
 *
 * Manages session secrets with categorization, search, and sharing capabilities.
 * Fetches real secrets from backend API instead of using hardcoded mock data.
 * Uses virtual scrolling for efficient rendering of large secret lists.
 */

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSessionActivityLogger, type SecretType } from '@/composables/useSessionActivityLogger'
import { useDebounce } from '@/composables/useDebounce'
import { useVirtualList } from '@/composables/useVirtualList'
import { secretsApiClient } from '@/utils/SecretsApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('SecretVault')
const { t } = useI18n()
const { logSecretUsage } = useSessionActivityLogger()

// Props
const props = defineProps<{
  /** Show only session secrets or all accessible */
  scope?: 'session' | 'user' | 'all'
}>()

// Emits
const emit = defineEmits<{
  share: [secretId: string]
  revoke: [secretId: string]
  copy: [secretId: string]
  add: [secret: SecretItem]
  delete: [secretId: string]
}>()

// Secret item type from backend API
interface SecretItem {
  id: string
  name: string
  type: string
  scope: string
  value?: string
  description?: string
  created_at?: string
  updated_at?: string
}

// Local state
const searchQuery = ref('')
const filterType = ref<SecretType | 'all'>('all')
const showAddSecret = ref(false)
const revealedSecrets = ref<Set<string>>(new Set())
const sortBy = ref<'name' | 'type' | 'recent'>('name')
const { isLoading, wrap } = useLoadingState()
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)

// Secrets data from API
const secrets = ref<SecretItem[]>([])

// Debounce search query for performance (Issue #4035)
const debouncedSearchQuery = useDebounce(searchQuery, 400)

// Combine and filter secrets
const allSecrets = computed<SecretItem[]>(() => {
  let filtered = [...secrets.value]

  // Filter by scope
  if (props.scope === 'session') {
    filtered = filtered.filter(s => s.scope === 'session' || s.scope === 'chat')
  } else if (props.scope === 'user') {
    filtered = filtered.filter(s => s.scope === 'user' || s.scope === 'global')
  }

  // Filter by type - handle both snake_case and regular secret types
  if (filterType.value !== 'all') {
    filtered = filtered.filter(s => {
      const secretType = s.type as SecretType
      return secretType === filterType.value
    })
  }

  // Filter by search (using debounced query)
  if (debouncedSearchQuery.value) {
    const query = debouncedSearchQuery.value.toLowerCase()
    filtered = filtered.filter(s =>
      s.name.toLowerCase().includes(query) ||
      (s.type && s.type.toLowerCase().includes(query)) ||
      (s.description && s.description.toLowerCase().includes(query))
    )
  }

  // Sort
  if (sortBy.value === 'name') {
    filtered.sort((a, b) => a.name.localeCompare(b.name))
  } else if (sortBy.value === 'type') {
    filtered.sort((a, b) => (a.type || '').localeCompare(b.type || ''))
  } else if (sortBy.value === 'recent') {
    filtered.sort((a, b) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime()
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime()
      return bTime - aTime
    })
  }

  // Add id field if missing (required for virtual list)
  return filtered.map(s => ({
    ...s,
    id: s.id || `secret_${Math.random()}`
  }))
})

// Virtual scrolling composable - Issue #4037
// Each secret card is approximately 280px (with padding, metadata, actions)
const { containerRef, visibleItems, totalHeight } = useVirtualList<SecretItem>(allSecrets, 280, 2)

// Get secret type icon
const getTypeIcon = (type: string): string => {
  switch (type) {
    case 'ssh_key': return 'key'
    case 'password': return 'lock'
    case 'api_key': return 'code-slash'
    case 'token': return 'shield-check'
    case 'certificate': return 'file-earmark-lock'
    default: return 'key-fill'
  }
}

// Get scope badge
const getScopeBadge = (scope: string): { color: string; label: string } => {
  switch (scope) {
    case 'user':
    case 'global':
      return { color: 'bg-blue-500/20 text-blue-400', label: t('secrets.vault.scopePersonal') }
    case 'session':
    case 'chat':
      return { color: 'bg-green-500/20 text-green-400', label: t('secrets.vault.scopeSession') }
    case 'shared':
      return { color: 'bg-purple-500/20 text-purple-400', label: t('secrets.vault.scopeShared') }
    default:
      return { color: 'bg-gray-500/20 text-autobot-text-muted', label: scope }
  }
}

// Toggle secret visibility
const toggleReveal = (secretId: string) => {
  if (revealedSecrets.value.has(secretId)) {
    revealedSecrets.value.delete(secretId)
  } else {
    revealedSecrets.value.add(secretId)
    // Log reveal action
    const secret = allSecrets.value.find(s => s.id === secretId)
    if (secret) {
      logSecretUsage('reveal', secret.id, secret.name, (secret.type || 'unknown') as SecretType)
    }
  }
}

// Copy secret to clipboard
const copySecret = (secret: SecretItem) => {
  if (!secret.value) {
    error.value = t('secrets.vault.errorNoValue')
    setTimeout(() => { error.value = null }, 3000)
    return
  }
  navigator.clipboard.writeText(secret.value)
  emit('copy', secret.id)
  logSecretUsage('copy', secret.id, secret.name, (secret.type || 'unknown') as SecretType)
  successMessage.value = t('secrets.vault.copiedSuccess')
  setTimeout(() => { successMessage.value = null }, 3000)
}

// Share secret
const shareSecret = (secretId: string) => {
  emit('share', secretId)
}

// Revoke secret
const revokeSecret = async (secretId: string) => {
  if (!window.confirm(t('secrets.vault.revokeConfirm'))) return

  await wrap(async () => {
  try {
    await secretsApiClient.deleteSecret(secretId)
    secrets.value = secrets.value.filter(s => s.id !== secretId)
    emit('delete', secretId)
    successMessage.value = t('secrets.vault.revokeSuccess')
    setTimeout(() => { successMessage.value = null }, 3000)
  } catch (err) {
    logger.error('Failed to revoke secret:', err)
    error.value = t('secrets.vault.revokeError')
    setTimeout(() => { error.value = null }, 3000)
  }
  })
}

// Format date
const formatDate = (date: string | Date | undefined): string => {
  if (!date) return 'N/A'
  const d = new Date(date)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: '2-digit' })
}

// Load secrets from backend
const loadSecrets = async () => {
  error.value = null
  await wrap(async () => {
  try {
    const response = (await secretsApiClient.getSecrets({})) as { secrets?: SecretItem[] }
    secrets.value = response.secrets || []
    logger.info(`Loaded ${secrets.value.length} secrets from backend`)
  } catch (err) {
    logger.error('Failed to load secrets:', err)
    error.value = t('secrets.vault.loadError')
    secrets.value = []
  }
  })
}

// Secret type options
const typeOptions = computed<Array<{ value: SecretType | 'all'; label: string }>>(() => [
  { value: 'all', label: t('secrets.vault.typeAll') },
  { value: 'ssh_key', label: t('secrets.vault.typeSshKeys') },
  { value: 'password', label: t('secrets.vault.typePasswords') },
  { value: 'api_key', label: t('secrets.vault.typeApiKeys') },
  { value: 'token', label: t('secrets.vault.typeTokens') },
  { value: 'certificate', label: t('secrets.vault.typeCertificates') }
])

// Load secrets on mount
onMounted(() => {
  loadSecrets()
})
</script>

<template>
  <div class="secret-vault h-full flex flex-col bg-autobot-bg-secondary rounded-lg">
    <!-- Error/Success Messages -->
    <div v-if="error" class="px-4 py-2 bg-red-900/50 text-red-300 text-sm border-b border-red-700">
      <i class="bi bi-exclamation-circle mr-2" />
      {{ error }}
    </div>
    <div v-if="successMessage" class="px-4 py-2 bg-green-900/50 text-green-300 text-sm border-b border-green-700">
      <i class="bi bi-check-circle mr-2" />
      {{ successMessage }}
    </div>

    <!-- Header -->
    <div class="px-4 py-3 border-b border-autobot-border-strong">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-semibold text-autobot-text-primary">
          <i class="bi bi-shield-lock mr-2" />
          {{ $t('secrets.vault.title') }}
        </h3>
        <button
          class="px-3 py-1.5 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          :aria-label="$t('secrets.vault.addSecretAriaLabel')"
          :disabled="isLoading"
          @click="showAddSecret = true"
        >
          <i class="bi bi-plus-lg" />
          <span>{{ $t('secrets.vault.addSecret') }}</span>
        </button>
      </div>

      <!-- Search and filters -->
      <div class="space-y-2">
        <!-- Search -->
        <div class="relative">
          <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-autobot-text-muted" />
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="$t('secrets.vault.searchPlaceholder')"
            class="w-full pl-10 pr-4 py-2 bg-autobot-bg-secondary border border-autobot-border-strong rounded-lg text-autobot-text-primary placeholder-autobot-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
        </div>

        <!-- Filter bar -->
        <div class="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            v-for="option in typeOptions"
            :key="option.value"
            :class="[
              'px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors',
              filterType === option.value
                ? 'bg-blue-500 text-white'
                : 'bg-autobot-bg-secondary text-autobot-text-muted hover:bg-autobot-bg-hover'
            ]"
            @click="filterType = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Secret list with virtual scrolling -->
    <div ref="containerRef" class="flex-1 overflow-y-auto custom-scrollbar relative">
      <!-- Loading state -->
      <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center bg-autobot-bg-secondary/50">
        <div class="flex flex-col items-center gap-3">
          <div class="animate-spin">
            <i class="bi bi-hourglass text-2xl text-blue-400" />
          </div>
          <div class="text-sm text-autobot-text-muted">{{ $t('secrets.vault.loading') }}</div>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="allSecrets.length === 0"
        class="absolute inset-0 flex flex-col items-center justify-center text-autobot-text-muted"
      >
        <i class="bi bi-shield-lock text-4xl mb-3" />
        <div class="text-sm font-medium mb-1">{{ $t('secrets.vault.noSecrets') }}</div>
        <div class="text-xs text-autobot-text-secondary">
          {{ searchQuery ? $t('secrets.vault.noSecretsSearch') : $t('secrets.vault.noSecretsHint') }}
        </div>
      </div>

      <!-- Virtualized secrets list -->
      <div v-else :style="{ height: totalHeight + 'px', position: 'relative' }">
        <TransitionGroup name="secret" class="p-4 space-y-2">
          <div
            v-for="virtualItem in visibleItems"
            :key="virtualItem.data.id"
            class="bg-autobot-bg-secondary/50 rounded-lg p-4 hover:bg-autobot-bg-hover transition-colors border border-autobot-border-strong"
            :style="{ transform: `translateY(${virtualItem.offset}px)` }"
          >
          <!-- Header -->
          <div class="flex items-start justify-between mb-3">
            <div class="flex items-start gap-3 flex-1 min-w-0">
              <div class="w-10 h-10 rounded-lg bg-autobot-bg-tertiary flex items-center justify-center text-lg flex-shrink-0">
                <i :class="`bi bi-${getTypeIcon(virtualItem.data.type)}`" class="text-autobot-text-muted" />
              </div>
              <div class="flex-1 min-w-0">
                <h4 class="text-sm font-medium text-autobot-text-primary truncate">
                  {{ virtualItem.data.name }}
                </h4>
                <div class="flex items-center gap-2 mt-1 flex-wrap">
                  <span
                    :class="[
                      'px-2 py-0.5 text-xs rounded',
                      getScopeBadge(virtualItem.data.scope).color
                    ]"
                  >
                    {{ getScopeBadge(virtualItem.data.scope).label }}
                  </span>
                  <span class="text-xs text-autobot-text-muted">
                    {{ virtualItem.data.type }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Secret value -->
          <div class="mb-3">
            <div class="relative">
              <input
                :type="revealedSecrets.has(virtualItem.data.id) ? 'text' : 'password'"
                :value="virtualItem.data.value || '••••••••'"
                readonly
                class="w-full px-3 py-2 bg-autobot-bg-secondary border border-autobot-border-strong rounded text-xs text-autobot-text-muted font-mono"
              >
              <button
                class="absolute right-2 top-1/2 -translate-y-1/2 text-autobot-text-muted hover:text-autobot-text-primary transition-colors"
                :aria-label="revealedSecrets.has(virtualItem.data.id) ? $t('secrets.vault.hideSecret') : $t('secrets.vault.revealSecret')"
                @click="toggleReveal(virtualItem.data.id)"
              >
                <i :class="revealedSecrets.has(virtualItem.data.id) ? 'bi bi-eye-slash' : 'bi bi-eye'" />
              </button>
            </div>
          </div>

          <!-- Metadata -->
          <div class="flex items-center gap-4 text-xs text-autobot-text-muted mb-3">
            <span v-if="virtualItem.data.created_at">
              <i class="bi bi-calendar mr-1" />
              {{ $t('secrets.vault.created', { date: formatDate(virtualItem.data.created_at) }) }}
            </span>
            <span v-if="virtualItem.data.updated_at && virtualItem.data.updated_at !== virtualItem.data.created_at">
              <i class="bi bi-clock mr-1" />
              {{ $t('secrets.vault.used', { date: formatDate(virtualItem.data.updated_at) }) }}
            </span>
          </div>

          <!-- Description if available -->
          <div v-if="virtualItem.data.description" class="text-xs text-autobot-text-muted mb-3">
            {{ virtualItem.data.description }}
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 flex-wrap">
            <button
              class="px-3 py-1.5 text-xs rounded bg-autobot-bg-tertiary hover:bg-autobot-bg-hover text-autobot-text-primary transition-colors flex items-center gap-1 disabled:opacity-50"
              :aria-label="$t('secrets.vault.copyAriaLabel')"
              :disabled="isLoading"
              @click="copySecret(virtualItem.data)"
            >
              <i class="bi bi-clipboard" />
              {{ $t('secrets.vault.copyBtn') }}
            </button>
            <button
              v-if="virtualItem.data.scope === 'user' || virtualItem.data.scope === 'global'"
              class="px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1 disabled:opacity-50"
              :aria-label="$t('secrets.vault.shareAriaLabel')"
              :disabled="isLoading"
              @click="shareSecret(virtualItem.data.id)"
            >
              <i class="bi bi-share" />
              {{ $t('secrets.vault.shareBtn') }}
            </button>
            <button
              class="px-3 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500 text-white transition-colors flex items-center gap-1 disabled:opacity-50"
              :aria-label="$t('secrets.vault.revokeAriaLabel')"
              :disabled="isLoading"
              @click="revokeSecret(virtualItem.data.id)"
            >
              <i class="bi bi-x-circle" />
              {{ $t('secrets.vault.deleteBtn') }}
            </button>
          </div>
        </div>
        </TransitionGroup>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Secret animations */
.secret-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.secret-leave-active {
  transition: all var(--duration-200) var(--ease-in);
}

.secret-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.secret-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.secret-move {
  transition: transform var(--duration-300) var(--ease-out);
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
  border-radius: var(--radius-default);
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.5);
}
</style>
