/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
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
// Number of consecutive frames to confirm speech start/stop
const ONSET_FRAMES = 3
const OFFSET_FRAMES = 8

class VadProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._aboveCount = 0
    this._belowCount = 0
    this._speaking = false
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
      if (this._speaking && this._belowCount >= OFFSET_FRAMES) {
        this._speaking = false
        this.port.postMessage({ type: 'vad', speaking: false, rms })
      }
    }

    return true
  }
}

registerProcessor('vad-processor', VadProcessor)
