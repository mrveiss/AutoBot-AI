// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Which moments of a video VideoProcessor samples (#12363 slice 4: moved out of the component).
 */

export type FrameExtractionMode = 'keyframes' | 'interval' | 'all'

/** Seconds between samples in `all` mode. */
const ALL_FRAMES_STEP_S = 0.5

/** Frame timestamps (seconds) for a video of `duration`, at most `maxFrames` of them. */
export function calculateFrameTimestamps(
  mode: FrameExtractionMode,
  duration: number,
  interval: number,
  maxFrames: number,
): number[] {
  const timestamps: number[] = []
  if (mode === 'keyframes') {
    // Simple keyframe estimation - beginning, quarters, end
    for (const p of [0, 0.25, 0.5, 0.75, 1]) {
      if (p * duration < duration) timestamps.push(p * duration)
    }
  } else {
    const step = mode === 'interval' ? interval : ALL_FRAMES_STEP_S
    for (let t = 0; t < duration; t += step) timestamps.push(t)
  }
  return timestamps.slice(0, maxFrames)
}
