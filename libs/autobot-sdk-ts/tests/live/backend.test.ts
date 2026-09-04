// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Live-backend tests for the @autobot/sdk TypeScript package (#15698).
 *
 * These require a REACHABLE backend and are excluded from the default
 * `npm test` run by `testPathIgnorePatterns` in jest.config.js. Run them
 * deliberately, against a backend that is actually up:
 *
 *     AUTOBOT_BASE_URL=http://<host>:<port> npm run test:live
 *
 * Set AUTOBOT_API_TOKEN as well if the target requires auth.
 *
 * There is deliberately NO "backend unavailable, skipping" escape hatch here.
 * The previous version of these tests carried one, and it was dead code for
 * the life of the file: it gated on `e instanceof Error`, but jest runs the
 * test body in a vm realm whose `Error` is not the realm that built the
 * `TypeError` undici throws from an injected `fetch`, so the branch was never
 * taken (#15698). Worse than not working, it was not wanted -- it ended in
 * `return`, which jest reports as PASSED. A suite whose whole purpose is to
 * reach a live backend must go RED when it cannot, not green with a warning
 * nobody reads.
 */

import { AutoBot } from "../../src/index.js";
import type { DataResponse, SessionList } from "../../src/index.js";

const BASE_URL = process.env["AUTOBOT_BASE_URL"] ?? "http://localhost:8000";

describe("AutoBot SDK -- live backend", () => {
  let bot: AutoBot;

  beforeEach(() => {
    bot = new AutoBot({ baseUrl: BASE_URL });
  });

  test("sessions.list returns typed DataResponse<SessionList>", async () => {
    const result: DataResponse<SessionList> = await bot.sessions.list(5);
    expect(result).toHaveProperty("success");
    expect(result.success).toBe(true);
    expect(Array.isArray(result.data?.sessions)).toBe(true);
  });

  test("knowledge.stats returns DataResponse<KnowledgeStats>", async () => {
    const result = await bot.knowledge.stats();
    expect(result).toHaveProperty("success");
  });
});
