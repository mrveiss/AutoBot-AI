// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #19458 — one window listener, one benign filter, one app.config.errorHandler.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const addSystemNotification = vi.hoisted(() => vi.fn())
const trackError = vi.hoisted(() => vi.fn())

vi.mock('@/stores/useAppStore', () => ({
  useAppStore: () => ({ addSystemNotification }),
}))
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string) => key } },
}))
vi.mock('@/utils/RumAgent', () => ({ default: { trackError } }))
vi.mock('../../utils/RumAgent', () => ({ default: { trackError } }))

import errorHandlerPlugin from '../errorHandler'
import { isBenignBrowserNotice } from '@/utils/benignBrowserNotice'

const WORDINGS = [
  'ResizeObserver loop limit exceeded',
  'ResizeObserver loop completed with undelivered notifications',
]

describe('window error listener (#19458)', () => {
  beforeEach(() => {
    addSystemNotification.mockClear()
    trackError.mockClear()
  })

  it.each(WORDINGS)('raises no system notification for "%s"', (message) => {
    window.dispatchEvent(new ErrorEvent('error', { message, cancelable: true }))
    expect(addSystemNotification).not.toHaveBeenCalled()
  })

  it('still notifies for a real error (RUM reporting is RumAgent\'s single path)', () => {
    const error = new Error('boom')
    window.dispatchEvent(new ErrorEvent('error', { message: 'boom', error }))
    expect(addSystemNotification).toHaveBeenCalledTimes(1)
    expect(addSystemNotification).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'error', title: 'nav.applicationError', message: 'boom' })
    )
    expect(trackError).not.toHaveBeenCalledWith('javascript_error', expect.anything())
  })

  it('raises no system notification for a benign unhandled rejection, but does for a real one', () => {
    const rejection = (reason: unknown) => {
      const event = new Event('unhandledrejection', { cancelable: true }) as Event & { reason: unknown }
      event.reason = reason
      window.dispatchEvent(event)
    }
    rejection(new Error(WORDINGS[1]))
    expect(addSystemNotification).not.toHaveBeenCalled()
    rejection(new Error('real rejection'))
    expect(addSystemNotification).toHaveBeenCalledTimes(1)
  })
})

describe('the single app.config.errorHandler (#19458)', () => {
  it('reports a Vue error to RUM and to the user', () => {
    const app = { config: { globalProperties: {} } as Record<string, unknown>, provide: vi.fn() }
    errorHandlerPlugin.install(app as never)
    const handler = app.config.errorHandler as (e: unknown, i: unknown, info: string) => void
    trackError.mockClear()
    handler(new Error('vue boom'), { $options: { name: 'Widget' } }, 'render')
    expect(trackError).toHaveBeenCalledWith(
      'vue_error',
      expect.objectContaining({ message: 'vue boom', component: 'Widget', componentInfo: 'render' })
    )
  })
})

describe('Vue errors reach the user (#19458)', () => {
  const install = () => {
    const app = { config: { globalProperties: {} } as Record<string, unknown>, provide: vi.fn() }
    errorHandlerPlugin.install(app as never)
    return app.config.errorHandler as (e: unknown, i: unknown, info: string) => void
  }

  it('raises a visible system notification for a Vue error', () => {
    addSystemNotification.mockClear()
    install()(new Error('vue boom'), null, 'render')
    expect(addSystemNotification).toHaveBeenCalledTimes(1)
    expect(addSystemNotification).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'error', title: 'nav.applicationError', message: 'vue boom' })
    )
  })

  it.each(WORDINGS)('raises none for a benign Vue-reported "%s"', (message) => {
    addSystemNotification.mockClear()
    install()(new Error(message), null, 'render')
    expect(addSystemNotification).not.toHaveBeenCalled()
  })
})

describe('isBenignBrowserNotice', () => {
  it.each(WORDINGS)('matches "%s" as string, Error and event-like', (message) => {
    expect(isBenignBrowserNotice(message)).toBe(true)
    expect(isBenignBrowserNotice(new Error(message))).toBe(true)
    expect(isBenignBrowserNotice('', { message })).toBe(true)
  })
  it('does not match real errors', () => {
    expect(isBenignBrowserNotice('boom', new Error('x'), undefined, null)).toBe(false)
  })
})

describe('single-definition guard (#19458)', () => {
  const SRC = join(__dirname, '..', '..')
  const files: string[] = []
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) {
        if (name !== '__tests__' && name !== 'node_modules') walk(full)
      } else if (/\.(ts|vue|js)$/.test(name) && !/\.(test|spec|stories)\./.test(name)) {
        files.push(full)
      }
    }
  }
  walk(SRC)
  const count = (re: RegExp, only?: (rel: string) => boolean) =>
    files
      .filter((f) => !only || only(relative(SRC, f)))
      .reduce((n, f) => n + (readFileSync(f, 'utf-8').match(re) ?? []).length, 0)

  it('has exactly one benign-notice list (ResizeObserver wordings appear once each)', () => {
    expect(count(/ResizeObserver loop limit exceeded/g)).toBe(1)
    expect(count(/ResizeObserver loop completed with undelivered notifications/g)).toBe(1)
  })

  it('has exactly one user-notifying window error listener, owned by the plugin', () => {
    const owners = ['App.vue', 'plugins/errorHandler.ts']
    expect(count(/addEventListener\(\s*['"]error['"]/g, (r) => r === 'App.vue')).toBe(0)
    expect(count(/addEventListener\(\s*['"]unhandledrejection['"]/g, (r) => r === 'App.vue')).toBe(0)
    expect(count(/addEventListener\(\s*['"]error['"]/g, (r) => owners.includes(r))).toBe(1)
  })

  it('has exactly one app.config.errorHandler assignment', () => {
    expect(count(/app\.config\.errorHandler\s*=/g)).toBe(1)
  })
})
