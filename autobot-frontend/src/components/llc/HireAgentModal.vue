<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  HireAgentModal (GH#10219) — minimal form to hire an LLC agent, including the
  adapter-type selector. Posts to POST /api/llc/companies/{id}/agent-hires.
-->
<template>
  <BaseModal
    :close-label="t('ui.modal.closeDialog')"
    :model-value="true"
    :title="t('hireAgent.title')"
    size="sm"
    @close="emit('close')"
  >
    <form class="hire-form" @submit.prevent="submit">
      <label class="field">
        <span class="field-label">{{ t('hireAgent.agentName') }}</span>
        <input v-model="agentName" type="text" required class="field-input" v-bind:placeholder="t('hireAgent.agentNamePlaceholder')" />
      </label>

      <label class="field">
        <span class="field-label">{{ t('hireAgent.model') }}</span>
        <select v-model="model" class="field-input">
          <option value="claude-sonnet-4-6">{{ t('hireAgent.modelSonnet') }}</option>
          <option value="claude-haiku-4-5-20251001">{{ t('hireAgent.modelHaiku') }}</option>
        </select>
      </label>

      <label class="field">
        <span class="field-label">{{ t('hireAgent.orgRole') }}</span>
        <select v-model="orgRole" class="field-input">
          <option value="worker">{{ t('hireAgent.roleWorker') }}</option>
          <option value="specialist">{{ t('hireAgent.roleSpecialist') }}</option>
          <option value="coordinator">{{ t('hireAgent.roleCoordinator') }}</option>
          <option value="manager">{{ t('hireAgent.roleManager') }}</option>
        </select>
      </label>

      <label class="field">
        <span class="field-label">{{ t('hireAgent.adapter') }}</span>
        <AdapterTypeSelect v-model="adapterType" />
      </label>

      <div class="flex items-center justify-between gap-3">
        <div>
          <span class="field-label">{{ t('hireAgent.runOnHeartbeat') }}</span>
          <p class="text-xs text-autobot-text-muted">{{ t('hireAgent.runOnHeartbeatHint') }}</p>
        </div>
        <BaseSwitch v-model="heartbeatEnabled" :label="t('hireAgent.runOnHeartbeat')" data-testid="hire-heartbeat" />
      </div>

      <BaseAlert v-if="pending" variant="info" :message="t('hireAgent.pendingApproval')" data-testid="hire-pending" />
      <p v-if="error" class="form-error">{{ error }}</p>
    </form>

    <template #actions>
      <BaseButton variant="ghost" type="button" @click="emit('close')">{{ t('common.cancel') }}</BaseButton>
      <BaseButton type="submit" :disabled="submitting || pending || !agentName" @click="submit">
        {{ submitting ? t('hireAgent.hiring') : t('hireAgent.hire') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { BaseAlert, BaseModal, BaseSwitch, BaseButton } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import AdapterTypeSelect from './AdapterTypeSelect.vue'
const { t } = useI18n()

const props = defineProps<{ companyId: string }>()
const emit = defineEmits<{ close: []; hired: [] }>()

const logger = createLogger('HireAgentModal')
const api = useApiClient()

const agentName = ref('')
const model = ref('claude-sonnet-4-6')
const orgRole = ref('worker')
const adapterType = ref('')
// #15907: off by default -- the 2026-09-28 ruling keeps a hire off the heartbeat
// unless the owner opts in (`AgentHireRequest.heartbeat_enabled` defaults False).
const heartbeatEnabled = ref(false)
const submitting = ref(false)
const error = ref('')
// A company that requires approval for hires answers 202 `pending_approval`: a request exists, no agent does (#8214).
const pending = ref(false)

async function submit(): Promise<void> {
  if (!agentName.value) return
  submitting.value = true
  error.value = ''
  try {
    const result = await api.post(`/api/llc/companies/${props.companyId}/agent-hires`, {
      agent_name: agentName.value,
      org_role: orgRole.value,
      model: model.value,
      adapter_type: adapterType.value,
      heartbeat_enabled: heartbeatEnabled.value,
    })
    if (result?.status === 'pending_approval') {
      pending.value = true
      return
    }
    emit('hired')
    emit('close')
  } catch (err: unknown) {
    // ApiClient throws an Error whose message already carries the API detail
    // (e.g. the 422 "Unknown adapter_type …").
    error.value = (err instanceof Error && err.message) || t('hireAgent.failed')
    logger.error('Hire agent failed', err)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
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
  color: var(--text-secondary);
}

.field-input {
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-primary);
}

.form-error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-error);
}
</style>
