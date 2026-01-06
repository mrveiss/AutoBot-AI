<template>
  <div class="sub-tab-content">
    <h3>Hardware Configuration</h3>

    <!-- Hardware Status Overview -->
    <div class="hardware-status-grid">
      <div class="hardware-card" :class="hardwareStatus.gpu.status">
        <div class="hardware-header">
          <i class="fas fa-microchip"></i>
          <h4>GPU Acceleration</h4>
        </div>
        <div class="hardware-status">
          <span class="status-indicator" :class="hardwareStatus.gpu.status"></span>
          {{ hardwareStatus.gpu.message }}
        </div>
        <div v-if="hardwareStatus.gpu.details" class="hardware-details">
          <div class="detail-item">
            <span>Utilization:</span>
            <span>{{ hardwareStatus.gpu.details.utilization || 'N/A' }}%</span>
          </div>
          <div class="detail-item">
            <span>Memory:</span>
            <span>{{ hardwareStatus.gpu.details.memory || 'N/A' }}</span>
          </div>
        </div>
        <button @click="testGPU" :disabled="isTestingGPU" class="test-hardware-btn">
          <i :class="isTestingGPU ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
          {{ isTestingGPU ? 'Testing...' : 'Test GPU' }}
        </button>
      </div>

      <div class="hardware-card" :class="hardwareStatus.npu.status">
        <div class="hardware-header">
          <i class="fas fa-brain"></i>
          <h4>NPU Acceleration</h4>
        </div>
        <div class="hardware-status">
          <span class="status-indicator" :class="hardwareStatus.npu.status"></span>
          {{ hardwareStatus.npu.message }}
        </div>
        <div v-if="hardwareStatus.npu.details" class="hardware-details">
          <div class="detail-item">
            <span>Available:</span>
            <span>{{ hardwareStatus.npu.details.available ? 'Yes' : 'No' }}</span>
          </div>
          <div class="detail-item">
            <span>WSL Mode:</span>
            <span>{{ hardwareStatus.npu.details.wsl_limitation ? 'Limited' : 'Full' }}</span>
          </div>
        </div>
        <button @click="testNPU" :disabled="isTestingNPU" class="test-hardware-btn">
          <i :class="isTestingNPU ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
          {{ isTestingNPU ? 'Testing...' : 'Test NPU' }}
        </button>
      </div>

      <div class="hardware-card" :class="hardwareStatus.memory.status">
        <div class="hardware-header">
          <i class="fas fa-memory"></i>
          <h4>System Memory</h4>
        </div>
        <div class="hardware-status">
          <span class="status-indicator" :class="hardwareStatus.memory.status"></span>
          {{ hardwareStatus.memory.message }}
        </div>
        <div v-if="hardwareStatus.memory.details" class="hardware-details">
          <div class="detail-item">
            <span>Total:</span>
            <span>{{ hardwareStatus.memory.details.total || 'N/A' }}</span>
          </div>
          <div class="detail-item">
            <span>Available:</span>
            <span>{{ hardwareStatus.memory.details.available || 'N/A' }}</span>
          </div>
        </div>
        <button @click="refreshMemoryStatus" class="test-hardware-btn">
          <i class="fas fa-sync"></i>
          Refresh
        </button>
      </div>
    </div>

    <!-- Hardware Settings -->
    <div class="hardware-settings">
      <div class="setting-item">
        <label for="enable-gpu">Enable GPU Acceleration</label>
        <input
          id="enable-gpu"
          type="checkbox"
          :checked="hardwareSettings?.enable_gpu || false"
          @change="handleCheckboxChange('hardware.enable_gpu')"
        />
      </div>
      <div class="setting-item">
        <label for="enable-npu">Enable NPU Acceleration</label>
        <input
          id="enable-npu"
          type="checkbox"
          :checked="hardwareSettings?.enable_npu || false"
          @change="handleCheckboxChange('hardware.enable_npu')"
        />
      </div>
      <div class="setting-item">
        <label for="memory-limit">Memory Limit (GB)</label>
        <input
          id="memory-limit"
          type="number"
          :value="hardwareSettings?.memory_limit || 8"
          min="1"
          max="64"
          @input="handleNumberInputChange('hardware.memory_limit')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Hardware Settings Panel Component
 *
 * Displays and manages hardware acceleration settings (GPU, NPU, Memory).
 * Extracted from BackendSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, reactive, onMounted } from 'vue'
import { NetworkConstants, BACKEND_URL } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('HardwareSettingsPanel')

// Type definitions
interface GPUDetails {
  utilization: number
  memory: string
  temperature: string
  name: string
}

interface NPUDetails {
  available: boolean
  wsl_limitation: boolean
}

interface MemoryDetails {
  total: string
  available: string
  used: string
  percent: string
}

interface HardwareStatusItem<T> {
  status: string
  message: string
  details: T | null
}

interface HardwareStatus {
  gpu: HardwareStatusItem<GPUDetails>
  npu: HardwareStatusItem<NPUDetails>
  memory: HardwareStatusItem<MemoryDetails>
}

interface HardwareSettings {
  enable_gpu?: boolean
  enable_npu?: boolean
  memory_limit?: number
}

interface Props {
  hardwareSettings?: HardwareSettings | null
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
  (e: 'test-hardware', type: 'gpu' | 'npu' | 'memory'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// State
const isTestingGPU = ref(false)
const isTestingNPU = ref(false)

const hardwareStatus = reactive<HardwareStatus>({
  gpu: {
    status: 'unknown',
    message: 'GPU status not checked',
    details: null
  },
  npu: {
    status: 'unknown',
    message: 'NPU status not checked',
    details: null
  },
  memory: {
    status: 'unknown',
    message: 'Memory status not checked',
    details: null
  }
})

// Event handlers
const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.checked)
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, parseInt(target.value, 10))
}

// Hardware test functions
const testGPU = async () => {
  isTestingGPU.value = true
  hardwareStatus.gpu.status = 'testing'
  hardwareStatus.gpu.message = 'Testing GPU...'

  try {
    // Issue #570: Use correct /api/monitoring/hardware path after refactor
    const response = await fetch(
      `${BACKEND_URL}/api/monitoring/hardware/gpu/test`,
      { method: 'POST' }
    )
    const data = await response.json()

    if (data.success) {
      hardwareStatus.gpu.status = 'healthy'
      hardwareStatus.gpu.message = data.message || 'GPU is available'
      hardwareStatus.gpu.details = data.details || null
    } else {
      hardwareStatus.gpu.status = 'unhealthy'
      hardwareStatus.gpu.message = data.message || 'GPU test failed'
    }
  } catch (error) {
    logger.error('GPU test failed', error)
    hardwareStatus.gpu.status = 'error'
    hardwareStatus.gpu.message = 'Failed to test GPU'
  } finally {
    isTestingGPU.value = false
  }
}

const testNPU = async () => {
  isTestingNPU.value = true
  hardwareStatus.npu.status = 'testing'
  hardwareStatus.npu.message = 'Testing NPU...'

  try {
    // Issue #570: Use correct /api/monitoring/hardware path after refactor
    const response = await fetch(
      `${BACKEND_URL}/api/monitoring/hardware/npu/test`,
      { method: 'POST' }
    )
    const data = await response.json()

    if (data.success) {
      hardwareStatus.npu.status = 'healthy'
      hardwareStatus.npu.message = data.message || 'NPU is available'
      hardwareStatus.npu.details = data.details || null
    } else {
      hardwareStatus.npu.status = 'degraded'
      hardwareStatus.npu.message = data.message || 'NPU limited in WSL'
      hardwareStatus.npu.details = data.details || null
    }
  } catch (error) {
    logger.error('NPU test failed', error)
    hardwareStatus.npu.status = 'error'
    hardwareStatus.npu.message = 'Failed to test NPU'
  } finally {
    isTestingNPU.value = false
  }
}

const refreshMemoryStatus = async () => {
  hardwareStatus.memory.status = 'testing'
  hardwareStatus.memory.message = 'Checking memory...'

  try {
    // Issue #570: Use correct /api/monitoring/hardware path after refactor
    const response = await fetch(
      `${BACKEND_URL}/api/monitoring/hardware/memory`
    )
    const data = await response.json()

    if (data.success) {
      hardwareStatus.memory.status = 'healthy'
      hardwareStatus.memory.message = 'Memory status OK'
      hardwareStatus.memory.details = data.details || null
    } else {
      hardwareStatus.memory.status = 'warning'
      hardwareStatus.memory.message = data.message || 'Memory status unknown'
    }
  } catch (error) {
    logger.error('Memory check failed', error)
    hardwareStatus.memory.status = 'error'
    hardwareStatus.memory.message = 'Failed to check memory'
  }
}

// Initialize on mount
onMounted(() => {
  refreshMemoryStatus()
})
</script>

<style scoped>
.sub-tab-content {
  padding: 1rem 0;
}

.hardware-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.hardware-card {
  background: var(--bg-secondary, #1e293b);
  border-radius: 8px;
  padding: 1.25rem;
  border: 1px solid var(--border-color, #475569);
  transition: all 0.2s;
}

.hardware-card.healthy {
  border-color: #10b981;
}

.hardware-card.degraded {
  border-color: #f59e0b;
}

.hardware-card.unhealthy,
.hardware-card.error {
  border-color: #ef4444;
}

.hardware-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.hardware-header i {
  font-size: 1.5rem;
  color: var(--primary-color, #667eea);
}

.hardware-header h4 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.hardware-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  font-size: 0.9rem;
  color: var(--text-secondary, #e2e8f0);
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-muted, #94a3b8);
}

.status-indicator.healthy {
  background: #10b981;
}

.status-indicator.degraded,
.status-indicator.warning {
  background: #f59e0b;
}

.status-indicator.unhealthy,
.status-indicator.error {
  background: #ef4444;
}

.status-indicator.testing {
  background: var(--primary-color, #667eea);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.hardware-details {
  background: var(--bg-tertiary, #334155);
  border-radius: 4px;
  padding: 0.75rem;
  margin-bottom: 1rem;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  padding: 0.25rem 0;
}

.detail-item span:first-child {
  color: var(--text-muted, #94a3b8);
}

.test-hardware-btn {
  width: 100%;
  padding: 0.75rem;
  background: var(--bg-tertiary, #334155);
  border: 1px solid var(--border-color, #475569);
  border-radius: 4px;
  color: var(--text-primary, #f8fafc);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.test-hardware-btn:hover:not(:disabled) {
  background: var(--bg-secondary, #1e293b);
  border-color: var(--primary-color, #667eea);
}

.test-hardware-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hardware-settings {
  background: var(--bg-secondary, #1e293b);
  border-radius: 8px;
  padding: 1.25rem;
  border: 1px solid var(--border-color, #475569);
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border-color, #475569);
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-item label {
  font-weight: 500;
  color: var(--text-secondary, #e2e8f0);
}

.setting-item input[type="checkbox"] {
  width: 1.25rem;
  height: 1.25rem;
  cursor: pointer;
}

.setting-item input[type="number"] {
  width: 100px;
  padding: 0.5rem;
  border: 1px solid var(--border-color, #475569);
  border-radius: 4px;
  background: var(--bg-tertiary, #334155);
  color: var(--text-primary, #f8fafc);
  text-align: right;
}

.setting-item input[type="number"]:focus {
  outline: none;
  border-color: var(--primary-color, #667eea);
}
</style>
