/**
 * Thumbnail Generation Web Worker
 *
 * Issue #4038: Offload CPU-intensive thumbnail generation to worker thread
 *
 * Generates video/image thumbnails using OffscreenCanvas to avoid blocking main thread.
 * Processes frames efficiently and returns optimized thumbnail data.
 */

interface ThumbnailRequest {
  id: string
  videoUrl: string
  timestamp: number
  width: number
  height: number
  format: 'image/jpeg' | 'image/png' | 'image/webp'
  quality?: number
}

interface ThumbnailResult {
  id: string
  success: boolean
  data?: string // base64 encoded image
  error?: string
  processingTime: number
}

/**
 * Generate thumbnail from video at specific timestamp
 */
async function generateThumbnail(request: ThumbnailRequest): Promise<ThumbnailResult> {
  const startTime = performance.now()

  try {
    // Fetch video
    const response = await fetch(request.videoUrl)
    if (!response.ok) {
      throw new Error(`Failed to fetch video: ${response.statusText}`)
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)

    // Create video element (off-screen)
    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.src = url

    // Wait for video to be loadable
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Video load timeout')), 10000)

      video.onloadedmetadata = () => {
        clearTimeout(timeout)
        resolve()
      }

      video.onerror = () => {
        clearTimeout(timeout)
        reject(new Error('Failed to load video'))
      }

      video.load()
    })

    // Seek to timestamp
    video.currentTime = Math.min(request.timestamp, video.duration)

    // Wait for frame to load
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Seek timeout')), 5000)

      const onSeeked = () => {
        clearTimeout(timeout)
        video.removeEventListener('seeked', onSeeked)
        resolve()
      }

      video.addEventListener('seeked', onSeeked)
    })

    // Create OffscreenCanvas for rendering
    const canvas = new OffscreenCanvas(request.width, request.height)
    const ctx = canvas.getContext('2d')

    if (!ctx) {
      throw new Error('Failed to get canvas context')
    }

    // Draw video frame to canvas
    ctx.drawImage(video, 0, 0, request.width, request.height)

    // Convert canvas to blob
    const imageBlob = await canvas.convertToBlob({
      type: request.format,
      quality: request.quality || 0.85
    })

    // Convert blob to base64 data URL
    const reader = new FileReader()
    const base64Data = await new Promise<string>((resolve, reject) => {
      reader.onload = () => {
        const result = reader.result as string
        resolve(result.split(',')[1]) // Extract base64 without data URL prefix
      }
      reader.onerror = reject
      reader.readAsDataURL(imageBlob)
    })

    // Cleanup
    URL.revokeObjectURL(url)
    video.src = ''

    const processingTime = performance.now() - startTime

    return {
      id: request.id,
      success: true,
      data: base64Data,
      processingTime
    }
  } catch (error) {
    const processingTime = performance.now() - startTime

    return {
      id: request.id,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      processingTime
    }
  }
}

/**
 * Handle incoming messages from main thread
 */
self.onmessage = async (event: MessageEvent<ThumbnailRequest>) => {
  const result = await generateThumbnail(event.data)
  self.postMessage(result)
}
