<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

PreferencesPanel.vue - User Preferences Configuration Panel
Issue #753: Additional Customization (Font Size, Accent Colors, Layout Density)
-->

<template>
  <div class="preferences-panel">
    <div class="panel-header">
      <h3 class="panel-title">
        <i class="fas fa-sliders-h"></i>
        Preferences
      </h3>
      <button @click="handleReset" class="reset-btn" title="Reset to defaults">
        <i class="fas fa-undo"></i>
        Reset
      </button>
    </div>

    <div class="panel-content">
      <!-- Font Size Preference -->
      <div class="preference-section">
        <label class="preference-label">
          <i class="fas fa-font"></i>
          Font Size
        </label>
        <div class="option-group">
          <button
            v-for="size in fontSizeOptions"
            :key="size.value"
            @click="handleSetFontSize(size.value)"
            :class="['option-btn', { active: fontSize === size.value }]"
          >
            {{ size.label }}
          </button>
        </div>
      </div>

      <!-- Accent Color Preference -->
      <div class="preference-section">
        <label class="preference-label">
          <i class="fas fa-palette"></i>
          Accent Color
        </label>
        <div class="color-grid">
          <button
            v-for="color in accentColorOptions"
            :key="color.value"
            @click="handleSetAccentColor(color.value)"
            :class="['color-btn', { active: accentColor === color.value }]"
            :style="{ '--preview-color': color.preview }"
            :title="color.label"
          >
            <span class="color-preview"></span>
            <span class="color-label">{{ color.label }}</span>
          </button>
        </div>
      </div>

      <!-- Layout Density Preference -->
      <div class="preference-section">
        <label class="preference-label">
          <i class="fas fa-th"></i>
          Layout Density
        </label>
        <div class="option-group">
          <button
            v-for="density in layoutDensityOptions"
            :key="density.value"
            @click="handleSetLayoutDensity(density.value)"
            :class="['option-btn', { active: layoutDensity === density.value }]"
          >
            {{ density.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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

// Font size options
const fontSizeOptions = [
  { value: 'small' as FontSize, label: 'Small' },
  { value: 'medium' as FontSize, label: 'Medium' },
  { value: 'large' as FontSize, label: 'Large' }
]

// Accent color options with preview colors
const accentColorOptions = [
  { value: 'teal' as AccentColor, label: 'Teal', preview: '#0d9488' },
  { value: 'emerald' as AccentColor, label: 'Emerald', preview: '#10b981' },
  { value: 'blue' as AccentColor, label: 'Blue', preview: '#3b82f6' },
  { value: 'purple' as AccentColor, label: 'Purple', preview: '#8b5cf6' },
  { value: 'orange' as AccentColor, label: 'Orange', preview: '#f97316' }
]

// Layout density options
const layoutDensityOptions = [
  { value: 'compact' as LayoutDensity, label: 'Compact' },
  { value: 'comfortable' as LayoutDensity, label: 'Comfortable' },
  { value: 'spacious' as LayoutDensity, label: 'Spacious' }
]

// Event handlers
function handleSetFontSize(size: FontSize) {
  setFontSize(size)
  logger.debug(`Font size changed to: ${size}`)
}

function handleSetAccentColor(color: AccentColor) {
  setAccentColor(color)
  logger.debug(`Accent color changed to: ${color}`)
}

function handleSetLayoutDensity(density: LayoutDensity) {
  setLayoutDensity(density)
  logger.debug(`Layout density changed to: ${density}`)
}

function handleReset() {
  resetPreferences()
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
 * PREFERENCE SECTIONS
 * ============================================ */

.preference-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
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

.option-btn.active {
  background: var(--color-primary);
  color: var(--text-inverse);
  border-color: var(--color-primary);
  font-weight: 600;
}

/* ============================================
 * COLOR GRID (Accent Colors)
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
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.color-btn:hover {
  background: var(--bg-secondary);
  border-color: var(--preview-color);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.color-btn.active {
  background: var(--bg-tertiary);
  border-color: var(--preview-color);
  border-width: 3px;
  box-shadow: var(--shadow-md);
}

.color-preview {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--preview-color);
  box-shadow: var(--shadow-sm);
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
