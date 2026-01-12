<template>
  <div class="sub-tab-content">
    <h3>Memory Configuration</h3>

    <div class="setting-item">
      <label for="enable-memory">Enable Memory System</label>
      <input
        id="enable-memory"
        type="checkbox"
        :checked="memorySettings?.enabled || false"
        @change="handleCheckboxChange('enabled')"
      />
    </div>

    <div class="setting-item">
      <label for="memory-type">Memory Type</label>
      <select
        id="memory-type"
        :value="memorySettings?.type || 'redis'"
        @change="handleSelectChange('type')"
      >
        <option value="redis">Redis</option>
        <option value="chroma">ChromaDB</option>
        <option value="memory">In-Memory</option>
      </select>
    </div>

    <div class="setting-item">
      <label for="memory-limit">Memory Limit (entries)</label>
      <input
        id="memory-limit"
        type="number"
        :value="memorySettings?.max_entries || 1000"
        min="100"
        max="10000"
        @input="handleNumberInputChange('max_entries')"
      />
    </div>

    <div class="setting-item">
      <label for="auto-cleanup">Auto Cleanup</label>
      <input
        id="auto-cleanup"
        type="checkbox"
        :checked="memorySettings?.auto_cleanup || false"
        @change="handleCheckboxChange('auto_cleanup')"
      />
    </div>

    <!-- Memory-type specific settings -->
    <div v-if="memorySettings?.type === 'redis'" class="provider-section">
      <h4>Redis Settings</h4>
      <div class="setting-item">
        <label for="redis-host">Redis Host</label>
        <input
          id="redis-host"
          type="text"
          :value="memorySettings?.redis_host || config.vm.redis"
          @input="handleInputChange('redis_host')"
        />
      </div>
      <div class="setting-item">
        <label for="redis-port">Redis Port</label>
        <input
          id="redis-port"
          type="number"
          :value="memorySettings?.redis_port || 6379"
          min="1"
          max="65535"
          @input="handleNumberInputChange('redis_port')"
        />
      </div>
      <div class="setting-item">
        <label for="redis-db">Redis Database</label>
        <select
          id="redis-db"
          :value="memorySettings?.redis_db || 'main'"
          @change="handleSelectChange('redis_db')"
        >
          <option value="main">Main (General cache)</option>
          <option value="knowledge">Knowledge (Vector store)</option>
          <option value="prompts">Prompts (Templates)</option>
          <option value="analytics">Analytics (Metrics)</option>
        </select>
      </div>
    </div>

    <div v-else-if="memorySettings?.type === 'chroma'" class="provider-section">
      <h4>ChromaDB Settings</h4>
      <div class="setting-item">
        <label for="chroma-collection">Collection Name</label>
        <input
          id="chroma-collection"
          type="text"
          :value="memorySettings?.chroma_collection || 'autobot_memory'"
          @input="handleInputChange('chroma_collection')"
        />
      </div>
      <div class="setting-item">
        <label for="chroma-persist-dir">Persist Directory</label>
        <input
          id="chroma-persist-dir"
          type="text"
          :value="memorySettings?.chroma_persist_dir || './data/chroma'"
          @input="handleInputChange('chroma_persist_dir')"
        />
      </div>
    </div>

    <!-- Memory Status -->
    <div class="memory-status-section">
      <h4>Memory Status</h4>
      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">Entries:</span>
          <span class="status-value">{{ memoryStatus?.entries || 0 }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Size:</span>
          <span class="status-value">{{ memoryStatus?.size || 'N/A' }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Last Cleanup:</span>
          <span class="status-value">{{ memoryStatus?.last_cleanup || 'Never' }}</span>
        </div>
      </div>
      <div class="status-actions">
        <button @click="handleClearMemory" class="danger-btn">
          <i class="fas fa-trash"></i> Clear All Memory
        </button>
        <button @click="handleForceCleanup" class="secondary-btn">
          <i class="fas fa-broom"></i> Force Cleanup
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Memory Settings Panel Component
 *
 * Manages memory system configuration for knowledge storage.
 * Extracted from BackendSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { createLogger } from '@/utils/debugUtils'
import { getConfig } from '@/config/ssot-config'

const logger = createLogger('MemorySettingsPanel')
const config = getConfig()

// Type definitions
interface MemorySettings {
  enabled?: boolean
  type?: string
  max_entries?: number
  auto_cleanup?: boolean
  redis_host?: string
  redis_port?: number
  redis_db?: string
  chroma_collection?: string
  chroma_persist_dir?: string
}

interface MemoryStatus {
  entries?: number
  size?: string
  last_cleanup?: string
}

interface Props {
  memorySettings?: MemorySettings | null
  memoryStatus?: MemoryStatus | null
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
  (e: 'clear-memory'): void
  (e: 'force-cleanup'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Event handlers
const handleInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.value)
}

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

const handleClearMemory = () => {
  if (confirm('Are you sure you want to clear all memory? This action cannot be undone.')) {
    logger.info('Clearing all memory')
    emit('clear-memory')
  }
}

const handleForceCleanup = () => {
  logger.info('Forcing memory cleanup')
  emit('force-cleanup')
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
  width: 1.25rem;
  height: 1.25rem;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg-transparent);
}

.provider-section {
  margin-top: var(--spacing-5);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.memory-status-section {
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
  margin-bottom: var(--spacing-4);
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
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.status-actions {
  display: flex;
  gap: var(--spacing-2);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.danger-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  background: var(--color-error);
  color: var(--text-on-primary);
  transition: all var(--duration-200) var(--ease-in-out);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.danger-btn:hover {
  background: var(--color-error-hover);
}

.secondary-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--text-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-tertiary);
  transition: all var(--duration-200) var(--ease-in-out);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.secondary-btn:hover {
  background: var(--text-tertiary);
  color: var(--text-on-primary);
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

  .status-actions {
    flex-direction: column;
  }
}
</style>
