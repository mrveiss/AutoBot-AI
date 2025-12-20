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
.risk-section {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.risk-indicator {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.risk-indicator.low {
  background: rgba(34, 197, 94, 0.1);
  border-left-color: #22c55e;
}

.risk-indicator.moderate {
  background: rgba(251, 191, 36, 0.1);
  border-left-color: #fbbf24;
}

.risk-indicator.high {
  background: rgba(239, 68, 68, 0.1);
  border-left-color: #ef4444;
}

.risk-indicator.critical {
  background: rgba(220, 38, 38, 0.1);
  border-left-color: #dc2626;
  animation: pulse 2s infinite;
}

.risk-label {
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
  color: #f3f4f6;
}

.risk-reasons {
  margin-top: 8px;
}

.risk-reason {
  font-size: 0.9em;
  color: #d1d5db;
  margin-bottom: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}
</style>
