// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tells the user how an Approve / Skip on a waiting workflow step went (#17677).
 *
 * `answerStep` resolves `false` when the server refuses and rejects when the request
 * itself fails; both are a failed answer, and both leave the step `waiting_approval`, so
 * the approval card stays and the user can retry. Neither may pass in silence.
 */
import { useI18n } from 'vue-i18n';
import { useNotificationBus } from '@/composables/useNotificationBus';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('StepAnswerToast');

export function useStepAnswerToast() {
  const { t } = useI18n();
  const { showToast } = useNotificationBus();

  /** Await an answer and toast its outcome; never rejects. */
  async function answerWithToast(answer: Promise<boolean>, kind: 'approve' | 'skip'): Promise<void> {
    const ok = await answer.catch((error: unknown) => {
      logger.error(`Step ${kind} failed:`, error);
      return false;
    });
    if (kind === 'approve') {
      showToast(t(ok ? 'workflow.builder.stepApproved' : 'workflow.builder.stepApproveFailed'), ok ? 'success' : 'error');
    } else {
      showToast(t(ok ? 'workflow.builder.stepSkipped' : 'workflow.builder.stepSkipFailed'), ok ? 'info' : 'error');
    }
  }

  return { answerWithToast };
}
