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
.advanced-options {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.advanced-options h4 {
  margin: 0 0 16px 0;
  color: #f3f4f6;
}

.option-group {
  margin-bottom: 16px;
}

.option-group label {
  display: block;
  margin-bottom: 8px;
  color: #f3f4f6;
}

.timeout-input {
  background: #111827;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 8px 12px;
  border-radius: 6px;
  width: 120px;
}

.password-options {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.password-options label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.password-input {
  margin-top: 16px;
}

.password-field {
  width: 100%;
  background: #111827;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.password-note {
  font-size: 0.85em;
  color: #f97316;
}

@media (max-width: 768px) {
  .password-options {
    flex-direction: column;
    gap: 8px;
  }

  .timeout-input {
    width: 100%;
    max-width: 200px;
  }
}
</style>
