// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SVG Icons Composable
 *
 * Issue #4040: SVG sprite sheet optimization
 *
 * Provides utilities for using SVG sprite sheets with <use> references.
 * Eliminates need for Font Awesome icons in many cases, reducing bundle size.
 *
 * Usage:
 * ```vue
 * <template>
 *   <svg class="icon">
 *     <use :href="`/icons.svg#${icon('home')}`"></use>
 *   </svg>
 * </template>
 *
 * <script setup>
 * import { useSvgIcons } from '@/composables/useSvgIcons'
 * const { icon, status } = useSvgIcons()
 * </script>
 * ```
 */

/**
 * Icon identifiers for common application icons
 */
export const ICON_IDS = {
  // Navigation
  home: 'icon-home',
  close: 'icon-close',
  menu: 'icon-menu',
  chevronRight: 'icon-chevron-right',
  chevronLeft: 'icon-chevron-left',
  chevronDown: 'icon-chevron-down',

  // Search & Input
  search: 'icon-search',

  // Actions
  edit: 'icon-edit',
  delete: 'icon-delete',
  add: 'icon-add',
  refresh: 'icon-refresh',

  // Status & Validation
  check: 'icon-check',
  error: 'icon-error',
  warning: 'icon-warning',
  info: 'icon-info',

  // Users & Collaboration
  user: 'icon-user',
  users: 'icon-users',

  // Files & Folders
  folder: 'icon-folder',
  file: 'icon-file',

  // Settings
  settings: 'icon-settings',
  key: 'icon-key',

  // Notifications
  bell: 'icon-bell',

  // Direction & Movement
  arrowRight: 'icon-arrow-right',
  arrowDown: 'icon-arrow-down',
  download: 'icon-download',
  upload: 'icon-upload'
}

/**
 * Status indicator identifiers
 */
export const STATUS_IDS = {
  online: 'status-online',
  offline: 'status-offline',
  away: 'status-away',
  success: 'status-success',
  error: 'status-error',
  warning: 'status-warning',
  loading: 'status-loading',
  inProgress: 'status-in-progress',
  blocked: 'status-blocked',
  completed: 'status-completed',
  processing: 'status-processing'
}

/**
 * Composable for SVG icon sprite sheet access
 */
export function useSvgIcons() {
  /**
   * Get the icon ID for a given icon name
   * @param name - The icon name (e.g., 'home', 'close')
   * @returns The icon ID for use in <use href="/icons.svg#id">
   */
  const icon = (name: keyof typeof ICON_IDS): string => {
    return ICON_IDS[name] || 'icon-info'
  }

  /**
   * Get the status icon ID for a given status
   * @param status - The status name (e.g., 'online', 'loading')
   * @returns The status icon ID for use in <use href="/status.svg#id">
   */
  const status = (statusName: keyof typeof STATUS_IDS): string => {
    return STATUS_IDS[statusName] || 'status-offline'
  }

  /**
   * Get the full SVG use reference for an icon
   * @param name - The icon name
   * @returns The full href for <use> tag
   */
  const iconHref = (name: keyof typeof ICON_IDS): string => {
    return `/icons.svg#${icon(name)}`
  }

  /**
   * Get the full SVG use reference for a status icon
   * @param statusName - The status name
   * @returns The full href for <use> tag
   */
  const statusHref = (statusName: keyof typeof STATUS_IDS): string => {
    return `/status.svg#${status(statusName)}`
  }

  return {
    icon,
    status,
    iconHref,
    statusHref,
    ICON_IDS,
    STATUS_IDS
  }
}
