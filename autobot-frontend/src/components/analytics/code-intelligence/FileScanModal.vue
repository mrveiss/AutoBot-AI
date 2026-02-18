<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Scan Single File</h3>
          <button class="close-btn" @click="$emit('close')">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label>File Path:</label>
            <input
              v-model="filePath"
              type="text"
              placeholder="/path/to/file.py"
              class="file-input"
              :class="{ error: pathError }"
            />
            <span v-if="pathError" class="error-text">{{ pathError }}</span>
          </div>

          <div class="form-group">
            <label>Scan Types:</label>
            <div class="checkbox-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.security" />
                <span>Security</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.performance" />
                <span>Performance</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.redis" />
                <span>Redis</span>
              </label>
            </div>
          </div>

          <p class="note">Note: Only Python (.py) files are supported</p>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" @click="$emit('close')">Cancel</button>
          <button
            class="btn-primary"
            @click="handleScan"
            :disabled="!canScan || scanning"
          >
            <span v-if="scanning" class="spinner-small"></span>
            {{ scanning ? 'Scanning...' : 'Scan File' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  close: []
  scan: [filePath: string, types: { security: boolean; performance: boolean; redis: boolean }]
}>()

const filePath = ref('')
const scanning = ref(false)
const scanTypes = ref({
  security: true,
  performance: false,
  redis: false
})

const pathError = computed(() => {
  if (!filePath.value) return ''
  if (!filePath.value.endsWith('.py')) return 'Only Python files (.py) are supported'
  return ''
})

const canScan = computed(() => {
  return filePath.value &&
    filePath.value.endsWith('.py') &&
    (scanTypes.value.security || scanTypes.value.performance || scanTypes.value.redis)
})

async function handleScan() {
  if (!canScan.value) return
  scanning.value = true
  emit('scan', filePath.value, { ...scanTypes.value })
  scanning.value = false
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 480px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-4);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.file-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-family: monospace;
}

.file-input.error {
  border-color: #ef4444;
}

.error-text {
  display: block;
  margin-top: var(--spacing-1);
  color: #ef4444;
  font-size: 0.875rem;
}

.checkbox-group {
  display: flex;
  gap: var(--spacing-4);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.note {
  color: var(--text-tertiary);
  font-size: 0.875rem;
  margin: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-primary);
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
}

.btn-primary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info-dark);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
