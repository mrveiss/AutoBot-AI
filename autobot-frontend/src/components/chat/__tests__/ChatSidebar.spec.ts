// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSidebar (#18243): composes the toolbar, the session list and System Control; new chat,
// search, selection, rename and delete still reach the controller, and Reload System still posts.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  store: { sessions: [] as unknown[], currentSessionId: 'a' as string | null, sidebarCollapsed: false },
  rs: null as never,
  folders: { folders: [] as unknown[], archivedFolders: [] as unknown[], fetchFolders: vi.fn(), assignSessionToFolder: vi.fn() },
  controller: {
    createNewSession: vi.fn(), switchToSession: vi.fn(), toggleSidebar: vi.fn(), resetCurrentChat: vi.fn(),
    loadChatSessions: vi.fn(), updateSessionTitle: vi.fn(), deleteChatSession: vi.fn().mockResolvedValue(undefined),
    getSessionFacts: vi.fn().mockResolvedValue({ facts: [] }), preserveSessionFacts: vi.fn(),
  },
  call: vi.fn(),
  confirm: vi.fn().mockResolvedValue(true),
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => h.rs }))
vi.mock('@/stores/useFolderStore', () => ({ useFolderStore: () => h.folders }))
vi.mock('@/models/controllers', () => ({ useChatController: () => h.controller }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: h.confirm }) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { call: h.call } }))
vi.mock('../ChatFolderTree.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ChatFolderNode.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../DeleteConversationDialog.vue', () => ({ default: { props: ['visible', 'sessionId'], template: '<div v-if="visible" data-testid="delete-dialog" :data-session="sessionId" />' } }))
vi.mock('../ShareConversationDialog.vue', () => ({ default: { props: ['visible'], template: '<div v-if="visible" data-testid="share-dialog" />' } }))

import ChatSidebar from '../ChatSidebar.vue'

// The store is read through a reactive proxy, so collapsing it re-renders the sidebar.
h.rs = reactive(h.store)

const session = (id: string, title: string) => ({ id, title, updatedAt: new Date(), messages: [{ sender: 'user', content: 'x' }] })
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = () => mount(ChatSidebar, { attachTo: document.body, global: { plugins: [i18n] } })
const byLabel = (w: ReturnType<typeof render>, label: string) => w.findAll('button').find((b) => b.attributes('aria-label') === label)!
const rowTitles = (w: ReturnType<typeof render>) => w.findAll('.chat-session-row__title').map((r) => r.text())

beforeEach(() => {
  vi.clearAllMocks()
  h.rs.sessions = reactive([session('a', 'Fleet check'), session('b', 'NPU plan')])
  h.rs.sidebarCollapsed = false
  h.call.mockResolvedValue(null)
})

describe('ChatSidebar', () => {
  it('lists the sessions and starts a new chat from the toolbar', async () => {
    const w = render()
    expect(rowTitles(w)).toEqual(['Fleet check', 'NPU plan'])
    await w.get('.aui-btn--primary').trigger('click')
    expect(h.controller.createNewSession).toHaveBeenCalled()
    w.unmount()
  })

  it('filters the list by the search text', async () => {
    const w = render()
    await w.get('input[type="search"]').setValue('npu')
    expect(rowTitles(w)).toEqual(['NPU plan'])
    w.unmount()
  })

  it('opens a session and closes the mobile overlay', async () => {
    const w = render()
    await w.findAll('.chat-session-row')[1].trigger('click')
    expect(h.controller.switchToSession).toHaveBeenCalledWith('b')
    expect(w.emitted('close-mobile')).toHaveLength(1)
    w.unmount()
  })

  it('selection mode shows checkboxes and deletes the ticked chats', async () => {
    const w = render()
    await byLabel(w, 'Select chats').trigger('click')
    await w.findAll('input[type="checkbox"]')[0].trigger('click')
    await byLabel(w, 'Delete Selected').trigger('click')
    await flushPromises()
    expect(h.confirm).toHaveBeenCalled()
    expect(h.controller.deleteChatSession).toHaveBeenCalledWith('a')
    w.unmount()
  })

  it('Delete Chat opens the delete dialog for the open chat', async () => {
    h.rs.currentSessionId = 'a'
    const w = render()
    await byLabel(w, 'Delete Chat').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="delete-dialog"]').exists()).toBe(true)
    expect(w.get('[data-testid="delete-dialog"]').attributes('data-session')).toBe('a')
    w.unmount()
  })

  it('keeps Reset Chat and Refresh List, disabling Reset without an open chat', async () => {
    h.rs.currentSessionId = null
    const w = render()
    expect(byLabel(w, 'Reset Chat').attributes('disabled')).toBeDefined()
    await byLabel(w, 'Refresh List').trigger('click')
    expect(h.controller.loadChatSessions).toHaveBeenCalled()
    h.rs.currentSessionId = 'a'
    w.unmount()
  })

  it('System Control is advanced and still posts the reload route', async () => {
    const w = render()
    const section = w.get('section.adv')
    expect(section.text()).toContain('System Control')
    h.call.mockResolvedValueOnce({ status: 'success' })
    await section.get('button').trigger('click')
    await flushPromises()
    expect(h.call).toHaveBeenCalledWith('post', '/api/system/reload_config')
    expect(section.text()).toContain('Ready')
    w.unmount()
  })

  it('System Control reports an error when the reload does not succeed', async () => {
    const w = render()
    const section = w.get('section.adv')
    h.call.mockRejectedValueOnce(new Error('down'))
    await section.get('button').trigger('click')
    await flushPromises()
    expect(section.text()).toContain('Error')
    w.unmount()
  })

  it('collapsed: shows only the toggle', () => {
    h.rs.sidebarCollapsed = true
    const w = render()
    expect(w.get('input[type="search"]').isVisible()).toBe(false)
    expect(w.get('section.adv').isVisible()).toBe(false)
    w.unmount()
  })

  it('keeps a pending reload when the sidebar collapses and expands', async () => {
    let finish!: (v: unknown) => void
    h.call.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    const w = render()
    await w.get('section.adv button').trigger('click')
    h.rs.sidebarCollapsed = true
    await flushPromises()
    h.rs.sidebarCollapsed = false
    await flushPromises()
    expect(w.get('section.adv').text()).toContain('Reloading')
    finish({ status: 'success' })
    await flushPromises()
    expect(w.get('section.adv').text()).toContain('Ready')
    w.unmount()
  })

  it('fetches the folders on mount', () => {
    render().unmount()
    expect(h.folders.fetchFolders).toHaveBeenCalled()
  })
})
