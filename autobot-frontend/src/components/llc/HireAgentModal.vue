<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  HireAgentModal (GH#10219) — minimal form to hire an LLC agent, including the
  adapter-type selector. Posts to POST /api/llc/companies/{id}/agent-hires.
-->
<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="Hire agent">
      <h3 class="modal-title">Hire Agent</h3>

      <form class="hire-form" @submit.prevent="submit">
        <label class="field">
          <span class="field-label">Agent name</span>
          <input v-model="agentName" type="text" required class="field-input" placeholder="e.g. Builder-1" />
        </label>

        <label class="field">
          <span class="field-label">Model</span>
          <select v-model="model" class="field-input">
            <option value="claude-sonnet-4-6">Sonnet (default)</option>
            <option value="claude-haiku-4-5-20251001">Haiku (assistant)</option>
          </select>
        </label>

        <label class="field">
          <span class="field-label">Org role</span>
          <select v-model="orgRole" class="field-input">
            <option value="worker">Worker</option>
            <option value="specialist">Specialist</option>
            <option value="coordinator">Coordinator</option>
            <option value="manager">Manager</option>
          </select>
        </label>

        <label class="field">
          <span class="field-label">Adapter</span>
          <AdapterTypeSelect v-model="adapterType" />
        </label>

        <p v-if="error" class="form-error">{{ error }}</p>

        <div class="form-actions">
          <button type="button" class="btn btn-ghost" @click="emit('close')">Cancel</button>
          <button type="submit" class="btn btn-primary" :disabled="submitting || !agentName">
            {{ submitting ? 'Hiring…' : 'Hire' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import AdapterTypeSelect from './AdapterTypeSelect.vue'

const props = defineProps<{ companyId: string }>()
const emit = defineEmits<{ close: []; hired: [] }>()

const logger = createLogger('HireAgentModal')
const api = useApiClient()

const agentName = ref('')
const model = ref('claude-sonnet-4-6')
const orgRole = ref('worker')
const adapterType = ref('')
const submitting = ref(false)
const error = ref('')

async function submit(): Promise<void> {
  if (!agentName.value) return
  submitting.value = true
  error.value = ''
  try {
    await api.post(`/api/llc/companies/${props.companyId}/agent-hires`, {
      agent_name: agentName.value,
      org_role: orgRole.value,
      model: model.value,
      adapter_type: adapterType.value,
    })
    emit('hired')
    emit('close')
  } catch (err: unknown) {
    // ApiClient throws an Error whose message already carries the API detail
    // (e.g. the 422 "Unknown adapter_type …").
    error.value = (err instanceof Error && err.message) || 'Failed to hire agent.'
    logger.error('Hire agent failed', err)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal-card {
  width: min(28rem, 92vw);
  background: var(--bg-surface, #fff);
  border-radius: 10px;
  padding: 1.5rem;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
}

.modal-title {
  margin: 0 0 1rem;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.hire-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary, #6b7280);
}

.field-input {
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #111827);
}

.form-error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-error, #dc2626);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.btn {
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn-ghost {
  background: transparent;
  border-color: var(--border-default, #d1d5db);
  color: var(--text-secondary, #6b7280);
}

.btn-primary {
  background: var(--color-accent, #c4651a);
  color: #fff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
