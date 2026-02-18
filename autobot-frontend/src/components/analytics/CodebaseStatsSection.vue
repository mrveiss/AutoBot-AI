<template>
  <div class="stats-section">
    <h3><i class="fas fa-chart-pie"></i> Codebase Statistics</h3>
    <div v-if="stats" class="stats-grid">
      <BasePanel variant="elevated" size="small">
        <div class="stat-value">{{ stats.total_files || 0 }}</div>
        <div class="stat-label">Total Files</div>
      </BasePanel>
      <BasePanel variant="elevated" size="small">
        <div class="stat-value">{{ stats.total_lines || 0 }}</div>
        <div class="stat-label">Lines of Code</div>
      </BasePanel>
      <BasePanel variant="elevated" size="small">
        <div class="stat-value">{{ stats.total_functions || 0 }}</div>
        <div class="stat-label">Functions</div>
      </BasePanel>
      <BasePanel variant="elevated" size="small">
        <div class="stat-value">{{ stats.total_classes || 0 }}</div>
        <div class="stat-label">Classes</div>
      </BasePanel>
    </div>
    <EmptyState
      v-else
      icon="fas fa-chart-bar"
      message="No codebase statistics available. Run analysis to generate data."
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Codebase Stats Section Component
 *
 * Displays codebase statistics cards.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface CodebaseStats {
  total_files: number
  total_lines: number
  total_functions: number
  total_classes: number
}

interface Props {
  stats: CodebaseStats | null
}

defineProps<Props>()
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.stats-section {
  margin-bottom: var(--spacing-6);
}

.stats-section h3 {
  color: var(--color-info);
  margin-bottom: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--color-info);
  text-align: center;
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-align: center;
  margin-top: var(--spacing-1);
}
</style>
