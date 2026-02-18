// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Type definitions for pinia-plugin-persistedstate
 *
 * This file extends Pinia's DefineStoreOptionsBase interface to properly type
 * the 'persist' option from pinia-plugin-persistedstate plugin.
 *
 * Issue #156: Eliminates need for 'as any' type casts in store definitions
 */

import 'pinia'

declare module 'pinia' {
  /**
   * Extends DefineStoreOptionsBase for options API stores
   */
  export interface DefineStoreOptionsBase<S, Store> {
    /**
     * Persistence configuration for pinia-plugin-persistedstate
     *
     * @see https://prazdevs.github.io/pinia-plugin-persistedstate/
     */
    persist?: PersistOptions | boolean
  }

  /**
   * Extends DefineSetupStoreOptions for setup/composition API stores
   */
  export interface DefineSetupStoreOptions<Id, SS, S, G, A> {
    /**
     * Persistence configuration for pinia-plugin-persistedstate
     *
     * @see https://prazdevs.github.io/pinia-plugin-persistedstate/
     */
    persist?: PersistOptions | boolean
  }

  /**
   * Configuration options for state persistence
   */
  export interface PersistOptions {
    /**
     * Storage key to use for persisting the store
     * @default store.$id
     */
    key?: string

    /**
     * Storage implementation to use
     * @default localStorage
     */
    storage?: Storage

    /**
     * Array of state paths to persist
     * If not provided, entire state is persisted
     *
     * @example
     * paths: ['user.name', 'settings.theme']
     */
    paths?: string[]

    /**
     * Custom serializer for complex types (e.g., Date, Map, Set)
     */
    serializer?: {
      /**
       * Serialize state before storing
       */
      serialize: (value: any) => string

      /**
       * Deserialize state when loading
       */
      deserialize: (value: string) => any
    }

    /**
     * Hook called before state is persisted
     */
    beforeRestore?: (context: any) => void

    /**
     * Hook called after state is restored
     */
    afterRestore?: (context: any) => void

    /**
     * Enable debug mode for persistence operations
     * @default false
     */
    debug?: boolean
  }
}
