<template>
  <BaseModal
    :model-value="isOpen"
    :title="$t('knowledge.share.title', { name: factTitle })"
    size="md"
    @close="closeDialog"
  >
    <template #title>
      <span class="modal-title-inner">
        <Icon name="share-alt" /> {{ $t('knowledge.share.title', { name: factTitle }) }}
      </span>
    </template>

        <!-- Search for users/groups -->
        <div class="search-section">
          <label for="share-search">{{ $t('knowledge.share.shareWith') }}</label>
          <div class="search-input-wrapper">
            <Icon name="search" class="search-icon" />
            <input
              id="share-search"
              v-model="searchQuery"
              type="text"
              :placeholder="$t('knowledge.share.searchPlaceholder')"
              class="search-input"
              @input="handleSearch"
            />
          </div>
        </div>

        <!-- Search results -->
        <div
          v-if="searching || searchError || searchResults.length > 0 || showNoResults"
          class="search-results"
        >
          <div v-if="searching" class="search-status">
            <Icon name="spinner" class="animate-spin" />
            {{ $t('knowledge.share.searching') }}
          </div>
          <div v-else-if="searchError" class="search-status search-status--error">
            <Icon name="exclamation-circle" />
            {{ searchError }}
          </div>
          <div v-else-if="showNoResults" class="search-status">
            {{ $t('knowledge.share.noResults') }}
          </div>
          <div
            v-for="result in searchResults"
            v-else
            :key="`${result.type}-${result.id}`"
            class="search-result-item"
            @click="addEntity(result)"
          >
            <Icon :name="result.type === 'user' ? 'user' : 'users'" />
            <span class="result-name">{{ result.name }}</span>
            <span class="result-type">{{ result.type === 'user' ? $t('knowledge.share.user') : $t('knowledge.share.team') }}</span>
          </div>
        </div>

        <!-- Current access list -->
        <div class="current-access">
          <h4>{{ $t('knowledge.share.currentAccess') }}</h4>
          <div v-if="currentAccess.length === 0" class="empty-state">
            {{ $t('knowledge.share.noAccess') }}
          </div>
          <div v-else class="access-list">
            <div
              v-for="access in currentAccess"
              :key="`${access.type}-${access.id}`"
              class="access-item"
            >
              <div class="access-info">
                <Icon :name="access.type === 'user' ? 'user' : 'users'" />
                <span class="access-name">{{ access.name }}</span>
                <span class="access-type">{{ access.type === 'user' ? $t('knowledge.share.user') : $t('knowledge.share.team') }}</span>
              </div>
              <div class="access-controls">
                <select
                  v-model="access.permission"
                  class="permission-select"
                  @change="handlePermissionChange(access)"
                >
                  <option value="read">{{ $t('knowledge.share.read') }}</option>
                  <option value="write">{{ $t('knowledge.share.write') }}</option>
                  <option value="admin">{{ $t('knowledge.share.admin') }}</option>
                </select>
                <button
                  class="remove-button"
                  @click="removeEntity(access)"
                  :aria-label="$t('knowledge.share.removeAccess')"
                >
                  <Icon name="trash-alt" />
                </button>
              </div>
            </div>
          </div>
        </div>

    <template #actions>
        <button class="btn btn-secondary" @click="closeDialog">
          {{ $t('knowledge.share.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          @click="saveChanges"
          :disabled="saving || !hasChanges"
        >
          <Icon name="spinner" class="animate-spin" />
          <Icon name="save" />
          {{ saving ? $t('knowledge.share.saving') : $t('knowledge.share.saveChanges') }}
        </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiService } from '@/services/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
const logger = createLogger('ShareKnowledgeDialog')

/**
 * Share Knowledge Dialog Component
 *
 * Issue #679: Dialog for sharing knowledge with users and groups.
 * Issue #2072: Replaced mock user search data with real API call.
 * Issue #3984: Fetch user/group names from API instead of displaying IDs.
 */

// Types
interface ShareEntity {
  id: string
  name: string
  type: 'user' | 'group'
  permission?: 'read' | 'write' | 'admin'
}

interface Props {
  isOpen: boolean
  factId: string
  factTitle: string
  currentUsers?: string[]
  currentGroups?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  currentUsers: () => [],
  currentGroups: () => [],
})

// Emits
const emit = defineEmits<{
  'close': []
  'save': [users: string[], groups: string[], permissions: Record<string, string>]
}>()

// State
const searchQuery = ref('')
const searchResults = ref<ShareEntity[]>([])
const currentAccess = ref<ShareEntity[]>([])
const saving = ref(false)
const originalAccess = ref<ShareEntity[]>([])
const searching = ref(false)
const searchError = ref<string | null>(null)
const showNoResults = ref(false)

// Cache for user/group lookups to avoid repeated API calls
const entityCache = new Map<string, ShareEntity>()

// Computed
const hasChanges = computed(() => {
  return JSON.stringify(currentAccess.value) !== JSON.stringify(originalAccess.value)
})

// Initialize access list from props
watch(
  () => [props.currentUsers, props.currentGroups, props.isOpen],
  () => {
    if (props.isOpen) {
      initializeAccessList()
    }
  },
  { immediate: true }
)

// Methods
const fetchEntityName = async (id: string, type: 'user' | 'group'): Promise<string> => {
  const cacheKey = `${type}:${id}`

  // Check cache first
  if (entityCache.has(cacheKey)) {
    return entityCache.get(cacheKey)?.name || id
  }

  try {
    let displayName = id
    if (type === 'user') {
      const userData = await apiService.getUserById(id)
      if (userData) {
        displayName = userData.display_name || userData.email || userData.username || id
      }
    } else {
      const groupData = await apiService.getGroupById(id)
      if (groupData) {
        displayName = groupData.name || id
      }
    }

    // Cache the result
    entityCache.set(cacheKey, { id, name: displayName, type })
    return displayName
  } catch (err) {
    logger.warn(`Failed to fetch ${type} details for ${id}: %o`, err)
    return id
  }
}

const initializeAccessList = async () => {
  const accessList: ShareEntity[] = []

  // Add users with fetched names
  for (const userId of props.currentUsers) {
    const name = await fetchEntityName(userId, 'user')
    accessList.push({
      id: userId,
      name,
      type: 'user',
      permission: 'read',
    })
  }

  // Add groups with fetched names
  for (const groupId of props.currentGroups) {
    const name = await fetchEntityName(groupId, 'group')
    accessList.push({
      id: groupId,
      name,
      type: 'group',
      permission: 'read',
    })
  }

  currentAccess.value = accessList
  originalAccess.value = JSON.parse(JSON.stringify(accessList))
}

const handleSearch = async () => {
  const query = searchQuery.value
  if (query.length < 2) {
    searchResults.value = []
    searchError.value = null
    showNoResults.value = false
    return
  }

  searching.value = true
  searchError.value = null
  showNoResults.value = false
  searchResults.value = []

  try {
    const url = `${getApiBase()}/user-management/users/search?q=${encodeURIComponent(query)}&limit=10`
    const response = await apiService.get<{
      users: ShareEntity[]
      available: boolean
      message: string
    }>(url)

    if (!response.available) {
      searchError.value = response.message || t('knowledge.share.searchUnavailable')
      logger.debug('User search not available: %s', response.message)
      return
    }

    searchResults.value = response.users
    showNoResults.value = response.users.length === 0
  } catch (err) {
    logger.error('User search failed: %o', err)
    searchError.value = t('knowledge.share.searchError')
  } finally {
    searching.value = false
  }
}

const addEntity = (entity: ShareEntity) => {
  // Check if already in list
  const exists = currentAccess.value.some(
    (a) => a.id === entity.id && a.type === entity.type
  )

  if (!exists) {
    currentAccess.value.push({
      ...entity,
      permission: 'read',
    })
  }

  // Clear search
  searchQuery.value = ''
  searchResults.value = []
  searchError.value = null
  showNoResults.value = false
}

const removeEntity = (entity: ShareEntity) => {
  currentAccess.value = currentAccess.value.filter(
    (a) => !(a.id === entity.id && a.type === entity.type)
  )
}

const handlePermissionChange = (_entity: ShareEntity) => {
  // Permission changes are already bound via v-model
  // Permissions are updated automatically via v-model binding
}

const saveChanges = async () => {
  saving.value = true

  try {
    const users = currentAccess.value
      .filter((a) => a.type === 'user')
      .map((a) => a.id)

    const groups = currentAccess.value
      .filter((a) => a.type === 'group')
      .map((a) => a.id)

    const permissions: Record<string, string> = {}
    currentAccess.value.forEach((a) => {
      permissions[`${a.type}:${a.id}`] = a.permission || 'read'
    })

    emit('save', users, groups, permissions)

    // Update original to match current (changes saved)
    originalAccess.value = JSON.parse(JSON.stringify(currentAccess.value))
  } finally {
    saving.value = false
  }
}

const closeDialog = () => {
  if (hasChanges.value) {
    if (!confirm(t('knowledge.share.unsavedConfirm'))) {
      return
    }
  }
  emit('close')
}
</script>

<style scoped>
.modal-title-inner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.search-section {
  margin-bottom: var(--spacing-6);
}

.search-section label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: 500;
  color: var(--text-secondary);
}

.search-input-wrapper {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-10);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-electric-500, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.search-results {
  margin-bottom: var(--spacing-6);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  max-height: 200px;
  overflow-y: auto;
}

.search-status {
  padding: var(--spacing-3);
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.search-status--error {
  color: var(--color-error);
}

.search-result-item {
  padding: var(--spacing-3);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  cursor: pointer;
  transition: background-color var(--duration-200);
}

.search-result-item:hover {
  background-color: var(--bg-secondary);
}

.search-result-item i {
  color: var(--text-muted);
}

.result-name {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.result-type {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
}

.current-access h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state {
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-muted);
  font-style: italic;
}

.access-list {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.access-item {
  padding: var(--spacing-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-default);
}

.access-item:last-child {
  border-bottom: none;
}

.access-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  flex: 1;
}

.access-info i {
  color: var(--text-muted);
}

.access-name {
  font-weight: 500;
  color: var(--text-primary);
}

.access-type {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
}

.access-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.permission-select {
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  cursor: pointer;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.remove-button {
  background: none;
  border: none;
  padding: var(--spacing-2);
  cursor: pointer;
  color: var(--color-error);
  border-radius: var(--radius-default);
  transition: background-color var(--duration-200);
}

.remove-button:hover {
  background-color: #fee2e2;
}

.btn {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-secondary {
  background-color: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background-color: var(--bg-secondary);
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
