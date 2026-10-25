// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * themePresets.ts - named theme + accent combinations
 * Issue #8988: User-Selectable Theme System - Custom Theme Presets
 *
 * Split out of useTheme.ts (#18223) to keep that file under its size ceiling.
 * Imports types only from useTheme, so there is no runtime cycle.
 */

import type { Theme, AccentColor } from './useTheme'

/** Theme preset options - named combinations of theme + accent + optional density */
export type ThemePreset =
  | 'auto' // System preference
  | 'catppuccin-mocha' // Dark + Purple
  | 'catppuccin-latte' // Light + Purple
  | 'solarized-dark' // Dark + Teal
  | 'solarized-light' // Light + Teal
  | 'high-contrast-dark' // Dark + Blue (high contrast)
  | 'high-contrast-light' // Light + Blue (high contrast)
  | 'brand-dark' // Dark + AutoBot brand color (teal)
  | 'brand-light' // Light + AutoBot brand color (teal)
  | 'midnight' // Dark + Indigo
  | 'sunset' // Light + Orange
  | 'forest' // Dark + Green
  | 'rose' // Light + Pink

/** Configuration for each theme preset */
export interface ThemePresetConfig {
  /** i18n key of the display name; render sites translate with t() (#18255) */
  nameKey: string
  /** i18n key of the one-line description */
  descriptionKey: string
  theme: Theme
  accentColor: AccentColor
  highContrast?: boolean
}

/** Preset configurations */
export const THEME_PRESETS: Record<ThemePreset, ThemePresetConfig> = {
  auto: {
    nameKey: 'ui.themePresets.names.auto',
    descriptionKey: 'ui.themePresets.descriptions.auto',
    theme: 'system',
    accentColor: 'theme',
  },
  'catppuccin-mocha': {
    nameKey: 'ui.themePresets.names.catppuccin-mocha',
    descriptionKey: 'ui.themePresets.descriptions.catppuccin-mocha',
    theme: 'dark',
    accentColor: 'purple',
  },
  'catppuccin-latte': {
    nameKey: 'ui.themePresets.names.catppuccin-latte',
    descriptionKey: 'ui.themePresets.descriptions.catppuccin-latte',
    theme: 'light',
    accentColor: 'purple',
  },
  'solarized-dark': {
    nameKey: 'ui.themePresets.names.solarized-dark',
    descriptionKey: 'ui.themePresets.descriptions.solarized-dark',
    theme: 'dark',
    accentColor: 'teal',
  },
  'solarized-light': {
    nameKey: 'ui.themePresets.names.solarized-light',
    descriptionKey: 'ui.themePresets.descriptions.solarized-light',
    theme: 'light',
    accentColor: 'teal',
  },
  'high-contrast-dark': {
    nameKey: 'ui.themePresets.names.high-contrast-dark',
    descriptionKey: 'ui.themePresets.descriptions.high-contrast-dark',
    theme: 'dark',
    accentColor: 'blue',
    highContrast: true,
  },
  'high-contrast-light': {
    nameKey: 'ui.themePresets.names.high-contrast-light',
    descriptionKey: 'ui.themePresets.descriptions.high-contrast-light',
    theme: 'light',
    accentColor: 'blue',
    highContrast: true,
  },
  'brand-dark': {
    nameKey: 'ui.themePresets.names.brand-dark',
    descriptionKey: 'ui.themePresets.descriptions.brand-dark',
    theme: 'dark',
    accentColor: 'teal',
  },
  'brand-light': {
    nameKey: 'ui.themePresets.names.brand-light',
    descriptionKey: 'ui.themePresets.descriptions.brand-light',
    theme: 'light',
    accentColor: 'teal',
  },
  midnight: {
    nameKey: 'ui.themePresets.names.midnight',
    descriptionKey: 'ui.themePresets.descriptions.midnight',
    theme: 'dark',
    accentColor: 'indigo',
  },
  sunset: {
    nameKey: 'ui.themePresets.names.sunset',
    descriptionKey: 'ui.themePresets.descriptions.sunset',
    theme: 'light',
    accentColor: 'orange',
  },
  forest: {
    nameKey: 'ui.themePresets.names.forest',
    descriptionKey: 'ui.themePresets.descriptions.forest',
    theme: 'dark',
    accentColor: 'green',
  },
  rose: {
    nameKey: 'ui.themePresets.names.rose',
    descriptionKey: 'ui.themePresets.descriptions.rose',
    theme: 'light',
    accentColor: 'pink',
  },
}
