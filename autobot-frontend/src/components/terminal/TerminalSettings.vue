<template>
  <div class="terminal-settings p-4 bg-gray-800 rounded-lg">
    <h3 class="text-white text-lg mb-4">Terminal Settings</h3>

    <div class="space-y-4">
      <!-- Font Size -->
      <div class="flex items-center justify-between">
        <label class="text-gray-300">Font Size</label>
        <div class="flex items-center gap-2">
          <input
            type="range"
            v-model.number="settings.fontSize"
            min="10"
            max="24"
            class="w-24 accent-blue-500"
            data-testid="font-size-slider"
          />
          <span class="text-gray-400 w-8 text-right">{{ settings.fontSize }}</span>
        </div>
      </div>

      <!-- Theme -->
      <div class="flex items-center justify-between">
        <label class="text-gray-300">Theme</label>
        <select
          v-model="settings.theme"
          class="bg-gray-700 text-white rounded px-2 py-1 border border-gray-600 focus:border-blue-500 focus:outline-none"
          data-testid="theme-select"
        >
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>
      </div>

      <!-- Cursor Style -->
      <div class="flex items-center justify-between">
        <label class="text-gray-300">Cursor Style</label>
        <select
          v-model="settings.cursorStyle"
          class="bg-gray-700 text-white rounded px-2 py-1 border border-gray-600 focus:border-blue-500 focus:outline-none"
          data-testid="cursor-style-select"
        >
          <option value="block">Block</option>
          <option value="underline">Underline</option>
          <option value="bar">Bar</option>
        </select>
      </div>

      <!-- Cursor Blink -->
      <div class="flex items-center justify-between">
        <label class="text-gray-300">Cursor Blink</label>
        <input
          type="checkbox"
          v-model="settings.cursorBlink"
          class="w-5 h-5 accent-blue-500 cursor-pointer"
          data-testid="cursor-blink-checkbox"
        />
      </div>
    </div>

    <button
      @click="saveSettings"
      class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800"
      data-testid="save-settings-button"
    >
      Save Settings
    </button>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, watch, onMounted } from 'vue'
import { createLogger, getStorageJson, setStorageJson } from '@/utils/debugUtils'

const logger = createLogger('TerminalSettings')

// Storage key for terminal settings
const STORAGE_KEY = 'terminal-settings'

/**
 * Terminal settings interface for type safety
 */
interface TerminalSettings {
  fontSize: number
  theme: 'dark' | 'light'
  cursorStyle: 'block' | 'underline' | 'bar'
  cursorBlink: boolean
}

/**
 * Default terminal settings
 */
const DEFAULT_SETTINGS: TerminalSettings = {
  fontSize: 14,
  theme: 'dark',
  cursorStyle: 'block',
  cursorBlink: true
}

// Emits
const emit = defineEmits<{
  update: [settings: TerminalSettings]
}>()

// Reactive settings state
const settings = ref<TerminalSettings>({ ...DEFAULT_SETTINGS })

/**
 * Load settings from localStorage on component mount.
 * Falls back to default settings if none exist or parsing fails.
 */
const loadSettings = (): void => {
  const stored = getStorageJson<TerminalSettings | null>(STORAGE_KEY, null)

  if (stored) {
    // Validate and merge with defaults to ensure all properties exist
    settings.value = {
      fontSize: validateFontSize(stored.fontSize),
      theme: validateTheme(stored.theme),
      cursorStyle: validateCursorStyle(stored.cursorStyle),
      cursorBlink: typeof stored.cursorBlink === 'boolean' ? stored.cursorBlink : DEFAULT_SETTINGS.cursorBlink
    }
    logger.info('Loaded terminal settings from storage', settings.value)
  } else {
    settings.value = { ...DEFAULT_SETTINGS }
    logger.info('Using default terminal settings')
  }
}

/**
 * Validate font size is within acceptable range.
 * @param size - Font size to validate
 * @returns Valid font size between 10 and 24
 */
const validateFontSize = (size: unknown): number => {
  if (typeof size !== 'number' || isNaN(size)) {
    return DEFAULT_SETTINGS.fontSize
  }
  return Math.min(24, Math.max(10, size))
}

/**
 * Validate theme value.
 * @param theme - Theme to validate
 * @returns Valid theme value
 */
const validateTheme = (theme: unknown): 'dark' | 'light' => {
  if (theme === 'dark' || theme === 'light') {
    return theme
  }
  return DEFAULT_SETTINGS.theme
}

/**
 * Validate cursor style value.
 * @param style - Cursor style to validate
 * @returns Valid cursor style value
 */
const validateCursorStyle = (style: unknown): 'block' | 'underline' | 'bar' => {
  if (style === 'block' || style === 'underline' || style === 'bar') {
    return style
  }
  return DEFAULT_SETTINGS.cursorStyle
}

/**
 * Save current settings to localStorage.
 * Emits update event after successful save.
 */
const saveSettings = (): void => {
  const success = setStorageJson(STORAGE_KEY, settings.value)

  if (success) {
    logger.info('Terminal settings saved', settings.value)
    emit('update', { ...settings.value })
  } else {
    logger.error('Failed to save terminal settings')
  }
}

// Watch for settings changes and emit update events
watch(
  settings,
  (newSettings) => {
    emit('update', { ...newSettings })
    logger.debug('Settings changed', newSettings)
  },
  { deep: true }
)

// Load settings on component mount
onMounted(() => {
  loadSettings()
})

// Expose methods for testing
defineExpose({
  loadSettings,
  saveSettings,
  settings
})
</script>

<style scoped>
/* Issue #749: Terminal Settings component styles */

.terminal-settings {
  min-width: 280px;
  max-width: 400px;
}

/* Range slider custom styling */
input[type='range'] {
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 3px;
  background: #4a5568;
}

input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

input[type='range']::-webkit-slider-thumb:hover {
  background: #2563eb;
}

input[type='range']::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: none;
  transition: background-color 0.15s ease;
}

input[type='range']::-moz-range-thumb:hover {
  background: #2563eb;
}

/* Checkbox custom styling */
input[type='checkbox'] {
  cursor: pointer;
}

/* Select dropdown styling */
select {
  cursor: pointer;
}

select:focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5);
}
</style>
