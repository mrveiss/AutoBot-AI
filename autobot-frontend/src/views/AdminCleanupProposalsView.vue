<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdminCleanupProposalsView — propose the two decided cleanups (#20567).
  Each card shows what is there (a count, never a file's contents) and a Propose button.
  A proposal only creates a pending approval; nothing is removed until a human approves it.
-->
<template>
  <div>
    <PageHeader :title="t('admin.cleanup.title')" :subtitle="t('admin.cleanup.subtitle')" />

    <BaseCard
      v-for="card in cards"
      :key="card.id"
      :title="t(`admin.cleanup.${card.id}.title`)"
      :subtitle="t(`admin.cleanup.${card.id}.description`)"
      :data-testid="`cleanup-${card.id}`"
    >
      <BaseAlert v-if="card.loadFailed" variant="warning" :message="t('admin.cleanup.statusUnavailable')" />
      <p v-else-if="!card.status">{{ t('admin.cleanup.loading') }}</p>
      <BaseAlert v-else-if="card.status.refused" variant="warning" :message="t('admin.cleanup.refused')" />
      <p v-else>{{ statusText(card) }}</p>
      <BaseAlert v-if="card.proposed" variant="success" :message="t('admin.cleanup.proposed')" />
      <router-link v-if="card.proposed" :to="approvalsLink">{{ t('admin.cleanup.openApprovals') }}</router-link>
      <BaseAlert v-if="card.error" variant="error" :message="card.error" />
      <BaseButton
        size="sm"
        :disabled="!card.status || card.status.count === 0 || !!card.status.refused || card.busy || card.proposed"
        @click="propose(card)"
      >
        {{ t('admin.cleanup.propose') }}
      </BaseButton>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, PageHeader, isHttpError } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']

const { t } = useI18n()
const logger = createLogger('AdminCleanupProposalsView')
const llcStore = useLlcCompanyStore()

interface Card {
  id: string
  statusUrl: string
  requestUrl: string
  status: Schemas['CleanupStatus'] | null
  loadFailed: boolean
  busy: boolean
  proposed: boolean
  error: string
}

const makeCard = (id: string, statusUrl: string, requestUrl: string): Card => ({
  id,
  statusUrl,
  requestUrl,
  status: null,
  loadFailed: false,
  busy: false,
  proposed: false,
  error: '',
})

const cards = reactive<Card[]>([
  makeCard('envCopies', '/api/admin/env-copies-cleanup', '/api/admin/env-copies-cleanup/requests'),
  makeCard('tierColumn', '/api/admin/org-tier-column', '/api/admin/org-tier-column/requests'),
])

// The approvals inbox is company-scoped: go to the selected company's, else the company picker.
const approvalsLink = computed(() =>
  llcStore.selectedCompanyId
    ? { name: 'llc-approvals', params: { companyId: llcStore.selectedCompanyId } }
    : { name: 'llc-company-select' },
)

function statusText(card: Card): string {
  const status = card.status
  if (!status) return ''
  return `${t('admin.cleanup.count', { count: status.count })} ${status.detail ?? ''}`.trim()
}

async function load(card: Card): Promise<void> {
  try {
    if (card.id === 'tierColumn') {
      const col: Schemas['OrgTierColumnStatus'] = await apiClient.get(card.statusUrl)
      card.status = {
        count: col.present ? 1 : 0,
        detail: t(col.present ? 'admin.cleanup.tierColumn.present' : 'admin.cleanup.tierColumn.absent'),
      }
    } else {
      const status: Schemas['CleanupStatus'] = await apiClient.get(card.statusUrl)
      card.status = status
    }
  } catch (err) {
    card.loadFailed = true
    logger.error('Could not load cleanup status', card.id, err)
  }
}

// Known refusals map to localised text; the server's own wording (English) is never shown.
function proposeErrorKey(err: unknown): string {
  if (isHttpError(err) && err.status === 403) return 'admin.cleanup.proposeForbidden'
  if (isHttpError(err) && err.status === 409) return 'admin.cleanup.proposeRefused'
  return 'admin.cleanup.proposeFailed'
}

async function propose(card: Card): Promise<void> {
  card.busy = true
  card.error = ''
  try {
    // The org-tier-column route answers with its own response model; both carry the approval id.
    const reply: Schemas['CleanupRequestResponse'] | Schemas['OrgTierColumnRequestResponse'] =
      await apiClient.post(card.requestUrl)
    card.proposed = !!reply.approval_id
  } catch (err) {
    card.error = t(proposeErrorKey(err))
    logger.error('Could not propose cleanup', card.id, err)
  } finally {
    card.busy = false
  }
}

onMounted(() => cards.forEach((card) => void load(card)))
</script>
