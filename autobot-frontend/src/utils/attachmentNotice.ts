// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tell the user why an attached file was not used, or only partly (#20195).
 *
 * The backend streams an `attachment_notice` message with `metadata.code` (and `filename` / `limit` where
 * they apply); the text is rendered here from `chat.attachmentNotice.<code>` in the user's language. An
 * unknown code (a newer backend) falls back to the generic "could not be read" text rather than showing
 * nothing.
 */

import i18n from '@/i18n'
import { useToast } from '@/composables/useToast'

export const ATTACHMENT_NOTICE_CODES = [
  'unavailable',
  'too_many',
  'image',
  'unsupported',
  'unreadable',
  'empty',
  'truncated',
  'over_budget',
] as const

export type AttachmentNoticeCode = (typeof ATTACHMENT_NOTICE_CODES)[number]

export interface AttachmentNoticeMetadata {
  code?: string
  filename?: string
  limit?: number
}

export function attachmentNoticeText(metadata: AttachmentNoticeMetadata | undefined): string {
  const known = ATTACHMENT_NOTICE_CODES.find((code) => code === metadata?.code)
  return i18n.global.t(`chat.attachmentNotice.${known ?? 'unreadable'}`, {
    filename: metadata?.filename ?? '',
    limit: metadata?.limit ?? '',
  })
}

export function showAttachmentNotice(metadata: AttachmentNoticeMetadata | undefined): void {
  useToast().showToast(attachmentNoticeText(metadata), 'warning')
}
