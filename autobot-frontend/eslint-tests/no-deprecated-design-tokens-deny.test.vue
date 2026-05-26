<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ESLint test fixture for the MVA-192 deprecated design-token rules:
    vue/no-restricted-static-attribute — catches size="small|medium|large" and variant="danger"
    vue/no-restricted-syntax            — catches :size="'small'|..." bound string literals

  Every attr tagged // EXPECT-ERROR SHOULD trigger the rule when scanned directly.
  This file is excluded from the production lint step (see eslint.config.ts ignore list).

  To verify locally:
    cd autobot-frontend
    npx eslint --no-ignore eslint-tests/no-deprecated-design-tokens-deny.test.vue
    # Expected: 8 errors (one per // EXPECT-ERROR line)
-->

<!-- eslint-disable vue/no-undef-components -->
<template>
  <!-- EXPECT-ERROR: static size="small" -->
  <BaseButton size="small" />

  <!-- EXPECT-ERROR: static size="medium" -->
  <BaseButton size="medium" />

  <!-- EXPECT-ERROR: static size="large" -->
  <BaseButton size="large" />

  <!-- EXPECT-ERROR: static variant="danger" -->
  <BaseButton variant="danger" />

  <!-- EXPECT-ERROR: bound :size="'small'" (string literal in expression) -->
  <BaseButton :size="'small'" />

  <!-- EXPECT-ERROR: bound :size="'medium'" -->
  <BaseButton :size="'medium'" />

  <!-- EXPECT-ERROR: bound :size="'large'" -->
  <BaseButton :size="'large'" />

  <!-- EXPECT-ERROR: bound :variant="'danger'" -->
  <BaseButton :variant="'danger'" />
</template>
