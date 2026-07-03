<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <BaseModal
    :model-value="show"
    :title="$t('analytics.findings.fileScan.title')"
    size="sm"
    @close="$emit('close')"
  >
    <div class="form-group">
      <label>{{ $t('analytics.findings.fileScan.filePathLabel') }}</label>
      <input
        v-model="filePath"
        type="text"
        :placeholder="$t('analytics.findings.fileScan.filePathPlaceholder')"
        class="file-input"
        :class="{ error: pathError }"
      />
      <span v-if="pathError" class="error-text">{{ pathError }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('analytics.findings.fileScan.scanTypesLabel') }}</label>
      <div class="checkbox-group">
        <label class="checkbox-label">
          <input type="checkbox" v-model="scanTypes.security" />
          <span>{{ $t('analytics.findings.fileScan.security') }}</span>
        </label>
        <label class="checkbox-label">
          <input type="checkbox" v-model="scanTypes.performance" />
          <span>{{ $t('analytics.findings.fileScan.performance') }}</span>
        </label>
        <label class="checkbox-label">
          <input type="checkbox" v-model="scanTypes.redis" />
          <span>{{ $t('analytics.findings.fileScan.redis') }}</span>
        </label>
      </div>
    </div>

    <p class="note">{{ $t('analytics.findings.fileScan.pythonOnlyNote') }}</p>

    <template #actions>
      <button class="btn-secondary" @click="$emit('close')">{{ $t('analytics.findings.fileScan.cancel') }}</button>
      <button
        class="btn-primary"
        @click="handleScan"
        :disabled="!canScan || scanning"
      >
        <span v-if="scanning" class="spinner-small"></span>
        {{ scanning ? $t('analytics.findings.fileScan.scanning') : $t('analytics.findings.fileScan.scanFile') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal } from '@autobot/ui'

const { t } = useI18n()

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
  if (!filePath.value.endsWith('.py')) return t('analytics.findings.fileScan.pythonOnlyError')
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
  border-color: var(--color-error);
}

.error-text {
  display: block;
  margin-top: var(--spacing-1);
  color: var(--color-error);
  font-size: var(--text-sm);
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
  font-size: var(--text-sm);
  margin: var(--spacing-0);
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
