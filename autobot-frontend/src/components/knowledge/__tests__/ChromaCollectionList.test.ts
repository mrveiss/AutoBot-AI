// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #19725: the vector browser lists collections that hold something, and empties on request. */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChromaCollectionList from '../ChromaCollectionList.vue'

const COLLECTIONS = [
  { name: 'docs', count: 2 },
  { name: 'work_item_a', count: 0 },
]

function list(collections = COLLECTIONS) {
  return mount(ChromaCollectionList, {
    props: { collections },
    global: { mocks: { $t: (key: string) => key } },
  })
}

describe('ChromaCollectionList', () => {
  it('hides empty collections until asked', async () => {
    const wrapper = list()
    expect(wrapper.findAll('.collection-name').map((n) => n.text())).toEqual(['docs'])
    await wrapper.find('input').setValue(true)
    expect(wrapper.findAll('.collection-name').map((n) => n.text())).toEqual(['docs', 'work_item_a'])
  })

  it('offers no toggle when nothing is hidden', () => {
    expect(list([{ name: 'docs', count: 2 }]).find('input').exists()).toBe(false)
  })

  it('still offers the toggle when every collection is empty', () => {
    const wrapper = list([{ name: 'work_item_a', count: 0 }])
    expect(wrapper.findAll('.collection-name')).toHaveLength(0)
    expect(wrapper.find('input').exists()).toBe(true)
  })

  it('names the one chosen', async () => {
    const wrapper = list()
    await wrapper.find('.collection-item').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([COLLECTIONS[0]])
  })
})
