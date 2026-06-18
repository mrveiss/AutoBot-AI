// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#9016 — VideoCell rendering tests
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VideoCell from './VideoCell.vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      videoCell: {
        copyUrl: 'Copy url',
        download: 'Download',
        failed: 'Video generation failed',
        generating: 'Generating video…',
        placeholder: 'Video',
      },
    },
  },
})

const mountCell = (richPayload: Record<string, unknown> | null) =>
  mount(VideoCell, {
    props: { richPayload },
    global: { stubs: { Icon: true }, plugins: [i18n] },
  })

describe('VideoCell.vue', () => {
  it('shows placeholder when richPayload is null', () => {
    const wrapper = mountCell(null)
    expect(wrapper.find('.video-placeholder').exists()).toBe(true)
    expect(wrapper.find('.video-content').exists()).toBe(false)
  })

  it('renders an inline video element when a video_url is present', () => {
    const wrapper = mountCell({
      video_url: 'https://v/clip.mp4',
      provider: 'runway',
      prompt: 'a sunrise',
      status: 'succeeded',
    })
    const video = wrapper.find('video.generated-video')
    expect(video.exists()).toBe(true)
    expect(video.attributes('src')).toBe('https://v/clip.mp4')
    expect(wrapper.find('.video-progress').exists()).toBe(false)
  })

  it('shows a progress indicator while generating', () => {
    const wrapper = mountCell({ provider: 'runway', status: 'running', progress: 0.4 })
    expect(wrapper.find('.video-progress').exists()).toBe(true)
    expect(wrapper.find('.progress-bar').attributes('style')).toContain('40%')
    expect(wrapper.find('video').exists()).toBe(false)
  })

  it('shows an error state when status is failed', () => {
    const wrapper = mountCell({ provider: 'runway', status: 'failed', error: 'moderation' })
    expect(wrapper.find('.video-error').exists()).toBe(true)
    expect(wrapper.text()).toContain('moderation')
  })

  it('maps the provider label', () => {
    const wrapper = mountCell({ video_url: 'https://v/c.mp4', provider: 'kling', status: 'succeeded' })
    expect(wrapper.find('.provider-badge').text()).toBe('Kling AI')
  })
})
