import type { Meta, StoryObj } from '@storybook/vue3';
import Icon from './Icon.vue';

const meta = {
  title: 'Components/UI/Icon',
  component: Icon,
  argTypes: {
    name: {
      control: 'select',
      options: [
        'chevron-down', 'chevron-up', 'chevron-left', 'chevron-right', 'sort',
        'times', 'times-circle', 'check', 'plus', 'plus-circle', 'minus',
        'redo', 'undo', 'refresh', 'edit', 'save', 'download', 'ban',
        'trash', 'filter', 'expand', 'expand-alt', 'compress-alt',
        'check-circle', 'exclamation-circle', 'exclamation-triangle',
        'info-circle', 'question-circle', 'spinner',
        'play', 'pause', 'play-circle',
        'sun', 'moon', 'desktop', 'palette',
        'paper-plane', 'comment', 'comments', 'terminal', 'microphone',
        'server', 'sync-alt', 'circle', 'star',
        'user', 'user-plus', 'users', 'lock', 'key', 'home',
        'arrow-left', 'arrow-right', 'arrow-up', 'arrow-down',
        'arrow-trend-up', 'arrow-trend-down',
        'chart-bar', 'chart-line', 'chart-pie', 'chart-area', 'signal',
        'robot', 'cube', 'file-code', 'file-import',
        'dollar-sign', 'piggy-bank', 'briefcase', 'tachometer-alt',
        'cog', 'cogs', 'tools', 'magic', 'wand-magic-sparkles',
        'lightbulb', 'clipboard-check', 'list-alt', 'list-ol', 'tasks',
        'chess', 'columns', 'stream', 'random', 'layer-group',
        'gamepad', 'puzzle-piece', 'bolt', 'camera',
        'inbox', 'sliders-h', 'font', 'paint-brush', 'th', 'th-large',
        'search', 'clock', 'history',
        'folder-open', 'file-alt',
        'plug', 'database', 'wifi', 'globe', 'window-restore',
        'project-diagram', 'sitemap', 'code-branch',
        'code', 'bug', 'clone',
        'leaf', 'sparkles', 'rocket',
        'users-cog', 'shield-alt', 'language', 'brain',
      ],
      description: 'Icon name from the ICONS registry',
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl'],
      description: 'Icon size',
    },
    spin: {
      control: 'boolean',
      description: 'Apply continuous spin animation',
    },
    strokeWidth: {
      control: { type: 'number', min: 0.5, max: 4, step: 0.5 },
      description: 'SVG stroke width',
    },
    filled: {
      control: 'boolean',
      description: 'Use fill instead of stroke',
    },
  },
} as Meta<typeof Icon>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    name: 'check',
    size: 'md',
  },
};

export const Spinning: Story = {
  args: {
    name: 'sync-alt',
    size: 'lg',
    spin: true,
  },
};

export const Filled: Story = {
  args: {
    name: 'star',
    size: 'lg',
    filled: true,
  },
};

export const ThickStroke: Story = {
  args: {
    name: 'check',
    size: 'lg',
    strokeWidth: 3,
  },
};

export const AllSizes: Story = {
  render: () => ({
    components: { Icon },
    template: `
      <div class="flex items-end gap-6">
        <div class="flex flex-col items-center gap-1"><Icon name="check-circle" size="xs" /><span class="text-xs">xs</span></div>
        <div class="flex flex-col items-center gap-1"><Icon name="check-circle" size="sm" /><span class="text-xs">sm</span></div>
        <div class="flex flex-col items-center gap-1"><Icon name="check-circle" size="md" /><span class="text-xs">md</span></div>
        <div class="flex flex-col items-center gap-1"><Icon name="check-circle" size="lg" /><span class="text-xs">lg</span></div>
        <div class="flex flex-col items-center gap-1"><Icon name="check-circle" size="xl" /><span class="text-xs">xl</span></div>
      </div>
    `,
  }),
};

const renderGroup = (names: readonly string[]) => ({
  components: { Icon },
  setup() {
    return { names };
  },
  template: `
    <div class="grid grid-cols-6 sm:grid-cols-8 gap-3">
      <div
        v-for="n in names"
        :key="n"
        class="flex flex-col items-center gap-1 p-2 border rounded text-center"
      >
        <Icon :name="n" size="md" />
        <span class="text-[10px] font-mono text-gray-600">{{ n }}</span>
      </div>
    </div>
  `,
});

export const NavigationIcons: Story = {
  render: () => renderGroup([
    'chevron-down', 'chevron-up', 'chevron-left', 'chevron-right',
    'arrow-left', 'arrow-right', 'arrow-up', 'arrow-down',
    'arrow-trend-up', 'arrow-trend-down', 'sort',
  ]),
};

export const ActionIcons: Story = {
  render: () => renderGroup([
    'times', 'times-circle', 'check', 'plus', 'plus-circle', 'minus',
    'edit', 'save', 'download', 'trash', 'ban', 'filter',
    'redo', 'undo', 'refresh', 'sync-alt',
    'expand', 'expand-alt', 'compress-alt',
  ]),
};

export const StatusIcons: Story = {
  render: () => renderGroup([
    'check-circle', 'exclamation-circle', 'exclamation-triangle',
    'info-circle', 'question-circle', 'spinner', 'circle', 'star',
  ]),
};

export const ThemeIcons: Story = {
  render: () => renderGroup([
    'sun', 'moon', 'desktop', 'palette', 'paint-brush',
  ]),
};

export const CommunicationIcons: Story = {
  render: () => renderGroup([
    'paper-plane', 'comment', 'comments', 'terminal', 'microphone',
  ]),
};

export const UserAuthIcons: Story = {
  render: () => renderGroup([
    'user', 'user-plus', 'users', 'users-cog', 'lock', 'key', 'home', 'shield-alt',
  ]),
};

export const DataAnalyticsIcons: Story = {
  render: () => renderGroup([
    'chart-bar', 'chart-line', 'chart-pie', 'chart-area',
    'signal', 'robot', 'cube', 'file-code', 'file-import',
    'tachometer-alt', 'project-diagram', 'sitemap',
  ]),
};

export const ToolsSettingsIcons: Story = {
  render: () => renderGroup([
    'cog', 'cogs', 'tools', 'magic', 'wand-magic-sparkles',
    'lightbulb', 'clipboard-check', 'list-alt', 'list-ol', 'tasks',
    'sliders-h', 'columns', 'stream', 'random', 'layer-group',
    'th', 'th-large',
  ]),
};

export const ConnectivityIcons: Story = {
  render: () => renderGroup([
    'server', 'plug', 'database', 'wifi', 'globe', 'window-restore',
  ]),
};

export const FilesCodeIcons: Story = {
  render: () => renderGroup([
    'folder-open', 'file-alt', 'code', 'code-branch', 'bug', 'clone',
  ]),
};

export const MediaTimeIcons: Story = {
  render: () => renderGroup([
    'play', 'pause', 'play-circle', 'camera', 'search', 'clock', 'history',
  ]),
};

export const FinanceIcons: Story = {
  render: () => renderGroup([
    'dollar-sign', 'piggy-bank', 'briefcase',
  ]),
};

export const MiscIcons: Story = {
  render: () => renderGroup([
    'inbox', 'font', 'gamepad', 'puzzle-piece', 'bolt', 'chess',
    'leaf', 'sparkles', 'rocket', 'language', 'brain',
  ]),
};
