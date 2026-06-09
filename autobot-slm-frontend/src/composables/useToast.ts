// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { ref, inject, provide, type Ref, type InjectionKey } from 'vue'

export type ToastType = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  message: string
  type: ToastType
  duration: number
}

export interface UseToastReturn {
  toasts: Ref<Toast[]>
  showToast: (message: string, type?: ToastType, duration?: number) => number
  removeToast: (id: number) => void
  clearAllToasts: () => void
}

export const MAX_TOASTS = 5

export const TOAST_DURATIONS: Record<ToastType, number> = {
  success: 4000,
  info: 4000,
  warning: 6000,
  error: 0,
}

export const TOAST_INJECT_KEY: InjectionKey<UseToastReturn> = Symbol('useToast')

const _toasts = ref<Toast[]>([])
let _nextId = 1

function _buildApi(toasts: Ref<Toast[]>, idCounter: { value: number }): UseToastReturn {
  const removeToast = (id: number): void => {
    const index = toasts.value.findIndex((t) => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  const showToast = (
    message: string,
    type: ToastType = 'info',
    duration?: number,
  ): number => {
    const resolvedDuration = duration !== undefined ? duration : TOAST_DURATIONS[type]
    const id = idCounter.value++
    const toast: Toast = { id, message, type, duration: resolvedDuration }

    if (toasts.value.length >= MAX_TOASTS) {
      toasts.value.splice(0, toasts.value.length - MAX_TOASTS + 1)
    }

    toasts.value.push(toast)

    if (resolvedDuration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, resolvedDuration)
    }

    return id
  }

  const clearAllToasts = (): void => {
    toasts.value.splice(0)
  }

  return { toasts, showToast, removeToast, clearAllToasts }
}

const _idCounter = { value: _nextId }
const _singletonApi = _buildApi(_toasts, _idCounter)

Object.defineProperty(_idCounter, 'value', {
  get: () => _nextId,
  set: (v: number) => { _nextId = v },
})

export function provideToast(): UseToastReturn {
  provide(TOAST_INJECT_KEY, _singletonApi)
  return _singletonApi
}

export function useToast(): UseToastReturn {
  const injected = inject(TOAST_INJECT_KEY, null)
  return injected ?? _singletonApi
}
