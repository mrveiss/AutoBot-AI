// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Tests for KnowledgeUpload.vue — file upload section.
 *
 * Covers:
 *  - Idle render: drop zone visible, no files selected
 *  - File selection: valid file added to the list
 *  - File type rejection: unsupported extension sets errorMessage
 *  - File size rejection: oversized file sets errorMessage
 *  - Duplicate detection: same file added twice appears only once
 *  - Upload triggering: uploadFiles calls controller.addFileDocument
 *  - Upload success state: file item status set to 'completed'
 *  - Upload failure state: file item status set to 'failed'
 *  - Remove file: removeFile removes item from list
 *  - Clear all: clearAllFiles empties the list
 *  - Drag and drop visual states
 *
 * NOTE: vitest.config has mockReset: true which clears vi.mock() factory
 * implementations between tests. All mock implementations are re-applied in
 * beforeEach.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { nextTick } from 'vue'

// ── Module-level mocks ───────────────────────────────────────────────────────
// vi.mock() calls are hoisted by Vitest so they always execute before any
// import statements even though they appear below.

// Mock vue-i18n: the component calls `useI18n()` in <script setup> AND uses
// `$t(...)` inside the template. We cover both paths:
//   • useI18n() mock: handled by vi.mock below + re-applied in beforeEach
//   • $t global: provided via global.mocks in every mount() call
vi.mock('vue-i18n', () => ({
  useI18n: vi.fn()
}))

// Controllers / composables replaced with lightweight stubs
vi.mock('@/models/controllers', () => ({
  useKnowledgeController: vi.fn()
}))

vi.mock('@/composables/knowledge/useKnowledgeIcons', () => ({
  useKnowledgeIcons: vi.fn()
}))

vi.mock('@/composables/useUploadProgress', () => ({
  useUploadProgress: vi.fn()
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  })
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import { useI18n } from 'vue-i18n'
import { useKnowledgeController } from '@/models/controllers'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { useUploadProgress } from '@/composables/useUploadProgress'
import KnowledgeUpload from '../KnowledgeUpload.vue'

// ── Mock factories ────────────────────────────────────────────────────────────

/** Returns the translation key verbatim — sufficient for existence checks. */
const stubT = (key: string, _params?: object) => key

function makeControllerMock() {
  return {
    loadCategories: vi.fn().mockResolvedValue(undefined),
    addTextDocument: vi.fn().mockResolvedValue(undefined),
    addUrlDocument: vi.fn().mockResolvedValue(undefined),
    addFileDocument: vi.fn().mockResolvedValue(undefined)
  }
}

function makeUploadProgressMock() {
  const progress = {
    show: false,
    title: '',
    status: '',
    percentage: 0
  }
  return {
    progress,
    startProgress: vi.fn(),
    completeProgress: vi.fn(),
    hideProgress: vi.fn(),
    simulateProgress: vi.fn().mockReturnValue(0 as unknown as ReturnType<typeof setInterval>)
  }
}

function makeKnowledgeBaseMock() {
  return {
    getFileIcon: vi.fn().mockReturnValue('fas fa-file')
  }
}

/** Apply all mock return values. Call this in beforeEach and before mount. */
function applyMocks(
  controllerMock: ReturnType<typeof makeControllerMock>,
  progressMock: ReturnType<typeof makeUploadProgressMock>
) {
  vi.mocked(useI18n).mockReturnValue({ t: stubT } as any)
  vi.mocked(useKnowledgeController).mockReturnValue(controllerMock as any)
  vi.mocked(useUploadProgress).mockReturnValue(progressMock as any)
  vi.mocked(useKnowledgeIcons).mockReturnValue(makeKnowledgeBaseMock() as any)
}

// ── Mount helper ─────────────────────────────────────────────────────────────

function mountKnowledgeUpload(
  controllerMock = makeControllerMock(),
  progressMock = makeUploadProgressMock()
) {
  applyMocks(controllerMock, progressMock)

  return mount(KnowledgeUpload, {
    global: {
      plugins: [
        createTestingPinia({
          createSpy: vi.fn,
          initialState: {
            knowledge: {
              categories: [{ id: 'cat1', name: 'Documentation' }]
            }
          }
        })
      ],
      // $t is used directly in the template ({{ $t(...) }}). global.mocks
      // injects it on every component instance in the subtree.
      mocks: {
        $t: stubT
      },
      // Stub BaseAlert to render predictably without requiring full vue-i18n setup
      stubs: {
        BaseAlert: {
          template: '<div class="base-alert" :data-variant="variant" :data-message="message"><slot>{{ message }}</slot></div>',
          props: ['variant', 'message']
        }
      }
    }
  })
}

// ── File utilities ────────────────────────────────────────────────────────────

/** Creates a File object filled with zero-bytes of the given size. */
function makeFile(name: string, sizeBytes: number, mimeType = 'text/plain'): File {
  const content = new Uint8Array(sizeBytes)
  return new File([content], name, { type: mimeType })
}

/**
 * Simulates selecting files via the hidden <input type="file"> inside the drop
 * zone (the one with the `accept` attribute).
 *
 * configurable: true is required so the property can be redefined on the same
 * element in subsequent calls within the same test (e.g. duplicate-detection
 * test calls selectFiles twice on the same wrapper).
 */
async function selectFiles(wrapper: any, files: File[]) {
  const fileInput = wrapper.find('input[type="file"][accept]')
  Object.defineProperty(fileInput.element, 'files', {
    value: files,
    writable: false,
    configurable: true
  })
  await fileInput.trigger('change')
  // Allow async addFiles() microtasks to complete
  await nextTick()
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('KnowledgeUpload — file upload section', () => {
  let controllerMock: ReturnType<typeof makeControllerMock>
  let progressMock: ReturnType<typeof makeUploadProgressMock>

  beforeEach(() => {
    // Re-apply mock implementations every test — required because vitest.config
    // has mockReset: true which wipes vi.mock() factory implementations.
    controllerMock = makeControllerMock()
    progressMock = makeUploadProgressMock()
    applyMocks(controllerMock, progressMock)
  })

  // ── Idle render ─────────────────────────────────────────────────────────

  it('renders the drop zone in idle state', () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    expect(wrapper.find('.file-drop-zone').exists()).toBe(true)
    expect(wrapper.find('.selected-files').exists()).toBe(false)
    expect(wrapper.find('.batch-options').exists()).toBe(false)
  })

  it('calls loadCategories on mount', () => {
    mountKnowledgeUpload(controllerMock, progressMock)
    expect(controllerMock.loadCategories).toHaveBeenCalledOnce()
  })

  it('does not show any alerts in idle state', () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)
    expect(wrapper.findAll('.base-alert')).toHaveLength(0)
  })

  // ── File selection ───────────────────────────────────────────────────────

  it('adds a valid supported file to the selected files list', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['hello world'], 'readme.txt', { type: 'text/plain' })])

    expect(wrapper.find('.selected-files').exists()).toBe(true)
    expect(wrapper.find('.file-name').text()).toContain('readme.txt')
  })

  it('shows the upload button once at least one file is selected', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['x'], 'data.csv', { type: 'text/csv' })])

    expect(wrapper.find('.upload-btn').exists()).toBe(true)
  })

  it('accepts multiple files at once', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [
      new File(['a'], 'a.txt', { type: 'text/plain' }),
      new File(['b'], 'b.md', { type: 'text/markdown' }),
      new File(['c'], 'c.json', { type: 'application/json' })
    ])

    expect(wrapper.findAll('.file-item')).toHaveLength(3)
  })

  // ── File type rejection ──────────────────────────────────────────────────

  it('sets an error alert when an unsupported file type (.exe) is selected', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['MZ'], 'program.exe', { type: 'application/octet-stream' })])

    expect(wrapper.find('.selected-files').exists()).toBe(false)
    const alert = wrapper.find('.base-alert')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-variant')).toBe('error')
  })

  it('rejects .zip files (unsupported extension)', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['PK'], 'archive.zip', { type: 'application/zip' })])

    expect(wrapper.find('.selected-files').exists()).toBe(false)
    expect(wrapper.find('.base-alert').exists()).toBe(true)
  })

  it('rejects image files (.png)', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['\x89PNG'], 'photo.png', { type: 'image/png' })])

    expect(wrapper.find('.selected-files').exists()).toBe(false)
    expect(wrapper.find('.base-alert').exists()).toBe(true)
  })

  // ── File size rejection ──────────────────────────────────────────────────

  it('sets an error alert when a file exceeds the 10 MB limit', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    // 10 MB + 1 byte
    await selectFiles(wrapper, [makeFile('big.txt', 10 * 1024 * 1024 + 1)])

    expect(wrapper.find('.selected-files').exists()).toBe(false)
    const alert = wrapper.find('.base-alert')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-variant')).toBe('error')
  })

  it('accepts a file exactly at the 10 MB limit', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [makeFile('exact.txt', 10 * 1024 * 1024)])

    expect(wrapper.find('.selected-files').exists()).toBe(true)
    expect(wrapper.find('.base-alert').exists()).toBe(false)
  })

  // ── Duplicate detection ──────────────────────────────────────────────────

  it('does not add a duplicate file (same name and size)', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    const file = new File(['hello'], 'note.txt', { type: 'text/plain' })
    // Select the same file twice — configurable: true in selectFiles() allows
    // the second Object.defineProperty call on the same element.
    await selectFiles(wrapper, [file])
    await selectFiles(wrapper, [file])

    expect(wrapper.findAll('.file-item')).toHaveLength(1)
  })

  // ── Remove / clear ───────────────────────────────────────────────────────

  it('removes a file when the remove button is clicked', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['x'], 'keep.md', { type: 'text/markdown' })])
    expect(wrapper.find('.file-item').exists()).toBe(true)

    await wrapper.find('.remove-file-btn').trigger('click')
    await nextTick()

    expect(wrapper.find('.file-item').exists()).toBe(false)
  })

  it('clears all files when the clear-all button is clicked', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [
      new File(['a'], 'a.txt', { type: 'text/plain' }),
      new File(['b'], 'b.md', { type: 'text/markdown' })
    ])
    expect(wrapper.findAll('.file-item')).toHaveLength(2)

    await wrapper.find('.clear-all-btn').trigger('click')
    await nextTick()

    expect(wrapper.find('.selected-files').exists()).toBe(false)
  })

  // ── Upload ───────────────────────────────────────────────────────────────

  it('calls controller.addFileDocument for each selected file on upload', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [
      new File(['a'], 'a.txt', { type: 'text/plain' }),
      new File(['b'], 'b.csv', { type: 'text/csv' })
    ])

    await wrapper.find('.upload-btn').trigger('click')
    await nextTick()
    await nextTick()

    expect(controllerMock.addFileDocument).toHaveBeenCalledTimes(2)
  })

  it('marks a file item as "completed" after a successful upload', async () => {
    controllerMock.addFileDocument.mockResolvedValue(undefined)
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['data'], 'report.json', { type: 'application/json' })])

    await wrapper.find('.upload-btn').trigger('click')
    await nextTick()
    await nextTick()

    expect(wrapper.find('.file-item.completed').exists()).toBe(true)
  })

  it('marks a file item as "failed" after an upload error', async () => {
    controllerMock.addFileDocument.mockRejectedValue(new Error('Network error'))
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await selectFiles(wrapper, [new File(['data'], 'report.json', { type: 'application/json' })])

    await wrapper.find('.upload-btn').trigger('click')
    await nextTick()
    await nextTick()

    expect(wrapper.find('.file-item.failed').exists()).toBe(true)
  })

  // ── Drag and drop ────────────────────────────────────────────────────────

  it('adds "dragging" class to the drop zone during dragenter', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await wrapper.find('.file-drop-zone').trigger('dragenter', {
      dataTransfer: { items: [] }
    })

    expect(wrapper.find('.file-drop-zone.dragging').exists()).toBe(true)
  })

  it('removes "dragging" class after dragleave when counter reaches zero', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    const dropZone = wrapper.find('.file-drop-zone')
    await dropZone.trigger('dragenter', { dataTransfer: { items: [] } })
    await dropZone.trigger('dragleave')

    expect(wrapper.find('.file-drop-zone.dragging').exists()).toBe(false)
  })

  it('adds a valid file dropped onto the drop zone', async () => {
    const wrapper = mountKnowledgeUpload(controllerMock, progressMock)

    await wrapper.find('.file-drop-zone').trigger('drop', {
      dataTransfer: { files: [new File(['hello'], 'notes.txt', { type: 'text/plain' })] }
    })
    await nextTick()

    expect(wrapper.find('.selected-files').exists()).toBe(true)
  })
})
