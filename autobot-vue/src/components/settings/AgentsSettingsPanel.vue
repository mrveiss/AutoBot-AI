<template>
  <div class="sub-tab-content">
    <h3>Agent Configuration</h3>

    <div class="setting-item">
      <label for="max-agents">Maximum Concurrent Agents</label>
      <input
        id="max-agents"
        type="number"
        :value="agentSettings?.max_concurrent || 5"
        min="1"
        max="20"
        @input="handleNumberInputChange('max_concurrent')"
      />
    </div>

    <div class="setting-item">
      <label for="agent-timeout">Agent Timeout (seconds)</label>
      <input
        id="agent-timeout"
        type="number"
        :value="agentSettings?.timeout || 300"
        min="30"
        max="3600"
        @input="handleNumberInputChange('timeout')"
      />
    </div>

    <div class="setting-item">
      <label for="enable-agent-memory">Enable Agent Memory</label>
      <input
        id="enable-agent-memory"
        type="checkbox"
        :checked="agentSettings?.enable_memory || false"
        @change="handleCheckboxChange('enable_memory')"
      />
    </div>

    <div class="setting-item">
      <label for="agent-log-level">Agent Log Level</label>
      <select
        id="agent-log-level"
        :value="agentSettings?.log_level || 'INFO'"
        @change="handleSelectChange('log_level')"
      >
        <option value="DEBUG">Debug</option>
        <option value="INFO">Info</option>
        <option value="WARNING">Warning</option>
        <option value="ERROR">Error</option>
      </select>
    </div>

    <!-- Advanced Agent Settings -->
    <div class="advanced-section">
      <h4>Advanced Settings</h4>

      <div class="setting-item">
        <label for="retry-attempts">Retry Attempts</label>
        <input
          id="retry-attempts"
          type="number"
          :value="agentSettings?.retry_attempts || 3"
          min="0"
          max="10"
          @input="handleNumberInputChange('retry_attempts')"
        />
      </div>

      <div class="setting-item">
        <label for="retry-delay">Retry Delay (ms)</label>
        <input
          id="retry-delay"
          type="number"
          :value="agentSettings?.retry_delay || 1000"
          min="100"
          max="30000"
          step="100"
          @input="handleNumberInputChange('retry_delay')"
        />
      </div>

      <div class="setting-item">
        <label for="enable-parallel">Enable Parallel Execution</label>
        <input
          id="enable-parallel"
          type="checkbox"
          :checked="agentSettings?.enable_parallel || true"
          @change="handleCheckboxChange('enable_parallel')"
        />
      </div>

      <div class="setting-item">
        <label for="priority-queue">Priority Queue</label>
        <input
          id="priority-queue"
          type="checkbox"
          :checked="agentSettings?.priority_queue || false"
          @change="handleCheckboxChange('priority_queue')"
        />
      </div>
    </div>

    <!-- Agent Types Configuration -->
    <div class="agent-types-section">
      <h4>Agent Types</h4>
      <div class="agent-types-grid">
        <div
          v-for="agentType in agentTypes"
          :key="agentType.id"
          class="agent-type-card"
          :class="{ enabled: isAgentTypeEnabled(agentType.id) }"
        >
          <div class="agent-type-header">
            <input
              type="checkbox"
              :id="`agent-${agentType.id}`"
              :checked="isAgentTypeEnabled(agentType.id)"
              @change="handleAgentTypeToggle(agentType.id)"
            />
            <label :for="`agent-${agentType.id}`">
              <i :class="agentType.icon"></i>
              {{ agentType.name }}
            </label>
          </div>
          <p class="agent-type-description">{{ agentType.description }}</p>
        </div>
      </div>
    </div>

    <!-- Agent Status -->
    <div v-if="agentStatus" class="agent-status-section">
      <h4>Current Status</h4>
      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">Active Agents:</span>
          <span class="status-value">{{ agentStatus.active || 0 }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Queued Tasks:</span>
          <span class="status-value">{{ agentStatus.queued || 0 }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Completed Today:</span>
          <span class="status-value">{{ agentStatus.completed_today || 0 }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Failed Today:</span>
          <span class="status-value error">{{ agentStatus.failed_today || 0 }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Agents Settings Panel Component
 *
 * Manages agent configuration and agent type settings.
 * Extracted from BackendSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentsSettingsPanel')

// Type definitions
interface AgentSettings {
  max_concurrent?: number
  timeout?: number
  enable_memory?: boolean
  log_level?: string
  retry_attempts?: number
  retry_delay?: number
  enable_parallel?: boolean
  priority_queue?: boolean
  enabled_types?: string[]
}

interface AgentStatus {
  active?: number
  queued?: number
  completed_today?: number
  failed_today?: number
}

interface AgentType {
  id: string
  name: string
  icon: string
  description: string
}

interface Props {
  agentSettings?: AgentSettings | null
  agentStatus?: AgentStatus | null
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Agent types configuration
const agentTypes: AgentType[] = [
  {
    id: 'orchestrator',
    name: 'Orchestrator',
    icon: 'fas fa-sitemap',
    description: 'Coordinates multi-agent workflows and task distribution'
  },
  {
    id: 'worker',
    name: 'Worker',
    icon: 'fas fa-cog',
    description: 'Executes individual tasks and operations'
  },
  {
    id: 'monitor',
    name: 'Monitor',
    icon: 'fas fa-eye',
    description: 'Observes system state and triggers alerts'
  },
  {
    id: 'analyzer',
    name: 'Analyzer',
    icon: 'fas fa-chart-line',
    description: 'Analyzes data and generates insights'
  },
  {
    id: 'executor',
    name: 'Executor',
    icon: 'fas fa-play',
    description: 'Runs automated scripts and commands'
  }
]

// Computed
const enabledTypes = computed(() => props.agentSettings?.enabled_types || [])

// Helpers
const isAgentTypeEnabled = (typeId: string): boolean => {
  return enabledTypes.value.includes(typeId)
}

// Event handlers
const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, parseInt(target.value, 10))
}

const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.checked)
}

const handleSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  emit('setting-changed', key, target.value)
}

const handleAgentTypeToggle = (typeId: string) => {
  const currentTypes = [...enabledTypes.value]
  const index = currentTypes.indexOf(typeId)

  if (index > -1) {
    currentTypes.splice(index, 1)
    logger.info(`Disabled agent type: ${typeId}`)
  } else {
    currentTypes.push(typeId)
    logger.info(`Enabled agent type: ${typeId}`)
  }

  emit('setting-changed', 'enabled_types', currentTypes)
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.sub-tab-content {
  padding: var(--spacing-4) 0;
}

.sub-tab-content h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: 1.125rem;
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-2);
}

.sub-tab-content h4 {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
  font-size: var(--text-base);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-light);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  flex: 1;
  margin-right: var(--spacing-4);
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 200px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out);
}

.setting-item input[type='checkbox'] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg-transparent);
}

.advanced-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.agent-types-section {
  margin-top: var(--spacing-6);
}

.agent-types-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.agent-type-card {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  transition: all var(--duration-200) var(--ease-in-out);
}

.agent-type-card.enabled {
  background: var(--color-primary-bg-transparent);
  border-color: var(--color-primary);
}

.agent-type-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.agent-type-header label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  cursor: pointer;
}

.agent-type-header i {
  width: 20px;
  text-align: center;
  color: var(--color-primary);
}

.agent-type-description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  padding-left: 28px;
}

.agent-status-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.status-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.status-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.status-value.error {
  color: var(--color-error);
}

@media (max-width: 768px) {
  .setting-item {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-2);
  }

  .setting-item label {
    margin-right: 0;
  }

  .setting-item input,
  .setting-item select {
    min-width: unset;
    width: 100%;
  }

  .agent-types-grid {
    grid-template-columns: 1fr;
  }
}
</style>
