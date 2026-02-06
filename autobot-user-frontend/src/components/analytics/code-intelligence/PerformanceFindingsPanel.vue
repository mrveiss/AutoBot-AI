<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <div class="performance-panel">
    <div class="panel-header">
      <h3><i class="fas fa-tachometer-alt"></i> Performance Issues</h3>
      <span v-if="findings.length > 0" class="count-badge">{{ findings.length }}</span>
    </div>
    <FindingsTable
      :findings="findings"
      :loading="loading"
      empty-message="No performance issues found"
    />
  </div>
</template>

<script setup lang="ts">
import FindingsTable from './FindingsTable.vue'
import type { PerformanceFinding } from '@/types/codeIntelligence'

defineProps<{
  findings: PerformanceFinding[]
  loading: boolean
}>()
</script>

<style scoped>
.performance-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.panel-header i {
  color: var(--chart-yellow, #f59e0b);
}

.count-badge {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
