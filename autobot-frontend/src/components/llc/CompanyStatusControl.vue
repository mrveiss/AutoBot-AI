<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#12231: company status control — a status badge plus the transition
  actions valid for the company's current llc_status (activate / suspend /
  offboard / archive). Wires the #12211/#12234 endpoints via
  useCompanyStatusApi; destructive transitions (offboard/archive) require a
  confirmation, and a rejected transition (HTTP 409) surfaces its message.
  Emits `updated` with the refreshed company so the parent can refresh.
-->
<template>
  <div class="company-status-control">
    <BaseBadge :variant="badgeVariant" size="sm">
      {{ t(`llcCompanyStatus.${status}`) }}
    </BaseBadge>

    <div v-if="actions.length" class="company-status-actions">
      <BaseButton
        v-for="action in actions"
        :key="action"
        :variant="actionVariant(action)"
        size="sm"
        :disabled="isBusy"
        @click="onAction(action)"
      >
        {{ t(`llcCompanyStatus.${action}`) }}
      </BaseButton>
    </div>

    <p v-if="errorMessage" class="company-status-error" role="alert">
      {{ errorMessage }}
    </p>

    <BaseModal
      v-if="pendingAction"
      :model-value="true"
      :title="t('llcCompanyStatus.confirmTitle')"
      :close-label="t('common.cancel')"
      size="sm"
      @close="cancelConfirm"
    >
      <p class="company-status-confirm">
        {{
          t(
            pendingAction === 'archive'
              ? 'llcCompanyStatus.confirmArchive'
              : 'llcCompanyStatus.confirmOffboard',
            { name: company.name },
          )
        }}
      </p>
      <template #actions>
        <BaseButton variant="ghost" :disabled="isBusy" @click="cancelConfirm">
          {{ t('common.cancel') }}
        </BaseButton>
        <BaseButton variant="danger" :disabled="isBusy" @click="runPending">
          {{ t('llcCompanyStatus.confirm') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseModal, type BadgeVariant, type ButtonVariant } from '@autobot/ui'
import {
  useCompanyStatusApi,
  transitionsFor,
  DESTRUCTIVE_ACTIONS,
  type CompanyStatus,
  type CompanyStatusAction,
  type CompanyStatusResult,
} from '@/composables/llc/useCompanyStatusApi'

const props = defineProps<{
  company: { id: string; name: string; llc_status?: string | null }
}>()

const emit = defineEmits<{ updated: [CompanyStatusResult] }>()

const { t } = useI18n()
const statusApi = useCompanyStatusApi()

const isBusy = ref(false)
const errorMessage = ref('')
const pendingAction = ref<CompanyStatusAction | null>(null)

const status = computed<CompanyStatus>(() => (props.company.llc_status ?? 'onboarding') as CompanyStatus)
const actions = computed(() => transitionsFor(props.company.llc_status))

const BADGE_VARIANTS: Record<CompanyStatus, BadgeVariant> = {
  onboarding: 'neutral',
  active: 'success',
  paused: 'warning',
  offboarding: 'warning',
  archived: 'danger',
}
const badgeVariant = computed<BadgeVariant>(() => BADGE_VARIANTS[status.value] ?? 'neutral')

function actionVariant(action: CompanyStatusAction): ButtonVariant {
  if (action === 'activate') return 'primary'
  if (DESTRUCTIVE_ACTIONS.has(action)) return 'danger'
  return 'secondary'
}

function onAction(action: CompanyStatusAction): void {
  errorMessage.value = ''
  if (DESTRUCTIVE_ACTIONS.has(action)) {
    pendingAction.value = action
    return
  }
  void apply(action)
}

function cancelConfirm(): void {
  pendingAction.value = null
}

async function runPending(): Promise<void> {
  const action = pendingAction.value
  if (action) await apply(action)
}

async function apply(action: CompanyStatusAction): Promise<void> {
  isBusy.value = true
  errorMessage.value = ''
  try {
    const updated = await statusApi.transition(props.company.id, action)
    emit('updated', updated)
    pendingAction.value = null
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : t('llcCompanyStatus.updateError')
  } finally {
    isBusy.value = false
  }
}
</script>

<style scoped>
.company-status-control {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.company-status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.company-status-error {
  flex-basis: 100%;
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-danger);
}

.company-status-confirm {
  margin: 0;
  color: var(--text-primary);
}
</style>
