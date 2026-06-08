// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

export const CANVAS_FEATURE_FLAG = import.meta.env.VITE_FEATURE_CANVAS === 'true'

export const CANVAS_SPLIT_DEFAULT = { chat: 35, canvas: 65 } as const

export const CANVAS_GUTTER_HOT_ZONE_PX = 8

export const CANVAS_AUTOSAVE_DEBOUNCE_MS = 1000

export const CANVAS_MOBILE_BREAKPOINT_PX = 390

export type CanvasLayoutVariant = 'split' | 'canvas-focus' | 'chat-focus' | 'full-canvas'
