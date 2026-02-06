<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

PreferencesPanel.vue - User Preferences Configuration Panel
Issue #753: Additional Customization (Font Size, Accent Colors, Layout Density)
-->

<template>
  <form class="preferences-panel" @submit.prevent>
    <div class="panel-header">
      <h3 class="panel-title">
        <i class="fas fa-sliders-h" aria-hidden="true"></i>
        Preferences
      </h3>
      <button
        @click="handleReset"
        class="reset-btn"
        type="button"
        aria-label="Reset all preferences to defaults"
      >
        <i class="fas fa-undo" aria-hidden="true"></i>
        Reset
      </button>
    </div>

    <div class="panel-content">
      <!-- Font Size Preference -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <i class="fas fa-font" aria-hidden="true"></i>
          Font Size
        </legend>
        <div class="option-group" role="radiogroup" aria-label="Font size options">
          <button
            v-for="size in fontSizeOptions"
            :key="size.value"
            @click="handleSetFontSize(size.value)"
            @keydown.enter="handleSetFontSize(size.value)"
            @keydown.space.prevent="handleSetFontSize(size.value)"
            :class="['option-btn', { active: fontSize === size.value }]"
            :aria-label="`Set font size to ${size.label}`"
            :aria-pressed="fontSize === size.value"
            role="button"
            type="button"
          >
            {{ size.label }}
          </button>
        </div>
      </fieldset>

      <!-- Accent Color Preference -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <i class="fas fa-palette" aria-hidden="true"></i>
          Accent Color
        </legend>
        <div class="color-grid" role="radiogroup" aria-label="Accent color options">
          <button
            v-for="color in accentColorOptions"
            :key="color.value"
            @click="handleSetAccentColor(color.value)"
            @keydown.enter="handleSetAccentColor(color.value)"
            @keydown.space.prevent="handleSetAccentColor(color.value)"
            :class="['color-btn', { active: accentColor === color.value }]"
            :data-color="color.value"
            :aria-label="`Set accent color to ${color.label}`"
            :aria-pressed="accentColor === color.value"
            role="button"
            type="button"
          >
            <span class="color-preview" :aria-hidden="true"></span>
            <span class="color-label">{{ color.label }}</span>
          </button>
        </div>
      </fieldset>

      <!-- Layout Density Preference -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <i class="fas fa-th" aria-hidden="true"></i>
          Layout Density
        </legend>
        <div class="option-group" role="radiogroup" aria-label="Layout density options">
          <button
            v-for="density in layoutDensityOptions"
            :key="density.value"
            @click="handleSetLayoutDensity(density.value)"
            @keydown.enter="handleSetLayoutDensity(density.value)"
            @keydown.space.prevent="handleSetLayoutDensity(density.value)"
            :class="['option-btn', { active: layoutDensity === density.value }]"
            :aria-label="`Set layout density to ${density.label}`"
            :aria-pressed="layoutDensity === density.value"
            role="button"
            type="button"
          >
            {{ density.label }}
          </button>
        </div>
      </fieldset>
    </div>

    <!-- Screen reader announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ announcement }}
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { usePreferences, type FontSize, type AccentColor, type LayoutDensity } from '@/composables/usePreferences'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PreferencesPanel')

// Initialize preferences
const {
  fontSize,
  accentColor,
  layoutDensity,
  setFontSize,
  setAccentColor,
  setLayoutDensity,
  resetPreferences
} = usePreferences()

// Screen reader announcements
const announcement = ref('')

// Font size options
const fontSizeOptions = [
  { value: 'small' as FontSize, label: 'Small' },
  { value: 'medium' as FontSize, label: 'Medium' },
  { value: 'large' as FontSize, label: 'Large' }
]

// Accent color options (CSS variables for preview colors)
const accentColorOptions = [
  { value: 'teal' as AccentColor, label: 'Teal' },
  { value: 'emerald' as AccentColor, label: 'Emerald' },
  { value: 'blue' as AccentColor, label: 'Blue' },
  { value: 'purple' as AccentColor, label: 'Purple' },
  { value: 'orange' as AccentColor, label: 'Orange' }
]

// Layout density options
const layoutDensityOptions = [
  { value: 'compact' as LayoutDensity, label: 'Compact' },
  { value: 'comfortable' as LayoutDensity, label: 'Comfortable' },
  { value: 'spacious' as LayoutDensity, label: 'Spacious' }
]

// Helper function to announce changes to screen readers
function announceChange(message: string): void {
  announcement.value = message
  setTimeout(() => {
    announcement.value = ''
  }, 1000)
}

// Event handlers with screen reader announcements
function handleSetFontSize(size: FontSize) {
  setFontSize(size)
  announceChange(`Font size changed to ${size}`)
  logger.debug(`Font size changed to: ${size}`)
}

function handleSetAccentColor(color: AccentColor) {
  setAccentColor(color)
  announceChange(`Accent color changed to ${color}`)
  logger.debug(`Accent color changed to: ${color}`)
}

function handleSetLayoutDensity(density: LayoutDensity) {
  setLayoutDensity(density)
  announceChange(`Layout density changed to ${density}`)
  logger.debug(`Layout density changed to: ${density}`)
}

function handleReset() {
  resetPreferences()
  announceChange('All preferences reset to defaults')
  logger.debug('Preferences reset to defaults')
}
</script>

<style scoped>
/* ============================================
 * PREFERENCES PANEL - Using Design Tokens
 * ============================================ */

.preferences-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

/* Screen reader only */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* ============================================
 * PANEL HEADER
 * ============================================ */

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.panel-title i {
  color: var(--color-primary);
}

.reset-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.reset-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--color-primary);
}

.reset-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* ============================================
 * PANEL CONTENT
 * ============================================ */

.panel-content {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

/* ============================================
 * PREFERENCE SECTIONS (Fieldsets)
 * ============================================ */

.preference-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  border: none;
  padding: 0;
  margin: 0;
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preference-label i {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

/* ============================================
 * OPTION GROUPS (Font Size, Layout Density)
 * ============================================ */

.option-group {
  display: flex;
  gap: var(--spacing-sm);
}

.option-btn {
  flex: 1;
  min-height: 44px; /* Touch-friendly tap target */
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.option-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--color-primary);
}

.option-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.option-btn.active {
  background: var(--color-primary);
  color: var(--text-inverse);
  border-color: var(--color-primary);
  font-weight: 600;
}

/* ============================================
 * COLOR GRID (Accent Colors)
 * Uses CSS variables from theme for preview colors
 * ============================================ */

.color-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: var(--spacing-sm);
}

.color-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  min-height: 44px; /* Touch-friendly tap target */
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.color-btn:hover {
  background: var(--bg-secondary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.color-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.color-btn.active {
  background: var(--bg-tertiary);
  border-width: 3px;
  box-shadow: var(--shadow-md);
}

/* Color preview using data attributes and CSS */
.color-preview {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
}

.color-btn[data-color="teal"] .color-preview {
  background: #0d9488;
}

.color-btn[data-color="emerald"] .color-preview {
  background: #10b981;
}

.color-btn[data-color="blue"] .color-preview {
  background: #3b82f6;
}

.color-btn[data-color="purple"] .color-preview {
  background: #8b5cf6;
}

.color-btn[data-color="orange"] .color-preview {
  background: #f97316;
}

/* Active color preview gets border */
.color-btn.active .color-preview {
  border: 2px solid var(--color-primary);
}

.color-label {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--text-secondary);
}

.color-btn.active .color-label {
  color: var(--text-primary);
  font-weight: 600;
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .panel-content {
    padding: var(--spacing-md);
  }

  .option-group {
    flex-direction: column;
  }

  .color-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
