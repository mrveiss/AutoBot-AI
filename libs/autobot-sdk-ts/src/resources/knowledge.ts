// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Knowledge resource operations.
 *
 * `/knowledge_base/search` is served by POST only; this used to ask for it
 * with GET, which answers 405 even once the path is right. The verb is part
 * of the route, so it's corrected here (#15528, mirroring the Python SDK's
 * already-fixed shape).
 *
 * None of these four routes returns a `DataResponse` envelope -- each
 * returns its document flat.
 */
import type { AutoBotHttpClient } from "../client.js";
import type { KnowledgeAddResult, KnowledgeEntries, KnowledgeSearchResult, KnowledgeStats } from "../types.js";

const DEFAULT_SEARCH_LIMIT = 10;
const DEFAULT_PAGE_SIZE = 50;

export class KnowledgeResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  stats(): Promise<KnowledgeStats> {
    return this.client.get("/knowledge_base/stats");
  }

  addText(text: string, category?: string, source?: string): Promise<KnowledgeAddResult> {
    const body: Record<string, unknown> = { text };
    if (category) body["category"] = category;
    if (source) body["source"] = source;
    return this.client.post("/knowledge_base/add_text", body);
  }

  /**
   * Search the knowledge base.
   *
   * The route takes its arguments in a JSON body, and names the result cap
   * `limit` (the route also accepts the legacy wire name `top_k`, but this
   * SDK only ever sent `limit`). It has no category filter -- use
   * {@link getEntries}, whose route does.
   */
  search(query: string, limit = DEFAULT_SEARCH_LIMIT): Promise<KnowledgeSearchResult> {
    return this.client.post("/knowledge_base/search", { query, limit });
  }

  /**
   * One page of stored entries, newest first.
   *
   * The route is **cursor**-paginated, not offset-paginated (#15528). Pass
   * the previous response's `next_cursor` to advance; omitting it starts at
   * the beginning.
   */
  getEntries(limit = DEFAULT_PAGE_SIZE, cursor?: string, category?: string): Promise<KnowledgeEntries> {
    return this.client.get("/knowledge_base/entries", { limit, cursor, category });
  }
}
