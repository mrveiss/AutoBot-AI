<template>
  <div class="stats-actions">
    <button @click="$emit('export')" class="action-btn">
      <i class="fas fa-download"></i>
      Export Statistics
    </button>
    <button @click="$emit('optimize')" class="action-btn">
      <i class="fas fa-compress"></i>
      Optimize Database
    </button>
    <button @click="$emit('generate-report')" class="action-btn primary">
      <i class="fas fa-file-chart-line"></i>
      Generate Report
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
 * Action buttons for exporting, optimizing, and reporting.
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface Emits {
  (e: 'export'): void
  (e: 'optimize'): void
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
  transition: all var(--duration-200) var(--ease-in-out);
}

.action-btn:hover {
  background: var(--bg-secondary);
}

.action-btn.primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.action-btn.primary:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
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
