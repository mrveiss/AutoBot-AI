<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ThemeToggle.vue - Theme Switching Component
  Issue #704: CSS Design System - Centralized Theming & SSOT Styles

  Provides a UI control for switching between dark/light/system themes.
  Uses the useTheme composable for reactive theme management.
-->
<template>
  <div class="theme-toggle" :class="{ 'theme-toggle--compact': compact }">
    <label v-if="showLabel" class="theme-toggle__label">
      <i class="fas fa-palette"></i>
      <span>Theme</span>
    </label>

    <!-- Dropdown mode (default) -->
    <div v-if="mode === 'dropdown'" class="theme-toggle__dropdown">
      <select
        v-model="selectedTheme"
        class="theme-toggle__select"
        :aria-label="'Select theme'"
        @change="handleThemeChange"
      >
        <option
          v-for="themeOption in availableThemes"
          :key="themeOption"
          :value="themeOption"
        >
          {{ themeLabels[themeOption] }}
        </option>
      </select>
      <i class="fas fa-chevron-down theme-toggle__dropdown-icon"></i>
    </div>

    <!-- Button group mode -->
    <div v-else-if="mode === 'buttons'" class="theme-toggle__buttons">
      <button
        v-for="themeOption in availableThemes"
        :key="themeOption"
        :class="[
          'theme-toggle__btn',
          { 'theme-toggle__btn--active': selectedTheme === themeOption }
        ]"
        :aria-pressed="selectedTheme === themeOption"
        :title="themeLabels[themeOption]"
        @click="setTheme(themeOption)"
      >
        <i :class="getThemeIcon(themeOption)"></i>
        <span v-if="!compact">{{ themeLabels[themeOption] }}</span>
      </button>
    </div>

    <!-- Simple toggle (dark/light only) -->
    <button
      v-else-if="mode === 'toggle'"
      class="theme-toggle__simple"
      :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
      @click="toggleTheme"
    >
      <i :class="isDark ? 'fas fa-sun' : 'fas fa-moon'"></i>
      <span v-if="!compact">{{ isDark ? 'Light' : 'Dark' }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * ThemeToggle Component
 *
 * Props:
 *   - mode: 'dropdown' | 'buttons' | 'toggle' - Display mode
 *   - compact: boolean - Show icons only (no labels)
 *   - showLabel: boolean - Show "Theme" label
 *
 * Usage:
 *   <ThemeToggle />
 *   <ThemeToggle mode="buttons" />
 *   <ThemeToggle mode="toggle" compact />
 */

import { ref, watch } from 'vue'
import { useTheme, type Theme } from '@/composables/useTheme'

interface Props {
  mode?: 'dropdown' | 'buttons' | 'toggle'
  compact?: boolean
  showLabel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'dropdown',
  compact: false,
  showLabel: true
})

const { theme, setTheme, toggleTheme, isDark, availableThemes, themeLabels } = useTheme()

// Local state for v-model binding
const selectedTheme = ref<Theme>(theme.value)

// Sync with composable state
watch(theme, (newTheme) => {
  selectedTheme.value = newTheme
})

/**
 * Handle dropdown change
 */
function handleThemeChange(): void {
  setTheme(selectedTheme.value)
}

/**
 * Get icon class for theme option
 */
function getThemeIcon(themeOption: Theme): string {
  const icons: Record<Theme, string> = {
    dark: 'fas fa-moon',
    light: 'fas fa-sun',
    system: 'fas fa-desktop'
  }
  return icons[themeOption]
}
</script>

<style scoped>
/**
 * Issue #704: Using CSS design tokens for theming
 */
.theme-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.theme-toggle--compact {
  gap: var(--spacing-xs);
}

.theme-toggle__label {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.theme-toggle__label i {
  font-size: var(--text-base);
}

/* Dropdown styles */
.theme-toggle__dropdown {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.theme-toggle__select {
  appearance: none;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  padding: var(--spacing-2) var(--spacing-8) var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  transition: border-color var(--duration-150) ease,
              box-shadow var(--duration-150) ease;
}

.theme-toggle__select:hover {
  border-color: var(--border-strong);
}

.theme-toggle__select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.theme-toggle__dropdown-icon {
  position: absolute;
  right: var(--spacing-3);
  pointer-events: none;
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

/* Button group styles */
.theme-toggle__buttons {
  display: flex;
  gap: var(--spacing-1);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-1);
  border: 1px solid var(--border-subtle);
}

.theme-toggle__btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.theme-toggle__btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.theme-toggle__btn--active {
  background: var(--bg-primary);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

/* Simple toggle button */
.theme-toggle__simple {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.theme-toggle__simple:hover {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.theme-toggle__simple:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

/* Compact mode adjustments */
.theme-toggle--compact .theme-toggle__btn,
.theme-toggle--compact .theme-toggle__simple {
  padding: var(--spacing-2);
}

.theme-toggle--compact .theme-toggle__select {
  padding: var(--spacing-2) var(--spacing-6) var(--spacing-2) var(--spacing-2);
}
</style>
