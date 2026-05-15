/**
 * Type augmentation for pinia-plugin-persistedstate
 * This allows the 'persist' option in defineStore without TypeScript errors
 */

import 'pinia'
import { PersistOptions } from 'pinia-plugin-persistedstate'

declare module 'pinia' {
  export interface DefineStoreOptionsBase<S, Store> {
    /**
     * Persist state with pinia-plugin-persistedstate
     */
    persist?: boolean | PersistOptions | PersistOptions[]
  }
}
