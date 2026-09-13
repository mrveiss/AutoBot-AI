// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #16495 AC2 -- a guard that proves the `/api` prefix reaches the wire, not
 * just that a resource method's source text names a path starting with it.
 *
 * `sdk_ts_request_contract_test.py` (the Python-side static guard, since this
 * package's own checker has no Node runtime) reads each resource method's
 * source text; it never touches `client.ts`, so nothing there exercises
 * `apiPath()`/`API_PREFIX`/`buildUrl()`. This file mocks `global.fetch`,
 * calls one method per resource through the real client, and asserts the
 * URL `fetch` actually received carries `/api` -- the same class of proof
 * `tests/integration.test.ts` gives the rest of the package's structure,
 * and deterministic for the same reason: no backend, no network.
 */

import { jest } from "@jest/globals";
import { AutoBot } from "../src/index.js";

/** Just the shape `client.ts`'s methods read off a response. */
interface FakeFetchResponse {
  ok: boolean;
  status: number;
  statusText: string;
  json: () => Promise<Record<string, unknown>>;
}

describe("AutoBot SDK -- every request reaches fetch under /api (#16495)", () => {
  // `jest` is not an ambient global under this package's ESM preset
  // (ts-jest/presets/default-esm + --experimental-vm-modules) the way
  // `describe`/`test`/`expect` are -- it must be imported from
  // @jest/globals, so the mock's type comes from `typeof jest.fn` rather
  // than the CJS-only `jest.Mock` namespace type. `jest.fn()` called with no
  // type argument infers `Mock<never>`, which rejects any real return value
  // with TS2345 -- the call signature has to be spelled out, and the
  // implementation passed alongside it so nothing is inferred from a
  // separate `mockResolvedValue` call instead. The parameters are
  // `unknown[]`, not `fetch`'s own signature, so reading `.mock.calls[0]`
  // back as `[string]` below is a widening cast, not a narrowing one.
  let fetchMock: ReturnType<typeof jest.fn<(...args: unknown[]) => Promise<FakeFetchResponse>>>;
  const originalFetch = global.fetch;

  beforeEach(() => {
    fetchMock = jest.fn<(...args: unknown[]) => Promise<FakeFetchResponse>>(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({}),
    }));
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  function calledPath(): string {
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as [string];
    return new URL(url).pathname;
  }

  test("sessions.list() (GET)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.sessions.list();
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("sessions.create() (POST)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.sessions.create();
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("knowledge.search() (POST)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.knowledge.search("query");
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("agents.health() (GET)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.agents.health();
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("agents.setEnabled() (POST, the runtime-chosen trailing segment)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.agents.setEnabled("agent-1", true);
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("analytics.usage() (GET)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.analytics.usage();
    expect(calledPath()).toMatch(/^\/api\//);
  });

  test("a path that already carries /api is not doubled (client.ts's apiPath() idempotence)", async () => {
    const bot = new AutoBot({ baseUrl: "http://localhost:8000" });
    await bot.get("/api/already-prefixed");
    expect(calledPath()).toBe("/api/already-prefixed");
  });
});
