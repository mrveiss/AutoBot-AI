/**
 * Upload Progress Composable
 *
 * Provides reusable progress tracking for file uploads, URL imports, and other async operations.
 * Centralized progress state management with consistent UI updates.
 */

import { reactive } from 'vue'

export interface UploadProgressState {
  show: boolean
  title: string
  percentage: number
  status: string
}

/**
 * Create a reusable upload progress tracker
 *
 * @example
 * const { progress, startProgress, updateProgress, completeProgress, hideProgress } = useUploadProgress()
 *
 * startProgress('Uploading files')
 * updateProgress(50, 'Uploading file 1 of 2...')
 * completeProgress('Upload complete!')
 */
export function useUploadProgress() {
  const progress = reactive<UploadProgressState>({
    show: false,
    title: '',
    percentage: 0,
    status: ''
  })

  /**
   * Start progress tracking with initial title
   *
   * @param title - Progress title (e.g., "Uploading files")
   * @param initialStatus - Optional initial status message
   */
  function startProgress(title: string, initialStatus: string = ''): void {
    progress.show = true
    progress.title = title
    progress.percentage = 0
    progress.status = initialStatus
  }

  /**
   * Update progress percentage and status
   *
   * @param percentage - Progress percentage (0-100)
   * @param status - Status message (e.g., "Uploading file 1 of 3...")
   */
  function updateProgress(percentage: number, status: string = ''): void {
    progress.percentage = Math.min(100, Math.max(0, percentage))
    if (status) {
      progress.status = status
    }
  }

  /**
   * Mark progress as complete (100%)
   *
   * @param completionMessage - Final status message (e.g., "Upload complete!")
   */
  function completeProgress(completionMessage: string = 'Complete!'): void {
    progress.percentage = 100
    progress.status = completionMessage
  }

  /**
   * Hide progress indicator
   * Optionally with a delay to show completion message
   *
   * @param delay - Optional delay in milliseconds before hiding (default: 0)
   */
  function hideProgress(delay: number = 0): void {
    if (delay > 0) {
      setTimeout(() => {
        progress.show = false
      }, delay)
    } else {
      progress.show = false
    }
  }

  /**
   * Reset progress to initial state
   */
  function resetProgress(): void {
    progress.show = false
    progress.title = ''
    progress.percentage = 0
    progress.status = ''
  }

  /**
   * Simulate incremental progress (for operations without real progress tracking)
   *
   * @param maxPercentage - Maximum percentage to reach (default: 90)
   * @param increment - Percentage to increase per interval (default: 10)
   * @param intervalMs - Interval in milliseconds (default: 200)
   * @returns Interval ID that can be used to stop simulation
   *
   * @example
   * const intervalId = simulateProgress(90, 10, 200)
   * // Later: clearInterval(intervalId)
   */
  function simulateProgress(
    maxPercentage: number = 90,
    increment: number = 10,
    intervalMs: number = 200
  ): number {
    return window.setInterval(() => {
      if (progress.percentage < maxPercentage) {
        progress.percentage += increment
      }
    }, intervalMs)
  }

  /**
   * Track multi-step operation progress
   *
   * @param currentStep - Current step number (1-based)
   * @param totalSteps - Total number of steps
   * @param stepDescription - Description of current step
   */
  function updateStepProgress(
    currentStep: number,
    totalSteps: number,
    stepDescription: string = ''
  ): void {
    const percentage = Math.round((currentStep / totalSteps) * 100)
    const status = stepDescription || `Step ${currentStep} of ${totalSteps}`

    updateProgress(percentage, status)
  }

  /**
   * Track file upload progress (for multiple files)
   *
   * @param uploadedCount - Number of files uploaded
   * @param totalCount - Total number of files
   * @param currentFileName - Name of file being uploaded (optional)
   */
  function updateFileProgress(
    uploadedCount: number,
    totalCount: number,
    currentFileName: string = ''
  ): void {
    const percentage = Math.round((uploadedCount / totalCount) * 100)
    const status = currentFileName
      ? `Uploading ${currentFileName}... (${uploadedCount} of ${totalCount})`
      : `Uploaded ${uploadedCount} of ${totalCount} files`

    updateProgress(percentage, status)
  }

  return {
    // State
    progress,

    // Basic operations
    startProgress,
    updateProgress,
    completeProgress,
    hideProgress,
    resetProgress,

    // Advanced operations
    simulateProgress,
    updateStepProgress,
    updateFileProgress
  }
}
