// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useChatSidebarSessions (#18243): search, multi-select, rename, share and delete, as they behaved
// inside ChatSidebar before the extraction.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  store: { sessions: [] as unknown[], currentSessionId: 'a' as string | null },
  controller: {
    deleteChatSession: vi.fn().mockResolvedValue(undefined),
    updateSessionTitle: vi.fn(),
    getSessionFacts: vi.fn().mockResolvedValue({ facts: [{ id: 'f1' }, { id: 'f2' }] }),
    preserveSessionFacts: vi.fn().mockResolvedValue({ updated_count: 1 }),
  },
  confirm: vi.fn().mockResolvedValue(true),
  showToast: vi.fn(),
  call: vi.fn().mockResolvedValue({ files: [] }),
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => h.store }))
vi.mock('@/models/controllers', () => ({ useChatController: () => h.controller }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: h.confirm }) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: h.showToast }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { call: h.call } }))
vi.mock('@/utils/conversationFileList', () => ({ mapFileList: () => ({ stats: { total: 0 } }) }))

import { useChatSidebarSessions } from '../useChatSidebarSessions'

const session = (id: string, title: string, content?: string) => ({
  id, title, updatedAt: new Date(),
  messages: content ? [{ sender: 'user', content }] : [],
})

function setup() {
  let api!: ReturnType<typeof useChatSidebarSessions>
  mount({ setup() { api = useChatSidebarSessions(); return () => null } }, {
    global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
  return api
}

beforeEach(() => {
  vi.clearAllMocks()
  h.confirm.mockResolvedValue(true)
  h.store.sessions = reactive([session('abcdefgh12345678', 'Alpha'), session('b', '', 'Hello there, this is a long first message'), session('c', '')])
})

describe('preview and search', () => {
  it('falls back from title to the first user message to a short id', () => {
    const api = setup()
    const [a, b, c] = h.store.sessions as ReturnType<typeof session>[]
    expect(api.getSessionPreview(a as never)).toBe('Chat 12345678...')
    expect(api.getSessionPreview(b as never)).toBe('Hello there, this is a long fi...')
    expect(api.getSessionPreview(c as never)).toBe('Chat c...')
  })

  it('filters by title or preview, case-insensitively, and clears', () => {
    const api = setup()
    api.searchQuery.value = 'ALP'
    expect(api.filteredSessions.value).toHaveLength(1)
    api.searchQuery.value = 'hello'
    expect(api.filteredSessions.value.map((s) => s.id)).toEqual(['b'])
    api.clearSearch()
    expect(api.filteredSessions.value).toHaveLength(3)
  })
})

describe('selection', () => {
  it('enters and leaves selection mode, clearing the selection', () => {
    const api = setup()
    api.enableSelectionMode()
    api.sessionSelection.toggle(h.store.sessions[0] as never)
    expect(api.sessionSelection.selectedCount.value).toBe(1)
    api.cancelSelection()
    expect(api.selectionMode.value).toBe(false)
    expect(api.sessionSelection.selectedCount.value).toBe(0)
  })

  it('deletes every selected session after confirming, and does nothing when declined', async () => {
    const api = setup()
    api.enableSelectionMode()
    api.sessionSelection.toggle(h.store.sessions[0] as never)
    api.sessionSelection.toggle(h.store.sessions[1] as never)
    h.confirm.mockResolvedValueOnce(false)
    await api.deleteSelectedSessions()
    expect(h.controller.deleteChatSession).not.toHaveBeenCalled()
    await api.deleteSelectedSessions()
    expect(h.controller.deleteChatSession).toHaveBeenCalledTimes(2)
    expect(api.selectionMode.value).toBe(false)
  })
})

describe('rename and share', () => {
  it('opens the modal with the title and saves the new name', async () => {
    const api = setup()
    await api.editSessionName(h.store.sessions[0] as never)
    expect(api.showEditModal.value).toBe(true)
    expect(api.editingName.value).toBe('Alpha')
    api.editingName.value = 'Renamed'
    api.saveSessionName()
    expect(h.controller.updateSessionTitle).toHaveBeenCalledWith('abcdefgh12345678', 'Renamed')
    expect(api.showEditModal.value).toBe(false)
  })

  it('opens the share dialog for a session and toasts the result', () => {
    const api = setup()
    api.openShareDialog('b')
    expect(api.showShareDialog.value).toBe(true)
    expect(api.shareTargetSessionId.value).toBe('b')
    api.handleShareComplete({ shared_with: ['x'] })
    expect(api.showShareDialog.value).toBe(false)
    expect(h.showToast).toHaveBeenCalledWith(en.chat.sidebar.sharedSuccess.replace('{count}', '1'), 'success')
  })
})

describe('delete with the knowledge-fact preview', () => {
  it.each([
    [[], [], 0, 'Deleted 1 chat'],
    [[{ id: 'f1' }, { id: 'f2' }], ['f1', 'f2'], 2, 'Deleted 1 chat (facts preserved in knowledge base)'],
    [[{ id: 'f1' }, { id: 'f2' }], [], 0, 'Deleted 1 chat and removed associated facts'],
  ])('toasts the singular rendered count for %j preserving %j', async (facts, keep, confirmed, text) => {
    h.controller.getSessionFacts.mockResolvedValueOnce({ facts })
    if (keep.length) h.controller.preserveSessionFacts.mockResolvedValueOnce({ updated_count: confirmed })
    const api = setup()
    await api.deleteSession('b')
    await api.handleDeleteConfirm('delete', undefined, keep as string[])
    expect(h.showToast).toHaveBeenCalledWith(text, 'success')
    expect(String(h.showToast.mock.calls.at(-1)?.[0])).not.toMatch(/Deleted\s{2}|\{count\}|chats/)
  })

  it('loads the preview, then deletes after preserving the ticked facts', async () => {
    const api = setup()
    await api.deleteSession('b')
    expect(api.showDeleteDialog.value).toBe(true)
    expect(api.deleteKBFacts.value).toHaveLength(2)
    expect(h.call).toHaveBeenCalledWith('get', '/api/conversation-files/conversation/{session_id}/list', { path: { session_id: 'b' } })
    await api.handleDeleteConfirm('delete', undefined, ['f1'])
    expect(h.controller.preserveSessionFacts).toHaveBeenCalledWith('b', ['f1'], true)
    expect(h.controller.deleteChatSession).toHaveBeenCalledWith('b', 'delete', undefined)
    expect(h.showToast).toHaveBeenCalledWith('Deleted 1 chat (facts removed from some, preserved in others)', 'success')
    expect(api.showDeleteDialog.value).toBe(false)
  })

  it('still deletes when the file list or preserving fails, and reports a failed delete', async () => {
    const api = setup()
    h.call.mockRejectedValueOnce(new Error('files down'))
    await api.deleteSession('b')
    expect(api.deleteFileStats.value).toBeNull()
    h.controller.preserveSessionFacts.mockRejectedValueOnce(new Error('x'))
    await api.handleDeleteConfirm('delete', undefined, ['f1'])
    expect(h.controller.deleteChatSession).toHaveBeenCalled()
    await api.deleteSession('b')
    h.controller.deleteChatSession.mockRejectedValueOnce(new Error('boom'))
    await api.handleDeleteConfirm('delete')
    expect(h.showToast).toHaveBeenLastCalledWith(en.chat.sidebar.deleteFailed, 'error')
  })

  it('reports only the facts the backend confirmed, and warns when some were not preserved', async () => {
    h.controller.preserveSessionFacts.mockResolvedValueOnce({ updated_count: 1 })
    const api = setup()
    await api.deleteSession('b')
    await api.handleDeleteConfirm('delete', undefined, ['f1', 'f2'])
    expect(h.showToast).toHaveBeenCalledWith(en.chat.sidebar.preserveFailed, 'warning')
    expect(h.showToast).toHaveBeenCalledWith(expect.stringContaining('Deleted 1 chat'), 'success')
  })

  it('keeps a failed preview distinct from an empty one', async () => {
    const api = setup()
    h.controller.getSessionFacts.mockResolvedValueOnce({ facts: [] })
    await api.deleteSession('b')
    expect(api.deletePreviewFailed.value).toBe(false)
    h.controller.getSessionFacts.mockRejectedValueOnce(new Error('kb down'))
    await api.deleteSession('b')
    expect(api.deletePreviewFailed.value).toBe(true)
    expect(api.deleteKBFacts.value).toBeNull()
    expect(h.showToast).toHaveBeenCalledWith(en.chat.sidebar.previewFailed, 'warning')
  })

  it('ignores the previews of a superseded request', async () => {
    const api = setup()
    let release!: (v: unknown) => void
    h.controller.getSessionFacts.mockReturnValueOnce(new Promise((resolve) => { release = resolve }))
    const first = api.deleteSession('a')
    h.controller.getSessionFacts.mockResolvedValueOnce({ facts: [{ id: 'only-b' }] })
    await api.deleteSession('b')
    release({ facts: [{ id: 'from-a' }, { id: 'from-a2' }] })
    await first
    expect(api.deleteTargetSessionId.value).toBe('b')
    expect(api.deleteKBFacts.value).toEqual([{ id: 'only-b' }])
  })

  it('cancelling closes the dialog and forgets the target', async () => {
    const api = setup()
    await api.deleteSession('b')
    api.handleDeleteCancel()
    expect(api.showDeleteDialog.value).toBe(false)
    expect(api.deleteTargetSessionId.value).toBeNull()
  })

  it('deleteCurrentSession targets the open chat', async () => {
    const api = setup()
    api.deleteCurrentSession()
    await vi.waitFor(() => expect(api.deleteTargetSessionId.value).toBe('a'))
  })
})
