<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ESLint test fixture for the MVA-192 deprecated design-token rules.
  Every usage below MUST NOT trigger a rule violation.

  To verify locally:
    cd autobot-frontend
    npx eslint --no-ignore eslint-tests/no-deprecated-design-tokens-allow.test.vue
    # Expected: 0 errors
-->

<!-- eslint-disable vue/no-undef-components -->
<template>
  <!-- Canonical size tokens — all OK -->
  <BaseButton size="sm" />
  <BaseButton size="md" />
  <BaseButton size="lg" />
  <BaseButton size="xs" />
  <BaseButton size="xl" />

  <!-- Canonical intent/variant tokens — all OK -->
  <BaseButton variant="error" />
  <BaseButton variant="warning" />
  <BaseButton variant="success" />
  <BaseButton variant="info" />

  <!-- Bound canonical tokens — OK -->
  <BaseButton :size="'sm'" />
  <BaseButton :size="'md'" />
  <BaseButton :variant="'error'" />

  <!-- Dynamic prop from variable — rule can't know the value, so not flagged -->
  <BaseButton :size="sizeVar" />
  <BaseButton :variant="computedVariant" />

  <!-- The word "small" in non-prop contexts (interpolation, JS, class) is OK -->
  <span>{{ 'small text here' }}</span>
  <div class="small-header">content</div>
</template>

<script setup lang="ts">
const sizeVar = 'sm'
const computedVariant = 'error'
</script>
