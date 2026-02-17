<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeDialog">
    <div class="modal-dialog">
      <div class="modal-header">
        <h3 class="modal-title">
          <i class="fas fa-share-alt"></i> Share "{{ factTitle }}"
        </h3>
        <button class="close-button" @click="closeDialog" aria-label="Close">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="modal-body">
        <!-- Search for users/groups -->
        <div class="search-section">
          <label for="share-search">Share with:</label>
          <div class="search-input-wrapper">
            <i class="fas fa-search search-icon"></i>
            <input
              id="share-search"
              v-model="searchQuery"
              type="text"
              placeholder="Search users or groups..."
              class="search-input"
              @input="handleSearch"
            />
          </div>
        </div>

        <!-- Search results -->
        <div v-if="searchResults.length > 0" class="search-results">
          <div
            v-for="result in searchResults"
            :key="`${result.type}-${result.id}`"
            class="search-result-item"
            @click="addEntity(result)"
          >
            <i :class="result.type === 'user' ? 'fas fa-user' : 'fas fa-users'"></i>
            <span class="result-name">{{ result.name }}</span>
            <span class="result-type">{{ result.type === 'user' ? 'User' : 'Team' }}</span>
          </div>
        </div>

        <!-- Current access list -->
        <div class="current-access">
          <h4>Current Access:</h4>
          <div v-if="currentAccess.length === 0" class="empty-state">
            No one else has access yet
          </div>
          <div v-else class="access-list">
            <div
              v-for="access in currentAccess"
              :key="`${access.type}-${access.id}`"
              class="access-item"
            >
              <div class="access-info">
                <i :class="access.type === 'user' ? 'fas fa-user' : 'fas fa-users'"></i>
                <span class="access-name">{{ access.name }}</span>
                <span class="access-type">{{ access.type === 'user' ? 'User' : 'Team' }}</span>
              </div>
              <div class="access-controls">
                <select
                  v-model="access.permission"
                  class="permission-select"
                  @change="handlePermissionChange(access)"
                >
                  <option value="read">Read</option>
                  <option value="write">Write</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  class="remove-button"
                  @click="removeEntity(access)"
                  aria-label="Remove access"
                >
                  <i class="fas fa-trash-alt"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" @click="closeDialog">
          Cancel
        </button>
        <button
          class="btn btn-primary"
          @click="saveChanges"
          :disabled="saving || !hasChanges"
        >
          <i class="fas fa-spinner fa-spin" v-if="saving"></i>
          <i class="fas fa-save" v-else></i>
          {{ saving ? 'Saving...' : 'Save Changes' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

/**
 * Share Knowledge Dialog Component
 *
 * Issue #679: Dialog for sharing knowledge with users and groups.
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
const initializeAccessList = () => {
  const accessList: ShareEntity[] = []

  // Add users
  props.currentUsers.forEach((userId) => {
    accessList.push({
      id: userId,
      name: userId, // TODO: Fetch user names from API
      type: 'user',
      permission: 'read',
    })
  })

  // Add groups
  props.currentGroups.forEach((groupId) => {
    accessList.push({
      id: groupId,
      name: groupId, // TODO: Fetch group names from API
      type: 'group',
      permission: 'read',
    })
  })

  currentAccess.value = accessList
  originalAccess.value = JSON.parse(JSON.stringify(accessList))
}

const handleSearch = async () => {
  if (searchQuery.value.length < 2) {
    searchResults.value = []
    return
  }

  // TODO: Call API to search users and groups
  // Placeholder mock data
  searchResults.value = [
    { id: 'user1', name: 'John Doe', type: 'user' },
    { id: 'user2', name: 'Jane Smith', type: 'user' },
    { id: 'group1', name: 'Engineering Team', type: 'group' },
    { id: 'group2', name: 'Security Team', type: 'group' },
  ].filter((item) =>
    item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
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
}

const removeEntity = (entity: ShareEntity) => {
  currentAccess.value = currentAccess.value.filter(
    (a) => !(a.id === entity.id && a.type === entity.type)
  )
}

const handlePermissionChange = (entity: ShareEntity) => {
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
    if (!confirm('You have unsaved changes. Are you sure you want to close?')) {
      return
    }
  }
  emit('close')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-dialog {
  background: var(--bg-card);
  border-radius: 0.5rem;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.close-button {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.25rem;
  transition: background-color 0.2s;
}

.close-button:hover {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.search-section {
  margin-bottom: 1.5rem;
}

.search-section label {
  display: block;
  margin-bottom: 0.5rem;
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
  padding: 0.5rem 0.75rem 0.5rem 2.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-electric-500, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.search-results {
  margin-bottom: 1.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  max-height: 200px;
  overflow-y: auto;
}

.search-result-item {
  padding: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  transition: background-color 0.2s;
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
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
}

.current-access h4 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: var(--text-muted);
  font-style: italic;
}

.access-list {
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
}

.access-item {
  padding: 0.75rem;
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
  gap: 0.75rem;
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
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
}

.access-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.permission-select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.25rem;
  font-size: 0.875rem;
  cursor: pointer;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.remove-button {
  background: none;
  border: none;
  padding: 0.5rem;
  cursor: pointer;
  color: #ef4444;
  border-radius: 0.25rem;
  transition: background-color 0.2s;
}

.remove-button:hover {
  background-color: #fee2e2;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
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
