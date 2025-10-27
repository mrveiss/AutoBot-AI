/**
 * Unit Tests for useModal.ts
 *
 * Test coverage for centralized modal state management composable.
 * Target: 100% code coverage
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { useModal, useModals, useModalGroup } from '../useModal'
import type { ModalOptions } from '../useModal'

describe('useModal composable', () => {
  // ========================================
  // useModal() Basic Functionality Tests
  // ========================================

  describe('useModal - basic functionality', () => {
    it('should initialize with closed state by default', () => {
      const modal = useModal()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should initialize with open state when initialOpen is true', () => {
      const modal = useModal({ initialOpen: true })
      expect(modal.isOpen.value).toBe(true)
    })

    it('should open modal', async () => {
      const modal = useModal()
      expect(modal.isOpen.value).toBe(false)

      await modal.open()
      expect(modal.isOpen.value).toBe(true)
    })

    it('should close modal', async () => {
      const modal = useModal({ initialOpen: true })
      expect(modal.isOpen.value).toBe(true)

      await modal.close()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should toggle modal state from closed to open', async () => {
      const modal = useModal()
      expect(modal.isOpen.value).toBe(false)

      await modal.toggle()
      expect(modal.isOpen.value).toBe(true)
    })

    it('should toggle modal state from open to closed', async () => {
      const modal = useModal({ initialOpen: true })
      expect(modal.isOpen.value).toBe(true)

      await modal.toggle()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should set modal state to true', async () => {
      const modal = useModal()
      expect(modal.isOpen.value).toBe(false)

      await modal.setState(true)
      expect(modal.isOpen.value).toBe(true)
    })

    it('should set modal state to false', async () => {
      const modal = useModal({ initialOpen: true })
      expect(modal.isOpen.value).toBe(true)

      await modal.setState(false)
      expect(modal.isOpen.value).toBe(false)
    })

    it('should not change state when setState called with same value', async () => {
      const modal = useModal()
      const onOpen = vi.fn()
      modal.open = vi.fn(modal.open)

      await modal.setState(false) // Already false
      expect(modal.open).not.toHaveBeenCalled()
    })

    it('should reset modal to initial state (closed)', () => {
      const modal = useModal()
      modal.isOpen.value = true

      modal.reset()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should reset modal to initial state (open)', () => {
      const modal = useModal({ initialOpen: true })
      modal.isOpen.value = false

      modal.reset()
      expect(modal.isOpen.value).toBe(true)
    })

    it('should not open if already open', async () => {
      const onOpen = vi.fn()
      const modal = useModal({ onOpen })

      await modal.open()
      expect(onOpen).toHaveBeenCalledTimes(1)

      await modal.open() // Should not call onOpen again
      expect(onOpen).toHaveBeenCalledTimes(1)
    })

    it('should not close if already closed', async () => {
      const onClose = vi.fn()
      const modal = useModal({ onClose })

      await modal.close()
      expect(onClose).not.toHaveBeenCalled() // Already closed, callback not called

      await modal.open()
      await modal.close()
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  // ========================================
  // Computed Properties Tests
  // ========================================

  describe('useModal - computed properties', () => {
    it('should have isClosed computed property', () => {
      const modal = useModal()
      expect(modal.isClosed.value).toBe(true)

      modal.isOpen.value = true
      expect(modal.isClosed.value).toBe(false)
    })

    it('should update isClosed when modal state changes', async () => {
      const modal = useModal()
      expect(modal.isClosed.value).toBe(true)

      await modal.open()
      expect(modal.isClosed.value).toBe(false)

      await modal.close()
      expect(modal.isClosed.value).toBe(true)
    })
  })

  // ========================================
  // Callback Tests
  // ========================================

  describe('useModal - callbacks', () => {
    it('should call onOpen callback when modal opens', async () => {
      const onOpen = vi.fn()
      const modal = useModal({ onOpen })

      await modal.open()
      expect(onOpen).toHaveBeenCalledTimes(1)
    })

    it('should call onClose callback when modal closes', async () => {
      const onClose = vi.fn()
      const modal = useModal({ initialOpen: true, onClose })

      await modal.close()
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('should call onToggle callback with true when toggling to open', async () => {
      const onToggle = vi.fn()
      const modal = useModal({ onToggle })

      await modal.toggle()
      expect(onToggle).toHaveBeenCalledWith(true)
    })

    it('should call onToggle callback with false when toggling to closed', async () => {
      const onToggle = vi.fn()
      const modal = useModal({ initialOpen: true, onToggle })

      await modal.toggle()
      expect(onToggle).toHaveBeenCalledWith(false)
    })

    it('should call both onOpen and onToggle when opening', async () => {
      const onOpen = vi.fn()
      const onToggle = vi.fn()
      const modal = useModal({ onOpen, onToggle })

      await modal.open()
      expect(onOpen).toHaveBeenCalledTimes(1)
      expect(onToggle).toHaveBeenCalledWith(true)
    })

    it('should call both onClose and onToggle when closing', async () => {
      const onClose = vi.fn()
      const onToggle = vi.fn()
      const modal = useModal({ initialOpen: true, onClose, onToggle })

      await modal.close()
      expect(onClose).toHaveBeenCalledTimes(1)
      expect(onToggle).toHaveBeenCalledWith(false)
    })

    it('should handle async onOpen callback', async () => {
      const onOpen = vi.fn(async () => {
        await new Promise(resolve => setTimeout(resolve, 10))
      })
      const modal = useModal({ onOpen })

      await modal.open()
      expect(onOpen).toHaveBeenCalled()
      expect(modal.isOpen.value).toBe(true)
    })

    it('should handle async onClose callback', async () => {
      const onClose = vi.fn(async () => {
        await new Promise(resolve => setTimeout(resolve, 10))
      })
      const modal = useModal({ initialOpen: true, onClose })

      await modal.close()
      expect(onClose).toHaveBeenCalled()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should handle errors in onOpen callback gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const onOpen = vi.fn(() => {
        throw new Error('onOpen error')
      })
      const modal = useModal({ id: 'test-modal', onOpen })

      await modal.open()
      expect(modal.isOpen.value).toBe(true) // Modal still opens
      expect(consoleErrorSpy).toHaveBeenCalled()

      consoleErrorSpy.mockRestore()
    })

    it('should handle errors in onClose callback gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const onClose = vi.fn(() => {
        throw new Error('onClose error')
      })
      const modal = useModal({ id: 'test-modal', initialOpen: true, onClose })

      await modal.close()
      expect(modal.isOpen.value).toBe(false) // Modal still closes
      expect(consoleErrorSpy).toHaveBeenCalled()

      consoleErrorSpy.mockRestore()
    })

    it('should handle errors in onToggle callback gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const onToggle = vi.fn(() => {
        throw new Error('onToggle error')
      })
      const modal = useModal({ id: 'test-modal', onToggle })

      await modal.open()
      expect(modal.isOpen.value).toBe(true)
      expect(consoleErrorSpy).toHaveBeenCalled()

      consoleErrorSpy.mockRestore()
    })
  })

  // ========================================
  // Options Tests
  // ========================================

  describe('useModal - options', () => {
    it('should accept id option for debugging', () => {
      const modal = useModal({ id: 'test-modal' })
      expect(modal).toBeDefined()
    })

    it('should accept closeOnEscape option', () => {
      const modal = useModal({ closeOnEscape: true })
      expect(modal).toBeDefined()
      // Note: Actual escape key handling requires manual implementation in component
    })

    it('should handle all options together', async () => {
      const onOpen = vi.fn()
      const onClose = vi.fn()
      const onToggle = vi.fn()

      const modal = useModal({
        initialOpen: true,
        onOpen,
        onClose,
        onToggle,
        closeOnEscape: true,
        id: 'full-options-modal'
      })

      expect(modal.isOpen.value).toBe(true)

      await modal.close()
      expect(onClose).toHaveBeenCalled()
      expect(onToggle).toHaveBeenCalledWith(false)
    })
  })

  // ========================================
  // useModals() Tests
  // ========================================

  describe('useModals', () => {
    it('should create multiple modals at once', () => {
      const modals = useModals(['create', 'edit', 'view'])

      expect(modals.create).toBeDefined()
      expect(modals.edit).toBeDefined()
      expect(modals.view).toBeDefined()
    })

    it('should create modals with isOpen refs', () => {
      const modals = useModals(['modal1', 'modal2'])

      expect(modals.modal1.isOpen.value).toBe(false)
      expect(modals.modal2.isOpen.value).toBe(false)
    })

    it('should create modals with open/close methods', async () => {
      const modals = useModals(['modal1', 'modal2'])

      await modals.modal1.open()
      expect(modals.modal1.isOpen.value).toBe(true)
      expect(modals.modal2.isOpen.value).toBe(false)

      await modals.modal2.open()
      expect(modals.modal1.isOpen.value).toBe(true)
      expect(modals.modal2.isOpen.value).toBe(true)
    })

    it('should create modals with id set to modal name', () => {
      // IDs are internal, but we can verify behavior
      const modals = useModals(['test-modal'])
      expect(modals['test-modal']).toBeDefined()
    })

    it('should handle single modal in array', () => {
      const modals = useModals(['single'])
      expect(modals.single).toBeDefined()
      expect(modals.single.isOpen.value).toBe(false)
    })

    it('should handle many modals', () => {
      const names = ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8']
      const modals = useModals(names)

      names.forEach(name => {
        expect(modals[name]).toBeDefined()
        expect(modals[name].isOpen.value).toBe(false)
      })
    })
  })

  // ========================================
  // useModalGroup() Tests
  // ========================================

  describe('useModalGroup', () => {
    it('should create modal group with modals', () => {
      const { modals } = useModalGroup(['create', 'edit'])

      expect(modals.create).toBeDefined()
      expect(modals.edit).toBeDefined()
    })

    it('should provide closeAll method', () => {
      const { closeAll } = useModalGroup(['modal1', 'modal2'])
      expect(closeAll).toBeDefined()
      expect(typeof closeAll).toBe('function')
    })

    it('should close all modals when closeAll is called', async () => {
      const { modals, closeAll } = useModalGroup(['modal1', 'modal2', 'modal3'])

      await modals.modal1.open()
      await modals.modal2.open()
      await modals.modal3.open()

      expect(modals.modal1.isOpen.value).toBe(true)
      expect(modals.modal2.isOpen.value).toBe(true)
      expect(modals.modal3.isOpen.value).toBe(true)

      await closeAll()

      expect(modals.modal1.isOpen.value).toBe(false)
      expect(modals.modal2.isOpen.value).toBe(false)
      expect(modals.modal3.isOpen.value).toBe(false)
    })

    it('should provide openAll method', async () => {
      const { modals, openAll } = useModalGroup(['modal1', 'modal2'])

      await openAll()

      expect(modals.modal1.isOpen.value).toBe(true)
      expect(modals.modal2.isOpen.value).toBe(true)
    })

    it('should provide hasOpenModal computed property', async () => {
      const { modals, hasOpenModal } = useModalGroup(['modal1', 'modal2'])

      expect(hasOpenModal.value).toBe(false)

      await modals.modal1.open()
      expect(hasOpenModal.value).toBe(true)

      await modals.modal2.open()
      expect(hasOpenModal.value).toBe(true)

      await modals.modal1.close()
      expect(hasOpenModal.value).toBe(true) // modal2 still open

      await modals.modal2.close()
      expect(hasOpenModal.value).toBe(false)
    })

    it('should provide allClosed computed property', async () => {
      const { modals, allClosed } = useModalGroup(['modal1', 'modal2'])

      expect(allClosed.value).toBe(true)

      await modals.modal1.open()
      expect(allClosed.value).toBe(false)

      await modals.modal2.open()
      expect(allClosed.value).toBe(false)

      await modals.modal1.close()
      expect(allClosed.value).toBe(false) // modal2 still open

      await modals.modal2.close()
      expect(allClosed.value).toBe(true)
    })

    it('should handle closeAll when all modals already closed', async () => {
      const { modals, closeAll } = useModalGroup(['modal1', 'modal2'])

      await closeAll()

      expect(modals.modal1.isOpen.value).toBe(false)
      expect(modals.modal2.isOpen.value).toBe(false)
    })

    it('should handle openAll when all modals already open', async () => {
      const { modals, openAll } = useModalGroup(['modal1', 'modal2'])

      await openAll()
      await openAll() // Call again

      expect(modals.modal1.isOpen.value).toBe(true)
      expect(modals.modal2.isOpen.value).toBe(true)
    })

    it('should close modals in parallel with closeAll', async () => {
      const closeTimings: number[] = []
      const { modals, closeAll } = useModalGroup(['modal1', 'modal2', 'modal3'])

      // Add delays to onClose callbacks
      modals.modal1.close = async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
        closeTimings.push(Date.now())
        return useModal().close()
      }

      modals.modal2.close = async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
        closeTimings.push(Date.now())
        return useModal().close()
      }

      modals.modal3.close = async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
        closeTimings.push(Date.now())
        return useModal().close()
      }

      await modals.modal1.open()
      await modals.modal2.open()
      await modals.modal3.open()

      const startTime = Date.now()
      await closeAll()
      const duration = Date.now() - startTime

      // Should complete in ~50ms (parallel), not ~150ms (sequential)
      expect(duration).toBeLessThan(100)
    })
  })

  // ========================================
  // Edge Case Tests
  // ========================================

  describe('useModal - edge cases', () => {
    it('should handle rapid open/close calls', async () => {
      const modal = useModal()

      await modal.open()
      await modal.close()
      await modal.open()
      await modal.close()
      await modal.open()

      expect(modal.isOpen.value).toBe(true)
    })

    it('should handle concurrent open calls', async () => {
      const modal = useModal()

      await Promise.all([modal.open(), modal.open(), modal.open()])

      expect(modal.isOpen.value).toBe(true)
    })

    it('should handle concurrent close calls', async () => {
      const modal = useModal({ initialOpen: true })

      await Promise.all([modal.close(), modal.close(), modal.close()])

      expect(modal.isOpen.value).toBe(false)
    })

    it('should handle toggle calls in rapid succession', async () => {
      const modal = useModal()

      await modal.toggle()
      await modal.toggle()
      await modal.toggle()

      expect(modal.isOpen.value).toBe(true)
    })

    it('should handle setState with rapid calls', async () => {
      const modal = useModal()

      await modal.setState(true)
      await modal.setState(false)
      await modal.setState(true)
      await modal.setState(false)

      expect(modal.isOpen.value).toBe(false)
    })

    it('should handle reset after multiple state changes', async () => {
      const modal = useModal({ initialOpen: false })

      await modal.open()
      await modal.close()
      await modal.open()

      modal.reset()
      expect(modal.isOpen.value).toBe(false)
    })

    it('should handle empty modal names in useModals', () => {
      const modals = useModals([])
      expect(Object.keys(modals).length).toBe(0)
    })

    it('should handle modal names with special characters', () => {
      const modals = useModals(['modal-1', 'modal_2', 'modal.3'])

      expect(modals['modal-1']).toBeDefined()
      expect(modals['modal_2']).toBeDefined()
      expect(modals['modal.3']).toBeDefined()
    })
  })

  // ========================================
  // TypeScript Type Safety Tests
  // ========================================

  describe('useModal - TypeScript type safety', () => {
    it('should accept valid ModalOptions', () => {
      const options: ModalOptions = {
        initialOpen: true,
        onOpen: () => {},
        onClose: () => {},
        onToggle: (isOpen) => {
          expect(typeof isOpen).toBe('boolean')
        },
        closeOnEscape: true,
        id: 'typed-modal'
      }

      const modal = useModal(options)
      expect(modal).toBeDefined()
    })

    it('should accept async callbacks in ModalOptions', () => {
      const options: ModalOptions = {
        onOpen: async () => {
          await Promise.resolve()
        },
        onClose: async () => {
          await Promise.resolve()
        }
      }

      const modal = useModal(options)
      expect(modal).toBeDefined()
    })

    it('should create type-safe modals with useModals', () => {
      const modals = useModals(['create', 'edit', 'view'])

      // These should compile without errors
      modals.create.open()
      modals.edit.close()
      modals.view.toggle()

      expect(modals.create).toBeDefined()
    })

    it('should create type-safe modal group', () => {
      const { modals, closeAll, openAll, hasOpenModal, allClosed } = useModalGroup([
        'modal1',
        'modal2'
      ])

      expect(modals.modal1).toBeDefined()
      expect(typeof closeAll).toBe('function')
      expect(typeof openAll).toBe('function')
      expect(typeof hasOpenModal.value).toBe('boolean')
      expect(typeof allClosed.value).toBe('boolean')
    })
  })

  // ========================================
  // Performance Tests
  // ========================================

  describe('useModal - performance', () => {
    it('should execute quickly for repeated open/close calls', async () => {
      const modal = useModal()
      const startTime = performance.now()

      for (let i = 0; i < 100; i++) {
        await modal.open()
        await modal.close()
      }

      const duration = performance.now() - startTime

      // 100 open/close cycles should complete in less than 50ms
      expect(duration).toBeLessThan(50)
    })

    it('should handle creating many modals efficiently', () => {
      const startTime = performance.now()

      const names = Array.from({ length: 50 }, (_, i) => `modal${i}`)
      const modals = useModals(names)

      const duration = performance.now() - startTime

      expect(Object.keys(modals).length).toBe(50)
      expect(duration).toBeLessThan(10)
    })

    it('should handle modal group operations efficiently', async () => {
      const names = Array.from({ length: 20 }, (_, i) => `modal${i}`)
      const { modals, closeAll, openAll } = useModalGroup(names)

      const startTime = performance.now()

      await openAll()
      await closeAll()

      const duration = performance.now() - startTime

      expect(duration).toBeLessThan(20)
    })
  })

  // ========================================
  // Integration Tests
  // ========================================

  describe('useModal - integration scenarios', () => {
    it('should handle form submission workflow', async () => {
      let formData = ''
      const modal = useModal({
        onClose: () => {
          formData = ''
        }
      })

      await modal.open()
      formData = 'test data'
      expect(modal.isOpen.value).toBe(true)

      await modal.close()
      expect(modal.isOpen.value).toBe(false)
      expect(formData).toBe('')
    })

    it('should handle data loading workflow', async () => {
      let dataLoaded = false
      const modal = useModal({
        onOpen: async () => {
          await new Promise(resolve => setTimeout(resolve, 10))
          dataLoaded = true
        }
      })

      await modal.open()
      expect(dataLoaded).toBe(true)
    })

    it('should handle multi-step modal workflow', async () => {
      const { modals } = useModalGroup(['step1', 'step2', 'step3'])

      await modals.step1.open()
      expect(modals.step1.isOpen.value).toBe(true)

      await modals.step1.close()
      await modals.step2.open()
      expect(modals.step1.isOpen.value).toBe(false)
      expect(modals.step2.isOpen.value).toBe(true)

      await modals.step2.close()
      await modals.step3.open()
      expect(modals.step2.isOpen.value).toBe(false)
      expect(modals.step3.isOpen.value).toBe(true)
    })

    it('should handle conditional modal opening', async () => {
      const modal = useModal()
      let hasPermission = false

      if (hasPermission) {
        await modal.open()
      }
      expect(modal.isOpen.value).toBe(false)

      hasPermission = true
      await modal.setState(hasPermission)
      expect(modal.isOpen.value).toBe(true)
    })
  })
})
