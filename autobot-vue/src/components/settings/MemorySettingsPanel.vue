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
          :value="memorySettings?.redis_host || '172.16.168.23'"
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

const logger = createLogger('MemorySettingsPanel')

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
.sub-tab-content {
  padding: 1rem 0;
}

.sub-tab-content h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.sub-tab-content h4 {
  margin: 0 0 16px 0;
  color: #34495e;
  font-weight: 500;
  font-size: 16px;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: #34495e;
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 200px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type='checkbox'] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.provider-section {
  margin-top: 20px;
  padding: 16px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
}

.memory-status-section {
  margin-top: 24px;
  padding: 16px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-label {
  font-size: 12px;
  color: #6c757d;
  text-transform: uppercase;
}

.status-value {
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
}

.status-actions {
  display: flex;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid #dee2e6;
}

.danger-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  background: #dc3545;
  color: white;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.danger-btn:hover {
  background: #c82333;
}

.secondary-btn {
  padding: 8px 16px;
  border: 1px solid #6c757d;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  background: white;
  color: #6c757d;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.secondary-btn:hover {
  background: #6c757d;
  color: white;
}

@media (max-width: 768px) {
  .setting-item {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
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
