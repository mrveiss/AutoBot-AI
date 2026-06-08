// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * VNC Desktop Interaction Controls Composable
 * Issue #74: Full desktop control and session integration
 */

import { ref } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useVncControls')

export interface MouseClickParams {
  x: number
  y: number
  button?: 'left' | 'middle' | 'right'
}

export interface MouseDragParams {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface MouseScrollParams {
  direction: 'up' | 'down'
  amount?: number
}

export interface VncActionResponse {
  status: 'success' | 'error'
  message: string
  image_data?: string
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}

export function useVncControls() {
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/click', params))
    } catch (err: unknown) {
      logger.error('Mouse click failed:', err)
      error.value = extractErrorMessage(err, 'Mouse click failed')
      return { status: 'error', message: error.value ?? 'Mouse click failed' }
    }
  }

  async function keyboardType(text: string): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/type', { text }))
    } catch (err: unknown) {
      logger.error('Keyboard type failed:', err)
      error.value = extractErrorMessage(err, 'Keyboard type failed')
      return { status: 'error', message: error.value ?? 'Keyboard type failed' }
    }
  }

  async function specialKey(key: string): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/key', { key }))
    } catch (err: unknown) {
      logger.error('Special key failed:', err)
      error.value = extractErrorMessage(err, 'Special key failed')
      return { status: 'error', message: error.value ?? 'Special key failed' }
    }
  }

  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/scroll', params))
    } catch (err: unknown) {
      logger.error('Mouse scroll failed:', err)
      error.value = extractErrorMessage(err, 'Mouse scroll failed')
      return { status: 'error', message: error.value ?? 'Mouse scroll failed' }
    }
  }

  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/drag', params))
    } catch (err: unknown) {
      logger.error('Mouse drag failed:', err)
      error.value = extractErrorMessage(err, 'Mouse drag failed')
      return { status: 'error', message: error.value ?? 'Mouse drag failed' }
    }
  }

  async function captureScreenshot(): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.get<VncActionResponse>('/vnc/screenshot'))
    } catch (err: unknown) {
      logger.error('Screenshot capture failed:', err)
      error.value = extractErrorMessage(err, 'Screenshot capture failed')
      return { status: 'error', message: error.value ?? 'Screenshot capture failed', image_data: '' }
    }
  }

  async function syncClipboard(content: string): Promise<VncActionResponse> {
    error.value = null
    try {
      return await wrap(() => ApiClient.post<VncActionResponse>('/vnc/clipboard', { content }))
    } catch (err: unknown) {
      logger.error('Clipboard sync failed:', err)
      error.value = extractErrorMessage(err, 'Clipboard sync failed')
      return { status: 'error', message: error.value ?? 'Clipboard sync failed' }
    }
  }

  async function sendCtrlAltDel(): Promise<VncActionResponse> {
    return specialKey('ctrl+alt+Delete')
  }

  return {
    loading,
    error,
    mouseClick,
    keyboardType,
    specialKey,
    mouseScroll,
    mouseDrag,
    captureScreenshot,
    syncClipboard,
    sendCtrlAltDel
  }
}
