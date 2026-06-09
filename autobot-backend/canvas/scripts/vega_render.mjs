// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Headless Vega-Lite v5 → SVG renderer (MVA-484).
 *
 * Reads a Vega-Lite spec from stdin as JSON, renders to SVG via vega-lite +
 * vega, writes the SVG string to stdout, exits 0 on success / 1 on error.
 *
 * Usage: echo '<spec-json>' | node vega_render.mjs
 *
 * Dependencies (install alongside the backend if not already present):
 *   npm install vega vega-lite canvas
 *   (canvas is optional — only needed for Canvas-backend PNG; SVG works without it)
 */

import { createCanvas } from 'canvas';
import * as vl from 'vega-lite';
import * as vega from 'vega';

async function main() {
  let inputJson = '';
  for await (const chunk of process.stdin) {
    inputJson += chunk;
  }

  let spec;
  try {
    spec = JSON.parse(inputJson);
  } catch (err) {
    process.stderr.write(`Invalid JSON input: ${err.message}\n`);
    process.exit(1);
  }

  let vegaSpec;
  try {
    vegaSpec = vl.compile(spec).spec;
  } catch (err) {
    process.stderr.write(`Vega-Lite compile error: ${err.message}\n`);
    process.exit(1);
  }

  try {
    const view = new vega.View(vega.parse(vegaSpec), { renderer: 'none' });
    await view.runAsync();
    const svg = await view.toSVG();
    process.stdout.write(svg);
    process.exit(0);
  } catch (err) {
    process.stderr.write(`Vega render error: ${err.message}\n`);
    process.exit(1);
  }
}

main().catch((err) => {
  process.stderr.write(`Unexpected error: ${err.message}\n`);
  process.exit(1);
});
