// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * VideoProcessor.processVideo gives each frame its own try/catch (#12363 slice 4): `processImage`
 * now throws on a non-2xx reply, and one rejected frame must be skipped, not abort the run, so the
 * completion event and toast still fire for the frames that did process.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'

const processImage = vi.fn()
const showToast = vi.fn()
vi.mock('@/composables/useVisionApi', () => ({ processImage: (...a: unknown[]) => processImage(...a) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast }) }))
vi.mock('@/composables/useThumbnailWorker', () => ({
  useThumbnailWorker: () => ({
    isSupported: { value: true },
    generateThumbnail: (...a: unknown[]) => generateThumbnail(...a),
  }),
}))

const generateThumbnail = vi.fn()
const OK = { confidence: 0.9, processing_time: 0.1, result_data: {} }

async function mountWithVideo() {
  const { default: VideoProcessor } = await import('../VideoProcessor.vue')
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const wrapper = mount(VideoProcessor, { global: { plugins: [i18n], stubs: { Icon: true } } })
  const file = new File(['x'], 'clip.mp4', { type: 'video/mp4' })
  await wrapper.find('.drop-zone').trigger('drop', { dataTransfer: { files: [file] } })
  ;(wrapper.vm as unknown as { videoDuration: number }).videoDuration = 6 // frames at 0s, 2s, 4s
  await flushPromises()
  return wrapper
}

describe('VideoProcessor frame failures', () => {
  beforeEach(() => {
    processImage.mockReset()
    showToast.mockReset()
    generateThumbnail.mockReset().mockResolvedValue('data:image/jpeg;base64,AAAA')
    URL.createObjectURL = vi.fn(() => 'blob:clip')
    URL.revokeObjectURL = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ blob: async () => new Blob(['f']) }))
  })

  it('skips a rejected frame and still completes with the others', async () => {
    processImage
      .mockRejectedValueOnce(new HttpError(500, 'boom'))
      .mockResolvedValue(OK)
    const wrapper = await mountWithVideo()
    await wrapper.find('.btn-process').trigger('click')
    await flushPromises()

    expect(processImage).toHaveBeenCalledTimes(3)
    const done = wrapper.emitted('analysis-complete')
    expect(done).toHaveLength(1)
    expect(done![0][0]).toMatchObject({ frames_processed: 2 })
    expect(showToast).toHaveBeenCalledWith('Processed 2 frames successfully', 'success')
    expect(showToast).toHaveBeenCalledWith('1 frame could not be analyzed and was skipped', 'warning')
    expect(wrapper.text()).not.toContain('HTTP 500')
  })

  it('shows the no-frames message, not raw HTTP text, when every frame fails', async () => {
    processImage.mockRejectedValue(new HttpError(500, 'boom'))
    const wrapper = await mountWithVideo()
    await wrapper.find('.btn-process').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('analysis-complete')).toBeUndefined()
    expect(wrapper.text()).toContain(en.vision.videoProcessor.errorNoFrames)
    expect(wrapper.text()).not.toContain('HTTP 500')
  })

  it('counts a frame that cannot be extracted as skipped in the toast', async () => {
    processImage.mockResolvedValue(OK)
    // No worker thumbnail and no canvas context for the second frame: extractFrame returns null.
    generateThumbnail
      .mockResolvedValueOnce('data:image/jpeg;base64,AAAA')
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('data:image/jpeg;base64,AAAA')
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const wrapper = await mountWithVideo()
    await wrapper.find('.btn-process').trigger('click')
    await flushPromises()

    expect(processImage).toHaveBeenCalledTimes(2)
    expect(showToast).toHaveBeenCalledWith('Processed 2 frames successfully', 'success')
    expect(showToast).toHaveBeenCalledWith('1 frame could not be analyzed and was skipped', 'warning')
  })

  it('pluralizes the skipped toast for several frames', async () => {
    processImage.mockResolvedValueOnce(OK).mockRejectedValue(new HttpError(500, 'boom'))
    const wrapper = await mountWithVideo()
    await wrapper.find('.btn-process').trigger('click')
    await flushPromises()

    expect(showToast).toHaveBeenCalledWith('2 frames could not be analyzed and were skipped', 'warning')
  })
})
