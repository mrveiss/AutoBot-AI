<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ThemePresetPicker.vue - Theme Preset Selection Component
  Issue #8988: User-Selectable Theme System - Custom Theme Presets

  Provides a UI for selecting named theme presets with visual previews.
-->
<template>
  <div class="theme-preset-picker">
    <div class="picker-header">
      <h3 class="picker-title">
        <Icon name="palette" size="md" />
        {{ t('ui.themePresets.title') }}
      </h3>
      <p class="picker-description">
        {{ t('ui.themePresets.description') }}
      </p>
    </div>

    <div class="presets-grid">
      <button
        v-for="presetKey in availablePresets"
        :key="presetKey"
        @click="handleSelectPreset(presetKey)"
        :class="['preset-card', { active: preset === presetKey }]"
        :aria-pressed="preset === presetKey"
        type="button"
      >
        <div class="preset-preview" :data-preset="presetKey">
          <div class="preview-bg"></div>
          <div class="preview-accent"></div>
        </div>
        <div class="preset-info">
          <span class="preset-name">{{ t(THEME_PRESETS[presetKey].nameKey) }}</span>
          <span class="preset-description">{{ t(THEME_PRESETS[presetKey].descriptionKey) }}</span>
        </div>
        <div v-if="preset === presetKey" class="preset-check">
          <Icon name="check-circle" size="sm" />
        </div>
      </button>
    </div>

    <!-- Advanced Controls -->
    <details class="advanced-controls">
      <summary class="advanced-summary">
        <Icon name="sliders-h" size="sm" />
        {{ t('ui.themePresets.advanced') }}
      </summary>
      <div class="advanced-content">
        <!-- Manual Theme Control -->
        <fieldset class="control-section">
          <legend class="control-label">
            <Icon name="sun" size="sm" />
            {{ t('ui.themePresets.baseTheme') }}
          </legend>
          <div class="option-group">
            <button
              v-for="themeOption in availableThemes"
              :key="themeOption"
              @click="handleSetTheme(themeOption)"
              :class="['option-btn', { active: theme === themeOption }]"
              :aria-pressed="theme === themeOption"
              type="button"
            >
              <Icon :name="getThemeIcon(themeOption)" size="sm" />
              <span>{{ t(themeLabelKeys[themeOption]) }}</span>
            </button>
          </div>
        </fieldset>

        <!-- Manual Accent Control -->
        <fieldset class="control-section">
          <legend class="control-label">
            <Icon name="palette" size="sm" />
            {{ t('ui.preferences.accentColor') }}
          </legend>
          <div class="accent-grid">
            <button
              v-for="colorOption in availableAccents"
              :key="colorOption"
              @click="handleSetAccent(colorOption)"
              :class="['accent-btn', { active: accentColor === colorOption }]"
              :data-accent="colorOption"
              :aria-pressed="accentColor === colorOption"
              type="button"
            >
              <span class="accent-swatch"></span>
              <span class="accent-label">{{ t(accentLabelKeys[colorOption]) }}</span>
            </button>
          </div>
        </fieldset>
      </div>
    </details>

    <!-- Deployed (SLM) themes, #18240 -->
    <div class="px-6 pb-6"><AdditionalThemesGroup /></div>
  </div>
</template>

<script setup lang="ts">
import { getThemeIcon } from '@/composables/themeIcons'
import { useI18n } from 'vue-i18n'
import { useTheme, type Theme, type ThemePreset, type AccentColor } from '@/composables/useTheme'
import Icon from '@/components/ui/Icon.vue'
import AdditionalThemesGroup from '@/components/settings/AdditionalThemesGroup.vue'
import { useAnnounce } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ThemePresetPicker')
const { t } = useI18n()

const {
  preset,
  theme,
  accentColor,
  setPreset,
  setTheme,
  setAccentColor,
  availablePresets,
  availableThemes,
  availableAccents,
  themeLabelKeys,
  accentLabelKeys,
  THEME_PRESETS,
} = useTheme()

// Screen reader announcements: the kit's one live region (#18240)
const { announce: announceChange } = useAnnounce()

/**
 * Handle preset selection
 */
function handleSelectPreset(presetKey: ThemePreset): void {
  setPreset(presetKey)
  announceChange(t('ui.themeToggle.presetChanged', { name: t(THEME_PRESETS[presetKey].nameKey) }))
  logger.debug(`Theme preset changed to: ${presetKey}`)
}

/**
 * Handle manual theme selection
 */
function handleSetTheme(themeOption: Theme): void {
  setTheme(themeOption)
  announceChange(t('ui.themeToggle.baseThemeChanged', { name: t(themeLabelKeys[themeOption]) }))
  logger.debug(`Base theme changed to: ${themeOption}`)
}

/**
 * Handle manual accent selection
 */
function handleSetAccent(colorOption: AccentColor): void {
  setAccentColor(colorOption)
  announceChange(t('ui.themeToggle.accentChanged', { name: t(accentLabelKeys[colorOption]) }))
  logger.debug(`Accent color changed to: ${colorOption}`)
}

</script>

<style scoped>
/* ============================================
 * THEME PRESET PICKER - Using Design Tokens
 * ============================================ */

.theme-preset-picker {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  overflow: hidden;
}

/* ============================================
 * PICKER HEADER
 * ============================================ */

.picker-header {
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.picker-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.picker-title svg {
  color: var(--color-primary);
}

.picker-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-normal);
}

/* ============================================
 * PRESETS GRID
 * ============================================ */

.presets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
}

.preset-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
  position: relative;
}

.preset-card:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.preset-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.preset-card.active {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
  border-width: 3px;
  padding: calc(var(--spacing-md) - 1px);
  box-shadow: var(--shadow-lg);
}

/* ============================================
 * PRESET PREVIEW
 * ============================================ */

.preset-preview {
  display: flex;
  gap: var(--spacing-0-5);
  height: 48px;
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.preview-bg {
  flex: 2;
  background: var(--bg-secondary);
}

.preview-accent {
  flex: 1;
  background: var(--color-primary);
}

/* Preset-specific preview colors */
[data-preset="auto"] .preview-bg {
  background: linear-gradient(135deg, var(--preset-preview-auto-dark) 50%, var(--preset-preview-auto-light) 50%);
}

[data-preset="catppuccin-mocha"] .preview-bg {
  background: var(--preset-preview-catppuccin-mocha-bg);
}

[data-preset="catppuccin-mocha"] .preview-accent {
  background: var(--preset-preview-catppuccin-mocha-accent);
}

[data-preset="catppuccin-latte"] .preview-bg {
  background: var(--preset-preview-catppuccin-latte-bg);
}

[data-preset="catppuccin-latte"] .preview-accent {
  background: var(--preset-preview-catppuccin-latte-accent);
}

[data-preset="solarized-dark"] .preview-bg {
  background: var(--preset-preview-solarized-dark-bg);
}

[data-preset="solarized-dark"] .preview-accent {
  background: var(--preset-preview-solarized-dark-accent);
}

[data-preset="solarized-light"] .preview-bg {
  background: var(--preset-preview-solarized-light-bg);
}

[data-preset="solarized-light"] .preview-accent {
  background: var(--preset-preview-solarized-light-accent);
}

[data-preset="high-contrast-dark"] .preview-bg {
  background: var(--preset-preview-high-contrast-dark-bg);
}

[data-preset="high-contrast-light"] .preview-bg {
  background: var(--preset-preview-high-contrast-light-bg);
}

[data-preset="brand-dark"] .preview-bg {
  background: var(--preset-preview-brand-dark-bg);
}

[data-preset="brand-dark"] .preview-accent {
  background: var(--preset-preview-brand-dark-accent);
}

[data-preset="brand-light"] .preview-bg {
  background: var(--preset-preview-brand-light-bg);
}

[data-preset="brand-light"] .preview-accent {
  background: var(--preset-preview-brand-light-accent);
}

[data-preset="midnight"] .preview-bg {
  background: var(--preset-preview-midnight-bg);
}

[data-preset="midnight"] .preview-accent {
  background: var(--preset-preview-midnight-accent);
}

[data-preset="sunset"] .preview-bg {
  background: var(--preset-preview-sunset-bg);
}

[data-preset="sunset"] .preview-accent {
  background: var(--preset-preview-sunset-accent);
}

[data-preset="forest"] .preview-bg {
  background: var(--preset-preview-forest-bg);
}

[data-preset="forest"] .preview-accent {
  background: var(--preset-preview-forest-accent);
}

[data-preset="rose"] .preview-bg {
  background: var(--preset-preview-rose-bg);
}

[data-preset="rose"] .preview-accent {
  background: var(--preset-preview-rose-accent);
}

/* ============================================
 * PRESET INFO
 * ============================================ */

.preset-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.preset-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.preset-description {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-tight);
}

.preset-check {
  position: absolute;
  top: var(--spacing-2);
  right: var(--spacing-2);
  color: var(--color-primary);
}

/* ============================================
 * ADVANCED CONTROLS
 * ============================================ */

.advanced-controls {
  border-top: 1px solid var(--border-default);
}

.advanced-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-xl);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  transition: color var(--duration-150);
}

.advanced-summary:hover {
  color: var(--text-primary);
}

.advanced-content {
  padding: var(--spacing-xl);
  background: var(--bg-tertiary);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.control-section {
  border: none;
  padding: 0;
  margin: 0;
}

.control-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.option-group {
  display: flex;
  gap: var(--spacing-sm);
}

.option-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150);
}

.option-btn:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
  color: var(--text-primary);
}

.option-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

/* ============================================
 * ACCENT GRID
 * ============================================ */

.accent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: var(--spacing-sm);
}

.accent-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm);
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150);
}

.accent-btn:hover {
  background: var(--bg-secondary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.accent-btn.active {
  border-color: var(--color-primary);
  border-width: 3px;
  padding: calc(var(--spacing-sm) - 1px);
}

.accent-swatch {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
}

[data-accent="theme"] .accent-swatch { background: var(--primary); } /* accent swatch colors; "theme" is the Refined ink */
[data-accent="blue"] .accent-swatch {
  background: var(--accent-swatch-blue);
}

[data-accent="green"] .accent-swatch {
  background: var(--accent-swatch-green);
}

[data-accent="purple"] .accent-swatch {
  background: var(--accent-swatch-purple);
}

[data-accent="orange"] .accent-swatch {
  background: var(--accent-swatch-orange);
}

[data-accent="pink"] .accent-swatch {
  background: var(--accent-swatch-pink);
}

[data-accent="teal"] .accent-swatch {
  background: var(--accent-swatch-teal);
}

[data-accent="indigo"] .accent-swatch {
  background: var(--accent-swatch-indigo);
}

[data-accent="red"] .accent-swatch {
  background: var(--accent-swatch-red);
}

.accent-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.accent-btn.active .accent-label {
  color: var(--text-primary);
  font-weight: 600;
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .presets-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--spacing-sm);
    padding: var(--spacing-md);
  }

  .picker-header {
    padding: var(--spacing-md);
  }

  .advanced-content {
    padding: var(--spacing-md);
  }

  .option-group {
    flex-direction: column;
  }

  .accent-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
