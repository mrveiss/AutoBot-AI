<template>
  <div class="scope-selector">
    <label for="scope-select" class="scope-label">
      <span class="label-text">{{ $t('knowledge.scopeSelector.label') }}</span>
      <span v-if="showHelp" class="label-help">
        <Icon name="question-circle" />
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
        <Icon name="lock" /> {{ $t('knowledge.scopeSelector.private') }}
      </option>
      <option value="shared" v-if="allowShared">
        <Icon name="users" /> {{ $t('knowledge.scopeSelector.shared') }}
      </option>
      <option value="group" v-if="allowGroup && userGroups.length > 0">
        <Icon name="users" /> {{ $t('knowledge.scopeSelector.group', { count: userGroups.length, plural: userGroups.length > 1 ? 's' : '' }) }}
      </option>
      <option value="organization" v-if="allowOrganization && hasOrganization">
        <Icon name="desktop" /> {{ $t('knowledge.scopeSelector.organization') }}
      </option>
      <option value="system" v-if="allowSystem && isAdmin">
        <Icon name="globe" /> {{ $t('knowledge.scopeSelector.system') }}
      </option>
    </select>

    <!-- Help text -->
    <div v-if="helpVisible" class="scope-help">
      <div class="help-item">
        <strong>{{ $t('knowledge.scopeSelector.private').split(' (')[0] }}:</strong> {{ $t('knowledge.scopeSelector.helpPrivate') }}
      </div>
      <div class="help-item">
        <strong>{{ $t('knowledge.scopeSelector.shared').split(' (')[0] }}:</strong> {{ $t('knowledge.scopeSelector.helpShared') }}
      </div>
      <div class="help-item" v-if="userGroups.length > 0">
        <strong>{{ $t('knowledge.scopeSelector.group', { count: userGroups.length, plural: userGroups.length > 1 ? 's' : '' }).split(' (')[0] }}:</strong> {{ $t('knowledge.scopeSelector.helpGroup') }}
      </div>
      <div class="help-item" v-if="hasOrganization">
        <strong>{{ $t('knowledge.scopeSelector.organization').split(' (')[0] }}:</strong> {{ $t('knowledge.scopeSelector.helpOrganization') }}
      </div>
      <div class="help-item" v-if="isAdmin">
        <strong>{{ $t('knowledge.scopeSelector.system').split(' (')[0] }}:</strong> {{ $t('knowledge.scopeSelector.helpSystem') }}
      </div>
    </div>

    <!-- Group selector (shown when group scope selected) -->
    <div v-if="selectedScope === 'group' && showGroupSelector" class="group-selector">
      <label>{{ $t('knowledge.scopeSelector.selectTeams') }}</label>
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
import Icon from '@/components/ui/Icon.vue'
import { ref, watch } from 'vue'

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
  gap: var(--spacing-2);
}

.scope-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
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
  padding: var(--spacing-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: border-color var(--duration-200);
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
.scope-dropdown:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.scope-dropdown:disabled {
  background-color: var(--bg-secondary);
  cursor: not-allowed;
  opacity: 0.6;
}

.scope-help {
  margin-top: var(--spacing-2);
  padding: var(--spacing-3);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 0.813rem;
}

.help-item {
  margin-bottom: var(--spacing-2);
}

.help-item:last-child {
  margin-bottom: var(--spacing-0);
}

.help-item strong {
  color: var(--text-primary);
}

.group-selector {
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background-color: var(--bg-secondary);
}

.group-selector label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: 500;
  color: var(--text-secondary);
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.group-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  cursor: pointer;
  transition: background-color var(--duration-200);
}

.group-item:hover {
  background-color: var(--bg-tertiary);
}

.group-item input[type="checkbox"] {
  cursor: pointer;
}
</style>
