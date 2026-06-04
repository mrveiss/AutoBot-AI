import type { Meta, StoryObj } from '@storybook/vue3';
import LanguageSwitcher from './LanguageSwitcher.vue';

const meta = {
  title: 'Components/Layout/LanguageSwitcher',
  component: LanguageSwitcher,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'Globe icon language switcher for the navigation bar. Renders an icon-button dropdown on desktop and an inline select on mobile. Reads/writes the active language via `usePreferences` and pulls available languages from `useAvailableLanguages`.',
      },
    },
  },
  argTypes: {
    mobile: {
      control: 'boolean',
      description:
        'Render the inline mobile variant (globe icon + native `<select>`) instead of the desktop dropdown trigger.',
    },
  },
} as Meta<typeof LanguageSwitcher>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Desktop: Story = {
  args: {
    mobile: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          'Desktop variant: a 40x40 icon button. Click the globe to open the dropdown and choose a language.',
      },
    },
  },
  render: (args: any) => ({
    components: { LanguageSwitcher },
    setup() {
      return { args };
    },
    template: `
      <div class="bg-autobot-primary p-4 inline-flex rounded-md">
        <LanguageSwitcher v-bind="args" />
      </div>
    `,
  }),
};

export const Mobile: Story = {
  args: {
    mobile: true,
  },
  parameters: {
    docs: {
      description: {
        story:
          'Mobile variant: an inline row with a globe icon and a native `<select>` for language choice.',
      },
    },
  },
  render: (args: any) => ({
    components: { LanguageSwitcher },
    setup() {
      return { args };
    },
    template: `
      <div class="bg-autobot-bg-secondary border border-autobot-border rounded-md w-64">
        <LanguageSwitcher v-bind="args" />
      </div>
    `,
  }),
};

export const InNavBar: Story = {
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        story:
          'Realistic placement inside a primary navigation bar, illustrating how the component sits next to other nav items.',
      },
    },
  },
  render: () => ({
    components: { LanguageSwitcher },
    template: `
      <nav class="bg-autobot-primary text-white px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <span class="font-bold text-lg">AutoBot</span>
          <span class="text-sm opacity-80">Dashboard</span>
        </div>
        <div class="flex items-center gap-3">
          <LanguageSwitcher />
        </div>
      </nav>
    `,
  }),
};

export const SideBySide: Story = {
  parameters: {
    docs: {
      description: {
        story:
          'Both variants rendered together for visual comparison of desktop vs mobile presentations.',
      },
    },
  },
  render: () => ({
    components: { LanguageSwitcher },
    template: `
      <div class="flex flex-col gap-6">
        <div>
          <p class="text-sm font-medium mb-2 text-autobot-text-secondary">Desktop</p>
          <div class="bg-autobot-primary p-4 inline-flex rounded-md">
            <LanguageSwitcher />
          </div>
        </div>
        <div>
          <p class="text-sm font-medium mb-2 text-autobot-text-secondary">Mobile</p>
          <div class="bg-autobot-bg-secondary border border-autobot-border rounded-md w-64">
            <LanguageSwitcher mobile />
          </div>
        </div>
      </div>
    `,
  }),
};
