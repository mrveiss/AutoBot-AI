<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdminCleanupProposalsView — propose the three decided cleanups (#20567).
  Each card shows what is there (a count, never a file's contents) and a Propose button.
  A proposal only creates a pending approval; nothing is removed until a human approves it.
-->
<template>
  <div class="admin-cleanup-view">
    <div class="page-header">
      <h2 class="page-title">{{ t('admin.cleanup.title') }}</h2>
      <p class="page-subtitle">{{ t('admin.cleanup.subtitle') }}</p>
    </div>

    <section v-for="card in cards" :key="card.id" class="cleanup-card" :data-testid="`cleanup-${card.id}`">
      <h3 class="card-title">{{ t(`admin.cleanup.${card.id}.title`) }}</h3>
      <p class="card-text">{{ t(`admin.cleanup.${card.id}.description`) }}</p>
      <p class="card-status" :class="{ 'card-status--refused': card.status?.refused }">
        <template v-if="card.loadFailed">{{ t('admin.cleanup.statusUnavailable') }}</template>
        <template v-else-if="!card.status">{{ t('admin.cleanup.loading') }}</template>
        <template v-else>{{ t('admin.cleanup.count', { count: card.status.count }) }} {{ card.status.detail }}</template>
      </p>
      <p v-if="card.proposed" class="card-proposed" role="status">
        {{ t('admin.cleanup.proposed') }}
        <router-link :to="approvalsLink">{{ t('admin.cleanup.openApprovals') }}</router-link>
      </p>
      <p v-if="card.error" class="card-error" role="alert">{{ card.error }}</p>
      <BaseButton
        size="sm"
        :disabled="!card.status || card.status.count === 0 || !!card.status.refused || card.busy || card.proposed"
        @click="propose(card)"
      >
        {{ t('admin.cleanup.propose') }}
      </BaseButton>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
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

const makeCard = (id: string, base: string): Card => ({
  id,
  statusUrl: `/api/admin/${base}`,
  requestUrl: `/api/admin/${base}/requests`,
  status: null,
  loadFailed: false,
  busy: false,
  proposed: false,
  error: '',
})

const cards = reactive<Card[]>([
  makeCard('envCopies', 'env-copies-cleanup'),
  makeCard('infrastructureDir', 'stale-infrastructure-dir'),
  makeCard('tierColumn', 'org-tier-column'),
])

// The approvals inbox is company-scoped: go to the selected company's, else the company picker.
const approvalsLink = computed(() =>
  llcStore.selectedCompanyId
    ? { name: 'llc-approvals', params: { companyId: llcStore.selectedCompanyId } }
    : { name: 'llc-company-select' },
)

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

async function propose(card: Card): Promise<void> {
  card.busy = true
  card.error = ''
  try {
    const reply: Schemas['CleanupRequestResponse'] = await apiClient.post(card.requestUrl)
    card.proposed = !!reply.approval_id
  } catch (err) {
    card.error = t('admin.cleanup.proposeFailed')
    logger.error('Could not propose cleanup', card.id, err)
  } finally {
    card.busy = false
  }
}

onMounted(() => cards.forEach((card) => void load(card)))
</script>

<style scoped>
.admin-cleanup-view {
  padding: var(--spacing-6);
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-6);
}

.page-title {
  font-size: var(--text-2xl);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

.cleanup-card {
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.card-title {
  font-size: var(--text-lg);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
}

.card-text,
.card-status {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
}

.card-status--refused,
.card-error {
  color: var(--color-error);
}

.card-error {
  font-size: var(--text-sm);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
}

.card-proposed {
  font-size: var(--text-sm);
  color: var(--color-success);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
}
</style>
