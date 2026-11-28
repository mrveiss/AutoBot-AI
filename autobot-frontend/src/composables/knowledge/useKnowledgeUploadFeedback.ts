// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * What the Knowledge upload screen tells the user (#18244): the overall progress bar, a success
 * message that clears itself and a transient error. The three entry forms share one instance,
 * so only one of them is "submitting" and one banner is shown.
 */
import { ref } from 'vue'
import { useUploadProgress } from '@/composables/useUploadProgress'
import { useTransientError } from '@/composables/useTransientError'

const SUCCESS_MS = 3000
const ERROR_MS = 5000

export function useKnowledgeUploadFeedback() {
  const progress = useUploadProgress()
  const successMessage = ref('')
  const isSubmitting = ref(false)
  const { message: errorMessage, show: showError, clear: clearError } = useTransientError(ERROR_MS)

  /** Show a success message, then clear it (and run `after`) once the user has had time to read it. */
  function showSuccess(message: string, after?: () => void): void {
    successMessage.value = message
    setTimeout(() => {
      successMessage.value = ''
      after?.()
    }, SUCCESS_MS)
  }

  function begin(): void {
    isSubmitting.value = true
    clearError()
    successMessage.value = ''
  }

  const end = () => { isSubmitting.value = false }

  return { ...progress, successMessage, isSubmitting, errorMessage, showError, clearError, showSuccess, begin, end }
}

export type UploadFeedback = ReturnType<typeof useKnowledgeUploadFeedback>
