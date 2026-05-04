import type { Meta, StoryObj } from '@storybook/vue3';

const meta = {
  title: 'Design System/Design Tokens',
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'Visual reference for the AutoBot design tokens exposed via Tailwind utilities. ' +
          'Colors come from the `autobot-*` token namespace defined in `src/assets/tailwind.css` ' +
          '(`@theme` block). Typography, spacing, radius, and shadow scales follow Tailwind defaults.',
      },
    },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Tokens: Story = {
  render: () => ({
    setup() {
      const semanticColors = [
        { name: 'autobot-primary', cls: 'bg-autobot-primary text-white' },
        { name: 'autobot-secondary', cls: 'bg-autobot-secondary text-white' },
        { name: 'autobot-success', cls: 'bg-autobot-success text-white' },
        { name: 'autobot-warning', cls: 'bg-autobot-warning text-white' },
        { name: 'autobot-error', cls: 'bg-autobot-error text-white' },
        { name: 'autobot-info', cls: 'bg-autobot-info text-white' },
      ];

      const surfaceColors = [
        { name: 'bg-primary', cls: 'bg-autobot-bg-primary' },
        { name: 'bg-secondary', cls: 'bg-autobot-bg-secondary' },
        { name: 'bg-tertiary', cls: 'bg-autobot-bg-tertiary' },
        { name: 'bg-elevated', cls: 'bg-autobot-bg-elevated' },
        { name: 'bg-card', cls: 'bg-autobot-bg-card' },
        { name: 'bg-input', cls: 'bg-autobot-bg-input' },
      ];

      const electricScale = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
      const blueGrayScale = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];

      const typography = [
        { cls: 'text-xs', label: 'text-xs', sample: 'The quick brown fox' },
        { cls: 'text-sm', label: 'text-sm', sample: 'The quick brown fox' },
        { cls: 'text-base', label: 'text-base', sample: 'The quick brown fox' },
        { cls: 'text-lg', label: 'text-lg', sample: 'The quick brown fox' },
        { cls: 'text-xl', label: 'text-xl', sample: 'The quick brown fox' },
        { cls: 'text-2xl', label: 'text-2xl', sample: 'The quick brown fox' },
        { cls: 'text-3xl', label: 'text-3xl', sample: 'The quick brown fox' },
        { cls: 'text-4xl', label: 'text-4xl', sample: 'The quick brown fox' },
      ];

      const fontWeights = [
        { cls: 'font-light', label: 'font-light' },
        { cls: 'font-normal', label: 'font-normal' },
        { cls: 'font-medium', label: 'font-medium' },
        { cls: 'font-semibold', label: 'font-semibold' },
        { cls: 'font-bold', label: 'font-bold' },
        { cls: 'font-extrabold', label: 'font-extrabold' },
      ];

      const spacings = [
        { cls: 'p-1', label: 'p-1', size: '0.25rem' },
        { cls: 'p-2', label: 'p-2', size: '0.5rem' },
        { cls: 'p-3', label: 'p-3', size: '0.75rem' },
        { cls: 'p-4', label: 'p-4', size: '1rem' },
        { cls: 'p-6', label: 'p-6', size: '1.5rem' },
        { cls: 'p-8', label: 'p-8', size: '2rem' },
      ];

      const radii = [
        { cls: 'rounded-none', label: 'rounded-none' },
        { cls: 'rounded-sm', label: 'rounded-sm' },
        { cls: 'rounded', label: 'rounded' },
        { cls: 'rounded-md', label: 'rounded-md' },
        { cls: 'rounded-lg', label: 'rounded-lg' },
        { cls: 'rounded-xl', label: 'rounded-xl' },
        { cls: 'rounded-full', label: 'rounded-full' },
      ];

      const shadows = [
        { cls: 'shadow-sm', label: 'shadow-sm' },
        { cls: 'shadow', label: 'shadow' },
        { cls: 'shadow-md', label: 'shadow-md' },
        { cls: 'shadow-lg', label: 'shadow-lg' },
        { cls: 'shadow-xl', label: 'shadow-xl' },
        { cls: 'shadow-2xl', label: 'shadow-2xl' },
      ];

      return {
        semanticColors,
        surfaceColors,
        electricScale,
        blueGrayScale,
        typography,
        fontWeights,
        spacings,
        radii,
        shadows,
      };
    },
    template: `
      <div class="max-w-6xl mx-auto p-8 space-y-12">
        <header>
          <h1 class="text-4xl font-bold mb-2">Design Tokens</h1>
          <p class="text-autobot-text-secondary">
            Color, typography, spacing, radius, and shadow primitives used across AutoBot.
          </p>
        </header>

        <!-- Semantic colors -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Semantic Colors</h2>
          <p class="text-sm text-autobot-text-secondary mb-4">
            Status and brand tokens that adapt to light/dark themes via CSS variables.
          </p>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div
              v-for="c in semanticColors"
              :key="c.name"
              :class="['rounded-lg p-6 flex flex-col justify-between min-h-24', c.cls]"
            >
              <span class="font-semibold">{{ c.name }}</span>
              <code class="text-xs opacity-80">{{ c.cls.split(' ')[0] }}</code>
            </div>
          </div>
        </section>

        <!-- Surface colors -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Surfaces</h2>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div
              v-for="c in surfaceColors"
              :key="c.name"
              :class="['rounded-lg p-6 border border-autobot-border min-h-24 flex flex-col justify-between', c.cls]"
            >
              <span class="font-semibold text-autobot-text-primary">{{ c.name }}</span>
              <code class="text-xs text-autobot-text-secondary">{{ c.cls }}</code>
            </div>
          </div>
        </section>

        <!-- Electric palette -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Electric (Primary) Scale</h2>
          <div class="grid grid-cols-6 md:grid-cols-11 gap-2">
            <div v-for="step in electricScale" :key="step" class="flex flex-col items-center gap-1">
              <div
                :class="['w-full h-12 rounded-md border border-autobot-border', \`bg-electric-\${step}\`]"
              ></div>
              <code class="text-[10px] text-autobot-text-secondary">{{ step }}</code>
            </div>
          </div>
        </section>

        <!-- BlueGray palette -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">BlueGray Scale</h2>
          <div class="grid grid-cols-5 md:grid-cols-10 gap-2">
            <div v-for="step in blueGrayScale" :key="step" class="flex flex-col items-center gap-1">
              <div
                :class="['w-full h-12 rounded-md border border-autobot-border', \`bg-blueGray-\${step}\`]"
              ></div>
              <code class="text-[10px] text-autobot-text-secondary">{{ step }}</code>
            </div>
          </div>
        </section>

        <!-- Typography scale -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Typography Scale</h2>
          <div class="space-y-3 border border-autobot-border rounded-lg p-6 bg-autobot-bg-card">
            <div v-for="t in typography" :key="t.label" class="flex items-baseline gap-6">
              <code class="text-xs text-autobot-text-muted w-20 shrink-0">{{ t.label }}</code>
              <span :class="t.cls" class="text-autobot-text-primary">{{ t.sample }}</span>
            </div>
          </div>
        </section>

        <!-- Font weights -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Font Weights</h2>
          <div class="space-y-2 border border-autobot-border rounded-lg p-6 bg-autobot-bg-card">
            <div v-for="w in fontWeights" :key="w.label" class="flex items-baseline gap-6">
              <code class="text-xs text-autobot-text-muted w-32 shrink-0">{{ w.label }}</code>
              <span :class="[w.cls, 'text-lg', 'text-autobot-text-primary']">The quick brown fox</span>
            </div>
          </div>
        </section>

        <!-- Spacing -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Spacing Scale</h2>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div
              v-for="s in spacings"
              :key="s.label"
              class="border border-autobot-border rounded-lg p-4 bg-autobot-bg-card"
            >
              <code class="block text-xs text-autobot-text-secondary mb-2">{{ s.label }} ({{ s.size }})</code>
              <div class="bg-autobot-bg-tertiary inline-block">
                <div :class="['bg-autobot-primary', s.cls]"></div>
              </div>
            </div>
          </div>
        </section>

        <!-- Border radius -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Border Radius</h2>
          <div class="grid grid-cols-3 md:grid-cols-7 gap-4">
            <div v-for="r in radii" :key="r.label" class="flex flex-col items-center gap-2">
              <div :class="['w-20 h-20 bg-autobot-primary', r.cls]"></div>
              <code class="text-xs text-autobot-text-secondary text-center">{{ r.label }}</code>
            </div>
          </div>
        </section>

        <!-- Shadows -->
        <section>
          <h2 class="text-2xl font-semibold mb-4">Shadows</h2>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-6 p-6 bg-autobot-bg-tertiary rounded-lg">
            <div v-for="sh in shadows" :key="sh.label" class="flex flex-col items-center gap-3">
              <div :class="['w-32 h-20 bg-autobot-bg-card rounded-md', sh.cls]"></div>
              <code class="text-xs text-autobot-text-secondary">{{ sh.label }}</code>
            </div>
          </div>
        </section>
      </div>
    `,
  }),
};
