// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { ref } from 'vue'
import { createLogger } from '../utils'

const logger = createLogger('useVncControls')

export interface MouseClickParams { x: number; y: number; button?: 'left' | 'middle' | 'right' }
export interface MouseDragParams { x1: number; y1: number; x2: number; y2: number }
export interface MouseScrollParams { direction: 'up' | 'down'; amount?: number }
export interface VncActionResponse { status: 'success' | 'error'; message: string; image_data?: string }

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}

async function vncFetch<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json() as Promise<T>
}

export function useVncControls(baseUrl = '/api') {
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function call<T>(fn: () => Promise<T>): Promise<T> {
    loading.value = true
    error.value = null
    try { return await fn() }
    finally { loading.value = false }
  }

  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/click`, params)) }
    catch (err) { logger.error('Mouse click failed:', err); const m = extractErrorMessage(err, 'Mouse click failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function keyboardType(text: string): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/type`, { text })) }
    catch (err) { logger.error('Keyboard type failed:', err); const m = extractErrorMessage(err, 'Keyboard type failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function specialKey(key: string): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/key`, { key })) }
    catch (err) { logger.error('Special key failed:', err); const m = extractErrorMessage(err, 'Special key failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/scroll`, params)) }
    catch (err) { logger.error('Mouse scroll failed:', err); const m = extractErrorMessage(err, 'Mouse scroll failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/drag`, params)) }
    catch (err) { logger.error('Mouse drag failed:', err); const m = extractErrorMessage(err, 'Mouse drag failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function captureScreenshot(): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('GET', `${baseUrl}/vnc/screenshot`)) }
    catch (err) { logger.error('Screenshot capture failed:', err); const m = extractErrorMessage(err, 'Screenshot capture failed'); error.value = m; return { status: 'error', message: m, image_data: '' } }
  }

  async function syncClipboard(content: string): Promise<VncActionResponse> {
    try { return await call(() => vncFetch('POST', `${baseUrl}/vnc/clipboard`, { content })) }
    catch (err) { logger.error('Clipboard sync failed:', err); const m = extractErrorMessage(err, 'Clipboard sync failed'); error.value = m; return { status: 'error', message: m } }
  }

  const sendCtrlAltDel = () => specialKey('ctrl+alt+Delete')

  return { loading, error, mouseClick, keyboardType, specialKey, mouseScroll, mouseDrag, captureScreenshot, syncClipboard, sendCtrlAltDel }
}
