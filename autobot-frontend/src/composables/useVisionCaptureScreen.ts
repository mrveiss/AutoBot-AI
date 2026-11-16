// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The Vision screen's behaviour (#20644): take or choose an image, analyse it, keep the history.
 *
 * What moved from the SLM's Vision tool is what only it offered: camera capture, capture of a shared
 * screen, and the history of the last 10 analyses. The analysis itself is the main app's existing
 * multimodal call (`useVisionApi.processImage` -> POST /api/multimodal/process/image), which reads
 * the uploaded image. The SLM's own "Analyze" is not ported: it sent the image to /api/vision/analyze,
 * which ignores it and analyses the server's screen instead.
 */
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { httpErrorText } from '@autobot/ui'
import { processImage } from '@/composables/useVisionApi'
import { captureImage, type CaptureSource } from '@/composables/useImageCapture'
import { useImageAnalysisHistory, type ImageAnalysisEntry } from '@/composables/useImageAnalysisHistory'
import { createLogger } from '@/utils/debugUtils'
import type { MultiModalResponse, ProcessingIntent } from '@/types/visionMultimodal'

const logger = createLogger('useVisionCaptureScreen')

/** The image being worked on, its preview URL (revoked when replaced or on leave), and its result. */
function useCurrentImage(error: Ref<string | null>) {
  const file = shallowRef<File | null>(null)
  const previewUrl = ref<string | null>(null)
  const result = shallowRef<MultiModalResponse | null>(null)

  function choose(next: File | null): void {
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    file.value = next
    previewUrl.value = next ? URL.createObjectURL(next) : null
    result.value = null
    error.value = null
  }

  onScopeDispose(() => choose(null))
  return { file, previewUrl, result, choose }
}

/** Camera or screen capture; a declined prompt or unsupported browser becomes the screen's error. */
function useCapture(choose: (file: File | null) => void, error: Ref<string | null>) {
  const { t } = useI18n()
  const capturing = ref(false)

  async function capture(source: CaptureSource): Promise<void> {
    capturing.value = true
    error.value = null
    try {
      choose(await captureImage(source))
    } catch (err) {
      logger.warn('Capture failed:', err)
      error.value = t('visionCapture.errors.capture', { detail: httpErrorText(err, t('visionCapture.errors.unknown')) })
    } finally {
      capturing.value = false
    }
  }

  return { capturing, capture }
}

/** Analyse the current image; each success lands in the history, a failure in the error. */
function useAnalysis(image: ReturnType<typeof useCurrentImage>, error: Ref<string | null>) {
  const { t } = useI18n()
  const history = useImageAnalysisHistory()
  const intent = ref<ProcessingIntent>('analysis')
  const question = ref('')
  const analyzing = ref(false)

  async function analyze(): Promise<void> {
    const file = image.file.value
    if (!file || analyzing.value) return
    const asked = intent.value === 'visual_qa' ? question.value.trim() || undefined : undefined
    analyzing.value = true
    error.value = null
    try {
      image.result.value = await processImage(file, intent.value, asked)
      history.add({ file, intent: intent.value, question: asked, result: image.result.value })
    } catch (err) {
      logger.error('Image analysis failed:', err)
      error.value = httpErrorText(err, t('visionCapture.errors.analysis'))
    } finally {
      analyzing.value = false
    }
  }

  return { history: history.entries, intent, question, analyzing, analyze }
}

export function useVisionCaptureScreen() {
  const error = ref<string | null>(null)
  const image = useCurrentImage(error)
  const capture = useCapture(image.choose, error)
  const analysis = useAnalysis(image, error)

  function reopen(entry: ImageAnalysisEntry): void {
    image.choose(entry.file)
    analysis.intent.value = entry.intent
    analysis.question.value = entry.question ?? ''
    image.result.value = entry.result
  }

  return { ...image, ...capture, ...analysis, error, reopen }
}
