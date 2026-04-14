<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

DarkModeToggle.vue - Theme Toggle Component
Issue #753: Dark/Light Mode Refinement
-->

<template>
  <button
    @click="toggleDarkMode"
    class="dark-mode-toggle"
    :title="isDark ? t('ui.darkModeToggle.switchToLight') : t('ui.darkModeToggle.switchToDark')"
    :aria-label="t('ui.darkModeToggle.toggleDarkMode')"
  >
    <transition name="icon-fade" mode="out-in">
      <i v-if="isDark" key="moon" class="fas fa-moon"></i>
      <i v-else key="sun" class="fas fa-sun"></i>
    </transition>
  </button>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'

const { isDark, toggleTheme } = useTheme()
const { t } = useI18n()

function toggleDarkMode() {
  toggleTheme()
}
</script>

<style scoped>
.dark-mode-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background-color: var(--bg-hover);
  color: var(--text-primary);
  font-size: var(--text-lg);
  transition: all var(--duration-200) var(--ease-out);
  cursor: pointer;
}

.dark-mode-toggle:hover {
  background-color: var(--bg-active);
  transform: scale(1.05);
}

.dark-mode-toggle:active {
  transform: scale(0.95);
}

.dark-mode-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  box-shadow: 0 0 0 4px var(--color-primary-bg);
}

/* Icon transition animation */
.icon-fade-enter-active,
.icon-fade-leave-active {
  transition: opacity var(--duration-150) var(--ease-out), transform var(--duration-150) var(--ease-out);
}

.icon-fade-enter-from {
  opacity: 0;
  transform: rotate(-90deg) scale(0.8);
}

.icon-fade-leave-to {
  opacity: 0;
  transform: rotate(90deg) scale(0.8);
}

/* Rotate animation on hover */
.dark-mode-toggle:hover i {
  animation: rotate-subtle 0.5s ease;
}

@keyframes rotate-subtle {
  0%, 100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(10deg);
  }
}
</style>
