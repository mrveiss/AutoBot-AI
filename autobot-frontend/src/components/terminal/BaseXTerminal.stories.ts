import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import BaseXTerminal from './BaseXTerminal.vue';

const meta = {
  title: 'Components/Terminal/BaseXTerminal',
  component: BaseXTerminal,
  tags: ['autodocs'],
  argTypes: {
    sessionId: {
      control: 'text',
      description: 'Terminal session identifier',
    },
    autoConnect: {
      control: 'boolean',
      description: 'Automatically connect the terminal on mount',
    },
    theme: {
      control: 'select',
      options: ['dark', 'light'],
      description: 'Color theme for the xterm.js terminal',
    },
    readOnly: {
      control: 'boolean',
      description: 'Disable keyboard input (read-only display mode)',
    },
    fontSize: {
      control: { type: 'number', min: 8, max: 32, step: 1 },
      description: 'Font size in pixels',
    },
    fontFamily: {
      control: 'text',
      description: 'CSS font-family string for the terminal',
    },
  },
} as Meta<typeof BaseXTerminal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// NOTE: BaseXTerminal initialises an xterm.js Terminal instance on mount and
// requires a real browser DOM.  In Storybook Canvas mode all stories render
// correctly; in JSDOM-based test environments the terminal element will remain
// empty.  The container sizing below gives the xterm viewport enough room to
// fit properly.

export const DarkTheme: Story = {
  render: () => ({
    components: { BaseXTerminal },
    template: `
      <div style="width: 800px; height: 400px; background: #1a1b26;">
        <BaseXTerminal session-id="story-dark" theme="dark" :auto-connect="false" />
      </div>
    `,
  }),
};

export const LightTheme: Story = {
  render: () => ({
    components: { BaseXTerminal },
    template: `
      <div style="width: 800px; height: 400px; background: #ffffff; border: 1px solid #ccc;">
        <BaseXTerminal session-id="story-light" theme="light" :auto-connect="false" />
      </div>
    `,
  }),
};

export const LargeFontSize: Story = {
  args: {
    sessionId: 'story-large-font',
    theme: 'dark',
    autoConnect: false,
    fontSize: 20,
  },
  render: (args: Record<string, unknown>) => ({
    components: { BaseXTerminal },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 400px; background: #1a1b26;">
        <BaseXTerminal v-bind="args" />
      </div>
    `,
  }),
};

export const ReadOnly: Story = {
  args: {
    sessionId: 'story-readonly',
    theme: 'dark',
    autoConnect: false,
    readOnly: true,
    fontSize: 14,
  },
  render: (args: Record<string, unknown>) => ({
    components: { BaseXTerminal },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 400px; background: #1a1b26;">
        <BaseXTerminal v-bind="args" />
      </div>
    `,
  }),
};

export const CustomFont: Story = {
  args: {
    sessionId: 'story-custom-font',
    theme: 'dark',
    autoConnect: false,
    fontSize: 14,
    fontFamily: 'Courier New, Courier, monospace',
  },
  render: (args: Record<string, unknown>) => ({
    components: { BaseXTerminal },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 400px; background: #1a1b26;">
        <BaseXTerminal v-bind="args" />
      </div>
    `,
  }),
};
