// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["**/__tests__/**/*.test.mjs"],
    environment: "node",
    globals: false,
  },
});
