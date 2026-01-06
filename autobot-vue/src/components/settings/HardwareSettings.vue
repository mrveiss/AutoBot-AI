<template>
  <div class="hardware-settings-container">
    <h3><i class="fas fa-server mr-2"></i>Hardware Configuration</h3>

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
    <div class="hardware-config-section">
      <h4>Hardware Settings</h4>
      <div class="setting-item">
        <label for="enable-gpu">Enable GPU Acceleration</label>
        <input
          id="enable-gpu"
          type="checkbox"
          :checked="hardwareConfig.enable_gpu"
          @change="updateSetting('enable_gpu', ($event.target as HTMLInputElement).checked)"
        />
      </div>
      <div class="setting-item">
        <label for="enable-npu">Enable NPU Acceleration</label>
        <input
          id="enable-npu"
          type="checkbox"
          :checked="hardwareConfig.enable_npu"
          @change="updateSetting('enable_npu', ($event.target as HTMLInputElement).checked)"
        />
      </div>
      <div class="setting-item">
        <label for="memory-limit">Memory Limit (GB)</label>
        <input
          id="memory-limit"
          type="number"
          :value="hardwareConfig.memory_limit"
          min="1"
          max="64"
          @input="updateSetting('memory_limit', Number(($event.target as HTMLInputElement).value))"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('HardwareSettings')

// Props
interface Props {
  isSettingsLoaded?: boolean
}

defineProps<Props>()

// Emits
const emit = defineEmits<{
  'setting-changed': [key: string, value: any]
  'change': []
}>()

// Hardware config state
const hardwareConfig = reactive({
  enable_gpu: false,
  enable_npu: false,
  memory_limit: 8
})

// Testing states
const isTestingGPU = ref(false)
const isTestingNPU = ref(false)

// Type definitions for hardware status
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

// Hardware status
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

const updateSetting = (key: string, value: any) => {
  (hardwareConfig as Record<string, any>)[key] = value
  emit('setting-changed', `hardware.${key}`, value)
  emit('change')
}

// Hardware testing methods
const testGPU = async () => {
  if (isTestingGPU.value) return

  isTestingGPU.value = true
  hardwareStatus.gpu.status = 'testing'
  hardwareStatus.gpu.message = 'Testing GPU...'

  try {
    const endpoint = getBackendUrl()
    const response = await fetch(`${endpoint}/api/monitoring/hardware/gpu`)

    if (response.ok) {
      const data = await response.json()

      if (data.available) {
        hardwareStatus.gpu.status = 'available'
        hardwareStatus.gpu.message = 'GPU acceleration available'

        const metrics = data.current_metrics || {}
        const memoryGB = metrics.memory_used && metrics.memory_total
          ? `${(metrics.memory_used / 1024).toFixed(1)}GB / ${(metrics.memory_total / 1024).toFixed(1)}GB`
          : 'Unknown'

        hardwareStatus.gpu.details = {
          utilization: metrics.utilization_percent || 0,
          memory: memoryGB,
          temperature: metrics.temperature_celsius ? `${metrics.temperature_celsius}°C` : 'N/A',
          name: metrics.gpu_name || 'Unknown GPU'
        }
      } else {
        hardwareStatus.gpu.status = 'unavailable'
        hardwareStatus.gpu.message = data.message || 'GPU not available or accessible'
      }
    } else {
      hardwareStatus.gpu.status = 'error'
      hardwareStatus.gpu.message = 'Failed to query GPU status'
    }
  } catch (error) {
    const err = error as Error
    logger.error('GPU test failed:', err)
    hardwareStatus.gpu.status = 'error'
    hardwareStatus.gpu.message = `GPU test failed: ${err.message}`
  } finally {
    isTestingGPU.value = false
  }
}

const testNPU = async () => {
  if (isTestingNPU.value) return

  isTestingNPU.value = true
  hardwareStatus.npu.status = 'testing'
  hardwareStatus.npu.message = 'Testing NPU...'

  try {
    const endpoint = getBackendUrl()
    const response = await fetch(`${endpoint}/api/monitoring/hardware/npu`)

    if (response.ok) {
      const data = await response.json()
      hardwareStatus.npu.status = data.available ? 'available' : 'unavailable'
      hardwareStatus.npu.message = data.message || 'NPU status retrieved'
      hardwareStatus.npu.details = {
        available: data.available,
        wsl_limitation: true
      }
    } else {
      hardwareStatus.npu.status = 'unavailable'
      hardwareStatus.npu.message = 'NPU not accessible'
    }
  } catch (error) {
    const err = error as Error
    logger.error('NPU test failed:', err)
    hardwareStatus.npu.status = 'error'
    hardwareStatus.npu.message = `NPU test failed: ${err.message}`
  } finally {
    isTestingNPU.value = false
  }
}

const refreshMemoryStatus = async () => {
  hardwareStatus.memory.status = 'checking'
  hardwareStatus.memory.message = 'Checking memory status...'

  try {
    const endpoint = getBackendUrl()
    const response = await fetch(`${endpoint}/api/system/metrics`)

    if (response.ok) {
      const data = await response.json()

      if (data.system && data.system.memory) {
        const memory = data.system.memory
        hardwareStatus.memory.status = 'available'
        hardwareStatus.memory.message = 'Memory status healthy'

        const totalGB = (memory.total / (1024 ** 3)).toFixed(1)
        const availableGB = (memory.available / (1024 ** 3)).toFixed(1)
        const usedGB = (memory.used / (1024 ** 3)).toFixed(1)

        hardwareStatus.memory.details = {
          total: `${totalGB} GB`,
          available: `${availableGB} GB`,
          used: `${usedGB} GB`,
          percent: memory.percent.toFixed(1) + '%'
        }
      } else {
        hardwareStatus.memory.status = 'unavailable'
        hardwareStatus.memory.message = 'Memory data not available'
      }
    } else {
      hardwareStatus.memory.status = 'error'
      hardwareStatus.memory.message = 'Failed to query memory status'
    }
  } catch (error) {
    const err = error as Error
    logger.error('Memory status check failed:', err)
    hardwareStatus.memory.status = 'error'
    hardwareStatus.memory.message = `Failed to get memory status: ${err.message}`
  }
}

onMounted(() => {
  refreshMemoryStatus()
})
</script>

<style scoped>
.hardware-settings-container {
  padding: 20px;
}

.hardware-settings-container h3 {
  margin: 0 0 24px 0;
  color: #2c3e50;
  font-size: 20px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

/* Hardware Status Grid */
.hardware-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.hardware-card {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.2s;
}

.hardware-card.available {
  border-color: #28a745;
  background: rgba(40, 167, 69, 0.05);
}

.hardware-card.unavailable {
  border-color: #dc3545;
  background: rgba(220, 53, 69, 0.05);
}

.hardware-card.testing,
.hardware-card.checking {
  border-color: #ffc107;
  background: rgba(255, 193, 7, 0.05);
}

.hardware-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.hardware-header i {
  font-size: 20px;
  color: #6c757d;
}

.hardware-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #495057;
}

.hardware-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #495057;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.available {
  background: #28a745;
}

.status-indicator.unavailable {
  background: #dc3545;
}

.status-indicator.testing,
.status-indicator.checking {
  background: #ffc107;
}

.status-indicator.unknown,
.status-indicator.error {
  background: #6c757d;
}

.hardware-details {
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
  color: #6c757d;
}

.test-hardware-btn {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  background: #007acc;
  color: white;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.test-hardware-btn:hover:not(:disabled) {
  background: #005fa3;
}

.test-hardware-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Hardware Config Section */
.hardware-config-section {
  margin-top: 20px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
}

.hardware-config-section h4 {
  margin: 0 0 16px 0;
  color: #495057;
  font-size: 16px;
  font-weight: 500;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #e9ecef;
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-item label {
  font-size: 14px;
  color: #495057;
}

.setting-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.setting-item input[type="number"] {
  width: 80px;
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .hardware-settings-container h3 {
    color: #ffffff;
  }

  .hardware-card {
    background: #2d2d2d;
    border-color: #555;
  }

  .hardware-card.available {
    background: rgba(40, 167, 69, 0.1);
  }

  .hardware-card.unavailable {
    background: rgba(220, 53, 69, 0.1);
  }

  .hardware-header h4,
  .hardware-status {
    color: #ffffff;
  }

  .hardware-config-section {
    background: #2d2d2d;
  }

  .hardware-config-section h4,
  .setting-item label {
    color: #ffffff;
  }

  .setting-item {
    border-color: #555;
  }

  .setting-item input[type="number"] {
    background: #3d3d3d;
    border-color: #555;
    color: #ffffff;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .hardware-status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
