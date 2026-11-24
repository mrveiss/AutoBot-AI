<template>
  <section class="flex flex-col gap-3" data-testid="audit-command-history">
    <div class="flex items-end gap-3">
      <BaseInput
        v-model="user"
        :label="$t('audit.commandHistory.userFilter')"
        :placeholder="$t('audit.commandHistory.userPlaceholder')"
        size="sm"
        @keyup.enter="load"
      />
      <BaseButton size="sm" :disabled="loading" @click="load">
        {{ $t('audit.commandHistory.refresh') }}
      </BaseButton>
    </div>

    <BaseAlert v-if="failed" variant="error" :message="$t('audit.commandHistory.error')">
      <template #actions>
        <BaseButton size="sm" @click="load">{{ $t('audit.commandHistory.retry') }}</BaseButton>
      </template>
    </BaseAlert>

    <BaseTable
      v-else
      :columns="columns"
      :rows="rows"
      row-key="key"
      :caption="$t('audit.commandHistory.caption')"
      :loading="loading"
      :loading-label="$t('audit.commandHistory.loading')"
      :empty-title="$t('audit.commandHistory.empty')"
      :empty-description="$t('audit.commandHistory.emptyHint')"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseInput, BaseTable } from '@autobot/ui'
import { useAuditApi, type CommandHistoryEntry, type CommandHistoryQuery } from '@/composables/useAuditApi'
import { createLogger } from '@/utils/debugUtils'

const HISTORY_LIMIT = 50

const { t } = useI18n()
const logger = createLogger('AuditCommandHistoryPanel')
const { getCommandHistory } = useAuditApi()

const user = ref('')
const loading = ref(false)
const failed = ref(false)
const entries = ref<CommandHistoryEntry[]>([])

const columns = computed(() => [
  { key: 'timestamp', label: t('audit.commandHistory.time') },
  { key: 'user', label: t('audit.commandHistory.user') },
  { key: 'action', label: t('audit.commandHistory.action') },
  { key: 'outcome', label: t('audit.commandHistory.outcome') },
])
const rows = computed(() => entries.value.map((e, i) => ({ ...e, key: `${e.timestamp}-${i}` })))

async function load() {
  loading.value = true
  failed.value = false
  const query: CommandHistoryQuery = { user: user.value.trim() || undefined, limit: HISTORY_LIMIT }
  const result = await getCommandHistory(query)
  loading.value = false
  if (!result) {
    failed.value = true
    logger.warn('Command history unavailable')
    return
  }
  entries.value = result
}

onMounted(load)
</script>
