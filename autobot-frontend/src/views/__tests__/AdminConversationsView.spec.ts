// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for AdminConversationsView.vue (#17832): data, empty, failed, refused and
// not-available states for the org session list and the transcript drawer. The
// composable is mocked, so no HTTP is made; the server remains the authority.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'

const mockList = vi.fn()
const mockOpen = vi.fn()

vi.mock('@/composables/useOrgConversationReview', () => ({
  TRANSCRIPT_PAGE_SIZE: 50,
  useOrgConversationReview: () => ({ listOrgSessions: mockList, openTranscript: mockOpen }),
}))

import AdminConversationsView from '../AdminConversationsView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const copy = en.admin.conversations

let wrapper: VueWrapper | null = null

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(AdminConversationsView, { global: { plugins: [i18n] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

const orgList = (sessions: unknown[]) => ({ sessions, count: sessions.length, scope: 'org', org_id: 'org-1' })

describe('AdminConversationsView.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('asks the server for the org list once and lists the sessions it returns', async () => {
    mockList.mockResolvedValue(
      orgList([{ id: 's-1', title: 'Quarterly plan', messageCount: 7, lastModified: '2026-10-30T10:00:00Z' }]),
    )
    const view = await mountView()

    expect(mockList).toHaveBeenCalledTimes(1)
    expect(view.text()).toContain('Quarterly plan')
    expect(view.text()).toContain('s-1')
    expect(view.text()).toContain(copy.auditNotice)
  })

  it('opens one transcript through the server and shows its messages', async () => {
    mockList.mockResolvedValue(orgList([{ id: 's-1', title: 'Quarterly plan' }]))
    mockOpen.mockResolvedValue({
      messages: [{ id: 'm-1', sender: 'user', text: 'hello <b>there</b>', timestamp: '2026-10-30T10:00:00Z' }],
      session_id: 's-1',
      total_count: 1,
      page: 1,
      per_page: 50,
    })
    const view = await mountView()

    await view.findAll('button').find((b) => b.text() === copy.openTranscript)!.trigger('click')
    await flushPromises()

    expect(mockOpen).toHaveBeenCalledWith('s-1', 1)
    expect(document.body.textContent).toContain(copy.openAudited)
    // Message text is rendered as text, never as markup.
    expect(document.body.textContent).toContain('hello <b>there</b>')
    expect(document.body.querySelector('li b')).toBeNull()
  })

  it('shows the empty state when the org has no sessions', async () => {
    mockList.mockResolvedValue(orgList([]))
    const view = await mountView()

    expect(view.text()).toContain(copy.emptyTitle)
  })

  it('says organization review is not available when the account has no organization', async () => {
    mockList.mockResolvedValue({ sessions: [], count: 0, scope: 'org' })
    const view = await mountView()

    expect(view.text()).toContain(copy.noOrgTitle)
    expect(view.text()).not.toContain(copy.emptyTitle)
  })

  it('shows a failure with retry when the list cannot be loaded, and retries', async () => {
    mockList.mockRejectedValueOnce(new HttpError(500)).mockResolvedValueOnce(orgList([{ id: 's-2', title: 'Recovered' }]))
    const view = await mountView()

    expect(view.text()).toContain(copy.failedTitle)
    await view.findAll('button').find((b) => b.text() === en.common.retry)!.trigger('click')
    await flushPromises()

    expect(mockList).toHaveBeenCalledTimes(2)
    expect(view.text()).toContain('Recovered')
    expect(view.text()).not.toContain(copy.failedTitle)
  })

  it('reports the server refusing the list, not a generic failure', async () => {
    mockList.mockRejectedValue(new HttpError(403))
    const view = await mountView()

    expect(view.text()).toContain(copy.refusedTitle)
    expect(view.text()).not.toContain(copy.failedTitle)
  })

  it('reports the server refusing a transcript', async () => {
    mockList.mockResolvedValue(orgList([{ id: 's-9', title: 'Other org' }]))
    mockOpen.mockRejectedValue(new HttpError(403))
    const view = await mountView()

    await view.findAll('button').find((b) => b.text() === copy.openTranscript)!.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain(copy.transcriptRefusedTitle)
  })

  it('shows an empty transcript state when a session has no messages', async () => {
    mockList.mockResolvedValue(orgList([{ id: 's-3', title: 'Empty one' }]))
    mockOpen.mockResolvedValue({ messages: [], session_id: 's-3', total_count: 0, page: 1, per_page: 50 })
    const view = await mountView()

    await view.findAll('button').find((b) => b.text() === copy.openTranscript)!.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain(copy.noMessagesTitle)
  })
})
