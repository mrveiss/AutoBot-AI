<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Permission Settings Component

  Provides UI for managing the Claude Code-style permission system:
  - Permission mode selector dropdown
  - Rule management UI (add/remove rules)
  - Project approval memory viewer
  - Permission system status display

  Issue: Permission System v2 - Claude Code Style
-->
<template>
  <div class="permission-settings">
    <!-- Header -->
    <div class="settings-header">
      <h3 class="settings-title">
        <i class="fas fa-shield-halved" aria-hidden="true"></i>
        Permission System
      </h3>
      <div class="settings-status">
        <span
          class="status-badge"
          :class="permissionStore.isEnabled ? 'status-enabled' : 'status-disabled'"
        >
          {{ permissionStore.isEnabled ? 'Enabled' : 'Disabled' }}
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="permissionStore.loading" class="loading-state">
      <LoadingSpinner size="md" />
      <span>Loading permission settings...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="permissionStore.error" class="error-state">
      <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
      <span>{{ permissionStore.error }}</span>
      <BaseButton variant="secondary" size="sm" @click="refreshData">
        Retry
      </BaseButton>
    </div>

    <!-- Main Content -->
    <div v-else class="settings-content">
      <!-- Permission Mode Section -->
      <div class="settings-section">
        <h4 class="section-title">
          <i class="fas fa-sliders" aria-hidden="true"></i>
          Permission Mode
        </h4>
        <p class="section-description">
          Controls how command approvals are handled. Some modes require admin privileges.
        </p>

        <div class="mode-selector">
          <select
            v-model="selectedMode"
            @change="onModeChange"
            class="mode-select"
            :disabled="permissionStore.loading"
          >
            <option
              v-for="mode in availableModes"
              :key="mode.value"
              :value="mode.value"
              :disabled="mode.adminOnly && !isAdmin"
            >
              {{ mode.label }}{{ mode.adminOnly ? ' (Admin)' : '' }}
            </option>
          </select>
          <div class="mode-description">
            {{ getModeDescription(selectedMode) }}
          </div>
        </div>
      </div>

      <!-- Permission Rules Section -->
      <div class="settings-section">
        <h4 class="section-title">
          <i class="fas fa-list-check" aria-hidden="true"></i>
          Permission Rules
          <span class="rules-count">({{ permissionStore.totalRulesCount }})</span>
        </h4>
        <p class="section-description">
          Define patterns that automatically allow, ask, or deny specific commands.
        </p>

        <!-- Rules Tabs -->
        <div class="rules-tabs">
          <button
            v-for="tab in ruleTabs"
            :key="tab.id"
            class="rules-tab"
            :class="{ active: activeRuleTab === tab.id }"
            @click="activeRuleTab = tab.id"
          >
            <i :class="tab.icon" aria-hidden="true"></i>
            {{ tab.label }}
            <span class="tab-count">{{ getRuleCount(tab.id) }}</span>
          </button>
        </div>

        <!-- Rules List -->
        <div class="rules-list">
          <div v-if="currentRules.length === 0" class="rules-empty">
            <i class="fas fa-inbox" aria-hidden="true"></i>
            <span>No {{ activeRuleTab }} rules configured</span>
          </div>
          <div
            v-for="rule in currentRules"
            :key="`${rule.tool}-${rule.pattern}`"
            class="rule-item"
          >
            <div class="rule-info">
              <code class="rule-pattern">{{ rule.tool }}({{ rule.pattern }})</code>
              <span class="rule-description">{{ rule.description }}</span>
            </div>
            <BaseButton
              variant="ghost"
              size="xs"
              @click="removeRule(rule)"
              class="rule-remove"
              aria-label="Remove rule"
            >
              <i class="fas fa-trash" aria-hidden="true"></i>
            </BaseButton>
          </div>
        </div>

        <!-- Add Rule Form -->
        <div class="add-rule-form">
          <h5 class="form-title">Add New Rule</h5>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Tool</label>
              <select v-model="newRule.tool" class="form-input">
                <option value="Bash">Bash</option>
                <option value="Edit">Edit</option>
                <option value="Write">Write</option>
                <option value="Read">Read</option>
              </select>
            </div>
            <div class="form-group flex-1">
              <label class="form-label">Pattern</label>
              <input
                v-model="newRule.pattern"
                type="text"
                class="form-input"
                placeholder="e.g., npm run *"
              />
            </div>
            <div class="form-group">
              <label class="form-label">Action</label>
              <select v-model="newRule.action" class="form-input">
                <option value="allow" :disabled="!isAdmin">Allow{{ !isAdmin ? ' (Admin)' : '' }}</option>
                <option value="ask">Ask</option>
                <option value="deny">Deny</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label class="form-label">Description (optional)</label>
              <input
                v-model="newRule.description"
                type="text"
                class="form-input"
                placeholder="What does this rule do?"
              />
            </div>
            <BaseButton
              variant="primary"
              size="sm"
              @click="addRule"
              :disabled="!canAddRule"
              class="add-rule-btn"
            >
              <i class="fas fa-plus" aria-hidden="true"></i>
              Add Rule
            </BaseButton>
          </div>
        </div>
      </div>

      <!-- Project Memory Section -->
      <div class="settings-section">
        <h4 class="section-title">
          <i class="fas fa-folder-open" aria-hidden="true"></i>
          Project Approval Memory
        </h4>
        <p class="section-description">
          View and manage remembered approvals for the current project.
        </p>

        <div v-if="!currentProjectPath" class="memory-empty">
          <i class="fas fa-folder-minus" aria-hidden="true"></i>
          <span>No project context set</span>
        </div>

        <div v-else class="memory-content">
          <div class="memory-header">
            <span class="memory-project">
              <i class="fas fa-folder" aria-hidden="true"></i>
              {{ currentProjectPath }}
            </span>
            <BaseButton
              variant="danger"
              size="xs"
              @click="clearProjectMemory"
              :disabled="permissionStore.getCurrentProjectApprovals.length === 0"
            >
              <i class="fas fa-trash" aria-hidden="true"></i>
              Clear All
            </BaseButton>
          </div>

          <div v-if="permissionStore.getCurrentProjectApprovals.length === 0" class="memory-empty">
            <span>No remembered approvals for this project</span>
          </div>

          <div v-else class="memory-list">
            <div
              v-for="approval in permissionStore.getCurrentProjectApprovals"
              :key="approval.pattern"
              class="memory-item"
            >
              <div class="memory-info">
                <code class="memory-pattern">{{ approval.pattern }}</code>
                <div class="memory-meta">
                  <span class="memory-risk" :class="`risk-${approval.risk_level.toLowerCase()}`">
                    {{ approval.risk_level }}
                  </span>
                  <span class="memory-date">
                    {{ formatDate(approval.created_at) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- System Status Section -->
      <div class="settings-section">
        <h4 class="section-title">
          <i class="fas fa-info-circle" aria-hidden="true"></i>
          System Status
        </h4>

        <div v-if="permissionStore.status" class="status-grid">
          <div class="status-item">
            <span class="status-label">Mode</span>
            <span class="status-value">{{ permissionStore.status.mode }}</span>
          </div>
          <div class="status-item">
            <span class="status-label">Approval Memory</span>
            <span class="status-value">
              {{ permissionStore.status.approval_memory_enabled ? 'Enabled' : 'Disabled' }}
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">Memory TTL</span>
            <span class="status-value">{{ permissionStore.status.approval_memory_ttl_days }} days</span>
          </div>
          <div class="status-item">
            <span class="status-label">Rules File</span>
            <span class="status-value">{{ permissionStore.status.rules_file }}</span>
          </div>
          <div class="status-item">
            <span class="status-label">Total Rules</span>
            <span class="status-value">{{ permissionStore.status.rules_count.total }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePermissionStore, type PermissionMode, type PermissionAction, type PermissionRule } from '@/stores/usePermissionStore'
import BaseButton from '@/components/base/BaseButton.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PermissionSettings')

const permissionStore = usePermissionStore()

// Props
const props = defineProps<{
  isAdmin?: boolean
  projectPath?: string | null
}>()

// Local state
const selectedMode = ref<PermissionMode>('default')
const activeRuleTab = ref<'allow' | 'ask' | 'deny'>('allow')
const currentProjectPath = ref<string | null>(props.projectPath || null)

const newRule = ref({
  tool: 'Bash',
  pattern: '',
  action: 'ask' as PermissionAction,
  description: ''
})

// Mode definitions
const availableModes = [
  { value: 'default', label: 'Default', adminOnly: false },
  { value: 'acceptEdits', label: 'Accept Edits', adminOnly: false },
  { value: 'plan', label: 'Plan Mode', adminOnly: false },
  { value: 'dontAsk', label: "Don't Ask", adminOnly: true },
  { value: 'bypassPermissions', label: 'Bypass Permissions', adminOnly: true }
]

// Rule tabs
const ruleTabs = [
  { id: 'allow' as const, label: 'Allow', icon: 'fas fa-check-circle text-green-600' },
  { id: 'ask' as const, label: 'Ask', icon: 'fas fa-question-circle text-yellow-600' },
  { id: 'deny' as const, label: 'Deny', icon: 'fas fa-times-circle text-red-600' }
]

// Computed
const isAdmin = computed(() => props.isAdmin ?? false)

const currentRules = computed<PermissionRule[]>(() => {
  switch (activeRuleTab.value) {
    case 'allow':
      return permissionStore.allowRules
    case 'ask':
      return permissionStore.askRules
    case 'deny':
      return permissionStore.denyRules
    default:
      return []
  }
})

const canAddRule = computed(() => {
  return newRule.value.pattern.trim() !== '' &&
         (newRule.value.action !== 'allow' || isAdmin.value)
})

// Methods
const getModeDescription = (mode: string): string => {
  const descriptions: Record<string, string> = {
    default: 'Ask for approval based on command risk level and rules',
    acceptEdits: 'Auto-approve file edits, ask for other commands',
    plan: 'Read-only mode - no command execution allowed',
    dontAsk: 'Auto-approve all commands (Admin only)',
    bypassPermissions: 'Skip all permission checks (Admin only)'
  }
  return descriptions[mode] || 'Unknown mode'
}

const getRuleCount = (type: 'allow' | 'ask' | 'deny'): number => {
  switch (type) {
    case 'allow':
      return permissionStore.allowRules.length
    case 'ask':
      return permissionStore.askRules.length
    case 'deny':
      return permissionStore.denyRules.length
    default:
      return 0
  }
}

const formatDate = (timestamp: number): string => {
  return new Date(timestamp * 1000).toLocaleDateString()
}

const onModeChange = async () => {
  try {
    const success = await permissionStore.setMode(selectedMode.value, isAdmin.value)
    if (success) {
      logger.info('Permission mode changed to:', selectedMode.value)
    } else {
      // Revert to current mode on failure
      selectedMode.value = permissionStore.currentMode
    }
  } catch (error) {
    logger.error('Failed to change mode:', error)
    selectedMode.value = permissionStore.currentMode
  }
}

const addRule = async () => {
  if (!canAddRule.value) return

  try {
    const success = await permissionStore.addRule(
      newRule.value.tool,
      newRule.value.pattern,
      newRule.value.action,
      newRule.value.description,
      isAdmin.value
    )

    if (success) {
      logger.info('Rule added:', newRule.value)
      // Reset form
      newRule.value = {
        tool: 'Bash',
        pattern: '',
        action: 'ask',
        description: ''
      }
    }
  } catch (error) {
    logger.error('Failed to add rule:', error)
  }
}

const removeRule = async (rule: PermissionRule) => {
  try {
    const success = await permissionStore.removeRule(rule.tool, rule.pattern)
    if (success) {
      logger.info('Rule removed:', rule)
    }
  } catch (error) {
    logger.error('Failed to remove rule:', error)
  }
}

const clearProjectMemory = async () => {
  if (!currentProjectPath.value) return

  if (!confirm('Clear all remembered approvals for this project?')) return

  try {
    const success = await permissionStore.clearProjectApprovals(currentProjectPath.value)
    if (success) {
      logger.info('Project memory cleared:', currentProjectPath.value)
    }
  } catch (error) {
    logger.error('Failed to clear project memory:', error)
  }
}

const refreshData = async () => {
  await permissionStore.initialize(isAdmin.value)
  selectedMode.value = permissionStore.currentMode

  if (currentProjectPath.value) {
    await permissionStore.fetchProjectApprovals(currentProjectPath.value, 'web_user')
  }
}

// Initialize on mount
onMounted(async () => {
  await refreshData()
})
</script>

<style scoped>
.permission-settings {
  @apply space-y-6;
}

.settings-header {
  @apply flex items-center justify-between pb-4 border-b border-gray-200;
}

.settings-title {
  @apply flex items-center gap-2 text-lg font-semibold text-gray-900;
}

.settings-title i {
  @apply text-indigo-600;
}

.status-badge {
  @apply px-2 py-1 text-xs font-medium rounded-full;
}

.status-enabled {
  @apply bg-green-100 text-green-800;
}

.status-disabled {
  @apply bg-gray-100 text-gray-600;
}

.loading-state,
.error-state {
  @apply flex items-center justify-center gap-3 py-8 text-gray-600;
}

.error-state {
  @apply text-red-600;
}

.settings-content {
  @apply space-y-6;
}

.settings-section {
  @apply p-4 bg-gray-50 rounded-lg border border-gray-200;
}

.section-title {
  @apply flex items-center gap-2 text-sm font-semibold text-gray-900 mb-1;
}

.section-title i {
  @apply text-gray-500;
}

.section-description {
  @apply text-xs text-gray-600 mb-4;
}

.rules-count {
  @apply text-gray-500 font-normal;
}

/* Mode Selector */
.mode-selector {
  @apply space-y-2;
}

.mode-select {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500;
}

.mode-description {
  @apply text-xs text-gray-600 italic;
}

/* Rules Tabs */
.rules-tabs {
  @apply flex gap-1 mb-3;
}

.rules-tab {
  @apply flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors;
  @apply text-gray-600 hover:bg-gray-200;
}

.rules-tab.active {
  @apply bg-indigo-100 text-indigo-700;
}

.tab-count {
  @apply px-1.5 py-0.5 text-xs bg-gray-200 rounded-full;
}

.rules-tab.active .tab-count {
  @apply bg-indigo-200;
}

/* Rules List */
.rules-list {
  @apply max-h-48 overflow-y-auto mb-4 border border-gray-200 rounded-md bg-white;
}

.rules-empty {
  @apply flex flex-col items-center justify-center gap-2 py-6 text-gray-500 text-sm;
}

.rule-item {
  @apply flex items-center justify-between px-3 py-2 border-b border-gray-100 last:border-b-0;
}

.rule-info {
  @apply flex-1 min-w-0;
}

.rule-pattern {
  @apply text-xs font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-800;
}

.rule-description {
  @apply block text-xs text-gray-500 mt-0.5 truncate;
}

/* Add Rule Form */
.add-rule-form {
  @apply p-3 bg-white border border-gray-200 rounded-md;
}

.form-title {
  @apply text-xs font-semibold text-gray-700 mb-2;
}

.form-row {
  @apply flex gap-2 mb-2 last:mb-0;
}

.form-group {
  @apply flex flex-col gap-1;
}

.form-group.flex-1 {
  flex: 1 1 0%;
}

.form-label {
  @apply text-xs font-medium text-gray-600;
}

.form-input {
  @apply px-2 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500;
}

.add-rule-btn {
  @apply self-end;
}

/* Project Memory */
.memory-empty {
  @apply flex flex-col items-center justify-center gap-2 py-6 text-gray-500 text-sm;
}

.memory-content {
  @apply space-y-3;
}

.memory-header {
  @apply flex items-center justify-between;
}

.memory-project {
  @apply flex items-center gap-2 text-sm text-gray-700;
}

.memory-list {
  @apply max-h-32 overflow-y-auto border border-gray-200 rounded-md bg-white;
}

.memory-item {
  @apply px-3 py-2 border-b border-gray-100 last:border-b-0;
}

.memory-info {
  @apply flex items-center justify-between;
}

.memory-pattern {
  @apply text-xs font-mono bg-gray-100 px-1.5 py-0.5 rounded;
}

.memory-meta {
  @apply flex items-center gap-2 text-xs;
}

.memory-risk {
  @apply px-1.5 py-0.5 rounded text-xs font-medium;
}

.memory-risk.risk-low {
  @apply bg-green-100 text-green-800;
}

.memory-risk.risk-moderate {
  @apply bg-yellow-100 text-yellow-800;
}

.memory-risk.risk-high {
  @apply bg-orange-100 text-orange-800;
}

.memory-risk.risk-dangerous {
  @apply bg-red-100 text-red-800;
}

.memory-date {
  @apply text-gray-500;
}

/* Status Grid */
.status-grid {
  @apply grid grid-cols-2 gap-3;
}

.status-item {
  @apply flex flex-col;
}

.status-label {
  @apply text-xs text-gray-500;
}

.status-value {
  @apply text-sm font-medium text-gray-900;
}
</style>
