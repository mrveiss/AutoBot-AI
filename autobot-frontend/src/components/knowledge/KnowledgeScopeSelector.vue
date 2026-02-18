<template>
  <div class="scope-selector">
    <label for="scope-select" class="scope-label">
      <span class="label-text">Knowledge Scope:</span>
      <span v-if="showHelp" class="label-help">
        <i class="fas fa-question-circle" @click="helpVisible = !helpVisible"></i>
      </span>
    </label>

    <select
      id="scope-select"
      v-model="selectedScope"
      class="scope-dropdown"
      @change="handleScopeChange"
      :disabled="disabled"
    >
      <option value="private">
        <i class="fas fa-lock"></i> Private (Only me)
      </option>
      <option value="shared" v-if="allowShared">
        <i class="fas fa-user-friends"></i> Shared (Specific users/groups)
      </option>
      <option value="group" v-if="allowGroup && userGroups.length > 0">
        <i class="fas fa-users"></i> Group ({{ userGroups.length }} team{{ userGroups.length > 1 ? 's' : '' }})
      </option>
      <option value="organization" v-if="allowOrganization && hasOrganization">
        <i class="fas fa-building"></i> Organization (Company-wide)
      </option>
      <option value="system" v-if="allowSystem && isAdmin">
        <i class="fas fa-globe"></i> System (Platform-wide)
      </option>
    </select>

    <!-- Help text -->
    <div v-if="helpVisible" class="scope-help">
      <div class="help-item">
        <strong>Private:</strong> Only you can access this knowledge.
      </div>
      <div class="help-item">
        <strong>Shared:</strong> You control who has access by explicitly sharing.
      </div>
      <div class="help-item" v-if="userGroups.length > 0">
        <strong>Group:</strong> Accessible to members of selected team(s).
      </div>
      <div class="help-item" v-if="hasOrganization">
        <strong>Organization:</strong> All members of your organization can access.
      </div>
      <div class="help-item" v-if="isAdmin">
        <strong>System:</strong> Accessible to all users on the platform.
      </div>
    </div>

    <!-- Group selector (shown when group scope selected) -->
    <div v-if="selectedScope === 'group' && showGroupSelector" class="group-selector">
      <label>Select Teams:</label>
      <div class="group-list">
        <label
          v-for="group in userGroups"
          :key="group.id"
          class="group-item"
        >
          <input
            type="checkbox"
            :value="group.id"
            v-model="selectedGroups"
            @change="handleGroupChange"
          />
          <span>{{ group.name }}</span>
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

/**
 * Knowledge Scope Selector Component
 *
 * Issue #679: Allows users to select visibility scope for knowledge facts.
 */

// Props
interface Props {
  modelValue?: string
  disabled?: boolean
  showHelp?: boolean
  showGroupSelector?: boolean
  allowShared?: boolean
  allowGroup?: boolean
  allowOrganization?: boolean
  allowSystem?: boolean
  userGroups?: Array<{ id: string; name: string }>
  hasOrganization?: boolean
  isAdmin?: boolean
  selectedGroupIds?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: 'private',
  disabled: false,
  showHelp: true,
  showGroupSelector: true,
  allowShared: true,
  allowGroup: true,
  allowOrganization: false,
  allowSystem: false,
  userGroups: () => [],
  hasOrganization: false,
  isAdmin: false,
  selectedGroupIds: () => [],
})

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:selectedGroupIds': [value: string[]]
  'scope-change': [scope: string, groupIds: string[]]
}>()

// State
const selectedScope = ref(props.modelValue)
const selectedGroups = ref<string[]>(props.selectedGroupIds)
const helpVisible = ref(false)

// Watch for prop changes
watch(
  () => props.modelValue,
  (newValue) => {
    selectedScope.value = newValue
  }
)

watch(
  () => props.selectedGroupIds,
  (newValue) => {
    selectedGroups.value = newValue
  }
)

// Handlers
const handleScopeChange = () => {
  emit('update:modelValue', selectedScope.value)
  emit('scope-change', selectedScope.value, selectedGroups.value)
}

const handleGroupChange = () => {
  emit('update:selectedGroupIds', selectedGroups.value)
  emit('scope-change', selectedScope.value, selectedGroups.value)
}
</script>

<style scoped>
.scope-selector {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.scope-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.label-help {
  cursor: pointer;
  color: var(--text-muted);
}

.label-help:hover {
  color: var(--color-electric-500, #3b82f6);
}

.scope-dropdown {
  padding: 0.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: border-color 0.2s;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.scope-dropdown:hover {
  border-color: var(--text-muted);
}

.scope-dropdown:focus {
  outline: none;
  border-color: var(--color-electric-500, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.scope-dropdown:disabled {
  background-color: var(--bg-secondary);
  cursor: not-allowed;
  opacity: 0.6;
}

.scope-help {
  margin-top: 0.5rem;
  padding: 0.75rem;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.813rem;
}

.help-item {
  margin-bottom: 0.5rem;
}

.help-item:last-child {
  margin-bottom: 0;
}

.help-item strong {
  color: var(--text-primary);
}

.group-selector {
  margin-top: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background-color: var(--bg-secondary);
}

.group-selector label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.group-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: background-color 0.2s;
}

.group-item:hover {
  background-color: var(--bg-tertiary);
}

.group-item input[type="checkbox"] {
  cursor: pointer;
}
</style>
