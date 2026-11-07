// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Visual regression: every Storybook story → screenshot diff
 *
 * Discovers stories at runtime via Storybook's `/index.json` endpoint and
 * iterates through them inside a single test. New stories get coverage
 * automatically — no per-story test boilerplate needed.
 *
 * Why one test instead of one per story:
 *   Playwright loads test files BEFORE its `webServer` config starts
 *   Storybook. Top-level `await fetch()` against :6006 would fail at
 *   collection time. A single test that fetches stories during the run
 *   sidesteps this. Trade-off: lose per-story failure isolation; gain a
 *   test file that loads cleanly even when Storybook isn't running yet.
 *
 * First-run behavior:
 *   The first time this runs after stories are added, baselines don't
 *   exist yet. Run with `--update-snapshots` to generate them, then
 *   commit the `__screenshots__/` directory.
 *
 *   $ npm run test:visual:update
 *   $ git add tests/visual/__screenshots__/
 *   $ git commit -m "chore(visual): regenerate baselines for <reason>"
 *
 * Issue #5077.
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';

interface StoryEntry {
  id: string;
  title: string;
  name: string;
  type: 'story' | 'docs';
  importPath: string;
}

interface StoryIndex {
  v: number;
  entries: Record<string, StoryEntry>;
}

async function fetchStoryIndex(page: Page): Promise<StoryEntry[]> {
  const res = await page.request.get('/index.json');
  if (!res.ok()) {
    throw new Error(
      `Storybook /index.json returned ${res.status()}. ` +
        `Is storybook running on :6006?`,
    );
  }
  const index = (await res.json()) as StoryIndex;
  return Object.values(index.entries).filter((e) => e.type === 'story');
}

/**
 * Why the story on *page* must not be compared, or null when it rendered (#18694).
 * The logged render error names the cause; the error display alone also fails the
 * story, since Storybook can show it (e.g. a preview-initialisation failure) without
 * logging `Error rendering story`.
 */
async function renderFailure(page: Page, renderErrors: string[]): Promise<string | null> {
  if (renderErrors.length > 0) {
    return renderErrors[0].split('\n')[0];
  }
  const errorDisplay = await page.evaluate(() =>
    document.body.classList.contains('sb-show-errordisplay'),
  );
  return errorDisplay ? 'Storybook showed its error display' : null;
}

async function snapshotStory(
  page: Page,
  story: StoryEntry,
): Promise<void> {
  // Storybook logs `Error rendering story '<id>'` for every story that throws, both when
  // it shows its error page and when a render error leaves the root empty under
  // `sb-show-main`. The console line is the one signal that covers both (#18694).
  const renderErrors: string[] = [];
  const onConsole = (msg: ConsoleMessage): void => {
    if (msg.type() === 'error' && msg.text().startsWith('Error rendering story')) {
      renderErrors.push(msg.text());
    }
  };
  page.on('console', onConsole);
  await page.goto(
    `/iframe.html?id=${encodeURIComponent(story.id)}&viewMode=story`,
    { waitUntil: 'load' },
  );

  // Storybook adds `sb-show-main` to <body> only after it finishes preparing
  // the story (mounting Vue, running decorators, etc.). Without this wait the
  // screenshot races against the preparation phase and captures a blank page.
  // A story that throws gets `sb-show-errordisplay` instead (or an empty root under
  // `sb-show-main`); either way it must fail here rather than be compared (#18694).
  await page.waitForFunction(
    () =>
      document.body.classList.contains('sb-show-main') ||
      document.body.classList.contains('sb-show-errordisplay'),
    { timeout: 10_000 },
  );
  page.off('console', onConsole);
  const failure = await renderFailure(page, renderErrors);
  if (failure !== null) {
    throw new Error(`story failed to render: ${failure}`);
  }

  // Full-page screenshot of the iframe document: avoids element-visibility
  // constraints while scoping the diff to the component story.
  await expect(page).toHaveScreenshot(`${story.id}.png`, { fullPage: false });
}

test('all Storybook stories match baseline screenshots', async ({ page }) => {
  const stories = await fetchStoryIndex(page);
  if (stories.length === 0) {
    throw new Error(
      'Storybook returned 0 stories — check that *.stories.ts files exist',
    );
  }

  // Soft-collect failures so one broken story doesn't hide the others.
  const failures: Array<{ story: string; error: Error }> = [];
  for (const story of stories) {
    try {
      await snapshotStory(page, story);
    } catch (err) {
      failures.push({
        story: `${story.title} / ${story.name}`,
        error: err instanceof Error ? err : new Error(String(err)),
      });
    }
  }

  if (failures.length > 0) {
    const summary = failures
      .map((f) => `  - ${f.story}: ${f.error.message.split('\n')[0]}`)
      .join('\n');
    throw new Error(
      `${failures.length}/${stories.length} stories failed visual diff:\n${summary}`,
    );
  }
});

// Contrast pair for renderFailure: no Storybook needed, so it runs with
// SKIP_STORYBOOK_START=1 too. The error display fails a story that logged nothing;
// a story under `sb-show-main` with no logged error is compared (#18694).
test.describe('render-failure detection', () => {
  test('the error display alone fails the story', async ({ page }) => {
    await page.setContent('<body class="sb-show-errordisplay"><div id="error-message"></div></body>');
    expect(await renderFailure(page, [])).toBe('Storybook showed its error display');
  });

  test('a logged render error names its first line', async ({ page }) => {
    await page.setContent('<body class="sb-show-main"></body>');
    expect(await renderFailure(page, ["Error rendering story 'x':\nstack"])).toBe("Error rendering story 'x':");
  });

  test('a rendered story with no logged error is compared', async ({ page }) => {
    await page.setContent('<body class="sb-show-main"><div id="storybook-root">ok</div></body>');
    expect(await renderFailure(page, [])).toBeNull();
  });
});
