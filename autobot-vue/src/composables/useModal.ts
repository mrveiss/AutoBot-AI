/**
 * Modal State Management Composable
 *
 * Centralized modal/dialog state management for Vue 3 applications.
 * Eliminates duplicate open/close logic across 35+ modals.
 *
 * @see analysis/frontend-refactoring/FRONTEND_REFACTORING_EXAMPLES.md
 *
 * Features:
 * - Simple open/close/toggle API
 * - Optional onOpen/onClose callbacks
 * - Type-safe modal state management
 * - Minimal boilerplate
 *
 * Usage:
 * ```typescript
 * import { useModal } from '@/composables/useModal'
 *
 * // Create modal state
 * const createModal = useModal()
 * const editModal = useModal({
 *   onOpen: () => console.log('Edit modal opened'),
 *   onClose: () => resetForm()
 * })
 *
 * // In template
 * <div v-if="createModal.isOpen">...</div>
 * <button @click="createModal.open()">Open</button>
 * <button @click="createModal.close()">Close</button>
 * ```
 */

import { ref, computed, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useModal
const logger = createLogger('useModal')

export interface ModalOptions {
  /**
   * Initial open state (default: false)
   */
  initialOpen?: boolean

  /**
   * Callback executed when modal opens
   */
  onOpen?: () => void | Promise<void>

  /**
   * Callback executed when modal closes
   */
  onClose?: () => void | Promise<void>

  /**
   * Callback executed when modal toggles
   * @param isOpen - New state after toggle
   */
  onToggle?: (isOpen: boolean) => void | Promise<void>

  /**
   * Auto-close on escape key (default: false)
   * Note: Requires manual keyboard listener in component
   */
  closeOnEscape?: boolean

  /**
   * Modal identifier for debugging/logging
   */
  id?: string
}

export interface UseModalReturn {
  /**
   * Reactive modal open state
   */
  isOpen: Ref<boolean>

  /**
   * Computed boolean indicating if modal is closed
   */
  isClosed: Readonly<Ref<boolean>>

  /**
   * Open the modal
   */
  open: () => Promise<void>

  /**
   * Close the modal
   */
  close: () => Promise<void>

  /**
   * Toggle modal state (open <-> closed)
   */
  toggle: () => Promise<void>

  /**
   * Set modal state directly
   * @param state - New open state
   */
  setState: (state: boolean) => Promise<void>

  /**
   * Reset modal to initial state
   */
  reset: () => void
}

/**
 * Create modal state management
 *
 * @param options - Modal configuration options
 * @returns Modal state and control methods
 *
 * @example
 * ```typescript
 * // Basic usage
 * const modal = useModal()
 * modal.open()  // Opens modal
 * modal.close() // Closes modal
 *
 * // With callbacks
 * const editModal = useModal({
 *   onOpen: async () => {
 *     await loadData()
 *   },
 *   onClose: () => {
 *     resetForm()
 *   }
 * })
 *
 * // With initial state
 * const welcomeModal = useModal({
 *   initialOpen: true,
 *   id: 'welcome-modal'
 * })
 *
 * // In template
 * <div v-if="modal.isOpen">
 *   <button @click="modal.close()">Close</button>
 * </div>
 * ```
 */
export function useModal(options: ModalOptions = {}): UseModalReturn {
  const {
    initialOpen = false,
    onOpen,
    onClose,
    onToggle,
    id
  } = options

  // Reactive state
  const isOpen = ref<boolean>(initialOpen)
  const initialState = initialOpen

  // Computed properties
  const isClosed = computed(() => !isOpen.value)

  // Log helper for debugging
  const log = (action: string) => {
    if (id && import.meta.env.DEV) {
      logger.debug(`[${id}] ${action}`)
    }
  }

  /**
   * Open the modal
   */
  const open = async (): Promise<void> => {
    if (isOpen.value) return // Already open

    isOpen.value = true
    log('opened')

    // Execute onOpen callback
    if (onOpen) {
      try {
        await onOpen()
      } catch (error) {
        logger.error(`[${id || 'default'}] Error in onOpen callback:`, error)
      }
    }

    // Execute onToggle callback
    if (onToggle) {
      try {
        await onToggle(true)
      } catch (error) {
        logger.error(`[${id || 'default'}] Error in onToggle callback:`, error)
      }
    }
  }

  /**
   * Close the modal
   */
  const close = async (): Promise<void> => {
    if (!isOpen.value) return // Already closed

    isOpen.value = false
    log('closed')

    // Execute onClose callback
    if (onClose) {
      try {
        await onClose()
      } catch (error) {
        logger.error(`[${id || 'default'}] Error in onClose callback:`, error)
      }
    }

    // Execute onToggle callback
    if (onToggle) {
      try {
        await onToggle(false)
      } catch (error) {
        logger.error(`[${id || 'default'}] Error in onToggle callback:`, error)
      }
    }
  }

  /**
   * Toggle modal state
   */
  const toggle = async (): Promise<void> => {
    if (isOpen.value) {
      await close()
    } else {
      await open()
    }
  }

  /**
   * Set modal state directly
   * @param state - New open state
   */
  const setState = async (state: boolean): Promise<void> => {
    if (state === isOpen.value) return // No change

    if (state) {
      await open()
    } else {
      await close()
    }
  }

  /**
   * Reset modal to initial state
   */
  const reset = (): void => {
    isOpen.value = initialState
    log('reset')
  }

  return {
    isOpen,
    isClosed,
    open,
    close,
    toggle,
    setState,
    reset
  }
}

/**
 * Create multiple modals at once
 *
 * @param names - Array of modal names
 * @returns Object with modal instances keyed by name
 *
 * @example
 * ```typescript
 * const modals = useModals(['create', 'edit', 'view', 'delete'])
 *
 * modals.create.open()
 * modals.edit.close()
 * modals.view.isOpen // ref(boolean)
 * ```
 */
export function useModals<T extends string>(
  names: T[]
): Record<T, UseModalReturn> {
  const modals: Record<string, UseModalReturn> = {}

  for (const name of names) {
    modals[name] = useModal({ id: name })
  }

  return modals as Record<T, UseModalReturn>
}

/**
 * Create a modal group with shared close behavior
 *
 * @param names - Array of modal names in the group
 * @returns Modal instances plus closeAll method
 *
 * @example
 * ```typescript
 * const { modals, closeAll } = useModalGroup(['create', 'edit', 'view'])
 *
 * modals.create.open()
 * modals.edit.open()
 *
 * // Close all modals in group
 * closeAll()
 * ```
 */
export function useModalGroup<T extends string>(names: T[]) {
  const modals = useModals(names)

  /**
   * Close all modals in the group
   */
  const closeAll = async (): Promise<void> => {
    // Issue #156 Fix: Add type assertion for Object.values result
    const closePromises = (Object.values(modals) as UseModalReturn[]).map(modal => modal.close())
    await Promise.all(closePromises)
  }

  /**
   * Open all modals in the group
   */
  const openAll = async (): Promise<void> => {
    // Issue #156 Fix: Add type assertion for Object.values result
    const openPromises = (Object.values(modals) as UseModalReturn[]).map(modal => modal.open())
    await Promise.all(openPromises)
  }

  /**
   * Check if any modal in group is open
   */
  const hasOpenModal = computed(() =>
    // Issue #156 Fix: Add type assertion for Object.values result
    (Object.values(modals) as UseModalReturn[]).some(modal => modal.isOpen.value)
  )

  /**
   * Check if all modals in group are closed
   */
  const allClosed = computed(() =>
    // Issue #156 Fix: Add type assertion for Object.values result
    (Object.values(modals) as UseModalReturn[]).every(modal => !modal.isOpen.value)
  )

  return {
    modals,
    closeAll,
    openAll,
    hasOpenModal,
    allClosed
  }
}
