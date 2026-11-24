<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  OwnerlessSessionsPanel (#20904): chat sessions that record no owner, and a Propose button per row.
  A proposal only creates a pending approval; nothing is assigned until a human approves it.
-->
<template>
  <BaseCard
    :title="t('admin.ownerless.title')"
    :subtitle="t('admin.ownerless.description')"
    data-testid="ownerless-sessions"
  >
    <BaseAlert v-if="loadFailed" variant="warning" :message="t('admin.ownerless.loadFailed')" />
    <p v-else-if="!report">{{ t('admin.cleanup.loading') }}</p>
    <p v-else-if="report.count === 0">{{ t('admin.ownerless.none') }}</p>
    <template v-else>
      <BaseInput v-model="owner" :label="t('admin.ownerless.ownerLabel')" :placeholder="t('admin.ownerless.ownerPlaceholder')" />
      <ul class="my-3 list-none p-0">
        <li class="flex items-center gap-3 py-1" v-for="id in report.session_ids" :key="id" :data-testid="`ownerless-${id}`">
          <code>{{ id }}</code>
          <span v-if="proposed.has(id)">{{ t('admin.ownerless.proposed') }}</span>
          <BaseButton v-else size="sm" :disabled="!owner.trim() || busy" @click="propose(id)">
            {{ t('admin.ownerless.propose') }}
          </BaseButton>
        </li>
      </ul>
      <router-link v-if="proposed.size" :to="approvalsLink">{{ t('admin.cleanup.openApprovals') }}</router-link>
    </template>
    <BaseAlert v-if="error" variant="error" :message="error" />
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, BaseInput, isHttpError } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { useOwnerlessChatSessionsApi } from '@/composables/useOwnerlessChatSessionsApi'

const { t } = useI18n()
const logger = createLogger('OwnerlessSessionsPanel')
const llcStore = useLlcCompanyStore()
const { report, loadFailed, load, propose: submit } = useOwnerlessChatSessionsApi()

const owner = ref('')
const busy = ref(false)
const error = ref('')
const proposed = reactive(new Set<string>())

// The approvals inbox is company-scoped: go to the selected company's, else the company picker.
const approvalsLink = computed(() =>
  llcStore.selectedCompanyId
    ? { name: 'llc-approvals', params: { companyId: llcStore.selectedCompanyId } }
    : { name: 'llc-company-select' },
)

// Known refusals map to localised text; the server's own wording (English) is never shown.
function errorKey(err: unknown): string {
  if (isHttpError(err) && err.status === 403) return 'admin.cleanup.proposeForbidden'
  if (isHttpError(err) && err.status === 409) return 'admin.ownerless.refusedConflict'
  if (isHttpError(err) && err.status === 422) return 'admin.ownerless.refusedOwner'
  return 'admin.cleanup.proposeFailed'
}

async function propose(sessionId: string): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await submit(sessionId, owner.value.trim())
    proposed.add(sessionId)
  } catch (err) {
    error.value = t(errorKey(err))
    if (isHttpError(err) && err.status === 409) await load() // the report moved on: show what is true now
    logger.error('Could not propose an owner', sessionId, err)
  } finally {
    busy.value = false
  }
}

onMounted(() => void load())
</script>
