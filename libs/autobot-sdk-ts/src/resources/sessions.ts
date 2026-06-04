// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { AutoBotHttpClient } from "../client.js";
import type {
  DataResponse,
  SessionCreate,
  SessionDelete,
  SessionList,
  SessionMessages,
  SessionUpdate,
} from "../types.js";

export class SessionsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  list(limit = 50, offset = 0): Promise<DataResponse<SessionList>> {
    return this.client.get("/chat/sessions", { limit, offset });
  }

  get(sessionId: string): Promise<DataResponse<SessionMessages>> {
    return this.client.get(`/chat/sessions/${sessionId}`);
  }

  create(title?: string, metadata?: Record<string, unknown>): Promise<DataResponse<SessionCreate>> {
    return this.client.post("/chat/sessions", { title, metadata });
  }

  update(sessionId: string, fields: Record<string, unknown>): Promise<DataResponse<SessionUpdate>> {
    return this.client.put(`/chat/sessions/${sessionId}`, fields);
  }

  delete(sessionId: string): Promise<DataResponse<SessionDelete>> {
    return this.client.delete(`/chat/sessions/${sessionId}`);
  }
}
