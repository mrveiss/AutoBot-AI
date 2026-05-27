// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { AutoBotHttpClient } from "../client.js";
import type {
  DataResponse,
  KnowledgeAddResult,
  KnowledgeSearchResult,
  KnowledgeStats,
} from "../types.js";

export class KnowledgeResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  stats(): Promise<DataResponse<KnowledgeStats>> {
    return this.client.get("/knowledge_base/stats");
  }

  addText(text: string, category?: string, source?: string): Promise<DataResponse<KnowledgeAddResult>> {
    return this.client.post("/knowledge_base/add_text", { text, category, source });
  }

  search(query: string, limit = 10, category?: string): Promise<DataResponse<KnowledgeSearchResult>> {
    return this.client.get("/knowledge_base/search", { query, limit, category });
  }

  getEntries(limit = 50, offset = 0, category?: string): Promise<DataResponse<KnowledgeSearchResult>> {
    return this.client.get("/knowledge_base/entries", { limit, offset, category });
  }
}
