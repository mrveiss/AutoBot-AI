<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  AgentRecentTasks.vue - one agent's recent tasks (#21270)
  null = the task history was not reported; [] = measured, nothing ran.
-->
<template>
  <p v-if="tasks == null" class="task-empty not-reported">{{ t('visualizations.agentActivity.notReported') }}</p>
  <p v-else-if="tasks.length === 0" class="task-empty">{{ t('visualizations.agentActivity.noRecentTasks') }}</p>
  <ul v-else class="task-list">
    <li v-for="task in tasks" :key="task.id" :class="task.status">
      <span class="task-name">{{ task.name }}</span>
      <span class="task-time">{{ formatTimeAgo(task.completedAt) }}</span>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ActivityAgent } from '@/composables/visualizations/useAgentActivityData'
import { agentActivityFormat } from '@/composables/visualizations/agentActivityFormat'

defineProps<{ tasks: ActivityAgent['recentTasks'] }>()

const { t, locale } = useI18n()
const { formatTimeAgo } = agentActivityFormat(t, () => locale.value)
</script>

<style scoped>
.task-list {
  list-style: none;
  padding: var(--spacing-0);
  margin: 0 0 var(--spacing-3) 0;
}

.task-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-1-5) var(--spacing-2);
  background: rgba(51, 65, 85, 0.3);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-1);
  font-size: var(--text-xs);
}

.task-list li.completed {
  border-left: 2px solid var(--color-success);
}

.task-list li.failed {
  border-left: 2px solid var(--color-error);
}

.task-name {
  color: var(--text-primary);
}

.task-time {
  color: var(--text-tertiary);
}

.task-empty {
  margin: 0 0 var(--spacing-3) 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}
</style>
