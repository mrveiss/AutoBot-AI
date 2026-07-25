// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * AudioWorklet processor for voice activity detection (VAD) (#1031)
 * Runs in the audio rendering thread for low-latency amplitude monitoring.
 *
 * Messages sent to main thread:
 *   {type: 'vad', speaking: boolean, rms: number}
 */

// RMS threshold for speech detection (0.0-1.0 range for float32 samples)
const SPEECH_THRESHOLD = 0.015
// Consecutive above-threshold frames to confirm speech START.
const ONSET_FRAMES = 3
// Consecutive sub-threshold frames to confirm speech STOP (silence window).
// Derived from the single `silenceThreshold` knob and supplied via
// processorOptions.offsetFrames (#12505). Falls back to ~800ms at a typical
// 48kHz render rate (800ms / (128/48000*1000) ~= 300 frames) when no option
// is passed - the previous hardcoded 8 (~21ms) cut speech off between words.
const DEFAULT_OFFSET_FRAMES = 300

class VadProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    this._aboveCount = 0
    this._belowCount = 0
    this._speaking = false
    const opts = options && options.processorOptions
    this._offsetFrames =
      opts && typeof opts.offsetFrames === 'number' && opts.offsetFrames > 0
        ? opts.offsetFrames
        : DEFAULT_OFFSET_FRAMES
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || !input[0]) return true

    const samples = input[0]
    let sum = 0
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i]
    }
    const rms = Math.sqrt(sum / samples.length)

    if (rms > SPEECH_THRESHOLD) {
      this._aboveCount++
      this._belowCount = 0
      if (!this._speaking && this._aboveCount >= ONSET_FRAMES) {
        this._speaking = true
        this.port.postMessage({ type: 'vad', speaking: true, rms })
      }
    } else {
      this._belowCount++
      this._aboveCount = 0
      if (this._speaking && this._belowCount >= this._offsetFrames) {
        this._speaking = false
        this.port.postMessage({ type: 'vad', speaking: false, rms })
      }
    }

    return true
  }
}

registerProcessor('vad-processor', VadProcessor)
