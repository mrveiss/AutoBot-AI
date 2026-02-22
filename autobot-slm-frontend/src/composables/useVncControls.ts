// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * VNC Desktop Interaction Controls Composable (SLM Frontend)
 * Issue #74: Full desktop control and session integration
 */

import { ref } from 'vue'
import axios, { type AxiosInstance } from 'axios'
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

export function useVncControls() {
  const client: AxiosInstance = axios.create({ baseURL: '/api' })
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Perform mouse click at coordinates
   */
  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/click', params)
      return response.data
    } catch (err: any) {
      logger.error('Mouse click failed:', err)
      error.value = err.message || 'Mouse click failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Type text via keyboard
   */
  async function keyboardType(text: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/type', { text })
      return response.data
    } catch (err: any) {
      logger.error('Keyboard type failed:', err)
      error.value = err.message || 'Keyboard type failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Send special key or key combination
   */
  async function specialKey(key: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/key', { key })
      return response.data
    } catch (err: any) {
      logger.error('Special key failed:', err)
      error.value = err.message || 'Special key failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Scroll mouse wheel
   */
  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/scroll', params)
      return response.data
    } catch (err: any) {
      logger.error('Mouse scroll failed:', err)
      error.value = err.message || 'Mouse scroll failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Perform mouse drag operation
   */
  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/drag', params)
      return response.data
    } catch (err: any) {
      logger.error('Mouse drag failed:', err)
      error.value = err.message || 'Mouse drag failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Capture desktop screenshot
   */
  async function captureScreenshot(): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<VncActionResponse>('/vnc/screenshot')
      return response.data
    } catch (err: any) {
      logger.error('Screenshot capture failed:', err)
      error.value = err.message || 'Screenshot capture failed'
      return {
        status: 'error',
        message: error.value ?? '',
        image_data: ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Sync clipboard content to remote desktop
   */
  async function syncClipboard(content: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/clipboard', { content })
      return response.data
    } catch (err: any) {
      logger.error('Clipboard sync failed:', err)
      error.value = err.message || 'Clipboard sync failed'
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Send Ctrl+Alt+Del
   */
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
