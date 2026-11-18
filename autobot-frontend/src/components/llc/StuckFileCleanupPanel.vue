<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div v-if="isAdmin || loadFailed">
    <BaseAlert v-if="loadFailed" variant="error" class="mb-3" data-testid="load-error" :message="$t('llc.approvals.stuckCleanup.loadError')">
      <template #actions>
        <BaseButton size="sm" @click="load">{{ $t('common.retry') }}</BaseButton>
      </template>
    </BaseAlert>
    <section v-if="pending.length > 0" class="p-3 mb-3 border rounded-md" data-testid="removal-proposals">
      <p class="font-semibold">{{ $t('llc.approvals.removals.title', { count: pending.length }) }}</p>
      <p class="text-sm text-secondary mb-2">{{ $t('llc.approvals.removals.hint') }}</p>
      <ul>
        <li v-for="item in pending" :key="item.id" class="flex items-center gap-3 py-1">
          <span class="font-mono">{{ item.title }}</span>
          <span class="flex-1 text-secondary">{{ item.description }}</span>
          <BaseButton size="sm" :disabled="deciding.has(item.id)" @click="decide(item.id, 'approve')">
            {{ $t('llc.approvals.removals.approve') }}
          </BaseButton>
          <BaseButton size="sm" :disabled="deciding.has(item.id)" @click="decide(item.id, 'reject')">
            {{ $t('llc.approvals.removals.reject') }}
          </BaseButton>
        </li>
      </ul>
    </section>
    <section v-if="status && status.stuck_cleanup_files > 0" class="p-3 mb-3 border rounded-md" data-testid="stuck-files">
      <p class="font-semibold">
        {{ $t('llc.approvals.stuckCleanup.title', { count: status.stuck_cleanup_files, size: formatBytes(status.stuck_cleanup_bytes) }) }}
      </p>
      <p class="text-sm text-secondary mb-2">{{ $t('llc.approvals.stuckCleanup.hint') }}</p>
      <ul>
        <li v-for="file in status.stuck_cleanup" :key="file.file_id" class="flex items-center gap-3 py-1">
          <span class="font-mono">{{ file.file_id }}</span>
          <span class="flex-1 text-secondary">{{ file.last_reason }} ({{ file.failed_attempts }})</span>
          <BaseButton size="sm" :disabled="resetting.has(file.file_id)" @click="reset(file.file_id)">
            {{ $t('llc.approvals.stuckCleanup.reset') }}
          </BaseButton>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * Admin-only. Deleted conversation files wait for a person: the pending destructive-action proposals
 * (non-company approvals, `GET /api/approval-gates/pending`) are approved or rejected here through the
 * existing approval-gate routes, and a file stuck after repeated refusals can be proposed again (#20234).
 */
import { BaseAlert, BaseButton, formatBytes, isHttpError } from '@autobot/ui'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'

interface StuckFile { file_id: string; file_size: number; failed_attempts: number; last_reason: string }
interface CleanupStatus { stuck_cleanup_files: number; stuck_cleanup_bytes: number; stuck_cleanup: StuckFile[] }
interface Proposal { id: string; title: string; description?: string; approval_type: string }

const logger = createLogger('StuckFileCleanupPanel')
const api = useApiClient()
const { t } = useI18n()
const { showToast } = useNotificationBus()
const isAdmin = ref(false)
const loadFailed = ref(false)
const status = ref<CleanupStatus | null>(null)
const pending = ref<Proposal[]>([])
const resetting = ref(new Set<string>())
const deciding = ref(new Set<string>())

/** 401/403 mean the caller is not an admin: the panel hides. Any other failure is shown with a Retry. */
function isNotAdmin(err: unknown): boolean {
  return isHttpError(err) && (err.status === 401 || err.status === 403)
}

async function load() {
  loadFailed.value = false
  try {
    const current: CleanupStatus = await api.get('/api/conversation-files/cleanup/status')
    status.value = current
    isAdmin.value = true
  } catch (err) {
    if (isNotAdmin(err)) {
      logger.debug('Cleanup status refused, panel hidden', err)
      isAdmin.value = false
      return
    }
    logger.error('Cleanup status failed to load', err)
    loadFailed.value = true
    return
  }
  try {
    const rows: Proposal[] = await api.get('/api/approval-gates/pending')
    pending.value = rows.filter((row) => row.approval_type === 'destructive_action')
  } catch (err) {
    if (isNotAdmin(err)) {
      isAdmin.value = false
      return
    }
    logger.error('Failed to load pending removal proposals', err)
    loadFailed.value = true
  }
}

function track(set: typeof resetting, id: string, on: boolean) {
  const next = new Set(set.value)
  if (on) next.add(id)
  else next.delete(id)
  set.value = next
}

async function decide(id: string, verb: 'approve' | 'reject') {
  track(deciding, id, true)
  try {
    await api.post(`/api/approval-gates/${id}/${verb}`, {})
    await load()
  } catch (err) {
    logger.error('Decision failed', err)
    showToast(t('llc.approvals.removals.decideError'), 'error')
  } finally {
    track(deciding, id, false)
  }
}

async function reset(fileId: string) {
  track(resetting, fileId, true)
  try {
    await api.post(`/api/conversation-files/cleanup/${fileId}/reset`, {})
    showToast(t('llc.approvals.stuckCleanup.resetDone'), 'success')
    await load()
  } catch (err) {
    logger.error('Reset failed', err)
    showToast(t('llc.approvals.stuckCleanup.resetError'), 'error')
  } finally {
    track(resetting, fileId, false)
  }
}

onMounted(load)
</script>
