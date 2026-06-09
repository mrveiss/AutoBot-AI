// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import Icon, { ICONS } from '@/components/ui/Icon.vue';

const DEFINED_GROUPS: Array<{ title: string; names: string[] }> = [
  {
    title: 'Navigation',
    names: ['chevron-down', 'sort', 'chevron-up', 'chevron-left', 'chevron-right'],
  },
  {
    title: 'Actions',
    names: [
      'times',
      'times-circle',
      'check',
      'plus',
      'plus-circle',
      'minus',
      'redo',
      'undo',
      'refresh',
      'edit',
      'save',
      'download',
      'ban',
      'trash',
      'filter',
      'expand',
      'expand-alt',
      'compress-alt',
    ],
  },
  {
    title: 'Status',
    names: [
      'check-circle',
      'exclamation-circle',
      'exclamation-triangle',
      'info-circle',
      'question-circle',
    ],
  },
  {
    title: 'Spinner / Loading',
    names: ['spinner'],
  },
  {
    title: 'Play / Media',
    names: ['play', 'pause', 'play-circle'],
  },
  {
    title: 'Theme',
    names: ['sun', 'moon', 'desktop', 'palette'],
  },
  {
    title: 'Communication',
    names: ['paper-plane', 'comment', 'comments', 'terminal', 'microphone'],
  },
  {
    title: 'Connectivity / Hardware',
    names: ['server', 'sync-alt', 'plug', 'database', 'wifi', 'globe'],
  },
  {
    title: 'Shapes',
    names: ['circle', 'star'],
  },
  {
    title: 'User / Auth',
    names: ['user', 'user-plus', 'users', 'users-cog', 'lock', 'key', 'home', 'shield-alt'],
  },
  {
    title: 'Arrows / Direction',
    names: [
      'arrow-left',
      'arrow-right',
      'arrow-up',
      'arrow-down',
      'arrow-trend-up',
      'arrow-trend-down',
    ],
  },
  {
    title: 'Data / Analytics',
    names: [
      'chart-bar',
      'chart-line',
      'chart-pie',
      'chart-area',
      'signal',
      'robot',
      'cube',
      'file-code',
      'file-import',
    ],
  },
  {
    title: 'Finance',
    names: ['dollar-sign', 'piggy-bank', 'briefcase', 'tachometer-alt'],
  },
  {
    title: 'Tools / Settings',
    names: [
      'cog',
      'cogs',
      'tools',
      'magic',
      'wand-magic-sparkles',
      'lightbulb',
      'clipboard-check',
      'list-alt',
      'list-ol',
      'tasks',
      'chess',
      'columns',
      'stream',
      'random',
      'layer-group',
    ],
  },
  {
    title: 'Game / Interactive',
    names: ['gamepad', 'puzzle-piece'],
  },
  {
    title: 'Power',
    names: ['bolt'],
  },
  {
    title: 'Camera',
    names: ['camera'],
  },
  {
    title: 'Misc',
    names: ['inbox', 'sliders-h', 'font', 'paint-brush', 'th', 'th-large'],
  },
  {
    title: 'Search / Time',
    names: ['search', 'clock', 'history'],
  },
  {
    title: 'Files / Folders',
    names: ['folder-open', 'file-alt'],
  },
  {
    title: 'Browser / Window',
    names: ['window-restore'],
  },
  {
    title: 'Diagrams / Structure',
    names: ['project-diagram', 'sitemap', 'code-branch'],
  },
  {
    title: 'Code / Development',
    names: ['code', 'bug', 'clone'],
  },
  {
    title: 'Nature / Environment',
    names: ['leaf', 'sparkles', 'rocket'],
  },
  {
    title: 'Language / i18n',
    names: ['language'],
  },
  {
    title: 'AI / Brain',
    names: ['brain'],
  },
];

// Derive catalog from the registry — any icon added to ICONS auto-appears here
const ALL_ICON_NAMES = Object.keys(ICONS);
const categorized = new Set(DEFINED_GROUPS.flatMap((g) => g.names));
const uncategorized = ALL_ICON_NAMES.filter((n) => !categorized.has(n));
const ICON_GROUPS = uncategorized.length > 0
  ? [...DEFINED_GROUPS, { title: 'Other', names: uncategorized }]
  : DEFINED_GROUPS;

const meta = {
  title: 'Design System/Icon Library',
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'Catalog of every icon in the AutoBot `Icon.vue` registry, grouped by category. ' +
          'Use the `name` prop to render an icon and `size`, `spin`, `filled`, and `strokeWidth` ' +
          'props to control presentation.',
      },
    },
  },
} satisfies Meta;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Catalog: Story = {
  parameters: {
    docs: {
      description: {
        story: `Full registry rendered as a labeled grid by category. Total: ${ALL_ICON_NAMES.length} icons.`,
      },
    },
  },
  render: () => ({
    components: { Icon },
    setup() {
      return { groups: ICON_GROUPS, total: ALL_ICON_NAMES.length };
    },
    template: `
      <div class="max-w-7xl mx-auto p-8 space-y-10">
        <header>
          <h1 class="text-3xl font-bold mb-2">Icon Library</h1>
          <p class="text-autobot-text-secondary">
            {{ total }} icons across {{ groups.length }} categories. Use
            <code class="px-1 py-0.5 bg-autobot-bg-tertiary rounded text-sm">&lt;Icon name="..." /&gt;</code>
            to render any of them.
          </p>
        </header>

        <section v-for="group in groups" :key="group.title">
          <h2 class="text-lg font-semibold mb-4 pb-2 border-b border-autobot-border">
            {{ group.title }}
            <span class="text-sm font-normal text-autobot-text-muted ml-2">
              ({{ group.names.length }})
            </span>
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div
              v-for="name in group.names"
              :key="name"
              class="flex flex-col items-center justify-center gap-2 p-4 rounded-md border border-autobot-border hover:bg-autobot-bg-hover transition-colors"
            >
              <Icon :name="name" size="lg" class="text-autobot-text-primary" />
              <code class="text-xs text-autobot-text-secondary text-center break-all">{{ name }}</code>
            </div>
          </div>
        </section>
      </div>
    `,
  }),
};

export const Sizes: Story = {
  parameters: {
    docs: {
      description: {
        story:
          'Available size variants — `xs` (0.75rem), `sm` (1rem), `md` (1.25rem, default), `lg` (1.5rem), `xl` (2rem).',
      },
    },
  },
  render: () => ({
    components: { Icon },
    setup() {
      return {
        sizes: ['xs', 'sm', 'md', 'lg', 'xl'] as const,
      };
    },
    template: `
      <div class="max-w-3xl mx-auto p-8">
        <h2 class="text-xl font-semibold mb-6">Size Scale</h2>
        <div class="grid grid-cols-5 gap-4">
          <div
            v-for="size in sizes"
            :key="size"
            class="flex flex-col items-center justify-center gap-3 p-6 rounded-md border border-autobot-border"
          >
            <Icon name="star" :size="size" class="text-autobot-primary" />
            <code class="text-xs text-autobot-text-secondary">{{ size }}</code>
          </div>
        </div>
      </div>
    `,
  }),
};

export const SpinAndFilled: Story = {
  parameters: {
    docs: {
      description: {
        story:
          'Loading state with `spin` prop and outlined vs filled rendering via the `filled` prop.',
      },
    },
  },
  render: () => ({
    components: { Icon },
    template: `
      <div class="max-w-3xl mx-auto p-8 space-y-8">
        <section>
          <h2 class="text-xl font-semibold mb-4">Spin animation</h2>
          <div class="flex items-center gap-6">
            <div class="flex flex-col items-center gap-2 p-4 rounded-md border border-autobot-border">
              <Icon name="spinner" size="xl" spin class="text-autobot-primary" />
              <code class="text-xs text-autobot-text-secondary">spinner (spin)</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-4 rounded-md border border-autobot-border">
              <Icon name="refresh" size="xl" spin class="text-autobot-primary" />
              <code class="text-xs text-autobot-text-secondary">refresh (spin)</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-4 rounded-md border border-autobot-border">
              <Icon name="sync-alt" size="xl" spin class="text-autobot-primary" />
              <code class="text-xs text-autobot-text-secondary">sync-alt (spin)</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-4 rounded-md border border-autobot-border">
              <Icon name="cog" size="xl" spin class="text-autobot-primary" />
              <code class="text-xs text-autobot-text-secondary">cog (spin)</code>
            </div>
          </div>
        </section>

        <section>
          <h2 class="text-xl font-semibold mb-4">Outlined vs Filled</h2>
          <div class="grid grid-cols-2 gap-4 max-w-lg">
            <div class="flex flex-col items-center gap-2 p-6 rounded-md border border-autobot-border">
              <Icon name="star" size="xl" class="text-autobot-warning" />
              <code class="text-xs text-autobot-text-secondary">filled = false</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-6 rounded-md border border-autobot-border">
              <Icon name="star" size="xl" filled class="text-autobot-warning" />
              <code class="text-xs text-autobot-text-secondary">filled = true</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-6 rounded-md border border-autobot-border">
              <Icon name="check-circle" size="xl" class="text-autobot-success" />
              <code class="text-xs text-autobot-text-secondary">check-circle outlined</code>
            </div>
            <div class="flex flex-col items-center gap-2 p-6 rounded-md border border-autobot-border">
              <Icon name="check-circle" size="xl" filled class="text-autobot-success" />
              <code class="text-xs text-autobot-text-secondary">check-circle filled</code>
            </div>
          </div>
        </section>
      </div>
    `,
  }),
};
