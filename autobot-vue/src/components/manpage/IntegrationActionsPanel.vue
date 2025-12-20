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
.integration-actions {
  background: #f8f9fa;
  border-radius: 10px;
  padding: 25px;
  margin-bottom: 30px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.section-header h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-size: 1.2rem;
}

.section-header h3 i {
  margin-right: 10px;
  color: #3498db;
}

.action-buttons {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

.action-info {
  color: #7f8c8d;
}

.action-info .info-item {
  margin-bottom: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #ecf0f1;
  display: block;
}

.action-info .info-item:last-child {
  border-bottom: none;
}

.action-info .info-item strong {
  color: #2c3e50;
}

@media (max-width: 768px) {
  .action-buttons {
    flex-direction: column;
  }
}
</style>
