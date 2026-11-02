<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div v-if="isAdmin">
    <section v-if="pending.length > 0" class="stuck-cleanup" data-testid="removal-proposals">
      <p class="stuck-title">{{ $t('llc.approvals.removals.title', { count: pending.length }) }}</p>
      <p class="stuck-hint">{{ $t('llc.approvals.removals.hint') }}</p>
      <ul class="stuck-list">
        <li v-for="item in pending" :key="item.id">
          <span class="stuck-file">{{ item.title }}</span>
          <span class="stuck-reason">{{ item.description }}</span>
          <BaseButton size="sm" :disabled="deciding.has(item.id)" @click="decide(item.id, 'approve')">
            {{ $t('llc.approvals.removals.approve') }}
          </BaseButton>
          <BaseButton size="sm" :disabled="deciding.has(item.id)" @click="decide(item.id, 'reject')">
            {{ $t('llc.approvals.removals.reject') }}
          </BaseButton>
        </li>
      </ul>
    </section>
    <section v-if="status && status.stuck_cleanup_files > 0" class="stuck-cleanup" data-testid="stuck-files">
      <p class="stuck-title">
        {{ $t('llc.approvals.stuckCleanup.title', { count: status.stuck_cleanup_files, size: formatBytes(status.stuck_cleanup_bytes) }) }}
      </p>
      <p class="stuck-hint">{{ $t('llc.approvals.stuckCleanup.hint') }}</p>
      <ul class="stuck-list">
        <li v-for="file in status.stuck_cleanup" :key="file.file_id">
          <span class="stuck-file">{{ file.file_id }}</span>
          <span class="stuck-reason">{{ file.last_reason }} ({{ file.failed_attempts }})</span>
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
import { BaseButton, formatBytes } from '@autobot/ui'
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
const status = ref<CleanupStatus | null>(null)
const pending = ref<Proposal[]>([])
const resetting = ref(new Set<string>())
const deciding = ref(new Set<string>())

async function load() {
  try {
    status.value = await api.get<CleanupStatus>('/api/conversation-files/cleanup/status')
    isAdmin.value = true
  } catch (err) {
    // 401/403 for a non-admin: the panel stays hidden and asks for nothing more.
    logger.debug('Cleanup status unavailable', err)
    return
  }
  try {
    const rows = await api.get<Proposal[]>('/api/approval-gates/pending')
    pending.value = rows.filter((row) => row.approval_type === 'destructive_action')
  } catch (err) {
    logger.error('Failed to load pending removal proposals', err)
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
    await api.post<unknown>(`/api/approval-gates/${id}/${verb}`, {})
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
    await api.post<unknown>(`/api/conversation-files/cleanup/${fileId}/reset`, {})
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

<style scoped>
.stuck-cleanup { padding: var(--spacing-3, 12px); border: 1px solid var(--border-default); border-radius: var(--radius-md, 6px); margin-bottom: var(--spacing-3, 12px); }
.stuck-title { font-weight: 600; margin: 0; }
.stuck-hint { color: var(--text-secondary); margin: 4px 0 8px; }
.stuck-list { list-style: none; padding: 0; margin: 0; }
.stuck-list li { display: flex; gap: var(--spacing-3, 12px); align-items: center; padding: 4px 0; }
.stuck-file { font-family: var(--font-mono, monospace); }
.stuck-reason { color: var(--text-secondary); flex: 1; }
</style>
