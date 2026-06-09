// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * VNC Desktop Interaction Controls Composable (SLM Frontend)
 * Issue #74: Full desktop control and session integration
 */

import { ref } from 'vue'
import axios, { type AxiosInstance } from 'axios'
import { createLogger } from '@/utils/debugUtils'
import { getSlmApiBase } from '@/config/ssot-config'

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
  const client: AxiosInstance = axios.create({ baseURL: getSlmApiBase() })
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/click', params)
      return response.data
    } catch (err: unknown) {
      logger.error('Mouse click failed:', err)
      error.value = extractErrorMessage(err, 'Mouse click failed')
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  async function keyboardType(text: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/type', { text })
      return response.data
    } catch (err: unknown) {
      logger.error('Keyboard type failed:', err)
      error.value = extractErrorMessage(err, 'Keyboard type failed')
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  async function specialKey(key: string): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/key', { key })
      return response.data
    } catch (err: unknown) {
      logger.error('Special key failed:', err)
      error.value = extractErrorMessage(err, 'Special key failed')
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/scroll', params)
      return response.data
    } catch (err: unknown) {
      logger.error('Mouse scroll failed:', err)
      error.value = extractErrorMessage(err, 'Mouse scroll failed')
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<VncActionResponse>('/vnc/drag', params)
      return response.data
    } catch (err: unknown) {
      logger.error('Mouse drag failed:', err)
      error.value = extractErrorMessage(err, 'Mouse drag failed')
      return {
        status: 'error',
        message: error.value ?? ''
      }
    } finally {
      loading.value = false
    }
  }

  async function captureScreenshot(): Promise<VncActionResponse> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<VncActionResponse>('/vnc/screenshot')
      return response.data
    } catch (err: unknown) {
      logger.error('Screenshot capture failed:', err)
      error.value = extractErrorMessage(err, 'Screenshot capture failed')
      return {
        status: 'error',
        message: error.value ?? '',
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
      const response = await client.post<VncActionResponse>('/vnc/clipboard', { content })
      return response.data
    } catch (err: unknown) {
      logger.error('Clipboard sync failed:', err)
      error.value = extractErrorMessage(err, 'Clipboard sync failed')
      return {
        status: 'error',
        message: error.value ?? ''
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
