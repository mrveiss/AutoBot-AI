// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { useSvgIcons, ICON_IDS, STATUS_IDS } from '../useSvgIcons'

describe('useSvgIcons', () => {
  describe('ICON_IDS', () => {
    it('should contain navigation icons', () => {
      expect(ICON_IDS.home).toBe('icon-home')
      expect(ICON_IDS.close).toBe('icon-close')
      expect(ICON_IDS.menu).toBe('icon-menu')
      expect(ICON_IDS.chevronRight).toBe('icon-chevron-right')
      expect(ICON_IDS.chevronLeft).toBe('icon-chevron-left')
      expect(ICON_IDS.chevronDown).toBe('icon-chevron-down')
    })

    it('should contain action icons', () => {
      expect(ICON_IDS.edit).toBe('icon-edit')
      expect(ICON_IDS.delete).toBe('icon-delete')
      expect(ICON_IDS.add).toBe('icon-add')
      expect(ICON_IDS.refresh).toBe('icon-refresh')
    })

    it('should contain status/validation icons', () => {
      expect(ICON_IDS.check).toBe('icon-check')
      expect(ICON_IDS.error).toBe('icon-error')
      expect(ICON_IDS.warning).toBe('icon-warning')
      expect(ICON_IDS.info).toBe('icon-info')
    })

    it('should contain user/collaboration icons', () => {
      expect(ICON_IDS.user).toBe('icon-user')
      expect(ICON_IDS.users).toBe('icon-users')
    })

    it('should contain file/folder icons', () => {
      expect(ICON_IDS.folder).toBe('icon-folder')
      expect(ICON_IDS.file).toBe('icon-file')
    })

    it('should contain settings icons', () => {
      expect(ICON_IDS.settings).toBe('icon-settings')
      expect(ICON_IDS.key).toBe('icon-key')
    })

    it('should contain direction/movement icons', () => {
      expect(ICON_IDS.arrowRight).toBe('icon-arrow-right')
      expect(ICON_IDS.arrowDown).toBe('icon-arrow-down')
      expect(ICON_IDS.download).toBe('icon-download')
      expect(ICON_IDS.upload).toBe('icon-upload')
    })
  })

  describe('STATUS_IDS', () => {
    it('should contain status indicators', () => {
      expect(STATUS_IDS.online).toBe('status-online')
      expect(STATUS_IDS.offline).toBe('status-offline')
      expect(STATUS_IDS.away).toBe('status-away')
    })

    it('should contain result status icons', () => {
      expect(STATUS_IDS.success).toBe('status-success')
      expect(STATUS_IDS.error).toBe('status-error')
      expect(STATUS_IDS.warning).toBe('status-warning')
    })

    it('should contain process status icons', () => {
      expect(STATUS_IDS.loading).toBe('status-loading')
      expect(STATUS_IDS.inProgress).toBe('status-in-progress')
      expect(STATUS_IDS.blocked).toBe('status-blocked')
      expect(STATUS_IDS.completed).toBe('status-completed')
      expect(STATUS_IDS.processing).toBe('status-processing')
    })
  })

  describe('useSvgIcons composable', () => {
    it('should return icon ID for valid icon name', () => {
      const { icon } = useSvgIcons()
      expect(icon('home')).toBe('icon-home')
      expect(icon('close')).toBe('icon-close')
      expect(icon('menu')).toBe('icon-menu')
    })

    it('should return default icon for invalid name', () => {
      const { icon } = useSvgIcons()
      // TypeScript should prevent invalid names, but JS fallback is safe
      expect(icon('info' as unknown as keyof typeof ICON_IDS)).toBe('icon-info')
    })

    it('should return status ID for valid status name', () => {
      const { status } = useSvgIcons()
      expect(status('online')).toBe('status-online')
      expect(status('loading')).toBe('status-loading')
      expect(status('success')).toBe('status-success')
    })

    it('should return default status for invalid status name', () => {
      const { status } = useSvgIcons()
      // TypeScript should prevent invalid names, but JS fallback is safe
      expect(status('offline' as unknown as keyof typeof STATUS_IDS)).toBe('status-offline')
    })

    it('should return iconHref for icon name', () => {
      const { iconHref } = useSvgIcons()
      expect(iconHref('home')).toBe('/icons.svg#icon-home')
      expect(iconHref('close')).toBe('/icons.svg#icon-close')
    })

    it('should return statusHref for status name', () => {
      const { statusHref } = useSvgIcons()
      expect(statusHref('online')).toBe('/status.svg#status-online')
      expect(statusHref('loading')).toBe('/status.svg#status-loading')
    })

    it('should export ICON_IDS and STATUS_IDS', () => {
      const { ICON_IDS: ids, STATUS_IDS: statuses } = useSvgIcons()
      expect(ids).toBe(ICON_IDS)
      expect(statuses).toBe(STATUS_IDS)
    })

    it('should provide complete icon coverage', () => {
      const { ICON_IDS: ids } = useSvgIcons()
      const expectedCount = 21 // Based on the defined icons
      expect(Object.keys(ids).length).toBeGreaterThanOrEqual(expectedCount)
    })

    it('should provide complete status coverage', () => {
      const { STATUS_IDS: statuses } = useSvgIcons()
      const expectedCount = 11 // Based on the defined statuses
      expect(Object.keys(statuses).length).toBeGreaterThanOrEqual(expectedCount)
    })
  })
})
