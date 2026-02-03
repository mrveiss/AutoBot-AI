/**
 * LocalStorage Composable
 *
 * Centralized localStorage management to eliminate duplicate storage logic across components.
 * Provides type-safe, reactive, SSR-compatible localStorage with automatic JSON handling.
 *
 * ⚠️ SECURITY WARNING:
 * localStorage is NOT secure storage. Data is:
 * - Stored in plain text (not encrypted)
 * - Accessible to all scripts on the same domain
 * - Visible in browser DevTools
 * - Persists across sessions
 *
 * DO NOT store sensitive data like:
 * - Passwords or credentials
 * - API keys or tokens (use httpOnly cookies instead)
 * - Personal identifiable information (PII)
 * - Credit card or payment information
 *
 * Use localStorage only for:
 * - User preferences and settings
 * - Non-sensitive UI state
 * - Cache data that can be safely exposed
 *
 * Features:
 * - Reactive localStorage with automatic Vue integration
 * - Type-safe with TypeScript generics
 * - Automatic JSON serialization/deserialization
 * - Error handling (quota exceeded, parse errors)
 * - SSR safety (no errors in server-side rendering)
 * - Cross-tab synchronization via storage events
 * - Default values with type inference
 * - Custom serializer/deserializer support
 * - Raw mode for string-only storage
 * - Remove/clear functionality
 * - OnError callbacks for error handling
 *
 * Usage:
 * ```typescript
 * import { useLocalStorage } from '@/composables/useLocalStorage'
 *
 * // Basic usage with auto-JSON
 * const user = useLocalStorage('user', { name: 'Guest', id: 0 })
 * user.value = { name: 'John', id: 123 } // Automatically saves to localStorage
 *
 * // String storage (raw mode)
 * const token = useLocalStorage('auth-token', '', { raw: true })
 *
 * // With error handling
 * const settings = useLocalStorage('settings', {}, {
 *   onError: (error) => console.error('Storage error:', error)
 * })
 *
 * // Remove value
 * user.value = null // Removes from localStorage
 * ```
 */

import { ref, watch, onUnmounted, getCurrentInstance, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useLocalStorage
const logger = createLogger('useLocalStorage')

// ========================================
// Types & Interfaces
// ========================================

export interface UseLocalStorageOptions<T> {
  /**
   * Use raw string storage without JSON serialization
   * Default: false (uses JSON)
   */
  raw?: boolean

  /**
   * Custom serializer function (only used if raw is false)
   * Default: JSON.stringify
   */
  serializer?: (value: T) => string

  /**
   * Custom deserializer function (only used if raw is false)
   * Default: JSON.parse
   */
  deserializer?: (value: string) => T

  /**
   * Listen for storage events from other tabs/windows
   * Default: true
   */
  listenToStorageChanges?: boolean

  /**
   * Error callback for localStorage operations
   * Called on quota exceeded, parse errors, etc.
   */
  onError?: (error: Error) => void

  /**
   * Merge strategy when storage event is received
   * 'overwrite' - Replace local value with storage value
   * 'ignore' - Keep local value unchanged
   * Default: 'overwrite'
   */
  mergeStrategy?: 'overwrite' | 'ignore'

  /**
   * Deep clone values to prevent reference mutations
   * Default: false (for performance)
   */
  deep?: boolean
}

// ========================================
// SSR Safety Helpers
// ========================================

/**
 * Check if localStorage is available (SSR safe)
 */
function isLocalStorageAvailable(): boolean {
  try {
    if (typeof window === 'undefined' || typeof localStorage === 'undefined') {
      return false
    }

    // Test if localStorage actually works (can fail in private browsing)
    const testKey = '__localStorage_test__'
    localStorage.setItem(testKey, 'test')
    localStorage.removeItem(testKey)
    return true
  } catch {
    return false
  }
}

// ========================================
// Default Serializers
// ========================================

const defaultSerializer = <T>(value: T): string => JSON.stringify(value)
const defaultDeserializer = <T>(value: string): T => JSON.parse(value)

// ========================================
// Main Composable
// ========================================

/**
 * Reactive localStorage with automatic JSON handling and cross-tab sync
 *
 * @param key - localStorage key
 * @param defaultValue - Default value when key doesn't exist
 * @param options - Configuration options
 * @returns Reactive localStorage reference and utilities
 *
 * @example Basic object storage
 * ```typescript
 * interface User {
 *   name: string
 *   id: number
 * }
 *
 * const user = useLocalStorage<User>('user', { name: 'Guest', id: 0 })
 *
 * // Update value (auto-saves to localStorage)
 * user.value = { name: 'John', id: 123 }
 *
 * // Remove from storage
 * user.value = null
 * ```
 *
 * @example String storage (raw mode)
 * ```typescript
 * const token = useLocalStorage('auth-token', '', { raw: true })
 * token.value = 'abc123'
 * ```
 *
 * @example With error handling
 * ```typescript
 * const settings = useLocalStorage('settings', {}, {
 *   onError: (error) => {
 *     if (error.name === 'QuotaExceededError') {
 *       console.error('localStorage quota exceeded!')
 *     }
 *   }
 * })
 * ```
 *
 * @example Custom serialization
 * ```typescript
 * const date = useLocalStorage('last-visit', new Date(), {
 *   serializer: (date) => date.toISOString(),
 *   deserializer: (str) => new Date(str)
 * })
 * ```
 */
export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
  options: UseLocalStorageOptions<T> = {}
): Ref<T | null> {
  // Validate key
  if (!key || typeof key !== 'string') {
    throw new Error(`[useLocalStorage] Invalid key: "${key}". Key must be a non-empty string.`)
  }

  const {
    raw = false,
    serializer = defaultSerializer,
    deserializer = defaultDeserializer,
    listenToStorageChanges = true,
    onError,
    mergeStrategy = 'overwrite',
    deep = false
  } = options

  // Check localStorage availability
  const isSupported = isLocalStorageAvailable()

  // ========================================
  // Read from localStorage
  // ========================================

  const readValue = (): T | null => {
    // SSR safety - return default if not available
    if (!isSupported) {
      return defaultValue
    }

    try {
      const item = localStorage.getItem(key)

      // No stored value - return default
      if (item === null) {
        return defaultValue
      }

      // Raw mode - return string directly
      if (raw) {
        return item as unknown as T
      }

      // JSON mode - deserialize
      const deserialized = deserializer(item)

      // Deep clone if requested (prevents reference mutations)
      return deep ? JSON.parse(JSON.stringify(deserialized)) : deserialized
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error))

      // Call error handler if provided
      if (onError) {
        onError(err)
      } else {
        logger.error(`Error reading key "${key}":`, err)
      }

      // Return default on error
      return defaultValue
    }
  }

  // ========================================
  // Write to localStorage
  // ========================================

  const writeValue = (value: T | null): void => {
    // SSR safety - skip if not available
    if (!isSupported) {
      return
    }

    try {
      // Null value - remove from storage
      if (value === null) {
        localStorage.removeItem(key)
        return
      }

      // Raw mode - store string directly
      if (raw) {
        localStorage.setItem(key, value as unknown as string)
        return
      }

      // JSON mode - serialize and store
      const serialized = serializer(value)
      localStorage.setItem(key, serialized)
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error))

      // Check for quota exceeded error
      if (err.name === 'QuotaExceededError' || err.message.includes('quota')) {
        const quotaError = new Error(
          `[useLocalStorage] localStorage quota exceeded for key "${key}". ` +
            `Consider removing old data or using a different storage solution.`
        )
        quotaError.name = 'QuotaExceededError'

        if (onError) {
          onError(quotaError)
        } else {
          logger.error(quotaError.message)
        }
      } else {
        // Other errors (serialization, etc.)
        if (onError) {
          onError(err)
        } else {
          logger.error(`Error writing key "${key}":`, err)
        }
      }
    }
  }

  // ========================================
  // Create Reactive Reference
  // ========================================

  const data = ref<T | null>(readValue()) as Ref<T | null>

  // Watch for changes and write to localStorage
  watch(
    data,
    (newValue) => {
      writeValue(newValue)
    },
    { deep: deep }
  )

  // ========================================
  // Cross-Tab Synchronization
  // ========================================

  if (isSupported && listenToStorageChanges) {
    const handleStorageChange = (event: StorageEvent): void => {
      // Only respond to changes for our key
      if (event.key !== key) {
        return
      }

      // Key was removed in another tab
      if (event.newValue === null) {
        if (mergeStrategy === 'overwrite') {
          data.value = null
        }
        return
      }

      // Key was changed in another tab
      if (mergeStrategy === 'overwrite') {
        try {
          // Raw mode - use string directly
          if (raw) {
            data.value = event.newValue as unknown as T
            return
          }

          // JSON mode - deserialize
          const deserialized = deserializer(event.newValue)
          data.value = deep ? JSON.parse(JSON.stringify(deserialized)) : deserialized
        } catch (error) {
          const err = error instanceof Error ? error : new Error(String(error))

          if (onError) {
            onError(err)
          } else {
            logger.error(
              `Error parsing storage event for key "${key}":`,
              err
            )
          }
        }
      }
    }

    // Listen for storage events from other tabs/windows
    window.addEventListener('storage', handleStorageChange)

    // Cleanup on component unmount to prevent memory leaks
    const instance = getCurrentInstance()
    if (instance) {
      onUnmounted(() => {
        window.removeEventListener('storage', handleStorageChange)
      })
    } else {
      logger.warn(
        `Key "${key}" used outside component context. ` +
        `Auto-cleanup disabled. Use within components for proper lifecycle management.`
      )
    }
  }

  return data
}

// ========================================
// Utility: Remove Item
// ========================================

/**
 * Remove an item from localStorage
 *
 * @param key - localStorage key to remove
 *
 * @example
 * ```typescript
 * removeLocalStorageItem('user')
 * ```
 */
export function removeLocalStorageItem(key: string): void {
  if (!isLocalStorageAvailable()) {
    return
  }

  try {
    localStorage.removeItem(key)
  } catch (error) {
    logger.error(`Error removing key "${key}":`, error)
  }
}

// ========================================
// Utility: Clear Storage
// ========================================

/**
 * Clear all localStorage items, optionally preserving specific keys
 *
 * @param keysToPreserve - Array of keys to preserve (not clear)
 *
 * @example Clear all
 * ```typescript
 * clearLocalStorage()
 * ```
 *
 * @example Preserve specific keys
 * ```typescript
 * clearLocalStorage(['auth-token', 'user-preferences'])
 * ```
 */
export function clearLocalStorage(keysToPreserve: string[] = []): void {
  if (!isLocalStorageAvailable()) {
    return
  }

  try {
    if (keysToPreserve.length === 0) {
      // Clear everything
      localStorage.clear()
      return
    }

    // Preserve specific keys
    const preserved: Record<string, string> = {}

    // Save preserved values
    keysToPreserve.forEach((key) => {
      const value = localStorage.getItem(key)
      if (value !== null) {
        preserved[key] = value
      }
    })

    // Clear everything
    localStorage.clear()

    // Restore preserved values
    Object.entries(preserved).forEach(([key, value]) => {
      localStorage.setItem(key, value)
    })
  } catch (error) {
    logger.error('Error clearing localStorage:', error)
  }
}

// ========================================
// Utility: Get All Keys
// ========================================

/**
 * Get all localStorage keys, optionally filtered by prefix
 *
 * @param prefix - Optional prefix to filter keys
 * @returns Array of localStorage keys
 *
 * @example Get all keys
 * ```typescript
 * const allKeys = getLocalStorageKeys()
 * ```
 *
 * @example Get keys with prefix
 * ```typescript
 * const apiKeys = getLocalStorageKeys('api-cache-')
 * ```
 */
export function getLocalStorageKeys(prefix?: string): string[] {
  if (!isLocalStorageAvailable()) {
    return []
  }

  try {
    const keys = Object.keys(localStorage)

    if (prefix) {
      return keys.filter((key) => key.startsWith(prefix))
    }

    return keys
  } catch (error) {
    logger.error('Error getting localStorage keys:', error)
    return []
  }
}

// ========================================
// Utility: Get Storage Size
// ========================================

/**
 * Get approximate size of localStorage in bytes
 *
 * @returns Size in bytes
 *
 * @example
 * ```typescript
 * const sizeBytes = getLocalStorageSize()
 * console.log(`LocalStorage: ${(sizeBytes / 1024).toFixed(2)} KB`)
 * ```
 */
export function getLocalStorageSize(): number {
  if (!isLocalStorageAvailable()) {
    return 0
  }

  try {
    let totalSize = 0

    for (const key in localStorage) {
      if (Object.prototype.hasOwnProperty.call(localStorage, key)) {
        const value = localStorage.getItem(key)
        if (value !== null) {
          // Count key + value in bytes (approximate UTF-16 encoding)
          totalSize += (key.length + value.length) * 2
        }
      }
    }

    return totalSize
  } catch (error) {
    logger.error('Error calculating localStorage size:', error)
    return 0
  }
}
