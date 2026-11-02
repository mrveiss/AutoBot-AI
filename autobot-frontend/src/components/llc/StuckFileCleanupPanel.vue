<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <section v-if="status && status.stuck_cleanup_files > 0" class="stuck-cleanup">
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
</template>

<script setup lang="ts">
import { BaseButton, formatBytes } from '@autobot/ui'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'

interface StuckFile { file_id: string; file_size: number; failed_attempts: number; last_reason: string }
interface CleanupStatus { stuck_cleanup_files: number; stuck_cleanup_bytes: number; stuck_cleanup: StuckFile[] }

const logger = createLogger('StuckFileCleanupPanel')
const api = useApiClient()
const { t } = useI18n()
const { showToast } = useNotificationBus()
const status = ref<CleanupStatus | null>(null)
const resetting = ref(new Set<string>())

async function load() {
  try {
    status.value = await api.get<CleanupStatus>('/api/conversation-files/cleanup/status')
  } catch (err) {
    // 401/403 for a non-admin: the panel simply stays hidden.
    logger.debug('Stuck file cleanup status unavailable', err)
  }
}

async function reset(fileId: string) {
  resetting.value = new Set(resetting.value).add(fileId)
  try {
    await api.post<unknown>(`/api/conversation-files/cleanup/${fileId}/reset`, {})
    showToast(t('llc.approvals.stuckCleanup.resetDone'), 'success')
    await load()
  } catch (err) {
    logger.error('Reset failed', err)
    showToast(t('llc.approvals.stuckCleanup.resetError'), 'error')
  } finally {
    const next = new Set(resetting.value)
    next.delete(fileId)
    resetting.value = next
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
