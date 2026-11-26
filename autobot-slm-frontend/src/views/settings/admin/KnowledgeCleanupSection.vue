// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

<script setup lang="ts">
/**
 * KnowledgeCleanupSection - the two knowledge-cleanup proposal surfaces on the Data hygiene page (#20992).
 *
 *   1. Stored connector credentials: records holding a clear-text copy beside the secrets-store copy.
 *   2. Empty vector collections: knowledge-base collections holding zero vectors.
 *
 * Each row only PROPOSES a removal (an approval-gate request). The decision is made in the existing
 * Approvals inbox; this section has no approve control and removes nothing itself.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { autobotApiErrorMessage } from '@/composables/useAutobotApi'
import {
  useKnowledgeCleanupApi,
  type ConnectorCredentialScan,
  type EmptyCollectionsReport,
} from '@/composables/useKnowledgeCleanupApi'
import { BaseAlert, BaseButton, BaseTable, type BaseTableColumn, createLogger } from '@autobot/ui'

const logger = createLogger('KnowledgeCleanupSection')
const api = useKnowledgeCleanupApi()
const { t } = useI18n()

interface RowResult {
  ok: boolean
  message: string
}

// -- Connector credentials ------------------------------------------------

const scan = ref<ConnectorCredentialScan | null>(null)
const scanLoading = ref(false)
const scanError = ref('')
const credentialResults = ref<Record<string, RowResult>>({})
const credentialProposing = ref<Record<string, boolean>>({})

async function fetchScan(): Promise<void> {
  scanLoading.value = true
  scanError.value = ''
  try {
    scan.value = await api.scanConnectorCredentials()
  } catch (err) {
    scanError.value = autobotApiErrorMessage(err, t('dataHygiene.knowledge.credentials.loadErrorFallback'))
    logger.error('Error scanning connector credentials:', err)
  } finally {
    scanLoading.value = false
  }
}

async function proposeStrip(connectorId: string): Promise<void> {
  credentialProposing.value = { ...credentialProposing.value, [connectorId]: true }
  try {
    const result = await api.proposeConnectorCredentialStrip(connectorId)
    credentialResults.value = {
      ...credentialResults.value,
      [connectorId]: { ok: true, message: t('dataHygiene.knowledge.proposed', { id: result.approval_id }) },
    }
  } catch (err) {
    credentialResults.value = {
      ...credentialResults.value,
      [connectorId]: { ok: false, message: autobotApiErrorMessage(err, t('dataHygiene.knowledge.proposeErrorFallback')) },
    }
  } finally {
    credentialProposing.value = { ...credentialProposing.value, [connectorId]: false }
  }
}

// -- Empty collections ----------------------------------------------------

const collections = ref<EmptyCollectionsReport | null>(null)
const collectionsLoading = ref(false)
const collectionsError = ref('')
const collectionResults = ref<Record<string, RowResult>>({})
const collectionProposing = ref<Record<string, boolean>>({})

async function fetchCollections(): Promise<void> {
  collectionsLoading.value = true
  collectionsError.value = ''
  try {
    collections.value = await api.getEmptyCollections()
  } catch (err) {
    collectionsError.value = autobotApiErrorMessage(err, t('dataHygiene.knowledge.collections.loadErrorFallback'))
    logger.error('Error listing empty collections:', err)
  } finally {
    collectionsLoading.value = false
  }
}

async function proposeDelete(collection: string): Promise<void> {
  collectionProposing.value = { ...collectionProposing.value, [collection]: true }
  try {
    const result = await api.proposeEmptyCollectionDelete(collection)
    collectionResults.value = {
      ...collectionResults.value,
      [collection]: { ok: true, message: t('dataHygiene.knowledge.proposed', { id: result.approval_id }) },
    }
  } catch (err) {
    collectionResults.value = {
      ...collectionResults.value,
      [collection]: { ok: false, message: autobotApiErrorMessage(err, t('dataHygiene.knowledge.proposeErrorFallback')) },
    }
  } finally {
    collectionProposing.value = { ...collectionProposing.value, [collection]: false }
  }
}

// BaseTable rows are plain records; the response interfaces carry no index signature.
const findings = computed(() => (scan.value?.findings ?? []).map((f) => ({ ...f, fieldList: f.fields.join(', ') })))
const emptyCollections = computed(() => (collections.value?.empty ?? []).map((name) => ({ name })))

const credentialColumns = computed<BaseTableColumn[]>(() => [
  { key: 'connector_id', label: t('dataHygiene.knowledge.credentials.connector'), monospace: true },
  { key: 'connector_type', label: t('dataHygiene.knowledge.credentials.type') },
  { key: 'fieldList', label: t('dataHygiene.knowledge.credentials.fields'), wrap: true },
])
const collectionColumns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('dataHygiene.knowledge.collections.name'), monospace: true },
])

function refresh(): void {
  credentialResults.value = {}
  collectionResults.value = {}
  fetchScan()
  fetchCollections()
}

onMounted(refresh)
</script>

<template>
  <section class="bg-autobot-bg-secondary rounded-lg shadow p-6 space-y-8" aria-labelledby="data-hygiene-knowledge-heading">
    <div class="flex items-center justify-between">
      <div>
        <h2 id="data-hygiene-knowledge-heading" class="text-lg font-semibold text-autobot-text-primary">
          {{ $t('dataHygiene.knowledge.title') }}
        </h2>
        <p class="text-sm text-autobot-text-secondary mt-1">{{ $t('dataHygiene.knowledge.subtitle') }}</p>
      </div>
      <BaseButton variant="secondary" size="sm" :disabled="scanLoading || collectionsLoading" @click="refresh">
        {{ $t('dataHygiene.refresh') }}
      </BaseButton>
    </div>

    <!-- Connector credentials -->
    <div data-testid="knowledge-credentials">
      <h3 class="text-sm font-semibold text-autobot-text-primary mb-1">{{ $t('dataHygiene.knowledge.credentials.title') }}</h3>
      <p class="text-xs text-autobot-text-secondary mb-3">{{ $t('dataHygiene.knowledge.credentials.subtitle') }}</p>
      <BaseAlert v-if="scanError" variant="error" :message="scanError" class="mb-3" />
      <BaseAlert
        v-if="scan && scan.unscannable_ids.length > 0"
        variant="warning"
        :message="$t('dataHygiene.knowledge.credentials.unscannable', { ids: scan.unscannable_ids.join(', ') })"
        class="mb-3"
      />
      <BaseTable
        :columns="credentialColumns"
        :rows="findings"
        row-key="connector_id"
        size="compact"
        :loading="scanLoading"
        :loading-label="$t('dataHygiene.knowledge.loading')"
        :empty-title="$t('dataHygiene.knowledge.credentials.empty')"
        :aria-label="$t('dataHygiene.knowledge.credentials.title')"
        :actions-label="$t('dataHygiene.knowledge.credentials.action')"
      >
        <template #actions="{ row }">
          <BaseButton
            v-if="row.has_secrets_store_copy"
            size="sm"
            :loading="credentialProposing[String(row.connector_id)]"
            @click="proposeStrip(String(row.connector_id))"
          >
            {{ $t('dataHygiene.knowledge.propose') }}
          </BaseButton>
          <span v-else class="text-xs text-autobot-warning">{{ $t('dataHygiene.knowledge.credentials.noStoreCopy') }}</span>
          <p
            v-if="credentialResults[String(row.connector_id)]"
            class="text-xs mt-1"
            :class="credentialResults[String(row.connector_id)].ok ? 'text-autobot-success' : 'text-autobot-error'"
          >
            {{ credentialResults[String(row.connector_id)].message }}
          </p>
        </template>
      </BaseTable>
    </div>

    <!-- Empty collections -->
    <div data-testid="knowledge-collections">
      <h3 class="text-sm font-semibold text-autobot-text-primary mb-1">{{ $t('dataHygiene.knowledge.collections.title') }}</h3>
      <p class="text-xs text-autobot-text-secondary mb-3">{{ $t('dataHygiene.knowledge.collections.subtitle') }}</p>
      <BaseAlert v-if="collectionsError" variant="error" :message="collectionsError" class="mb-3" />
      <BaseAlert
        v-if="collections && collections.unreadable.length > 0"
        variant="warning"
        :message="$t('dataHygiene.knowledge.collections.unreadable', { names: collections.unreadable.join(', ') })"
        class="mb-3"
      />
      <BaseTable
        :columns="collectionColumns"
        :rows="emptyCollections"
        row-key="name"
        size="compact"
        :loading="collectionsLoading"
        :loading-label="$t('dataHygiene.knowledge.loading')"
        :empty-title="$t('dataHygiene.knowledge.collections.empty')"
        :aria-label="$t('dataHygiene.knowledge.collections.title')"
        :actions-label="$t('dataHygiene.knowledge.collections.action')"
      >
        <template #actions="{ row }">
          <BaseButton size="sm" :loading="collectionProposing[String(row.name)]" @click="proposeDelete(String(row.name))">
            {{ $t('dataHygiene.knowledge.propose') }}
          </BaseButton>
          <p
            v-if="collectionResults[String(row.name)]"
            class="text-xs mt-1"
            :class="collectionResults[String(row.name)].ok ? 'text-autobot-success' : 'text-autobot-error'"
          >
            {{ collectionResults[String(row.name)].message }}
          </p>
        </template>
      </BaseTable>
    </div>
  </section>
</template>
