<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  DuplicateSecrets — stored credentials that share one name and vault (#17850).
  Counts and vaults only: no secret id, name or value is shown (#17865). Propose verifies each copy against what it
  connects to and asks an administrator, in the Approvals inbox, to remove the copies that do not work; it removes
  nothing itself. Lives on the Secrets page (/secrets?view=duplicates): /secrets is the one place secrets are managed.
-->
<template>
  <div data-testid="duplicate-secrets">
    <BaseCard :title="t('admin.cleanup.secretDuplicates.title')" :subtitle="t('admin.cleanup.secretDuplicates.description')">
      <BaseAlert v-if="loadFailed" variant="warning" :message="t('admin.cleanup.statusUnavailable')" />
      <p v-else-if="!status">{{ t('admin.cleanup.loading') }}</p>
      <template v-else>
        <p>
          {{ t('admin.cleanup.count', { count: status.group_count }) }}
          {{ t('admin.cleanup.secretDuplicates.copies', { count: status.copy_count }) }}
        </p>
        <ul v-if="status.groups.length">
          <li v-for="(group, index) in status.groups" :key="index">
            {{ group.owner_vault }}: {{ t('admin.cleanup.secretDuplicates.copies', { count: group.copy_count }) }}
            <router-link v-if="group.approval_id" :to="approvalsLink">{{ t('admin.cleanup.openApprovals') }}</router-link>
          </li>
        </ul>
      </template>
      <BaseAlert v-if="proposed" variant="success" :message="t('admin.cleanup.proposed')" />
      <router-link v-if="proposed" :to="approvalsLink">{{ t('admin.cleanup.openApprovals') }}</router-link>
      <BaseAlert v-if="error" variant="error" :message="error" />
      <BaseButton size="sm" :disabled="!canPropose" @click="propose">
        {{ t('admin.cleanup.propose') }}
      </BaseButton>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, isHttpError } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']

const STATUS_URL = '/api/admin/secret-duplicates'
const REQUEST_URL = '/api/admin/secret-duplicates/requests'

const { t } = useI18n()
const logger = createLogger('DuplicateSecrets')
const llcStore = useLlcCompanyStore()

const status = ref<Schemas['DuplicateStatus'] | null>(null)
const loadFailed = ref(false)
const busy = ref(false)
const proposed = ref(false)
const remaining = ref(0) // duplicated groups the last request left for another call (the per-request cap)
const error = ref('')

// The approvals inbox is company-scoped: go to the selected company's, else the company picker.
const approvalsLink = computed(() =>
  llcStore.selectedCompanyId
    ? { name: 'llc-approvals', params: { companyId: llcStore.selectedCompanyId } }
    : { name: 'llc-company-select' },
)

// Propose stays available while groups remain, so the last groups of a capped request can be proposed too.
const canPropose = computed(
  () => !!status.value && status.value.group_count > 0 && !busy.value && (!proposed.value || remaining.value > 0),
)

async function load(): Promise<void> {
  try {
    const loaded: Schemas['DuplicateStatus'] = await apiClient.get(STATUS_URL)
    status.value = loaded
    loadFailed.value = false
  } catch (err) {
    loadFailed.value = true
    logger.error('Could not load duplicate secrets', err)
  }
}

// Known refusals map to localised text; the server's own wording (English) is never shown.
function proposeErrorKey(err: unknown): string {
  if (isHttpError(err) && err.status === 403) return 'admin.cleanup.proposeForbidden'
  if (isHttpError(err) && err.status === 409) return 'admin.cleanup.proposeRefused'
  return 'admin.cleanup.proposeFailed'
}

async function propose(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const reply: Schemas['DuplicateRequestResponse'] = await apiClient.post(REQUEST_URL)
    proposed.value = proposed.value || reply.proposals.some((proposal) => !!proposal.approval_id)
    remaining.value = reply.remaining
    await load()
  } catch (err) {
    error.value = t(proposeErrorKey(err))
    logger.error('Could not propose duplicate secret resolution', err)
  } finally {
    busy.value = false
  }
}

onMounted(() => void load())
</script>
