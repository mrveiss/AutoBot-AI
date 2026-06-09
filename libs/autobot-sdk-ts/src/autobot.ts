// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { AutoBotHttpClient, type ClientOptions } from "./client.js";
import { AgentsResource } from "./resources/agents.js";
import { AnalyticsResource } from "./resources/analytics.js";
import { KnowledgeResource } from "./resources/knowledge.js";
import { SessionsResource } from "./resources/sessions.js";

/**
 * Top-level SDK client with typed resource namespaces.
 *
 * ```ts
 * const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
 * const result = await bot.sessions.list();
 * ```
 */
export class AutoBot extends AutoBotHttpClient {
  readonly sessions: SessionsResource;
  readonly agents: AgentsResource;
  readonly knowledge: KnowledgeResource;
  readonly analytics: AnalyticsResource;

  constructor(options: ClientOptions = {}) {
    super(options);
    this.sessions = new SessionsResource(this);
    this.agents = new AgentsResource(this);
    this.knowledge = new KnowledgeResource(this);
    this.analytics = new AnalyticsResource(this);
  }
}
