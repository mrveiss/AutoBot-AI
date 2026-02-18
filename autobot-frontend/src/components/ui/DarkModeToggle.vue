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
    :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    aria-label="Toggle dark mode"
  >
    <transition name="icon-fade" mode="out-in">
      <i v-if="isDark" key="moon" class="fas fa-moon"></i>
      <i v-else key="sun" class="fas fa-sun"></i>
    </transition>
  </button>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleTheme } = useTheme()

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
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
  font-size: 18px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.dark-mode-toggle:hover {
  background-color: rgba(255, 255, 255, 0.2);
  transform: scale(1.05);
}

.dark-mode-toggle:active {
  transform: scale(0.95);
}

.dark-mode-toggle:focus-visible {
  outline: 2px solid white;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.1);
}

/* Icon transition animation */
.icon-fade-enter-active,
.icon-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
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
