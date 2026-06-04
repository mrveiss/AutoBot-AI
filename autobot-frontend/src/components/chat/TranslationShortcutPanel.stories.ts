import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TranslationShortcutPanel from './TranslationShortcutPanel.vue';

const meta = {
  title: 'Components/Chat/TranslationShortcutPanel',
  component: TranslationShortcutPanel,
  tags: ['autodocs'],
  argTypes: {
    initialText: {
      control: 'text',
      description: 'Pre-populated text to translate',
    },
  },
} as Meta<typeof TranslationShortcutPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    initialText: '',
  },
};

export const WithPrefilledText: Story = {
  args: {
    initialText: 'Hello, how are you? I hope you are doing well today.',
  },
};

export const WithLongText: Story = {
  args: {
    initialText: 'The quick brown fox jumps over the lazy dog. This is a sample sentence used to demonstrate the translation feature with a longer piece of text that might wrap across multiple lines.',
  },
};
