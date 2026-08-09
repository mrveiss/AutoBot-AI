// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * BackupsView — destination, status and deletion (#13307).
 *
 * The reported symptom was "no idea where they are created". `backup_path` was
 * already in `BackupResponse` and the page had **zero** references to it.
 *
 * Auditing the view turned up something worse, and silent. The API field is
 * `status` (`models/schemas.py` `BackupResponse`); the TypeScript type declared
 * `state`, and the template read `backup.state` throughout. Every read was
 * `undefined`, so:
 *
 *   * the Status column rendered blank, and
 *   * `v-if="backup.state === 'completed'"` was never true, so the **Restore
 *     button never appeared for any backup** — a feature that shipped, was
 *     typed, and could not be reached.
 *
 * Nothing raises for either: TypeScript was satisfied because the interface
 * agreed with the template, and both were wrong about the wire format. Only a
 * test that renders a real API payload catches it, which is what this is.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import BackupsView from './BackupsView.vue'
import en from '@/locales/en.json'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

/** Exactly the shape `BackupResponse` serialises — `status`, not `state`. */
const COMPLETED_BACKUP = {
  id: 1,
  backup_id: 'abc123def456',
  node_id: 'node-a',
  service_type: 'redis',
  backup_path: '/var/lib/slm/backups/abc123def456_20260804_101500.rdb',
  status: 'completed',
  size_bytes: 2048,
  checksum: 'deadbeef',
  error: null,
  started_at: '2026-08-04T10:15:00Z',
  completed_at: '2026-08-04T10:15:30Z',
  created_at: '2026-08-04T10:15:00Z',
}

const IN_PROGRESS_BACKUP = {
  ...COMPLETED_BACKUP,
  id: 2,
  backup_id: 'running00000',
  backup_path: null,
  status: 'in_progress',
  completed_at: null,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function routeBody(url: string) {
  if (url.includes('/stateful/backups')) return { backups: [COMPLETED_BACKUP, IN_PROGRESS_BACKUP], total: 2 }
  if (url.includes('/stateful/replications')) return { replications: [], total: 0 }
  return { nodes: [], total: 0 }
}

async function mountBackups() {
  const wrapper = mount(BackupsView, { global: { plugins: [i18n] } })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('BackupsView (#13307)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    fetchMock = vi.fn(async (url: string) => jsonResponse(routeBody(String(url))))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows where each backup was written', async () => {
    const wrapper = await mountBackups()

    expect(wrapper.text()).toContain(COMPLETED_BACKUP.backup_path)
  })

  it('says so plainly when a backup has no stored file yet', async () => {
    const wrapper = await mountBackups()

    // `backup_path` is null until the copy to SLM storage succeeds. Rendering
    // an empty cell there would read as "somewhere unknown", which is the
    // confusion this issue is about.
    expect(wrapper.text()).toContain(en.backupsView.locationPending)
  })

  it('renders the status the API actually sends', async () => {
    const wrapper = await mountBackups()

    // Blank before the fix: the template read `backup.state`, which does not
    // exist on the wire.
    expect(wrapper.text()).toContain('completed')
    expect(wrapper.text()).toContain('in_progress')
  })

  it('offers Restore for a completed backup', async () => {
    const wrapper = await mountBackups()

    const restore = wrapper.findAll('button').filter((b) => b.text() === en.backupsView.restore)
    expect(restore.length, 'the Restore button never rendered — it was gated on a field that is always undefined').toBe(
      1,
    )
  })

  it('does not offer Restore or Delete while a backup is still running', async () => {
    const wrapper = await mountBackups()

    const deletes = wrapper.findAll('button').filter((b) => b.text() === en.backupsView.delete)
    // Only the completed row: deleting a running backup would race its own
    // writer, and the API rejects it with 409 anyway.
    expect(deletes.length).toBe(1)
  })

  it('deletes through the API and refreshes the list', async () => {
    const wrapper = await mountBackups()
    fetchMock.mockClear()

    const del = wrapper.findAll('button').find((b) => b.text() === en.backupsView.delete)
    await del!.trigger('click')
    await flushPromises()

    const call = fetchMock.mock.calls.find(
      (c) => String(c[0]).includes(`/stateful/backups/${COMPLETED_BACKUP.backup_id}`) &&
        (c[1] as RequestInit)?.method === 'DELETE',
    )
    expect(call, 'no DELETE request was issued for the backup').toBeDefined()

    // The list must be re-read, or the deleted row lingers until a manual reload.
    const refetched = fetchMock.mock.calls.filter(
      (c) => String(c[0]).includes('/stateful/backups') && !(c[1] as RequestInit)?.method?.includes('DELETE'),
    )
    expect(refetched.length).toBeGreaterThan(0)
  })

  it('confirms before deleting, because the stored file goes with it', async () => {
    const wrapper = await mountBackups()
    vi.mocked(window.confirm).mockReturnValue(false)
    fetchMock.mockClear()

    const del = wrapper.findAll('button').find((b) => b.text() === en.backupsView.delete)
    await del!.trigger('click')
    await flushPromises()

    const deleteCalls = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'DELETE')
    expect(deleteCalls.length, 'a declined confirm still issued the DELETE').toBe(0)
  })
})
