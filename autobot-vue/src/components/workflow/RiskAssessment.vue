<template>
  <div class="risk-section">
    <div class="risk-indicator" :class="level">
      <span class="risk-label">Risk Level: {{ level.toUpperCase() }}</span>
      <div class="risk-reasons">
        <div v-for="reason in reasons" :key="reason" class="risk-reason">
          • {{ reason }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Risk Assessment Component
 *
 * Displays risk level and reasons for a command.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface Props {
  level: 'low' | 'moderate' | 'high' | 'critical'
  reasons: string[]
}

defineProps<Props>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.risk-section {
  padding: 20px;
  border-bottom: 1px solid var(--border-primary);
}

.risk-indicator {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.risk-indicator.low {
  background: var(--color-success-alpha-10);
  border-left-color: var(--color-success);
}

.risk-indicator.moderate {
  background: var(--color-warning-alpha-10);
  border-left-color: var(--color-warning);
}

.risk-indicator.high {
  background: var(--color-error-alpha-10);
  border-left-color: var(--color-error);
}

.risk-indicator.critical {
  background: var(--color-danger-alpha-10);
  border-left-color: var(--color-danger);
  animation: pulse 2s infinite;
}

.risk-label {
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.risk-reasons {
  margin-top: 8px;
}

.risk-reason {
  font-size: 0.9em;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}
</style>
