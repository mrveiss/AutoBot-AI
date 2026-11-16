// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// VisionCaptureView (#20644): what moved from the SLM's Vision tool. A camera or screen capture becomes
// the image, the existing multimodal client analyses it, each analysis lands in the history, and a
// failed capture or analysis is shown.

import { describe, it, expect, beforeEach, beforeAll, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { processImage, captureImage, canCapture } = vi.hoisted(() => ({
  processImage: vi.fn(),
  captureImage: vi.fn(),
  canCapture: vi.fn(() => true),
}))

vi.mock('@/composables/useVisionApi', () => ({ processImage }))
vi.mock('@/composables/useImageCapture', () => ({ captureImage, canCapture, CaptureError: class extends Error {} }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
// The kit barrel pulls reka-ui; BaseTabs is stubbed to render every panel so each source is reachable.
vi.mock('@autobot/ui', () => ({
  httpErrorText: (err: unknown, fallback: string) => (err instanceof Error && err.message ? err.message : fallback),
  formatDateTime: () => 'when',
  PageHeader: { template: '<header />' },
  BaseButton: { props: ['disabled', 'loading'], emits: ['click'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  BaseCard: { props: ['title'], template: '<section><slot name="actions" /><slot /></section>' },
  BaseBadge: { props: ['label'], template: '<span>{{ label }}</span>' },
  BaseAlert: { props: ['message'], template: '<p role="alert">{{ message }}</p>' },
  BaseSelectMenu: { props: ['modelValue', 'options', 'label'], template: '<select />' },
  BaseInput: { props: ['modelValue', 'label'], template: '<input />' },
  BaseTabs: {
    props: ['items', 'label', 'modelValue'],
    template: '<div><div v-for="item in items" :key="item.value"><slot :name="`panel-${item.value}`" /></div></div>',
  },
  EmptyState: { props: ['title', 'description'], template: '<div><p>{{ title }}</p></div>' },
}))

import VisionCaptureView from '../VisionCaptureView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const png = (name = 'shot.png') => new File(['x'], name, { type: 'image/png' })
const reply = (description: string) => ({
  success: true, result_id: 'r', modality: 'image', processing_time: 0.5, confidence: 0.9,
  result_data: { description, labels: ['cat'] },
})

const mountView = () => mount(VisionCaptureView, { global: { plugins: [i18n] } })

beforeAll(() => {
  let n = 0
  URL.createObjectURL = vi.fn(() => `blob:${++n}`)
  URL.revokeObjectURL = vi.fn()
})

describe('VisionCaptureView (#20644)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    canCapture.mockReturnValue(true)
  })

  it('takes a camera still and analyses it with the multimodal client', async () => {
    captureImage.mockResolvedValue(png())
    processImage.mockResolvedValue(reply('A cat on a sofa'))
    const wrapper = mountView()
    await wrapper.get('[data-testid="vision-capture-camera"]').trigger('click')
    await flushPromises()
    expect(captureImage).toHaveBeenCalledWith('camera')
    await wrapper.get('[data-testid="vision-analyze"]').trigger('click')
    await flushPromises()
    expect(processImage).toHaveBeenCalledWith(expect.any(File), 'analysis', undefined)
    expect(wrapper.get('[data-testid="vision-result"]').text()).toContain('A cat on a sofa')
  })

  it('captures a shared screen', async () => {
    captureImage.mockResolvedValue(png())
    const wrapper = mountView()
    await wrapper.get('[data-testid="vision-capture-screen"]').trigger('click')
    await flushPromises()
    expect(captureImage).toHaveBeenCalledWith('screen')
    expect(wrapper.find('[data-testid="vision-analyze"]').exists()).toBe(true)
  })

  it('shows a declined capture instead of failing silently', async () => {
    captureImage.mockRejectedValue(new Error('Permission denied'))
    const wrapper = mountView()
    await wrapper.get('[data-testid="vision-capture-camera"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="vision-error"]').text()).toBe('The image could not be captured: Permission denied')
  })

  it('disables a capture source the browser cannot use, and says why', () => {
    canCapture.mockReturnValue(false)
    const wrapper = mountView()
    expect(wrapper.get('[data-testid="vision-capture-camera"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('This browser cannot capture here.')
  })

  it('shows a failed analysis and adds nothing to the history', async () => {
    captureImage.mockResolvedValue(png())
    processImage.mockRejectedValue(new Error('Model unavailable'))
    const wrapper = mountView()
    await wrapper.get('[data-testid="vision-capture-camera"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="vision-analyze"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="vision-error"]').text()).toBe('Model unavailable')
    expect(wrapper.find('[data-testid="vision-history"]').exists()).toBe(false)
  })

  it('records each analysis in the history and reopens it', async () => {
    captureImage.mockResolvedValueOnce(png('one.png')).mockResolvedValueOnce(png('two.png'))
    processImage.mockResolvedValueOnce(reply('first')).mockResolvedValueOnce(reply('second'))
    const wrapper = mountView()
    for (let i = 0; i < 2; i++) {
      await wrapper.get('[data-testid="vision-capture-camera"]').trigger('click')
      await flushPromises()
      await wrapper.get('[data-testid="vision-analyze"]').trigger('click')
      await flushPromises()
    }
    const items = wrapper.get('[data-testid="vision-history"]').findAll('button')
    expect(items).toHaveLength(2)
    await items[1].trigger('click')
    expect(wrapper.get('[data-testid="vision-result"]').text()).toContain('first')
  })
})
