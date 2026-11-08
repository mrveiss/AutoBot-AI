// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The conversation-file preview contract, typed from the generated API types (#20906).
 *
 * `GET /api/conversation-files/conversation/{session_id}/preview/{file_id}` answers with the file's info and,
 * for a text file, the first part of its content. The type is read from `paths`, so a backend change that
 * alters the response fails type-checking here instead of rendering an empty pane.
 */
import type { paths } from '@/types/generated/api'

type PreviewPath = '/api/conversation-files/conversation/{session_id}/preview/{file_id}'

export type ConversationFilePreview =
  paths[PreviewPath]['get']['responses'][200]['content']['application/json']
