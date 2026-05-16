import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalStatusBar from './TerminalStatusBar.vue';

const meta = {
  title: 'Components/Terminal/TerminalStatusBar',
  component: TerminalStatusBar,
  tags: ['autodocs'],
  argTypes: {
    connectionStatus: {
      control: 'select',
      options: ['connected', 'connecting', 'disconnected', 'error'],
      description: 'Current connection state displayed in the status bar',
    },
    connecting: {
      control: 'boolean',
      description: 'Whether a connection attempt is in progress',
    },
    canInput: {
      control: 'boolean',
      description: 'Whether user input is currently accepted',
    },
    sessionId: {
      control: 'text',
      description: 'Terminal session identifier displayed in the status bar',
    },
    outputLinesCount: {
      control: { type: 'number', min: 0 },
      description: 'Number of output lines to display in the stats section',
    },
  },
} as Meta<typeof TerminalStatusBar>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Connected: Story = {
  args: {
    connectionStatus: 'connected',
    connecting: false,
    canInput: true,
    sessionId: 'sess-abc-1234',
    outputLinesCount: 42,
  },
};

export const Connecting: Story = {
  args: {
    connectionStatus: 'connecting',
    connecting: true,
    canInput: false,
    sessionId: null,
    outputLinesCount: 0,
  },
};

export const Disconnected: Story = {
  args: {
    connectionStatus: 'disconnected',
    connecting: false,
    canInput: false,
    sessionId: null,
    outputLinesCount: 0,
  },
};

export const Error: Story = {
  args: {
    connectionStatus: 'error',
    connecting: false,
    canInput: false,
    sessionId: 'sess-xyz-9876',
    outputLinesCount: 15,
  },
};

export const HighOutputCount: Story = {
  args: {
    connectionStatus: 'connected',
    connecting: false,
    canInput: true,
    sessionId: 'sess-long-running',
    outputLinesCount: 9999,
  },
};
