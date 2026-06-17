// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Integration tests for the @autobot/sdk TypeScript package.
 *
 * These tests run against a live local backend. Set AUTOBOT_BASE_URL to
 * override the default http://localhost:8000. Set AUTOBOT_API_TOKEN if auth
 * is required.
 */

import { AutoBot, AutoBotHttpClient } from "../src/index.js";
import type { DataResponse, SessionList } from "../src/index.js";

const BASE_URL = process.env["AUTOBOT_BASE_URL"] ?? "http://localhost:8000";

describe("AutoBot SDK — package structure", () => {
  test("AutoBot extends AutoBotHttpClient", () => {
    const bot = new AutoBot({ baseUrl: BASE_URL });
    expect(bot).toBeInstanceOf(AutoBotHttpClient);
  });

  test("all resource namespaces are present", () => {
    const bot = new AutoBot({ baseUrl: BASE_URL });
    expect(bot.sessions).toBeDefined();
    expect(bot.agents).toBeDefined();
    expect(bot.knowledge).toBeDefined();
    expect(bot.analytics).toBeDefined();
  });

  test("token is injected from env var", () => {
    const original = process.env["AUTOBOT_API_TOKEN"];
    process.env["AUTOBOT_API_TOKEN"] = "env-token-test";
    const bot = new AutoBot({ baseUrl: BASE_URL });
    expect((bot as unknown as { token: string }).token).toBe("env-token-test");
    if (original === undefined) {
      delete process.env["AUTOBOT_API_TOKEN"];
    } else {
      process.env["AUTOBOT_API_TOKEN"] = original;
    }
  });

  test("explicit token overrides env var", () => {
    process.env["AUTOBOT_API_TOKEN"] = "env-token";
    const bot = new AutoBot({ baseUrl: BASE_URL, token: "explicit-token" });
    expect((bot as unknown as { token: string }).token).toBe("explicit-token");
    delete process.env["AUTOBOT_API_TOKEN"];
  });
});

describe("AutoBot SDK — live backend (requires running backend)", () => {
  let bot: AutoBot;

  beforeEach(() => {
    bot = new AutoBot({ baseUrl: BASE_URL });
  });

  test("sessions.list returns typed DataResponse<SessionList>", async () => {
    let result: DataResponse<SessionList>;
    try {
      result = await bot.sessions.list(5);
    } catch (e: unknown) {
      if (e instanceof Error && (e.message.includes("fetch failed") || e.message.includes("ECONNREFUSED") || e.message.includes("404"))) {
        console.warn("AutoBot backend not available, skipping live test");
        return;
      }
      throw e;
    }
    expect(result).toHaveProperty("success");
    expect(result.success).toBe(true);
    expect(Array.isArray(result.data?.sessions)).toBe(true);
  });

  test("knowledge.stats returns DataResponse<KnowledgeStats>", async () => {
    try {
      const result = await bot.knowledge.stats();
      expect(result).toHaveProperty("success");
    } catch (e: unknown) {
      if (e instanceof Error && (e.message.includes("fetch failed") || e.message.includes("ECONNREFUSED") || e.message.includes("404"))) {
        console.warn("AutoBot backend not available, skipping live test");
        return;
      }
      throw e;
    }
  });
});
