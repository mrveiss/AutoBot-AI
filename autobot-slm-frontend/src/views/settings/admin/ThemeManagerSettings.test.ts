// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ThemeManagerSettings (#20605): the installed themes from GET /themes, each state said apart
 * (reading, failed, main app not available, none installed), an upload that refuses what cannot
 * pass (not a .zip, over the proxy's size cap, not an admin, a package the backend rejects) and
 * an uninstall only ever sent after the confirmation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import ThemeManagerSettings from './ThemeManagerSettings.vue'
import en from '@/locales/en.json'

const client = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
vi.mock('@/composables/useAutobotApi', () => ({ createAutobotBackendClient: () => client }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const L = en.settings.admin.themeManager

const amber = { id: 'amber', name: 'Amber', author: 'Ada', version: '1.2.0', supports: ['light', 'dark'] }
const ember = { id: 'ember', name: 'Ember', author: 'Bo', version: '0.3.1', supports: ['dark'] }

let wrapper: VueWrapper | undefined

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(ThemeManagerSettings, { global: { plugins: [i18n], stubs: { teleport: true } } })
  await flushPromises()
  return wrapper
}

const byId = (w: VueWrapper, id: string) => w.find(`[data-testid="${id}"]`)

/** Puts a file in the hidden input and fires its change, as the browser's picker does. */
async function pick(w: VueWrapper, file: File): Promise<void> {
  const input = byId(w, 'slm-themes-file')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const zip = (name = 'amber.zip') => new File(['PK'], name, { type: 'application/zip' })

beforeEach(() => {
  client.get.mockReset()
  client.post.mockReset()
  client.delete.mockReset()
  client.get.mockResolvedValue([amber, ember])
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('ThemeManagerSettings data', () => {
  it('reads GET /themes once and lists every installed theme with its fields', async () => {
    const w = await mountView()
    expect(client.get).toHaveBeenCalledWith('/themes', { maxRetries: 1 })
    const rows = byId(w, 'slm-themes-table').findAll('tbody tr').map((r) => r.text())
    expect(rows).toHaveLength(2)
    expect(rows[0]).toContain('Amber')
    expect(rows[0]).toContain('1.2.0')
    expect(rows[0]).toContain('Ada')
    expect(rows[0]).toContain('light, dark')
    expect(rows[1]).toContain('ember')
  })

  it('shows a reading state until the list answers', async () => {
    client.get.mockImplementation(() => new Promise(() => {}))
    const w = await mountView()
    expect(byId(w, 'slm-themes-loading').text()).toContain(L.loading)
    expect(byId(w, 'slm-themes-install').exists()).toBe(false)
  })

  it('says none are installed, and still offers the upload', async () => {
    client.get.mockResolvedValue([])
    const w = await mountView()
    expect(byId(w, 'slm-themes-empty').text()).toContain(L.emptyTitle)
    expect(byId(w, 'slm-themes-table').exists()).toBe(false)
    expect(byId(w, 'slm-themes-install').exists()).toBe(true)
  })
})

describe('ThemeManagerSettings failed and main app down', () => {
  it('says the read failed, with the backend detail, when it answers an error', async () => {
    client.get.mockRejectedValue(HttpError.withDetail(500, 'Server Error', 'themes directory unreadable'))
    const w = await mountView()
    expect(byId(w, 'slm-themes-error').text()).toContain('themes directory unreadable')
    expect(byId(w, 'slm-themes-unavailable').exists()).toBe(false)
  })

  it.each([502, 503, 504])('says the theme manager is not available when the proxy answers %i', async (status) => {
    client.get.mockRejectedValue(new HttpError(status))
    const w = await mountView()
    expect(byId(w, 'slm-themes-unavailable').text()).toContain(L.unavailableTitle)
    expect(byId(w, 'slm-themes-error').exists()).toBe(false)
    expect(byId(w, 'slm-themes-install').exists()).toBe(false)
  })

  it('says not available when the request never gets an answer', async () => {
    client.get.mockRejectedValue(new TypeError('Failed to fetch'))
    const w = await mountView()
    expect(byId(w, 'slm-themes-unavailable').text()).toContain(L.unavailableBody)
  })

  it('says the read failed, not that nothing is installed, when the answer is not a list', async () => {
    client.get.mockResolvedValue({ detail: 'x' })
    const w = await mountView()
    expect(byId(w, 'slm-themes-empty').exists()).toBe(false)
    expect(byId(w, 'slm-themes-error').exists()).toBe(true)
  })

  it('says not available when the request timed out', async () => {
    client.get.mockRejectedValue(new Error('Request timeout after 30000ms'))
    const w = await mountView()
    expect(byId(w, 'slm-themes-unavailable').exists()).toBe(true)
  })

  it('reads again on refresh', async () => {
    client.get.mockRejectedValueOnce(new HttpError(503))
    const w = await mountView()
    await byId(w, 'slm-themes-refresh').trigger('click')
    await flushPromises()
    expect(client.get).toHaveBeenCalledTimes(2)
    expect(byId(w, 'slm-themes-table').exists()).toBe(true)
  })
})

describe('ThemeManagerSettings upload', () => {
  it('posts the package as the multipart "file" field, says it installed, and reads the list again', async () => {
    client.post.mockResolvedValue(amber)
    const w = await mountView()
    await pick(w, zip())
    expect(client.post).toHaveBeenCalledTimes(1)
    const [url, body] = client.post.mock.calls[0]
    expect(url).toBe('/themes')
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBeInstanceOf(File)
    expect(byId(w, 'slm-themes-notice').text()).toContain('Installed Amber 1.2.0.')
    expect(client.get).toHaveBeenCalledTimes(2)
  })

  it('refuses a file that is not a .zip without sending anything', async () => {
    const w = await mountView()
    await pick(w, new File(['x'], 'amber.tar.gz'))
    expect(client.post).not.toHaveBeenCalled()
    expect(byId(w, 'slm-themes-notice').text()).toContain(L.notZip)
  })

  it('says the proxy refused a package over its size cap (413), not that the package is bad', async () => {
    client.post.mockRejectedValue(new HttpError(413, 'Request Entity Too Large'))
    const w = await mountView()
    await pick(w, zip())
    expect(byId(w, 'slm-themes-notice').text()).toContain(L.tooLarge)
    expect(client.get).toHaveBeenCalledTimes(1)
  })

  it.each([401, 403])('says only an administrator can change themes on %i', async (status) => {
    client.post.mockRejectedValue(new HttpError(status))
    const w = await mountView()
    await pick(w, zip())
    expect(byId(w, 'slm-themes-notice').text()).toContain(L.adminOnly)
  })

  it('shows the backend detail for a package it rejects (400) or an id already taken (409)', async () => {
    client.post.mockRejectedValueOnce(HttpError.withDetail(400, 'Bad Request', 'theme.css not found'))
    client.post.mockRejectedValueOnce(HttpError.withDetail(409, 'Conflict', "Theme 'amber' already installed"))
    const w = await mountView()
    await pick(w, zip())
    expect(byId(w, 'slm-themes-notice').text()).toContain('theme.css not found')
    await pick(w, zip())
    expect(byId(w, 'slm-themes-notice').text()).toContain("Theme 'amber' already installed")
  })

  it('says the main app is not available when it goes down during the upload', async () => {
    client.post.mockRejectedValue(new HttpError(502))
    const w = await mountView()
    await pick(w, zip())
    expect(byId(w, 'slm-themes-notice').text()).toContain(L.unavailableBody)
  })
})

describe('ThemeManagerSettings uninstall', () => {
  it('sends nothing until the confirmation, then deletes by id and reads again', async () => {
    client.delete.mockResolvedValue({ status: 'deleted', id: 'amber' })
    const w = await mountView()
    await byId(w, 'slm-themes-uninstall-amber').trigger('click')
    expect(client.delete).not.toHaveBeenCalled()
    expect(byId(w, 'slm-themes-confirm-body').text()).toBe(L.confirmBody)
    await byId(w, 'slm-themes-confirm-remove').trigger('click')
    await flushPromises()
    expect(client.delete).toHaveBeenCalledWith('/themes/amber')
    expect(byId(w, 'slm-themes-notice').text()).toContain('Uninstalled Amber.')
    expect(client.get).toHaveBeenCalledTimes(2)
  })

  it('cancelling sends nothing', async () => {
    const w = await mountView()
    await byId(w, 'slm-themes-uninstall-amber').trigger('click')
    await byId(w, 'slm-themes-confirm-cancel').trigger('click')
    expect(client.delete).not.toHaveBeenCalled()
  })

  it('says why a delete failed and keeps the list', async () => {
    client.delete.mockRejectedValue(HttpError.withDetail(404, 'Not Found', "Theme 'amber' not found"))
    const w = await mountView()
    await byId(w, 'slm-themes-uninstall-amber').trigger('click')
    await byId(w, 'slm-themes-confirm-remove').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-themes-notice').text()).toContain("Theme 'amber' not found")
    expect(client.get).toHaveBeenCalledTimes(1)
  })

  it('names the malformed answer with a translated message (#20816)', async () => {
    client.get.mockResolvedValue({ detail: 'x' })
    const w = await mountView()
    // A control string, not the en.json value the view reads: the message is the translated sentence.
    expect(byId(w, 'slm-themes-error').text()).toContain('The theme list answer was not a list.')
  })

  it('ignores an older read that resolves after a newer one (#20816)', async () => {
    const w = await mountView()
    // The refresh is slow (older); an install then re-reads and answers at once (newer).
    let resolveOld: (v: unknown) => void = () => {}
    client.get.mockReturnValueOnce(new Promise((r) => { resolveOld = r }))
    await byId(w, 'slm-themes-refresh').trigger('click')
    client.post.mockResolvedValue(ember)
    client.get.mockResolvedValueOnce([ember])
    await pick(w, zip('ember.zip'))
    expect(w.text()).toContain('Ember')
    resolveOld([amber])
    await flushPromises()
    expect(w.text()).toContain('Ember')
    expect(w.text()).not.toContain('Amber')
  })

  it('ignores an older read that rejects after a newer one succeeded (#20816)', async () => {
    const w = await mountView()
    let rejectOld: (e: unknown) => void = () => {}
    client.get.mockReturnValueOnce(new Promise((_, rej) => { rejectOld = rej }))
    await byId(w, 'slm-themes-refresh').trigger('click')
    client.post.mockResolvedValue(ember)
    client.get.mockResolvedValueOnce([ember])
    await pick(w, zip('ember.zip'))
    rejectOld(new TypeError('Failed to fetch'))
    await flushPromises()
    expect(byId(w, 'slm-themes-unavailable').exists()).toBe(false)
    expect(byId(w, 'slm-themes-error').exists()).toBe(false)
    expect(w.text()).toContain('Ember')
  })
})
