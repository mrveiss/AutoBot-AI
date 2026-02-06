<template>
  <div v-if="show" class="advanced-options">
    <h4>⚙️ Advanced Options</h4>

    <!-- Automatic Execution -->
    <div class="option-group">
      <label>
        <input
          type="checkbox"
          :checked="autoExecution"
          @change="$emit('update:autoExecution', ($event.target as HTMLInputElement).checked)"
        />
        🔄 Automatic execution of remaining steps
      </label>
    </div>

    <!-- Timeout Settings -->
    <div class="option-group">
      <label>⏱️ Execution timeout (seconds):</label>
      <input
        type="number"
        :value="timeout"
        @input="$emit('update:timeout', Number(($event.target as HTMLInputElement).value))"
        min="5"
        max="300"
        class="timeout-input"
      />
    </div>

    <!-- Password Protection -->
    <div class="option-group">
      <label>🔐 Password protection for destructive commands:</label>
      <div class="password-options">
        <label>
          <input
            type="radio"
            :checked="passwordProtection === 'none'"
            @change="$emit('update:passwordProtection', 'none')"
          />
          None
        </label>
        <label>
          <input
            type="radio"
            :checked="passwordProtection === 'required'"
            @change="$emit('update:passwordProtection', 'required')"
          />
          Required
        </label>
        <label>
          <input
            type="radio"
            :checked="passwordProtection === 'optional'"
            @change="$emit('update:passwordProtection', 'optional')"
          />
          Optional
        </label>
      </div>

      <div v-if="passwordProtection !== 'none'" class="password-input">
        <input
          type="password"
          :value="password"
          @input="$emit('update:password', ($event.target as HTMLInputElement).value)"
          placeholder="Enter admin password..."
          class="password-field"
        />
        <div class="password-note">Required for executing high-risk commands</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Advanced Options Panel Component
 *
 * Provides advanced workflow execution options.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface Props {
  show: boolean
  autoExecution: boolean
  timeout: number
  passwordProtection: 'none' | 'required' | 'optional'
  password: string
}

interface Emits {
  (e: 'update:autoExecution', value: boolean): void
  (e: 'update:timeout', value: number): void
  (e: 'update:passwordProtection', value: 'none' | 'required' | 'optional'): void
  (e: 'update:password', value: string): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/**
 * Issue #704: Migrated to design tokens
 * All hardcoded colors replaced with CSS custom properties from design-tokens.css
 */
.advanced-options {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.advanced-options h4 {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-primary);
}

.option-group {
  margin-bottom: var(--spacing-4);
}

.option-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  color: var(--text-primary);
}

.timeout-input {
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  color: var(--text-on-primary);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  width: 120px;
}

.password-options {
  display: flex;
  gap: var(--spacing-4);
  margin-top: var(--spacing-2);
}

.password-options label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.password-input {
  margin-top: var(--spacing-4);
}

.password-field {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  color: var(--text-on-primary);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
}

.password-note {
  font-size: var(--text-sm);
  color: var(--chart-orange);
}

@media (max-width: 768px) {
  .password-options {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .timeout-input {
    width: 100%;
    max-width: 200px;
  }
}
</style>
