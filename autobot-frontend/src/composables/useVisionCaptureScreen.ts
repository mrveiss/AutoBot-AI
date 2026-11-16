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
import { CaptureError, captureImage, type CaptureSource } from '@/composables/useImageCapture'
import { useImageAnalysisHistory, type ImageAnalysisEntry } from '@/composables/useImageAnalysisHistory'
import { createLogger } from '@/utils/debugUtils'
import type { MultiModalResponse, ProcessingIntent } from '@/types/visionMultimodal'

const logger = createLogger('useVisionCaptureScreen')

/** Why a capture failed, in the user's language: our own coded failure, else the browser's reason. */
function captureFailureText(err: unknown, t: (key: string) => string): string {
  if (err instanceof CaptureError) return t('visionCapture.errors.noImage')
  return httpErrorText(err, t('visionCapture.errors.unknown'))
}

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

/** Set once the screen's scope ends: work finishing after that must not create object URLs nobody revokes. */
interface Lifetime {
  disposed: boolean
}

/** Camera or screen capture; a declined prompt or unsupported browser becomes the screen's error. */
function useCapture(choose: (file: File | null) => void, error: Ref<string | null>, life: Lifetime) {
  const { t } = useI18n()
  const capturing = ref(false)

  async function capture(source: CaptureSource): Promise<void> {
    capturing.value = true
    error.value = null
    try {
      const file = await captureImage(source)
      if (!life.disposed) choose(file)
    } catch (err) {
      logger.warn('Capture failed:', err)
      error.value = t('visionCapture.errors.capture', { detail: captureFailureText(err, t) })
    } finally {
      capturing.value = false
    }
  }

  return { capturing, capture }
}

/** One analysis request, with the intent and question fixed when it is sent (#20644 review). */
interface AnalysisRequest {
  file: File
  intent: ProcessingIntent
  question?: string
}

type Translate = (key: string, values?: Record<string, unknown>) => string
type AnalysisOutcome = { result: MultiModalResponse } | { failure: string }

/**
 * The reply, or the user-facing reason it is not one. The image route can answer 200 with
 * `success: false`, an empty `result_data` and an `error_message`; that is a failure, not a result.
 */
async function requestAnalysis(request: AnalysisRequest, t: Translate): Promise<AnalysisOutcome> {
  try {
    const result = await processImage(request.file, request.intent, request.question)
    if (result.success) return { result }
    logger.warn('Image analysis reported failure:', result.error_message)
    const detail = result.error_message || t('visionCapture.errors.unknown')
    return { failure: t('visionCapture.errors.analysisUnsuccessful', { detail }) }
  } catch (err) {
    logger.error('Image analysis failed:', err)
    return { failure: httpErrorText(err, t('visionCapture.errors.analysis')) }
  }
}

/** Analyse the current image; each success lands in the history, a failure in the error. */
function useAnalysis(image: ReturnType<typeof useCurrentImage>, error: Ref<string | null>, life: Lifetime) {
  const { t } = useI18n()
  const history = useImageAnalysisHistory()
  const intent = ref<ProcessingIntent>('analysis')
  const question = ref('')
  const analyzing = ref(false)

  async function analyze(): Promise<void> {
    const file = image.file.value
    if (!file || analyzing.value) return
    // Fixed now: a change to the intent while the request runs must not relabel this answer.
    const sent = intent.value
    const request = { file, intent: sent, question: sent === 'visual_qa' ? question.value.trim() || undefined : undefined }
    analyzing.value = true
    error.value = null
    const outcome = await requestAnalysis(request, t)
    analyzing.value = false
    if (life.disposed) return
    if ('failure' in outcome) {
      error.value = outcome.failure
      return
    }
    image.result.value = outcome.result
    history.add({ ...request, result: outcome.result })
  }

  return { history: history.entries, intent, question, analyzing, analyze }
}

export function useVisionCaptureScreen() {
  const error = ref<string | null>(null)
  const life: Lifetime = { disposed: false }
  onScopeDispose(() => {
    life.disposed = true
  })
  const image = useCurrentImage(error)
  const capture = useCapture(image.choose, error, life)
  const analysis = useAnalysis(image, error, life)

  function reopen(entry: ImageAnalysisEntry): void {
    image.choose(entry.file)
    analysis.intent.value = entry.intent
    analysis.question.value = entry.question ?? ''
    image.result.value = entry.result
  }

  return { ...image, ...capture, ...analysis, error, reopen }
}
