<template>
  <div v-if="uiSettings && isSettingsLoaded" class="settings-section">
    <h3>User Interface Settings</h3>

    <!-- Theme Selection - Issue #704: CSS Design System -->
    <div class="setting-item setting-item--theme">
      <div class="setting-label">
        <label for="theme-select">
          <i class="fas fa-palette"></i>
          Theme
        </label>
        <span class="setting-hint">Choose your preferred color theme</span>
      </div>
      <div class="theme-options">
        <button
          v-for="themeOption in availableThemes"
          :key="themeOption"
          :class="['theme-btn', { 'theme-btn--active': currentTheme === themeOption }]"
          :title="themeLabels[themeOption]"
          @click="handleThemeChange(themeOption)"
        >
          <i :class="getThemeIcon(themeOption)"></i>
          <span>{{ themeLabels[themeOption] }}</span>
        </button>
      </div>
    </div>
    <div class="setting-item">
      <label for="language-select">Language</label>
      <select
        id="language-select"
        :value="uiSettings.language"
        @change="handleSelectChange('language', $event)"
      >
        <option value="en">English</option>
        <option value="es">Spanish</option>
        <option value="fr">French</option>
      </select>
    </div>
    <div class="setting-item">
      <label for="show-timestamps">Show Timestamps</label>
      <input
        id="show-timestamps"
        type="checkbox"
        :checked="uiSettings.show_timestamps"
        @change="handleCheckboxChange('show_timestamps', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="show-status-bar">Show Status Bar</label>
      <input
        id="show-status-bar"
        type="checkbox"
        :checked="uiSettings.show_status_bar"
        @change="handleCheckboxChange('show_status_bar', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="auto-refresh-interval">Auto Refresh Interval (seconds)</label>
      <input
        id="auto-refresh-interval"
        type="number"
        :value="uiSettings.auto_refresh_interval"
        min="5"
        max="300"
        @input="handleNumberInputChange('auto_refresh_interval', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTheme, type Theme } from '@/composables/useTheme'

interface UISettings {
  theme: 'light' | 'dark' | 'auto'
  language: string
  show_timestamps: boolean
  show_status_bar: boolean
  auto_refresh_interval: number
}

interface Props {
  uiSettings: UISettings | null
  isSettingsLoaded: boolean
}

interface Emits {
  (e: 'setting-changed', key: string, value: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Issue #704: Use the design system theme composable
const { theme: currentTheme, setTheme, availableThemes, themeLabels } = useTheme()

const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

/**
 * Handle theme change - Issue #704
 * Updates both the design system theme and emits setting change
 */
const handleThemeChange = (themeOption: Theme) => {
  setTheme(themeOption)
  // Also emit to parent for persistence in backend settings
  updateSetting('theme', themeOption === 'system' ? 'auto' : themeOption)
}

/**
 * Get icon class for theme option
 */
const getThemeIcon = (themeOption: Theme): string => {
  const icons: Record<Theme, string> = {
    dark: 'fas fa-moon',
    light: 'fas fa-sun',
    system: 'fas fa-desktop'
  }
  return icons[themeOption]
}

// Issue #156 Fix: Typed event handlers to replace inline $event.target usage
// Issue #704 Fix: Refactored to accept event directly instead of returning curried function
const handleSelectChange = (key: string, event: Event) => {
  const target = event.target as HTMLSelectElement
  updateSetting(key, target.value)
}

const handleCheckboxChange = (key: string, event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.checked)
}

const handleNumberInputChange = (key: string, event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, parseInt(target.value))
}
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.settings-section {
  margin-bottom: var(--spacing-lg);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
}

.settings-section h3 {
  margin: 0 0 var(--spacing-lg) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-lg);
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-sm);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  flex: 1;
  margin-right: var(--spacing-md);
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 150px;
  padding: var(--spacing-sm) var(--spacing-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-150) ease,
              box-shadow var(--duration-150) ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.setting-item input:invalid {
  border-color: var(--color-error);
  box-shadow: var(--shadow-focus-error);
}

/* Theme selector styles - Issue #704 */
.setting-item--theme {
  flex-direction: column;
  align-items: flex-start;
  gap: var(--spacing-sm);
}

.setting-label {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.setting-label label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.setting-label label i {
  color: var(--color-primary);
}

.setting-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.theme-options {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.theme-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border: 2px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.theme-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-default);
  color: var(--text-primary);
}

.theme-btn--active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.theme-btn--active:hover {
  background: var(--color-primary-bg-hover);
}

.theme-btn i {
  font-size: var(--text-base);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: var(--spacing-xs);
  }

  .setting-item input,
  .setting-item select {
    min-width: auto;
    width: 100%;
  }

  .theme-options {
    width: 100%;
  }

  .theme-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>