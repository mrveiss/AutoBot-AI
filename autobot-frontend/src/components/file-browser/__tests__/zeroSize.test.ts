// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The missing-size text of the file browser comes from the `fileBrowser.zeroSize` i18n key
 * (#19885), so a locale can change it; the size formatter holds no display literal.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FilePreview from '../FilePreview.vue'
import FileListTable from '../FileListTable.vue'
import { fileBrowserSizeOptions, formatFileSize } from '@/utils/formatHelpers'

function i18nWith(zeroSize: string) {
  const messages = { fileBrowser: { ...en.fileBrowser, zeroSize } }
  return createI18n({ legacy: false, locale: 'en', messages: { en: messages } })
}

const globalCfg = (zeroSize: string) => ({
  plugins: [i18nWith(zeroSize)],
  stubs: { Icon: true, EmptyState: true, BaseButton: true },
})

describe('file browser missing-size text (#19885)', () => {
  it('FilePreview renders the locale key for a missing size', () => {
    const w = mount(FilePreview, {
      props: { showPreview: true, previewFile: { name: 'a.bin', type: 'other', fileType: 'bin' } },
      global: globalCfg('NULL-BAJTI'),
    })
    expect(w.find('.file-info').text()).toContain('NULL-BAJTI')
  })

  it('FileListTable renders the locale key for a missing size', () => {
    const w = mount(FileListTable, {
      props: {
        files: [{ name: 'a.bin', path: '/a.bin', is_dir: false }],
        sortField: 'name',
        sortOrder: 'asc',
      },
      global: globalCfg('NULL-BAJTI'),
    })
    expect(w.text()).toContain('NULL-BAJTI')
  })

  it('the options factory takes the text and still formats a real size', () => {
    const opts = fileBrowserSizeOptions('none')
    expect(formatFileSize(undefined, opts)).toBe('none')
    expect(formatFileSize(1536, opts)).toBe('1.5 KB')
  })
})
