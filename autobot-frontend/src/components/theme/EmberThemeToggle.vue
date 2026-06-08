<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  EmberThemeToggle.vue - Theme Variant Toggle Component
  Issue #9274 / MVA-3096: Ember Theme Integration

  Simple toggle component to switch between Default and Ember theme variants.
  Designed to be added to Settings or as a standalone control.
-->
<template>
  <div class="ember-theme-toggle">
    <h3 class="text-lg font-semibold mb-2">Theme Variant</h3>
    <div class="flex gap-3">
      <button
        v-for="variant in availableVariants"
        :key="variant"
        @click="setThemeVariant(variant)"
        :class="{
          'bg-autobot-primary text-white': themeVariant === variant,
          'bg-autobot-bg-tertiary text-autobot-text-primary hover:bg-autobot-bg-hover': themeVariant !== variant
        }"
        class="px-4 py-2 rounded-md transition-colors duration-200"
      >
        {{ variantLabels[variant] }}
      </button>
    </div>
    <p class="text-sm text-autobot-text-secondary mt-2">
      {{ variantDescriptions[themeVariant] }}
    </p>

    <!-- Ember icon showcase when Ember is selected -->
    <div v-if="themeVariant === 'ember'" class="mt-4 p-4 rounded-md" style="background: var(--color-accent-subtle); border: 1px solid var(--color-accent-border);">
      <h4 class="text-sm font-medium mb-2" style="color: var(--color-accent-text);">Ember Icon Set</h4>
      <div class="flex gap-3 flex-wrap">
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-chat"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-layers"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-blocks"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-scope"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-code"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-mesh"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-sliders"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-send"/></svg>
        <svg class="ember-icon" style="color: var(--color-accent);"><use href="#i-spark"/></svg>
      </div>
    </div>

    <!-- Ember gradient showcase -->
    <div v-if="themeVariant === 'ember'" class="mt-3 p-4 rounded-md" style="background: var(--gradient-ember);">
      <p class="text-white text-sm font-medium">Ember Gradient Showcase</p>
      <p class="text-white text-xs opacity-90 mt-1">Marigold → Tangerine → Wine</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useThemeVariant } from '@/composables/useThemeVariant'

const {
  themeVariant,
  setThemeVariant,
  availableVariants,
  variantLabels,
  variantDescriptions,
} = useThemeVariant()
</script>

<style scoped>
.ember-theme-toggle {
  padding: 1rem;
}
</style>
