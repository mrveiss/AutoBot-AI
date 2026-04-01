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
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/click', params)
      return response
    } catch (err: unknown) {
      logger.error('Mouse click failed:', err)
      error.value = extractErrorMessage(err, 'Mouse click failed')
      return {
        status: 'error',
        message: error.value ?? 'Mouse click failed'
      }
    } finally {
      loading.value = false
    }
  }

  async function keyboardType(text: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/type', { text })
      return response
    } catch (err: unknown) {
      logger.error('Keyboard type failed:', err)
      error.value = extractErrorMessage(err, 'Keyboard type failed')
      return {
        status: 'error',
        message: error.value ?? 'Keyboard type failed'
      }
    } finally {
      loading.value = false
    }
  }

  async function specialKey(key: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/key', { key })
      return response
    } catch (err: unknown) {
      logger.error('Special key failed:', err)
      error.value = extractErrorMessage(err, 'Special key failed')
      return {
        status: 'error',
        message: error.value ?? 'Special key failed'
      }
    } finally {
      loading.value = false
    }
  }

  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/scroll', params)
      return response
    } catch (err: unknown) {
      logger.error('Mouse scroll failed:', err)
      error.value = extractErrorMessage(err, 'Mouse scroll failed')
      return {
        status: 'error',
        message: error.value ?? 'Mouse scroll failed'
      }
    } finally {
      loading.value = false
    }
  }

  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/drag', params)
      return response
    } catch (err: unknown) {
      logger.error('Mouse drag failed:', err)
      error.value = extractErrorMessage(err, 'Mouse drag failed')
      return {
        status: 'error',
        message: error.value ?? 'Mouse drag failed'
      }
    } finally {
      loading.value = false
    }
  }

  async function captureScreenshot(): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.get<VncActionResponse>('/vnc/screenshot')
      return response
    } catch (err: unknown) {
      logger.error('Screenshot capture failed:', err)
      error.value = extractErrorMessage(err, 'Screenshot capture failed')
      return {
        status: 'error',
        message: error.value ?? 'Screenshot capture failed',
        image_data: ''
      }
    } finally {
      loading.value = false
    }
  }

  async function syncClipboard(content: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await ApiClient.post<VncActionResponse>('/vnc/clipboard', { content })
      return response
    } catch (err: unknown) {
      logger.error('Clipboard sync failed:', err)
      error.value = extractErrorMessage(err, 'Clipboard sync failed')
      return {
        status: 'error',
        message: error.value ?? 'Clipboard sync failed'
      }
    } finally {
      loading.value = false
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
