<template>
  <div class="stats-actions">
    <button @click="$emit('export')" class="action-btn">
      <Icon name="download" />
      {{ $t('knowledge.stats.exportStats') }}
    </button>
    <button @click="$emit('generate-report')" class="action-btn primary">
      <Icon name="file-chart-line" />
      {{ $t('knowledge.stats.generateReport') }}
    </button>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Stats Actions Panel Component
 *
 * Action buttons for exporting stats and generating reports.
 * Wired into KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
 */
import Icon from '@/components/ui/Icon.vue'

interface Emits {
  (e: 'export'): void
  (e: 'generate-report'): void
}

defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.stats-actions {
  display: flex;
  justify-content: center;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
  border: 1px solid var(--border-default);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: var(--transition-all);
}

.action-btn:hover {
  background: var(--bg-secondary);
}

.action-btn.primary {
  background: var(--color-info);
  color: var(--text-on-primary);
  border-color: var(--color-info);
}

.action-btn.primary:hover {
  background: var(--color-info-hover);
  border-color: var(--color-info-hover);
}

@media (max-width: 768px) {
  .stats-actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
