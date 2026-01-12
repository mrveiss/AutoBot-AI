<template>
  <div class="integration-actions">
    <div class="section-header">
      <h3><i class="fas fa-cogs"></i> Integration Actions</h3>
    </div>

    <div class="action-buttons">
      <BaseButton
        variant="primary"
        @click="$emit('initialize')"
        :disabled="loading.initialize || !canInitialize"
        :loading="loading.initialize"
      >
        <i class="fas fa-rocket"></i>
        Initialize Machine Knowledge
      </BaseButton>

      <BaseButton
        variant="success"
        @click="$emit('integrate')"
        :disabled="loading.integrate || !canIntegrate"
        :loading="loading.integrate"
      >
        <i class="fas fa-book-open"></i>
        Integrate Man Pages
      </BaseButton>

      <BaseButton
        variant="info"
        @click="$emit('test-search')"
        :disabled="loading.search || !hasIntegration"
        :loading="loading.search"
      >
        <i class="fas fa-search"></i>
        Test Search
      </BaseButton>
    </div>

    <slot name="progress"></slot>

    <div class="action-info">
      <div class="info-item">
        <strong>Initialize Machine Knowledge:</strong>
        Detects your machine and creates machine-specific knowledge including man page integration.
      </div>
      <div class="info-item">
        <strong>Integrate Man Pages:</strong>
        Extracts manual pages for available Linux commands (Linux only).
      </div>
      <div class="info-item">
        <strong>Test Search:</strong>
        Tests searching through integrated man page knowledge.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Integration Actions Panel Component
 *
 * Provides action buttons for man page integration operations.
 * Extracted from ManPageManager.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseButton from '@/components/base/BaseButton.vue'

interface LoadingState {
  initialize: boolean
  integrate: boolean
  search: boolean
}

interface Props {
  loading: LoadingState
  canInitialize: boolean
  canIntegrate: boolean
  hasIntegration: boolean
}

interface Emits {
  (e: 'initialize'): void
  (e: 'integrate'): void
  (e: 'test-search'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.integration-actions {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-8);
  box-shadow: var(--shadow-md);
}

.section-header h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-size: var(--text-lg);
}

.section-header h3 i {
  margin-right: var(--spacing-2-5);
  color: var(--color-info);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  flex-wrap: wrap;
}

.action-info {
  color: var(--text-tertiary);
}

.action-info .info-item {
  margin-bottom: var(--spacing-2-5);
  padding: var(--spacing-2-5) 0;
  border-bottom: 1px solid var(--border-light);
  display: block;
}

.action-info .info-item:last-child {
  border-bottom: none;
}

.action-info .info-item strong {
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .action-buttons {
    flex-direction: column;
  }
}
</style>
