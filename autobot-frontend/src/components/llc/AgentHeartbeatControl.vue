<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #15907: an agent's heartbeat state, with the switch that turns it on or off.

  The heartbeat is the optional periodic schedule; nothing else about how an
  agent wakes is decided here. Writes PUT
  /api/llc/companies/{companyId}/controls/agents/{agentId}/heartbeat, which sets
  `heartbeat_enabled`, the column the scheduler reads. The switch shows the
  server's answer: a refused or failed write puts it back and says why.
-->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseSwitch } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const props = defineProps<{ companyId: string; agentId: string; enabled: boolean }>()
const emit = defineEmits<{ changed: [enabled: boolean] }>()

const { t } = useI18n()
const api = useApiClient()
const logger = createLogger('AgentHeartbeatControl')

const on = ref(props.enabled)
const saving = ref(false)
const error = ref('')

watch(() => props.enabled, (value) => { on.value = value })

async function onChange(next: boolean): Promise<void> {
  saving.value = true
  error.value = ''
  const url = `/api/llc/companies/${props.companyId}/controls/agents/${encodeURIComponent(props.agentId)}/heartbeat`
  try {
    await api.put(url, { heartbeat_enabled: next })
    emit('changed', next)
  } catch (err: unknown) {
    on.value = !next
    error.value = t('llc.orgChart.heartbeat.saveFailed', { detail: err instanceof Error ? err.message : String(err) })
    logger.error('Heartbeat toggle failed', err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex items-center justify-between gap-3" data-testid="agent-heartbeat-control">
    <div>
      <p class="text-sm font-medium text-autobot-text-primary">{{ t('llc.orgChart.heartbeat.label') }}</p>
      <p class="text-xs text-autobot-text-muted" data-testid="agent-heartbeat-state">
        {{ on ? t('llc.orgChart.heartbeat.on') : t('llc.orgChart.heartbeat.off') }}
      </p>
      <p v-if="error" class="text-xs text-autobot-error" role="alert">{{ error }}</p>
    </div>
    <BaseSwitch
      v-model="on"
      :label="t('llc.orgChart.heartbeat.label')"
      :disabled="saving"
      size="sm"
      @change="onChange"
    />
  </div>
</template>
