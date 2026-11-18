// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * themeIcons.ts - the one icon per theme (#18223)
 *
 * ThemeToggle and ThemePresetPicker each kept their own copy of this record,
 * so a new theme needed two edits and could be iconless in one of them.
 */

import type { IconName } from '@/components/ui/Icon.vue'
import type { Theme } from './useTheme'

export const THEME_ICONS: Record<Theme, IconName> = {
  dark: 'moon',
  light: 'sun',
  contrast: 'eye',
  'contrast-dark': 'eye',
  mono: 'circle',
  system: 'desktop',
}

export function getThemeIcon(theme: Theme): IconName {
  return THEME_ICONS[theme]
}
