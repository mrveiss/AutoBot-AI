// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

<script setup lang="ts">
/**
 * DataHygieneView - Orphan-storage preview, orphan-resource repair, and the
 * audit trail both leave behind (#17040).
 *
 * Three sections, each backed by the main AutoBot backend through the
 * `/autobot-api` proxy (`useAutobotApi`):
 *
 *   1. Unreferenced storage (`GET /admin/orphan-storage`) — read-only
 *      preview. Deletion is NEVER issued directly: selecting rows and
 *      confirming the preview modal only PROPOSES a cleanup, one
 *      `POST /approval-gates` request per candidate
 *      (`approval_type: 'destructive_action'`, `context.action:
 *      'orphan_storage_delete'` — the exact contract
 *      `services/orphan_storage_cleanup_action.py` documents). Approving the
 *      resulting gate in the existing approval inbox is what actually runs
 *      the cleanup; this view never shows an approve/reject control itself.
 *
 *   2. Unreachable resources (`GET /admin/orphans`) — facts/secrets no live
 *      owner can reach. "Repair" reassigns a live owner
 *      (`POST /admin/orphans/repair`) and is NOT a deletion, so it is called
 *      directly, the same way `api/admin_orphan_repair.py`'s own handler
 *      does — no approval gate.
 *
 *   3. Audit trail (`GET /audit/logs`) — recent entries for the three
 *      operation-name strings actually emitted by the two paths above
 *      (`orphan_storage.delete`, `approval.post_action_failed`,
 *      `resource.repair_orphan` — found by grepping their `audit_log(...)`
 *      call sites, not guessed).
 */

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  autobotApiErrorMessage,
  useAutobotApi,
  type AuditLogEntry,
  type OrphanResource,
  type OrphanStorageCandidate,
  type OrphanStorageListResponse,
  type UserResponse,
} from '@/composables/useAutobotApi'
import { formatFileSize } from '@/utils/formatHelpers'
import { formatRelativeTime } from '@/utils/dateUtils'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DataHygieneView')
const api = useAutobotApi()
// Runtime-composed messages (error fallbacks, per-row results) go through
// `t()` here -- everything else in this file is templated with `$t()`.
const { t } = useI18n()

// -- Unreferenced storage -----------------------------------------------

const orphanStorage = ref<OrphanStorageListResponse | null>(null)
const storageLoading = ref(false)
const storageError = ref('')
const selectedKeys = ref<Set<string>>(new Set())
const previewOpen = ref(false)
const proposing = ref(false)

interface ProposalResult {
  key: string
  candidate: OrphanStorageCandidate
  ok: boolean
  message: string
}
const proposalResults = ref<ProposalResult[]>([])

function candidateKey(c: OrphanStorageCandidate): string {
  return `${c.provider}:${c.id}`
}

const candidates = computed(() => orphanStorage.value?.candidates ?? [])
const unavailableProviders = computed(
  () => orphanStorage.value?.provider_statuses.filter((s) => !s.available) ?? [],
)
const selectedCandidates = computed(() =>
  candidates.value.filter((c) => selectedKeys.value.has(candidateKey(c))),
)

async function fetchOrphanStorage(): Promise<void> {
  storageLoading.value = true
  storageError.value = ''
  // bb's review, #17157: a stale propose-result from a previous fetch would otherwise
  // linger next to a row whose underlying candidate has since changed.
  proposalResults.value = []
  try {
    orphanStorage.value = await api.getOrphanStorage()
  } catch (err) {
    storageError.value = autobotApiErrorMessage(err, t('dataHygiene.storage.loadErrorFallback'))
    logger.error('Error fetching orphan-storage candidates:', err)
  } finally {
    storageLoading.value = false
  }
}

function toggleCandidate(c: OrphanStorageCandidate): void {
  if (!c.deletable) return
  const key = candidateKey(c)
  const next = new Set(selectedKeys.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  selectedKeys.value = next
}

function openPreview(): void {
  if (selectedCandidates.value.length === 0) return
  previewOpen.value = true
}

/** #17040 AC: cancelling here issues NO request — the operator only closes the dialog. */
function cancelPreview(): void {
  previewOpen.value = false
}

async function confirmPreview(): Promise<void> {
  const targets = selectedCandidates.value
  if (targets.length === 0) return
  proposing.value = true
  const outcomes = await Promise.allSettled(
    targets.map((candidate) =>
      api.createApproval({
        title: `Propose deleting orphaned storage: ${candidate.provider}:${candidate.location}`,
        description:
          `Orphan-storage cleanup candidate at ${candidate.location} (provider: ${candidate.provider}, ` +
          `size: ${formatFileSize(candidate.size_bytes)}). Reason: ${candidate.reason}.`,
        approval_type: 'destructive_action',
        requested_by_agent: 'data_hygiene_console',
        context: {
          action: 'orphan_storage_delete',
          provider: candidate.provider,
          candidate_id: candidate.id,
        },
      }),
    ),
  )

  // #17040 AC: each row's own outcome is recorded and shown -- a failure on
  // one candidate never suppresses, or gets merged into, another's result.
  const results: ProposalResult[] = targets.map((candidate, i) => {
    const outcome = outcomes[i]
    const key = candidateKey(candidate)
    if (outcome.status === 'fulfilled') {
      return { key, candidate, ok: true, message: t('dataHygiene.storage.resultSuccess', { id: outcome.value.id }) }
    }
    return {
      key,
      candidate,
      ok: false,
      message: autobotApiErrorMessage(outcome.reason, t('dataHygiene.storage.proposeErrorFallback')),
    }
  })
  proposalResults.value = results

  proposing.value = false
  previewOpen.value = false
  selectedKeys.value = new Set()
}

// -- Unreachable resources -------------------------------------------------

const RESOURCE_TYPES = ['knowledge_fact', 'secret'] as const
type ResourceType = (typeof RESOURCE_TYPES)[number]

const resourceType = ref<ResourceType>('knowledge_fact')
const orphans = ref<OrphanResource[]>([])
const orphansLoading = ref(false)
const orphansError = ref('')
const users = ref<UserResponse[]>([])
const newOwnerByResource = ref<Record<string, string>>({})
const repairingResource = ref<Record<string, boolean>>({})

interface RepairRowResult {
  ok: boolean
  message: string
}
const repairResults = ref<Record<string, RepairRowResult>>({})

async function fetchUsers(): Promise<void> {
  try {
    users.value = await api.getUsers()
  } catch (err) {
    // Non-fatal: the owner dropdown is simply empty, and repair() below
    // already refuses (missing new_owner_id) rather than silently no-op.
    logger.error('Error fetching users for the owner picker:', err)
  }
}

async function fetchOrphans(): Promise<void> {
  orphansLoading.value = true
  orphansError.value = ''
  // bb's review, #17157: same staleness as fetchOrphanStorage -- a repair result from a
  // previous fetch (or a previous resourceType) must not linger next to a different row.
  repairResults.value = {}
  try {
    const data = await api.getOrphans(resourceType.value)
    orphans.value = data.orphans
  } catch (err) {
    orphansError.value = autobotApiErrorMessage(err, t('dataHygiene.resources.loadErrorFallback'))
    logger.error('Error fetching orphaned resources:', err)
  } finally {
    orphansLoading.value = false
  }
}

function formatConditions(conditions: Record<string, unknown>): string {
  return Object.entries(conditions)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(', ')
}

async function repairResource(resource: OrphanResource): Promise<void> {
  const newOwnerId = newOwnerByResource.value[resource.resource_id]
  if (!newOwnerId) {
    repairResults.value = {
      ...repairResults.value,
      [resource.resource_id]: { ok: false, message: t('dataHygiene.resources.selectOwnerFirst') },
    }
    return
  }
  repairingResource.value = { ...repairingResource.value, [resource.resource_id]: true }
  try {
    const result = await api.repairOrphan({
      resource_type: resourceType.value,
      resource_id: resource.resource_id,
      new_owner_id: newOwnerId,
    })
    repairResults.value = {
      ...repairResults.value,
      [resource.resource_id]: { ok: true, message: t('dataHygiene.resources.repairSuccess', { owner: result.new_owner_id }) },
    }
    // The resource is no longer orphaned -- reflect that immediately.
    await fetchOrphans()
  } catch (err) {
    repairResults.value = {
      ...repairResults.value,
      [resource.resource_id]: {
        ok: false,
        message: autobotApiErrorMessage(err, t('dataHygiene.resources.repairErrorFallback')),
      },
    }
  } finally {
    repairingResource.value = { ...repairingResource.value, [resource.resource_id]: false }
  }
}

// -- Audit trail -------------------------------------------------------

// The only operation-name strings actually emitted by the two actions above
// (grepped from their own `audit_log(...)` call sites -- never guessed):
//   - services/orphan_storage_cleanup_action.py: "orphan_storage.delete"
//   - services/approval_execution.py:            "approval.post_action_failed"
//   - services/orphan_repair.py:                 "resource.repair_orphan"
const AUDIT_OPERATIONS = [
  'orphan_storage.delete',
  'approval.post_action_failed',
  'resource.repair_orphan',
] as const

const AUDIT_LIMIT_PER_OPERATION = 25

/** `AuditLogEntry.timestamp` is Unix-epoch SECONDS, not an ISO string or ms. */
function formatAuditTime(ts: number): string {
  return formatRelativeTime(new Date(ts * 1000).toISOString())
}

const auditEntries = ref<AuditLogEntry[]>([])
const auditLoading = ref(false)
const auditPartialError = ref('')
// bb's review, #17157: each operation caps at AUDIT_LIMIT_PER_OPERATION and the response
// already says whether more exist (has_more) -- surfaced rather than left silently truncated.
const auditHasMore = ref(false)

async function fetchAudit(): Promise<void> {
  auditLoading.value = true
  auditPartialError.value = ''
  auditHasMore.value = false
  const outcomes = await Promise.allSettled(
    AUDIT_OPERATIONS.map((operation) =>
      api.getAuditLogs({ operation, limit: AUDIT_LIMIT_PER_OPERATION }),
    ),
  )

  const entries: AuditLogEntry[] = []
  const failedOperations: string[] = []
  let hasMore = false
  outcomes.forEach((outcome, i) => {
    if (outcome.status === 'fulfilled') {
      entries.push(...outcome.value.entries)
      hasMore = hasMore || outcome.value.has_more
    } else {
      failedOperations.push(AUDIT_OPERATIONS[i])
      logger.error(`Error fetching audit logs for operation ${AUDIT_OPERATIONS[i]}:`, outcome.reason)
    }
  })
  entries.sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0))
  auditEntries.value = entries
  auditHasMore.value = hasMore

  // #17040 AC: a failed query is never swallowed into an empty-looking list --
  // it is named explicitly, distinct from "no matching entries".
  if (failedOperations.length > 0) {
    auditPartialError.value = t('dataHygiene.audit.partialError', { operations: failedOperations.join(', ') })
  }

  auditLoading.value = false
}

onMounted(() => {
  fetchOrphanStorage()
  fetchUsers()
  fetchOrphans()
  fetchAudit()
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto space-y-8">
    <div>
      <h1 class="text-2xl font-bold text-gray-900">{{ $t('dataHygiene.title') }}</h1>
      <p class="text-sm text-gray-500 mt-1">{{ $t('dataHygiene.subtitle') }}</p>
    </div>

    <!-- ============================= Unreferenced storage ============================= -->
    <section class="bg-white rounded-lg shadow p-6" aria-labelledby="data-hygiene-storage-heading">
      <div class="flex items-center justify-between mb-1">
        <h2 id="data-hygiene-storage-heading" class="text-lg font-semibold text-gray-900">
          {{ $t('dataHygiene.storage.title') }}
        </h2>
        <button
          class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-sm"
          :disabled="storageLoading"
          @click="fetchOrphanStorage"
        >
          {{ $t('dataHygiene.refresh') }}
        </button>
      </div>
      <p class="text-sm text-gray-500 mb-4">{{ $t('dataHygiene.storage.subtitle') }}</p>

      <div v-if="storageError" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
        {{ storageError }}
      </div>
      <div
        v-for="status in unavailableProviders"
        :key="status.provider"
        class="mb-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700"
        role="alert"
        data-testid="storage-provider-unavailable"
      >
        {{ $t('dataHygiene.storage.providerUnavailable', { provider: status.provider, error: status.error || 'unknown error' }) }}
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-2 gap-4 mb-4 max-w-md">
        <div class="bg-gray-50 rounded-lg p-4">
          <p class="text-xs uppercase text-gray-500">{{ $t('dataHygiene.storage.totalCandidates') }}</p>
          <p class="text-2xl font-bold text-gray-900" data-testid="storage-total-count">
            {{ orphanStorage?.total_count ?? 0 }}
          </p>
        </div>
        <div class="bg-gray-50 rounded-lg p-4">
          <p class="text-xs uppercase text-gray-500">{{ $t('dataHygiene.storage.totalSize') }}</p>
          <p class="text-2xl font-bold text-gray-900" data-testid="storage-total-size">
            {{ formatFileSize(orphanStorage?.total_size_bytes ?? 0) }}
          </p>
        </div>
      </div>

      <div class="overflow-x-auto border border-gray-200 rounded-lg">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th class="px-3 py-2 text-left"></th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.storage.provider') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.storage.location') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.storage.size') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.storage.age') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.storage.reason') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="storageLoading && candidates.length === 0">
              <td colspan="6" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.storage.loading') }}</td>
            </tr>
            <tr v-else-if="candidates.length === 0">
              <td colspan="6" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.storage.empty') }}</td>
            </tr>
            <tr
              v-for="c in candidates"
              :key="candidateKey(c)"
              class="hover:bg-gray-50"
              data-testid="storage-row"
            >
              <td class="px-3 py-2">
                <input
                  type="checkbox"
                  :checked="selectedKeys.has(candidateKey(c))"
                  :disabled="!c.deletable"
                  :aria-label="`select ${c.provider}:${c.location}`"
                  data-testid="storage-select"
                  @change="toggleCandidate(c)"
                />
              </td>
              <td class="px-3 py-2 text-gray-900">{{ c.provider }}</td>
              <td class="px-3 py-2 font-mono text-xs text-gray-600">{{ c.location }}</td>
              <td class="px-3 py-2">{{ formatFileSize(c.size_bytes) }}</td>
              <td class="px-3 py-2 text-gray-500">{{ formatRelativeTime(c.modified_at) }}</td>
              <td class="px-3 py-2">
                <span>{{ c.reason }}</span>
                <span v-if="!c.deletable" class="ml-2 px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">
                  {{ $t('dataHygiene.storage.notDeletable') }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-4">
        <button
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm"
          :disabled="selectedCandidates.length === 0"
          data-testid="storage-preview-button"
          @click="openPreview"
        >
          {{ $t('dataHygiene.storage.previewButton', { count: selectedCandidates.length }) }}
        </button>
      </div>

      <!-- Per-candidate proposal results (#17040 AC: a failure is shown per-row, never swallowed) -->
      <div v-if="proposalResults.length > 0" class="mt-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-2">{{ $t('dataHygiene.storage.resultsTitle') }}</h3>
        <ul class="space-y-1">
          <li
            v-for="r in proposalResults"
            :key="r.key"
            class="text-sm px-3 py-2 rounded-lg"
            :class="r.ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'"
            :data-testid="r.ok ? 'proposal-result-success' : 'proposal-result-failure'"
            role="status"
          >
            {{ r.candidate.provider }}:{{ r.candidate.location }} — {{ r.message }}
          </li>
        </ul>
      </div>

      <!-- Preview modal -->
      <div v-if="previewOpen" class="fixed inset-0 z-50 flex items-center justify-center" data-testid="storage-preview-modal">
        <div class="absolute inset-0 bg-black/50" @click="cancelPreview"></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-2">{{ $t('dataHygiene.storage.previewTitle') }}</h3>
          <p class="text-sm text-gray-600 mb-4">
            {{ $t('dataHygiene.storage.previewBody', { count: selectedCandidates.length }) }}
          </p>
          <ul class="space-y-2 max-h-64 overflow-y-auto mb-4">
            <li
              v-for="c in selectedCandidates"
              :key="candidateKey(c)"
              class="text-sm p-2 bg-gray-50 rounded-lg"
              data-testid="preview-candidate"
            >
              <span class="font-medium">{{ c.provider }}:{{ c.location }}</span>
              <span class="text-gray-500"> — {{ formatFileSize(c.size_bytes) }}, {{ c.reason }}</span>
            </li>
          </ul>
          <div class="flex justify-end gap-3">
            <button
              class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              data-testid="storage-preview-cancel"
              @click="cancelPreview"
            >
              {{ $t('dataHygiene.storage.previewCancel') }}
            </button>
            <button
              class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              :disabled="proposing"
              data-testid="storage-preview-confirm"
              @click="confirmPreview"
            >
              {{ proposing ? $t('dataHygiene.storage.proposing') : $t('dataHygiene.storage.previewConfirm') }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================= Unreachable resources ============================= -->
    <section class="bg-white rounded-lg shadow p-6" aria-labelledby="data-hygiene-resources-heading">
      <div class="flex items-center justify-between mb-1">
        <h2 id="data-hygiene-resources-heading" class="text-lg font-semibold text-gray-900">
          {{ $t('dataHygiene.resources.title') }}
        </h2>
      </div>
      <p class="text-sm text-gray-500 mb-4">{{ $t('dataHygiene.resources.subtitle') }}</p>

      <div v-if="orphansError" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
        {{ orphansError }}
      </div>

      <div class="flex items-end gap-3 mb-4">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('dataHygiene.resources.resourceType') }}</label>
          <select v-model="resourceType" class="px-3 py-2 border border-gray-300 rounded-lg text-sm" data-testid="resource-type-select">
            <option v-for="rt in RESOURCE_TYPES" :key="rt" :value="rt">
              {{ rt === 'knowledge_fact' ? $t('dataHygiene.resources.knowledgeFact') : $t('dataHygiene.resources.secret') }}
            </option>
          </select>
        </div>
        <button
          class="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-sm"
          :disabled="orphansLoading"
          data-testid="resources-load-button"
          @click="fetchOrphans"
        >
          {{ $t('dataHygiene.resources.load') }}
        </button>
      </div>

      <div class="overflow-x-auto border border-gray-200 rounded-lg">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.resources.resourceId') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.resources.conditions') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.resources.newOwner') }}</th>
              <th class="px-3 py-2 text-left"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="orphansLoading && orphans.length === 0">
              <td colspan="4" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.resources.loading') }}</td>
            </tr>
            <tr v-else-if="orphans.length === 0">
              <td colspan="4" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.resources.empty') }}</td>
            </tr>
            <tr v-for="o in orphans" :key="o.resource_id" data-testid="resource-row">
              <td class="px-3 py-2 font-mono text-xs text-gray-600">{{ o.resource_id }}</td>
              <td class="px-3 py-2 text-gray-600 text-xs">{{ formatConditions(o.conditions) }}</td>
              <td class="px-3 py-2">
                <select
                  v-model="newOwnerByResource[o.resource_id]"
                  class="px-2 py-1 border border-gray-300 rounded-lg text-xs"
                  data-testid="resource-owner-select"
                >
                  <option value="">{{ $t('dataHygiene.resources.selectOwner') }}</option>
                  <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
                </select>
              </td>
              <td class="px-3 py-2">
                <button
                  class="px-3 py-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-xs"
                  :disabled="repairingResource[o.resource_id]"
                  data-testid="resource-repair-button"
                  @click="repairResource(o)"
                >
                  {{ repairingResource[o.resource_id] ? $t('dataHygiene.resources.repairing') : $t('dataHygiene.resources.repair') }}
                </button>
                <div
                  v-if="repairResults[o.resource_id]"
                  class="mt-1 text-xs"
                  :class="repairResults[o.resource_id].ok ? 'text-green-700' : 'text-red-700'"
                  :data-testid="repairResults[o.resource_id].ok ? 'repair-result-success' : 'repair-result-failure'"
                  role="status"
                >
                  {{ repairResults[o.resource_id].message }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ============================= Audit trail ============================= -->
    <section class="bg-white rounded-lg shadow p-6" aria-labelledby="data-hygiene-audit-heading">
      <div class="flex items-center justify-between mb-1">
        <h2 id="data-hygiene-audit-heading" class="text-lg font-semibold text-gray-900">
          {{ $t('dataHygiene.audit.title') }}
        </h2>
        <button
          class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-sm"
          :disabled="auditLoading"
          @click="fetchAudit"
        >
          {{ $t('dataHygiene.refresh') }}
        </button>
      </div>
      <p class="text-sm text-gray-500 mb-4">{{ $t('dataHygiene.audit.subtitle') }}</p>

      <div
        v-if="auditPartialError"
        class="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700"
        role="alert"
        data-testid="audit-partial-error"
      >
        {{ auditPartialError }}
      </div>

      <div class="overflow-x-auto border border-gray-200 rounded-lg">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.audit.timestamp') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.audit.operation') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.audit.result') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.audit.actor') }}</th>
              <th class="px-3 py-2 text-left">{{ $t('dataHygiene.audit.resource') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="auditLoading && auditEntries.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.audit.loading') }}</td>
            </tr>
            <tr v-else-if="auditEntries.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-gray-400">{{ $t('dataHygiene.audit.empty') }}</td>
            </tr>
            <tr v-for="entry in auditEntries" :key="entry.id" data-testid="audit-row">
              <td class="px-3 py-2 text-gray-500">{{ formatAuditTime(entry.timestamp) }}</td>
              <td class="px-3 py-2 font-mono text-xs text-gray-900">{{ entry.operation }}</td>
              <td class="px-3 py-2">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium"
                  :class="entry.result === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
                >
                  {{ entry.result }}
                </span>
              </td>
              <td class="px-3 py-2 text-gray-600">{{ entry.user_id || '—' }}</td>
              <td class="px-3 py-2 font-mono text-xs text-gray-600">{{ entry.resource || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="auditHasMore" class="text-xs text-gray-500 mt-2" data-testid="audit-has-more">
          {{ $t('dataHygiene.audit.moreAvailable') }}
        </p>
      </div>
    </section>
  </div>
</template>
