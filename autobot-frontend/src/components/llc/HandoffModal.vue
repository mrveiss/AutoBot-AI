<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  GH#10531/#10534: hand a work item from a human to an agent, or from an agent to
  a human reviewer. Wired to the real handoff endpoints (NOT /release):
    to_agent → POST /work-items/{id}/handoff/to-agent  (FR-HYBRID-06)
    to_human → POST /work-items/{id}/handoff/to-human  (FR-HYBRID-05/02)
-->
<template>
  <BaseModal
    :model-value="true"
    :title="modalTitle"
    size="sm"
    @close="emit('close')"
  >
    <label class="handoff-label">
      {{ direction === 'to_agent' ? $t('nav.llcSelectAgent') : $t('nav.llcSelectReviewer') }}
      <select v-model="targetId" class="handoff-select">
        <option value="" disabled>—</option>
        <template v-if="direction === 'to_agent'">
          <option v-for="a in people.agents.value" :key="a.id" :value="a.id">{{ a.name }}</option>
        </template>
        <template v-else>
          <option v-for="h in people.humans.value" :key="h.user_id" :value="h.user_id">
            {{ h.name }} ({{ h.role }})
          </option>
        </template>
      </select>
    </label>

    <label class="handoff-label">
      {{ $t('nav.llcHandoffNotes') }}
      <textarea v-model="notes" class="handoff-notes" rows="4" :placeholder="$t('nav.llcHandoffNotesPlaceholder')" />
    </label>

    <p v-if="error" class="handoff-error">{{ error }}</p>

    <template #actions>
      <button class="handoff-cancel" :disabled="isSubmitting" @click="emit('close')">
        {{ $t('common.cancel') }}
      </button>
      <button class="handoff-confirm" :disabled="!targetId || isSubmitting" @click="submit">
        {{ isSubmitting ? $t('common.loading') : $t('nav.llcHandoffConfirm') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { useUserStore } from '@/stores/useUserStore'
import { createLogger } from '@/utils/debugUtils'
import { useCompanyPeople } from '@/composables/llc/useCompanyPeople'
import { BaseModal } from '@autobot/ui'

const props = defineProps<{
  workItemId: string
  companyId: string
  direction: 'to_agent' | 'to_human'
  // The item's current agent assignee (PK) — required for to_human handoff.
  agentAssigneeId?: string | null
}>()

const emit = defineEmits<{ close: []; done: [] }>()

const { t } = useI18n()
const api = useApiClient()
const userStore = useUserStore()
const logger = createLogger('HandoffModal')
const people = useCompanyPeople(props.companyId)

const targetId = ref('')
const notes = ref('')
const isSubmitting = ref(false)
const error = ref<string | null>(null)

const modalTitle = computed(() =>
  props.direction === 'to_agent' ? t('nav.llcHandoffToAgent') : t('nav.llcHandoffToHuman')
)

onMounted(() => void people.load())

async function submit(): Promise<void> {
  if (!targetId.value) return
  isSubmitting.value = true
  error.value = null
  try {
    if (props.direction === 'to_agent') {
      await api.post(`/api/llc/work-items/${props.workItemId}/handoff/to-agent`, {
        user_id: userStore.currentUser?.id ?? '',
        company_id: props.companyId,
        target_agent_id: targetId.value,
        human_notes: notes.value,
        user_display: userStore.currentUser?.displayName ?? '',
      })
    } else {
      await api.post(`/api/llc/work-items/${props.workItemId}/handoff/to-human`, {
        agent_id: props.agentAssigneeId ?? '',
        reviewer_user_id: targetId.value,
        company_id: props.companyId,
        agent_notes: notes.value || null,
      })
    }
    emit('done')
  } catch (err) {
    logger.error('Handoff failed', err)
    error.value = err instanceof Error ? err.message : 'Handoff failed'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.handoff-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-secondary, #6b7280);
  margin-bottom: 0.875rem;
}
.handoff-select,
.handoff-notes {
  font-size: 0.875rem;
  padding: 0.5rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-input, #fff);
  color: var(--text-primary, #111827);
}
.handoff-error {
  font-size: 0.8125rem;
  color: var(--color-error, #cb3326);
  margin: 0;
}
.handoff-cancel,
.handoff-confirm {
  padding: 0.5rem 0.875rem;
  border-radius: var(--radius-md, 8px);
  font-size: 0.875rem;
  font-weight: 500;
}
.handoff-confirm {
  background: var(--color-accent, #c4651a);
  color: #fff;
}
.handoff-confirm:disabled {
  opacity: 0.5;
}
.handoff-cancel {
  border: 1px solid var(--border-default, #e5e7eb);
  color: var(--text-secondary, #6b7280);
}
</style>
