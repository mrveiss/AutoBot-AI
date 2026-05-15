// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
import { test, expect, type Page } from '@playwright/test';

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

async function snapshotStory(
  page: Page,
  story: StoryEntry,
): Promise<void> {
  await page.goto(
    `/iframe.html?id=${encodeURIComponent(story.id)}&viewMode=story`,
    { waitUntil: 'load' },
  );

  // Storybook adds `sb-show-main` to <body> only after it finishes preparing
  // the story (mounting Vue, running decorators, etc.). Without this wait the
  // screenshot races against the preparation phase and captures a blank page.
  await page.waitForFunction(
    () => document.body.classList.contains('sb-show-main'),
    { timeout: 10_000 },
  );

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
