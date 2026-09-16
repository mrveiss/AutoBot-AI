// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Session resource operations.
 *
 * `list()` used to send `limit`/`offset`. `GET /chat/sessions` accepts
 * neither -- it declares `scope` and `team_id` and returns the caller's
 * whole list -- so FastAPI dropped both and the caller's paging silently
 * did not apply (#15528, mirroring #15119's already-fixed Python shape).
 * The two parameters the route does take are offered instead. `get()`
 * gains the route's real `page`/`per_page`, which the SDK could not reach
 * at all.
 */
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

  /**
   * Chat sessions visible to the caller.
   *
   * `scope` is `"user"` (the route's default), `"org"`, `"team"` or
   * `"shared"`; `teamId` is required when `scope="team"`. The route is not
   * paginated, which is why there is no `limit`/`offset` here (#15528).
   */
  list(scope?: string, teamId?: string): Promise<DataResponse<SessionList>> {
    return this.client.get("/chat/sessions", { scope, team_id: teamId });
  }

  /**
   * One session's messages, page by page.
   *
   * `page`/`perPage` are the route's own parameter names; omitting either
   * leaves the route's default in force rather than restating it here, so
   * the two cannot drift apart.
   */
  get(sessionId: string, page?: number, perPage?: number): Promise<DataResponse<SessionMessages>> {
    return this.client.get(`/chat/sessions/${sessionId}`, { page, per_page: perPage });
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
