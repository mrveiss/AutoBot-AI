// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

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

/**
 * HTTP transport for the VNC control endpoints.
 *
 * Injected because the three hosts legitimately differ: the main SPA has
 * `ApiClient` (auth headers, base-URL resolution, error envelopes), the SLM SPA
 * has an axios instance bound to `getSlmApiBase()`, and a standalone embed has
 * neither. This package declares only `vue` as a peer dependency, so it cannot
 * import either client — sharing the logic requires injecting what differs
 * (#12931). Same seam as the NPU task-queue getter in #12656.
 */
export type VncRequest = <T>(method: 'GET' | 'POST', path: string, body?: unknown) => Promise<T>

export interface UseVncControlsOptions {
  /** Path prefix for the `/vnc/*` endpoints. */
  baseUrl?: string
  /**
   * Threaded into every request body as `session_id` (#12002), so a lock
   * owner's toolbar drives their own session rather than whichever is default.
   */
  sessionId?: string
  /** Defaults to plain `fetch` — see {@link VncRequest}. */
  request?: VncRequest
}

export function useVncControls(options: UseVncControlsOptions = {}) {
  const { baseUrl = '/api', sessionId, request = vncFetch } = options

  // #12002: every POST body carries the session id when one was supplied.
  const withSession = (body?: Record<string, unknown>) =>
    sessionId === undefined ? body : { ...(body ?? {}), session_id: sessionId }

  const loading = ref(false)
  const error = ref<string | null>(null)

  async function call<T>(fn: () => Promise<T>): Promise<T> {
    loading.value = true
    error.value = null
    try { return await fn() }
    finally { loading.value = false }
  }

  async function mouseClick(params: MouseClickParams): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/click`, withSession({ ...params }))) }
    catch (err) { logger.error('Mouse click failed:', err); const m = extractErrorMessage(err, 'Mouse click failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function keyboardType(text: string): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/type`, withSession({ text }))) }
    catch (err) { logger.error('Keyboard type failed:', err); const m = extractErrorMessage(err, 'Keyboard type failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function specialKey(key: string): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/key`, withSession({ key }))) }
    catch (err) { logger.error('Special key failed:', err); const m = extractErrorMessage(err, 'Special key failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function mouseScroll(params: MouseScrollParams): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/scroll`, withSession({ ...params }))) }
    catch (err) { logger.error('Mouse scroll failed:', err); const m = extractErrorMessage(err, 'Mouse scroll failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function mouseDrag(params: MouseDragParams): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/drag`, withSession({ ...params }))) }
    catch (err) { logger.error('Mouse drag failed:', err); const m = extractErrorMessage(err, 'Mouse drag failed'); error.value = m; return { status: 'error', message: m } }
  }

  async function captureScreenshot(): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('GET', `${baseUrl}/vnc/screenshot`)) }
    catch (err) { logger.error('Screenshot capture failed:', err); const m = extractErrorMessage(err, 'Screenshot capture failed'); error.value = m; return { status: 'error', message: m, image_data: '' } }
  }

  async function syncClipboard(content: string): Promise<VncActionResponse> {
    try { return await call(() => request<VncActionResponse>('POST', `${baseUrl}/vnc/clipboard`, withSession({ content }))) }
    catch (err) { logger.error('Clipboard sync failed:', err); const m = extractErrorMessage(err, 'Clipboard sync failed'); error.value = m; return { status: 'error', message: m } }
  }

  const sendCtrlAltDel = () => specialKey('ctrl+alt+Delete')

  return { loading, error, mouseClick, keyboardType, specialKey, mouseScroll, mouseDrag, captureScreenshot, syncClipboard, sendCtrlAltDel }
}
