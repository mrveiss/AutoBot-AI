<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SkipLink - Accessible skip navigation link.
 *
 * Provides a visually hidden link that becomes visible on focus,
 * allowing keyboard users to skip past navigation to main content.
 *
 * Issue #754: Accessibility audit and improvements.
 */

withDefaults(defineProps<{
  /** CSS selector or id of the target element to skip to. */
  target?: string
  /** Link text shown when focused. */
  label?: string
}>(), {
  target: '#main-content',
  label: 'Skip to main content',
})

function handleClick(event: MouseEvent, target: string): void {
  event.preventDefault()
  const el = document.querySelector(target)
  if (el instanceof HTMLElement) {
    el.setAttribute('tabindex', '-1')
    el.focus()
    el.removeAttribute('tabindex')
  }
}
</script>

<template>
  <a
    :href="target"
    class="skip-link"
    @click="handleClick($event, target)"
  >
    {{ label }}
  </a>
</template>

<style scoped>
.skip-link {
  position: absolute;
  top: -100%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  padding: 0.75rem 1.5rem;
  background: var(--a11y-bg, #0284c7);
  color: var(--a11y-text, #ffffff);
  font-weight: 600;
  font-size: 0.875rem;
  border-radius: 0 0 0.5rem 0.5rem;
  text-decoration: none;
  transition: top 0.15s ease-in-out;
}

.skip-link:focus {
  top: 0;
  outline: 2px solid var(--a11y-focus-ring, #38bdf8);
  outline-offset: 2px;
}
</style>
