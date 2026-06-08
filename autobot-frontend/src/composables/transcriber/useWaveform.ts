// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useWaveform(container: Ref<HTMLElement | null>) {
  const currentTime = ref(0)
  const duration = ref(0)
  const isPlaying = ref(false)
  let ws: import('wavesurfer.js').default | null = null

  async function init(audioUrl: string) {
    const WaveSurfer = (await import('wavesurfer.js')).default
    if (!container.value) return
    ws?.destroy()
    ws = WaveSurfer.create({
      container: container.value,
      waveColor: 'var(--color-primary-300, #93c5fd)',
      progressColor: 'var(--color-primary-600, #2563eb)',
      height: 64,
      normalize: true,
    })
    ws.on('timeupdate', (t: number) => { currentTime.value = t })
    ws.on('ready', () => { duration.value = ws!.getDuration() })
    ws.on('play', () => { isPlaying.value = true })
    ws.on('pause', () => { isPlaying.value = false })
    await ws.load(audioUrl)
  }

  function seekTo(seconds: number) {
    if (ws && duration.value > 0) ws.seekTo(seconds / duration.value)
  }

  function togglePlay() { ws?.playPause() }

  onUnmounted(() => { ws?.destroy(); ws = null })

  return { currentTime, duration, isPlaying, init, seekTo, togglePlay }
}
