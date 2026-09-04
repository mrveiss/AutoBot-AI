// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Structural tests for the @autobot/sdk TypeScript package.
 *
 * Everything here is deterministic and needs NO backend, which is what makes
 * this file safe to gate in CI (`NPM Package Tests`, #15676). The two tests
 * that do need a reachable backend live in tests/live/backend.test.ts and run
 * via `npm run test:live` -- see #15698 for why they were separated rather
 * than left behind a "skip if unreachable" branch that reported a false pass.
 *
 * AUTOBOT_BASE_URL is still honoured; nothing here dials it.
 */

import { AutoBot, AutoBotHttpClient } from "../src/index.js";

const BASE_URL = process.env["AUTOBOT_BASE_URL"] ?? "http://localhost:8000";

describe("AutoBot SDK -- package structure", () => {
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
