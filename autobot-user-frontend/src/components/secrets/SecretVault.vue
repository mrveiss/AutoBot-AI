<script setup lang="ts">
/**
 * Secret Vault Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Manages session secrets with categorization, search, and sharing capabilities.
 */

import { ref, computed } from 'vue'
import { useChatStore, type SessionSecret } from '@/stores/useChatStore'
import { useSessionActivityLogger, type SecretType } from '@/composables/useSessionActivityLogger'

const chatStore = useChatStore()
const { linkSecretToSession, logSecretUsage } = useSessionActivityLogger()

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
}>()

// Local state
const searchQuery = ref('')
const filterType = ref<SecretType | 'all'>('all')
const showAddSecret = ref(false)
const revealedSecrets = ref<Set<string>>(new Set())
const sortBy = ref<'name' | 'type' | 'recent'>('name')

// Mock secrets data (in real implementation, comes from API)
const mockSecrets: Array<SessionSecret & { value: string; createdAt: Date; lastUsed?: Date }> = [
  {
    id: 'secret-1',
    name: 'GitHub API Token',
    type: 'api_key',
    scope: 'user',
    ownerId: 'user-1',
    usageCount: 5,
    value: 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    createdAt: new Date('2024-01-15'),
    lastUsed: new Date('2024-02-14')
  },
  {
    id: 'secret-2',
    name: 'SSH Private Key',
    type: 'ssh_key',
    scope: 'session',
    ownerId: 'user-1',
    usageCount: 2,
    value: '-----BEGIN OPENSSH PRIVATE KEY-----\nxxxxxxxx\n-----END OPENSSH PRIVATE KEY-----',
    createdAt: new Date('2024-02-01')
  },
  {
    id: 'secret-3',
    name: 'Database Password',
    type: 'password',
    scope: 'shared',
    ownerId: 'user-2',
    usageCount: 12,
    value: 'super_secret_password_123',
    createdAt: new Date('2024-02-10'),
    lastUsed: new Date('2024-02-15')
  },
  {
    id: 'secret-4',
    name: 'AWS Access Token',
    type: 'token',
    scope: 'user',
    ownerId: 'user-1',
    usageCount: 0,
    value: 'AKIAxxxxxxxxxxxxxxxxx',
    createdAt: new Date('2024-01-20')
  }
]

// Get current session secrets
const currentSession = computed(() => chatStore.currentSession)
const sessionSecrets = computed(() => {
  if (!currentSession.value?.sessionSecrets) return []
  return currentSession.value.sessionSecrets
})

// Combine and filter secrets
const allSecrets = computed(() => {
  // Merge mock data with session secrets
  const combined = [...mockSecrets]

  // Filter by scope
  let filtered = combined
  if (props.scope === 'session') {
    filtered = combined.filter(s => s.scope === 'session')
  } else if (props.scope === 'user') {
    filtered = combined.filter(s => s.scope === 'user')
  }

  // Filter by type
  if (filterType.value !== 'all') {
    filtered = filtered.filter(s => s.type === filterType.value)
  }

  // Filter by search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(s =>
      s.name.toLowerCase().includes(query) ||
      s.type.toLowerCase().includes(query)
    )
  }

  // Sort
  if (sortBy.value === 'name') {
    filtered.sort((a, b) => a.name.localeCompare(b.name))
  } else if (sortBy.value === 'type') {
    filtered.sort((a, b) => a.type.localeCompare(b.type))
  } else if (sortBy.value === 'recent') {
    filtered.sort((a, b) => {
      const aTime = a.lastUsed?.getTime() || a.createdAt.getTime()
      const bTime = b.lastUsed?.getTime() || b.createdAt.getTime()
      return bTime - aTime
    })
  }

  return filtered
})

// Get secret type icon
const getTypeIcon = (type: SecretType): string => {
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
const getScopeBadge = (scope: SessionSecret['scope']): { color: string; label: string } => {
  switch (scope) {
    case 'user':
      return { color: 'bg-blue-500/20 text-blue-400', label: 'Personal' }
    case 'session':
      return { color: 'bg-green-500/20 text-green-400', label: 'Session' }
    case 'shared':
      return { color: 'bg-purple-500/20 text-purple-400', label: 'Shared' }
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
      logSecretUsage('reveal', secret.id, secret.name, secret.type as SecretType)
    }
  }
}

// Copy secret to clipboard
const copySecret = (secret: typeof mockSecrets[0]) => {
  navigator.clipboard.writeText(secret.value)
  emit('copy', secret.id)
  logSecretUsage('copy', secret.id, secret.name, secret.type as SecretType)
}

// Share secret
const shareSecret = (secretId: string) => {
  emit('share', secretId)
}

// Revoke secret
const revokeSecret = (secretId: string) => {
  if (!window.confirm('Are you sure you want to revoke access to this secret?')) return
  emit('revoke', secretId)
}

// Format date
const formatDate = (date: Date): string => {
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

// Secret type options
const typeOptions: Array<{ value: SecretType | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'ssh_key', label: 'SSH Keys' },
  { value: 'password', label: 'Passwords' },
  { value: 'api_key', label: 'API Keys' },
  { value: 'token', label: 'Tokens' },
  { value: 'certificate', label: 'Certificates' }
]
</script>

<template>
  <div class="secret-vault h-full flex flex-col bg-gray-800 rounded-lg">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-gray-700">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-semibold text-gray-200">
          <i class="bi bi-shield-lock mr-2" />
          Secret Vault
        </h3>
        <button
          class="px-3 py-1.5 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors flex items-center gap-2"
          aria-label="Add secret"
          @click="showAddSecret = true"
        >
          <i class="bi bi-plus-lg" />
          <span>Add Secret</span>
        </button>
      </div>

      <!-- Search and filters -->
      <div class="space-y-2">
        <!-- Search -->
        <div class="relative">
          <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search secrets..."
            class="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
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
                : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            ]"
            @click="filterType = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Secret list -->
    <div class="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
      <TransitionGroup name="secret">
        <div
          v-for="secret in allSecrets"
          :key="secret.id"
          class="bg-gray-700/50 rounded-lg p-4 hover:bg-gray-700 transition-colors border border-gray-600"
        >
          <!-- Header -->
          <div class="flex items-start justify-between mb-3">
            <div class="flex items-start gap-3 flex-1 min-w-0">
              <div class="w-10 h-10 rounded-lg bg-gray-600 flex items-center justify-center text-lg flex-shrink-0">
                <i :class="`bi bi-${getTypeIcon(secret.type as SecretType)}`" class="text-gray-300" />
              </div>
              <div class="flex-1 min-w-0">
                <h4 class="text-sm font-medium text-gray-200 truncate">
                  {{ secret.name }}
                </h4>
                <div class="flex items-center gap-2 mt-1 flex-wrap">
                  <span
                    :class="[
                      'px-2 py-0.5 text-xs rounded',
                      getScopeBadge(secret.scope).color
                    ]"
                  >
                    {{ getScopeBadge(secret.scope).label }}
                  </span>
                  <span class="text-xs text-gray-500">
                    {{ secret.type.replace('_', ' ') }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Secret value -->
          <div class="mb-3">
            <div class="relative">
              <input
                :type="revealedSecrets.has(secret.id) ? 'text' : 'password'"
                :value="secret.value"
                readonly
                class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-xs text-gray-300 font-mono"
              >
              <button
                class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 transition-colors"
                :aria-label="revealedSecrets.has(secret.id) ? 'Hide secret' : 'Reveal secret'"
                @click="toggleReveal(secret.id)"
              >
                <i :class="revealedSecrets.has(secret.id) ? 'bi bi-eye-slash' : 'bi bi-eye'" />
              </button>
            </div>
          </div>

          <!-- Metadata -->
          <div class="flex items-center gap-4 text-xs text-gray-500 mb-3">
            <span>
              <i class="bi bi-calendar mr-1" />
              Created {{ formatDate(secret.createdAt) }}
            </span>
            <span v-if="secret.lastUsed">
              <i class="bi bi-clock mr-1" />
              Used {{ formatDate(secret.lastUsed) }}
            </span>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 flex-wrap">
            <button
              class="px-3 py-1.5 text-xs rounded bg-gray-600 hover:bg-gray-500 text-gray-200 transition-colors flex items-center gap-1"
              aria-label="Copy to clipboard"
              @click="copySecret(secret)"
            >
              <i class="bi bi-clipboard" />
              Copy
            </button>
            <button
              v-if="secret.scope === 'user'"
              class="px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1"
              aria-label="Share with session"
              @click="shareSecret(secret.id)"
            >
              <i class="bi bi-share" />
              Share
            </button>
            <button
              v-if="secret.scope === 'shared'"
              class="px-3 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500 text-white transition-colors flex items-center gap-1"
              aria-label="Revoke access"
              @click="revokeSecret(secret.id)"
            >
              <i class="bi bi-x-circle" />
              Revoke
            </button>
          </div>
        </div>
      </TransitionGroup>

      <!-- Empty state -->
      <div
        v-if="allSecrets.length === 0"
        class="flex flex-col items-center justify-center py-12 text-gray-500"
      >
        <i class="bi bi-shield-lock text-4xl mb-3" />
        <div class="text-sm font-medium mb-1">No secrets found</div>
        <div class="text-xs text-gray-600">
          {{ searchQuery ? 'Try a different search' : 'Add a secret to get started' }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Secret animations */
.secret-enter-active {
  transition: all 0.3s ease-out;
}

.secret-leave-active {
  transition: all 0.2s ease-in;
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
  transition: transform 0.3s ease;
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
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.5);
}
</style>
