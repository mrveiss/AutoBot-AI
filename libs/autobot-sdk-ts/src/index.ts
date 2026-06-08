// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * @autobot/sdk — Typed TypeScript SDK for the AutoBot REST API.
 *
 * Quick start:
 * ```ts
 * import { AutoBot } from "@autobot/sdk";
 *
 * const bot = new AutoBot();
 * const sessions = await bot.sessions.list();
 * console.log(sessions.data?.sessions);
 * ```
 *
 * Auth: set AUTOBOT_API_TOKEN env var, or pass `token:` to the constructor.
 */

export { AutoBot } from "./autobot.js";
export { AutoBotHttpClient } from "./client.js";
export type { ClientOptions } from "./client.js";
export type {
  AgentConfig,
  AgentHealth,
  AnalyticsPerformance,
  AnalyticsUsage,
  ChatMessage,
  DataResponse,
  KnowledgeAddResult,
  KnowledgeEntry,
  KnowledgeSearchResult,
  KnowledgeStats,
  Session,
  SessionCreate,
  SessionDelete,
  SessionList,
  SessionMessages,
  SessionUpdate,
} from "./types.js";
