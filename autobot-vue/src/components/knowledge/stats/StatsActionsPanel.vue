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
.stats-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
}

.action-btn.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.action-btn.primary:hover {
  background: #2563eb;
  border-color: #2563eb;
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
