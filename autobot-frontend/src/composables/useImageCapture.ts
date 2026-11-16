// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Take one still image from the user's camera or from a screen they choose to share (#20644).
 *
 * Moved from the SLM's Vision tool: the main app could analyse an uploaded image but had no way to
 * take one. Both run entirely in the browser (getUserMedia / getDisplayMedia); the frame becomes a
 * PNG `File` the existing multimodal client uploads. Every stream track is stopped once the frame
 * is taken, whether or not it succeeded, so the camera light and the share banner go out.
 */

export type CaptureSource = 'camera' | 'screen'

/** Whether this browser can capture from *source* (a secure context is required for both). */
export function canCapture(source: CaptureSource): boolean {
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices
  if (!devices) return false
  return source === 'camera' ? typeof devices.getUserMedia === 'function' : typeof devices.getDisplayMedia === 'function'
}

function openStream(source: CaptureSource): Promise<MediaStream> {
  const devices = navigator.mediaDevices
  return source === 'camera' ? devices.getUserMedia({ video: true }) : devices.getDisplayMedia({ video: true })
}

function canvasToPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('capture produced no image'))), 'image/png')
  })
}

/** Draw the stream's current frame into a PNG blob. */
async function grabFrame(stream: MediaStream): Promise<Blob> {
  const video = document.createElement('video')
  video.muted = true
  video.srcObject = stream
  await video.play()
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  canvas.getContext('2d')?.drawImage(video, 0, 0)
  video.pause()
  return canvasToPng(canvas)
}

/**
 * One frame from *source* as a PNG `File`. Rejects when the user declines the permission prompt or
 * the browser cannot capture; the caller shows that failure.
 */
export async function captureImage(source: CaptureSource, now: Date = new Date()): Promise<File> {
  const stream = await openStream(source)
  try {
    const blob = await grabFrame(stream)
    return new File([blob], `${source}-${now.toISOString().replace(/[:.]/g, '-')}.png`, { type: 'image/png' })
  } finally {
    stream.getTracks().forEach((track) => track.stop())
  }
}
