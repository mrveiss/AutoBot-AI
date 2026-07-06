<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #9049 - Plugin capability approval dialog -->

<template>
  <div
    v-if="open"
    class="capability-approval-overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="capability-dialog-title"
    @click.self="handleCancel"
  >
    <div class="capability-approval-dialog">
      <div class="dialog-header">
        <h2 id="capability-dialog-title">{{ $t('plugins.capabilities.approvalTitle') }}</h2>
        <button
          class="close-btn"
          @click="handleCancel"
          :aria-label="$t('common.close')"
        >
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      <div v-if="loading" class="dialog-loading">
        <svg class="spinner" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span>{{ $t('plugins.capabilities.loading') }}</span>
      </div>

      <div v-else-if="error" class="dialog-error">
        <svg fill="currentColor" viewBox="0 0 20 20">
          <path
            fill-rule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
            clip-rule="evenodd"
          />
        </svg>
        <span>{{ error }}</span>
      </div>

      <div v-else class="dialog-body">
        <div class="plugin-info">
          <h3>{{ pluginName }}</h3>
          <span v-if="capabilityInfo" :class="['trust-tier-badge', `tier-${capabilityInfo.trust_tier}`]">
            {{ capabilityInfo.trust_tier }}
          </span>
        </div>

        <p class="approval-description">{{ $t('plugins.capabilities.approvalDescription') }}</p>

        <div v-if="capabilityInfo && capabilityInfo.pending_approval.length > 0" class="capabilities-list">
          <div
            v-for="capability in capabilityInfo.pending_approval"
            :key="capability"
            class="capability-item"
          >
            <label class="capability-label">
              <input
                type="checkbox"
                :value="capability"
                v-model="selectedCapabilities"
                class="capability-checkbox"
              />
              <span class="capability-name">{{ capability }}</span>
            </label>
            <span class="capability-description">{{ getCapabilityDescription(capability) }}</span>
          </div>
        </div>
        <div v-else class="no-pending">
          {{ $t('plugins.capabilities.noPending') }}
        </div>
      </div>

      <div class="dialog-actions">
        <button
          class="btn btn-secondary"
          @click="handleCancel"
        >
          {{ $t('common.cancel') }}
        </button>
        <button
          v-if="capabilityInfo && capabilityInfo.pending_approval.length > 0"
          class="btn btn-primary"
          @click="handleApproveSelected"
          :disabled="selectedCapabilities.length === 0 || approving"
        >
          {{ approving ? $t('plugins.capabilities.approving') : $t('plugins.capabilities.approveSelected') }}
        </button>
        <button
          v-if="capabilityInfo && capabilityInfo.pending_approval.length > 0"
          class="btn btn-primary"
          @click="handleApproveAll"
          :disabled="approving"
        >
          {{ approving ? $t('plugins.capabilities.approving') : $t('plugins.capabilities.approveAll') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePlugins, type CapabilityInfo } from '@/composables/usePlugins'


const props = defineProps<{
  pluginName: string
  open: boolean
}>()

const emit = defineEmits<{
  approved: []
  close: []
}>()

const { getCapabilities, approveCapabilities } = usePlugins()

const loading = ref(false)
const error = ref<string | null>(null)
const capabilityInfo = ref<CapabilityInfo | null>(null)
const selectedCapabilities = ref<string[]>([])
const approving = ref(false)

// Capability descriptions map
const capabilityDescriptions: Record<string, string> = {
  'kb:read': 'Read from Knowledge Base',
  'kb:write': 'Write to Knowledge Base',
  'kb:admin': 'Admin operations on KB',
  'llm:call': 'Call LLM providers',
  'llm:embedding': 'Generate embeddings',
  'llm:fine_tune': 'Fine-tune models',
  'filesystem:read': 'Read files from disk',
  'filesystem:write': 'Write files to disk',
  'filesystem:delete': 'Delete files from disk',
  'network:outbound': 'Make outbound HTTP requests',
  'network:inbound': 'Accept inbound HTTP requests',
  'database:read': 'Read from AutoBot database',
  'database:write': 'Write to AutoBot database',
  'database:admin': 'Database admin operations',
  'agent:read': 'Read agent metadata',
  'agent:execute': 'Execute agent tasks',
  'agent:admin': 'Create/delete agents',
  'system:env': 'Access environment variables',
  'system:process': 'Spawn processes',
  'system:admin': 'System-level admin operations',
  'redis:read': 'Read from Redis',
  'redis:write': 'Write to Redis',
  'workflow:read': 'Read workflow definitions',
  'workflow:execute': 'Execute workflows',
}

function getCapabilityDescription(capability: string): string {
  return capabilityDescriptions[capability] || 'Unknown capability'
}

async function fetchCapabilities() {
  loading.value = true
  error.value = null
  try {
    const data = await getCapabilities(props.pluginName)
    if (data) {
      capabilityInfo.value = data
      selectedCapabilities.value = []
    } else {
      error.value = 'Failed to fetch capabilities'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch capabilities'
  } finally {
    loading.value = false
  }
}

async function handleApproveSelected() {
  if (selectedCapabilities.value.length === 0) return

  approving.value = true
  try {
    const success = await approveCapabilities(props.pluginName, selectedCapabilities.value)
    if (success) {
      emit('approved')
      emit('close')
    } else {
      error.value = 'Failed to approve capabilities'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to approve capabilities'
  } finally {
    approving.value = false
  }
}

async function handleApproveAll() {
  if (!capabilityInfo.value) return

  approving.value = true
  try {
    const success = await approveCapabilities(
      props.pluginName,
      capabilityInfo.value.pending_approval
    )
    if (success) {
      emit('approved')
      emit('close')
    } else {
      error.value = 'Failed to approve capabilities'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to approve capabilities'
  } finally {
    approving.value = false
  }
}

function handleCancel() {
  emit('close')
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    fetchCapabilities()
  }
})
</script>

<style scoped>
.capability-approval-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.capability-approval-dialog {
  background: var(--bg-primary);
  border-radius: 8px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-default);
}

.dialog-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  padding: 0.5rem;
  cursor: pointer;
  color: var(--text-secondary);
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: var(--color-background-hover);
}

.close-btn svg {
  width: 20px;
  height: 20px;
}

.dialog-loading,
.dialog-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--text-secondary);
}

.dialog-error {
  color: var(--color-error);
}

.spinner {
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.plugin-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.plugin-info h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.trust-tier-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.tier-official {
  background-color: #10b981;
  color: white;
}

.tier-verified {
  background-color: #3b82f6;
  color: white;
}

.tier-community {
  background-color: #f59e0b;
  color: white;
}

.tier-unverified {
  background-color: #ef4444;
  color: white;
}

.approval-description {
  margin-bottom: 1.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.capabilities-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.capability-item {
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.75rem;
  transition: background-color 0.2s;
}

.capability-item:hover {
  background-color: var(--color-background-hover);
}

.capability-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  margin-bottom: 0.25rem;
}

.capability-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.capability-name {
  font-weight: 600;
  color: var(--text-primary);
  font-family: monospace;
}

.capability-description {
  display: block;
  margin-left: 1.65rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.no-pending {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid var(--border-default);
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--color-background-secondary);
  color: var(--text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background-color: var(--color-background-hover);
}

.btn-primary {
  background-color: var(--color-primary);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}
</style>
