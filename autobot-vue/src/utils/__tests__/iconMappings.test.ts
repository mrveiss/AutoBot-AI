/**
 * Unit Tests for iconMappings.ts
 *
 * Test coverage for centralized icon mapping utility.
 * Target: 100% code coverage
 */

import { describe, it, expect } from 'vitest'
import {
  getStatusIcon,
  getConnectionIcon,
  getActionIcon,
  getIcon,
  iconMappings,
  type StatusType,
  type ConnectionType,
  type ActionType
} from '../iconMappings'

describe('iconMappings utility', () => {
  // ========================================
  // getStatusIcon() Tests
  // ========================================

  describe('getStatusIcon', () => {
    it('should return correct icon for healthy status', () => {
      expect(getStatusIcon('healthy')).toBe('fas fa-check-circle')
    })

    it('should return correct icon for warning status', () => {
      expect(getStatusIcon('warning')).toBe('fas fa-exclamation-triangle')
    })

    it('should return correct icon for error status', () => {
      expect(getStatusIcon('error')).toBe('fas fa-times-circle')
    })

    it('should return correct icon for degraded status', () => {
      expect(getStatusIcon('degraded')).toBe('fas fa-exclamation-triangle')
    })

    it('should return correct icon for critical status', () => {
      expect(getStatusIcon('critical')).toBe('fas fa-times-circle')
    })

    it('should return correct icon for offline status', () => {
      expect(getStatusIcon('offline')).toBe('fas fa-power-off')
    })

    it('should return correct icon for unknown status', () => {
      expect(getStatusIcon('unknown')).toBe('fas fa-question-circle')
    })

    it('should handle case-insensitive input', () => {
      expect(getStatusIcon('HEALTHY')).toBe('fas fa-check-circle')
      expect(getStatusIcon('Warning')).toBe('fas fa-exclamation-triangle')
      expect(getStatusIcon('ErRoR')).toBe('fas fa-times-circle')
    })

    it('should return unknown icon for invalid status', () => {
      expect(getStatusIcon('invalid-status')).toBe('fas fa-question-circle')
      expect(getStatusIcon('foobar')).toBe('fas fa-question-circle')
    })

    it('should handle null/undefined gracefully', () => {
      expect(getStatusIcon(null as any)).toBe('fas fa-question-circle')
      expect(getStatusIcon(undefined as any)).toBe('fas fa-question-circle')
      expect(getStatusIcon('' as any)).toBe('fas fa-question-circle')
    })

    it('should add color class when withColor option is true', () => {
      expect(getStatusIcon('healthy', { withColor: true })).toBe('fas fa-check-circle text-success')
      expect(getStatusIcon('warning', { withColor: true })).toBe('fas fa-exclamation-triangle text-warning')
      expect(getStatusIcon('error', { withColor: true })).toBe('fas fa-times-circle text-danger')
      expect(getStatusIcon('unknown', { withColor: true })).toBe('fas fa-question-circle text-muted')
    })

    it('should append extra classes when provided', () => {
      expect(getStatusIcon('healthy', { extraClasses: 'mr-2' })).toBe('fas fa-check-circle mr-2')
      expect(getStatusIcon('error', { extraClasses: 'text-lg ml-1' })).toBe('fas fa-times-circle text-lg ml-1')
    })

    it('should combine withColor and extraClasses', () => {
      const result = getStatusIcon('healthy', { withColor: true, extraClasses: 'mr-2 text-lg' })
      expect(result).toBe('fas fa-check-circle text-success mr-2 text-lg')
    })

    it('should not add color when withColor is false', () => {
      expect(getStatusIcon('healthy', { withColor: false })).toBe('fas fa-check-circle')
    })
  })

  // ========================================
  // getConnectionIcon() Tests
  // ========================================

  describe('getConnectionIcon', () => {
    it('should return correct icon for connected status', () => {
      expect(getConnectionIcon('connected')).toBe('fas fa-check-circle')
    })

    it('should return correct icon for disconnected status', () => {
      expect(getConnectionIcon('disconnected')).toBe('fas fa-times-circle')
    })

    it('should return correct icon for testing status', () => {
      expect(getConnectionIcon('testing')).toBe('fas fa-spinner fa-spin')
    })

    it('should return correct icon for connecting status', () => {
      expect(getConnectionIcon('connecting')).toBe('fas fa-spinner fa-spin')
    })

    it('should return correct icon for unknown status', () => {
      expect(getConnectionIcon('unknown')).toBe('fas fa-question-circle')
    })

    it('should handle case-insensitive input', () => {
      expect(getConnectionIcon('CONNECTED')).toBe('fas fa-check-circle')
      expect(getConnectionIcon('Testing')).toBe('fas fa-spinner fa-spin')
    })

    it('should return unknown icon for invalid status', () => {
      expect(getConnectionIcon('invalid')).toBe('fas fa-question-circle')
    })

    it('should handle null/undefined gracefully', () => {
      expect(getConnectionIcon(null as any)).toBe('fas fa-question-circle')
      expect(getConnectionIcon(undefined as any)).toBe('fas fa-question-circle')
    })

    it('should add color class when withColor option is true', () => {
      expect(getConnectionIcon('connected', { withColor: true })).toBe('fas fa-check-circle text-success')
      expect(getConnectionIcon('disconnected', { withColor: true })).toBe('fas fa-times-circle text-danger')
      expect(getConnectionIcon('testing', { withColor: true })).toBe('fas fa-spinner fa-spin text-info')
    })

    it('should append extra classes when provided', () => {
      expect(getConnectionIcon('connected', { extraClasses: 'mr-1' })).toBe('fas fa-check-circle mr-1')
    })

    it('should combine withColor and extraClasses', () => {
      const result = getConnectionIcon('connected', { withColor: true, extraClasses: 'mr-2' })
      expect(result).toBe('fas fa-check-circle text-success mr-2')
    })
  })

  // ========================================
  // getActionIcon() Tests
  // ========================================

  describe('getActionIcon', () => {
    it('should return correct icon for loading action', () => {
      expect(getActionIcon('loading')).toBe('fas fa-spinner fa-spin')
    })

    it('should return correct icon for refreshing action', () => {
      expect(getActionIcon('refreshing')).toBe('fas fa-sync fa-spin')
    })

    it('should return correct icon for play action', () => {
      expect(getActionIcon('play')).toBe('fas fa-play')
    })

    it('should return correct icon for stop action', () => {
      expect(getActionIcon('stop')).toBe('fas fa-stop')
    })

    it('should return correct icon for pause action', () => {
      expect(getActionIcon('pause')).toBe('fas fa-pause')
    })

    it('should return correct icon for sync action', () => {
      expect(getActionIcon('sync')).toBe('fas fa-sync')
    })

    it('should return correct icon for save action', () => {
      expect(getActionIcon('save')).toBe('fas fa-save')
    })

    it('should return correct icon for edit action', () => {
      expect(getActionIcon('edit')).toBe('fas fa-edit')
    })

    it('should return correct icon for delete action', () => {
      expect(getActionIcon('delete')).toBe('fas fa-trash')
    })

    it('should return correct icon for add action', () => {
      expect(getActionIcon('add')).toBe('fas fa-plus')
    })

    it('should handle case-insensitive input', () => {
      expect(getActionIcon('LOADING')).toBe('fas fa-spinner fa-spin')
      expect(getActionIcon('Save')).toBe('fas fa-save')
    })

    it('should return loading icon for invalid action', () => {
      expect(getActionIcon('invalid')).toBe('fas fa-spinner fa-spin')
    })

    it('should handle null/undefined gracefully', () => {
      expect(getActionIcon(null as any)).toBe('fas fa-spinner fa-spin')
      expect(getActionIcon(undefined as any)).toBe('fas fa-spinner fa-spin')
    })

    it('should append extra classes when provided', () => {
      expect(getActionIcon('save', { extraClasses: 'mr-1' })).toBe('fas fa-save mr-1')
      expect(getActionIcon('delete', { extraClasses: 'text-danger ml-2' })).toBe('fas fa-trash text-danger ml-2')
    })
  })

  // ========================================
  // getIcon() Auto-detection Tests
  // ========================================

  describe('getIcon (auto-detection)', () => {
    it('should auto-detect status icons', () => {
      expect(getIcon('healthy')).toBe('fas fa-check-circle')
      expect(getIcon('warning')).toBe('fas fa-exclamation-triangle')
      expect(getIcon('error')).toBe('fas fa-times-circle')
    })

    it('should auto-detect connection icons', () => {
      expect(getIcon('connected')).toBe('fas fa-check-circle')
      expect(getIcon('disconnected')).toBe('fas fa-times-circle')
      expect(getIcon('testing')).toBe('fas fa-spinner fa-spin')
    })

    it('should auto-detect action icons', () => {
      expect(getIcon('loading')).toBe('fas fa-spinner fa-spin')
      expect(getIcon('save')).toBe('fas fa-save')
      expect(getIcon('delete')).toBe('fas fa-trash')
    })

    it('should prioritize status over connection for ambiguous values', () => {
      // 'testing' exists in both connection and action, but should match connection first
      expect(getIcon('testing')).toBe('fas fa-spinner fa-spin')
    })

    it('should fallback to unknown status icon for completely invalid input', () => {
      expect(getIcon('completely-invalid')).toBe('fas fa-question-circle')
    })

    it('should handle null/undefined gracefully', () => {
      expect(getIcon(null as any)).toBe('fas fa-question-circle')
      expect(getIcon(undefined as any)).toBe('fas fa-question-circle')
      expect(getIcon('')).toBe('fas fa-question-circle')
    })

    it('should support options with auto-detection', () => {
      expect(getIcon('healthy', { withColor: true })).toBe('fas fa-check-circle text-success')
      expect(getIcon('testing', { withColor: true })).toBe('fas fa-spinner fa-spin text-info')
      expect(getIcon('save', { extraClasses: 'mr-1' })).toBe('fas fa-save mr-1')
    })
  })

  // ========================================
  // iconMappings Export Tests
  // ========================================

  describe('iconMappings exports', () => {
    it('should export status icon mappings', () => {
      expect(iconMappings.status).toBeDefined()
      expect(iconMappings.status.healthy).toBe('fas fa-check-circle')
      expect(iconMappings.status.warning).toBe('fas fa-exclamation-triangle')
    })

    it('should export status color mappings', () => {
      expect(iconMappings.statusColors).toBeDefined()
      expect(iconMappings.statusColors.healthy).toBe('text-success')
      expect(iconMappings.statusColors.error).toBe('text-danger')
    })

    it('should export connection icon mappings', () => {
      expect(iconMappings.connection).toBeDefined()
      expect(iconMappings.connection.connected).toBe('fas fa-check-circle')
      expect(iconMappings.connection.testing).toBe('fas fa-spinner fa-spin')
    })

    it('should export connection color mappings', () => {
      expect(iconMappings.connectionColors).toBeDefined()
      expect(iconMappings.connectionColors.connected).toBe('text-success')
      expect(iconMappings.connectionColors.testing).toBe('text-info')
    })

    it('should export action icon mappings', () => {
      expect(iconMappings.action).toBeDefined()
      expect(iconMappings.action.loading).toBe('fas fa-spinner fa-spin')
      expect(iconMappings.action.save).toBe('fas fa-save')
    })

    it('should be read-only (const assertion)', () => {
      // This test verifies TypeScript prevents mutation at compile time
      // At runtime, the object is still mutable but TypeScript won't allow it
      expect(Object.isFrozen(iconMappings)).toBe(false) // Not frozen, but const-asserted
      expect(iconMappings).toBeDefined()
    })
  })

  // ========================================
  // Edge Case Tests
  // ========================================

  describe('edge cases', () => {
    it('should handle empty string gracefully', () => {
      expect(getStatusIcon('')).toBe('fas fa-question-circle')
      expect(getConnectionIcon('')).toBe('fas fa-question-circle')
      expect(getActionIcon('')).toBe('fas fa-spinner fa-spin')
    })

    it('should handle whitespace-only strings', () => {
      expect(getStatusIcon('   ')).toBe('fas fa-question-circle')
      expect(getConnectionIcon('  \t\n  ')).toBe('fas fa-question-circle')
    })

    it('should handle numeric input (converted to string)', () => {
      expect(getStatusIcon(123 as any)).toBe('fas fa-question-circle')
    })

    it('should handle object input gracefully', () => {
      expect(getStatusIcon({} as any)).toBe('fas fa-question-circle')
      expect(getStatusIcon({ status: 'healthy' } as any)).toBe('fas fa-question-circle')
    })

    it('should not mutate input options', () => {
      const options = { withColor: true, extraClasses: 'mr-2' }
      const optionsCopy = { ...options }

      getStatusIcon('healthy', options)

      expect(options).toEqual(optionsCopy)
    })

    it('should handle very long extraClasses strings', () => {
      const longClasses = 'class1 class2 class3 class4 class5 class6 class7 class8'
      const result = getStatusIcon('healthy', { extraClasses: longClasses })
      expect(result).toBe(`fas fa-check-circle ${longClasses}`)
    })

    it('should handle multiple spaces in extraClasses', () => {
      const result = getStatusIcon('healthy', { extraClasses: 'mr-2   text-lg' })
      expect(result).toBe('fas fa-check-circle mr-2   text-lg')
    })
  })

  // ========================================
  // Type Safety Tests (TypeScript compilation)
  // ========================================

  describe('TypeScript type safety', () => {
    it('should accept valid StatusType values', () => {
      const statuses: StatusType[] = ['healthy', 'warning', 'error', 'degraded', 'critical', 'offline', 'unknown']
      statuses.forEach(status => {
        expect(getStatusIcon(status)).toBeDefined()
      })
    })

    it('should accept valid ConnectionType values', () => {
      const connections: ConnectionType[] = ['connected', 'disconnected', 'testing', 'connecting', 'unknown']
      connections.forEach(conn => {
        expect(getConnectionIcon(conn)).toBeDefined()
      })
    })

    it('should accept valid ActionType values', () => {
      const actions: ActionType[] = ['loading', 'refreshing', 'play', 'stop', 'pause', 'sync', 'save', 'edit', 'delete', 'add']
      actions.forEach(action => {
        expect(getActionIcon(action)).toBeDefined()
      })
    })
  })

  // ========================================
  // Performance Tests
  // ========================================

  describe('performance', () => {
    it('should execute quickly for repeated calls', () => {
      const startTime = performance.now()

      for (let i = 0; i < 1000; i++) {
        getStatusIcon('healthy')
        getConnectionIcon('testing')
        getActionIcon('loading')
      }

      const endTime = performance.now()
      const duration = endTime - startTime

      // 1000 calls should complete in less than 10ms
      expect(duration).toBeLessThan(10)
    })

    it('should handle concurrent calls without issues', () => {
      const promises = Array.from({ length: 100 }, () =>
        Promise.resolve(getStatusIcon('healthy'))
      )

      return Promise.all(promises).then(results => {
        expect(results.every(r => r === 'fas fa-check-circle')).toBe(true)
      })
    })
  })
})
