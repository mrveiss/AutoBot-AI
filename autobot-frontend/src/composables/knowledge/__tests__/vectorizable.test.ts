// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// The one vectorize rule (#22332): `pending` is not yet vectorized, so it is vectorizable.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { isVectorizable, vectorizableIds } from '../vectorizable'
import BatchSelectionToolbar from '@/components/knowledge/BatchSelectionToolbar.vue'
import VectorizationActionButton from '@/components/knowledge/VectorizationActionButton.vue'

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } })

describe('isVectorizable', () => {
  it.each([
    ['pending', true],
    ['failed', true],
    ['unknown', true],
    [undefined, true],
    ['vectorized', false],
  ] as const)('%s -> %s', (status, expected) => {
    expect(isVectorizable(status)).toBe(expected)
  })

  it('keeps ids that are unrecorded or not vectorized', () => {
    const states = new Map([['a', { status: 'vectorized' as const }], ['b', { status: 'pending' as const }]])
    expect(vectorizableIds(['a', 'b', 'c'], states)).toEqual(['b', 'c'])
  })
})

describe('the toolbar and the button follow the same rule', () => {
  it('BatchSelectionToolbar emits pending and failed ids, never vectorized ones', async () => {
    const w = mount(BatchSelectionToolbar, {
      props: {
        selectedDocuments: [
          { id: 'p', status: 'pending' },
          { id: 'f', status: 'failed' },
          { id: 'v', status: 'vectorized' },
        ],
      },
      global: { plugins: [i18n], stubs: { Icon: true } },
    })
    await w.get('.batch-vectorize').trigger('click')
    expect(w.emitted('vectorize')?.[0]).toEqual([['p', 'f']])
  })

  it('VectorizationActionButton is enabled for pending and disabled only when vectorized', () => {
    const mountWith = (status: 'pending' | 'vectorized') =>
      mount(VectorizationActionButton, { props: { documentId: 'd', status }, global: { plugins: [i18n], stubs: { Icon: true } } })
    expect(mountWith('pending').attributes('disabled')).toBeUndefined()
    expect(mountWith('vectorized').attributes('disabled')).toBeDefined()
  })
})
