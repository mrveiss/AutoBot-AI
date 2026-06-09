// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import {  defineComponent, h } from 'vue';
import AsyncComponentWrapper from './AsyncComponentWrapper.vue';

// Simple inline component used as the loaded result in success stories
const SimpleLoaded = defineComponent({
  name: 'SimpleLoaded',
  template: '<div style="padding: 1rem; background: #d1fae5; border-radius: 0.5rem; color: #065f46;">Component loaded successfully!</div>',
});

// Simple inline component that renders a data table for the rich story
const RichLoaded = defineComponent({
  name: 'RichLoaded',
  template: `
    <div style="padding: 1.5rem; background: #eff6ff; border-radius: 0.5rem; color: #1e3a5f;">
      <h3 style="margin: 0 0 0.5rem 0;">Async Component Content</h3>
      <p style="margin: 0; font-size: 0.875rem;">This content was loaded asynchronously via AsyncComponentWrapper.</p>
    </div>
  `,
});

const meta = {
  title: 'Components/Async/AsyncComponentWrapper',
  component: AsyncComponentWrapper,
  tags: ['autodocs'],
  argTypes: {
    componentName: {
      control: 'text',
      description: 'Display name shown in the loading spinner and error fallback',
    },
    loadingMessage: {
      control: 'text',
      description: 'Message shown beneath the spinner while loading',
    },
    maxRetries: {
      control: { type: 'number', min: 0, max: 10 },
      description: 'Maximum number of automatic retries before showing the error fallback',
    },
    retryDelay: {
      control: { type: 'number', min: 0, max: 5000 },
      description: 'Base delay in ms between retries (exponential backoff applied)',
    },
    timeout: {
      control: { type: 'number', min: 1000, max: 30000 },
      description: 'Milliseconds before treating the load as timed out',
    },
  },
} as Meta<typeof AsyncComponentWrapper>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// Loader that resolves immediately
const fastLoader = () => Promise.resolve({ default: SimpleLoaded });

// Loader with a deliberate 800ms delay so the spinner is visible
const slowLoader = () =>
  new Promise<{ default: typeof RichLoaded }>((resolve) =>
    setTimeout(() => resolve({ default: RichLoaded }), 800)
  );

// Loader that always rejects so the error fallback is shown
const failingLoader = () => Promise.reject(new Error('ChunkLoadError: Loading chunk 99 failed.'));

export const Default: Story = {
  render: () => ({
    components: { AsyncComponentWrapper },
    setup() {
      return { loader: fastLoader };
    },
    template: '<AsyncComponentWrapper :componentLoader="loader" componentName="SimpleLoaded" />',
  }),
};

export const WithLoadingSpinner: Story = {
  render: () => ({
    components: { AsyncComponentWrapper },
    setup() {
      return { loader: slowLoader };
    },
    template: `
      <AsyncComponentWrapper
        :componentLoader="loader"
        componentName="RichLoaded"
        loadingMessage="Fetching dashboard data, please wait..."
      />
    `,
  }),
};

export const ErrorFallback: Story = {
  render: () => ({
    components: { AsyncComponentWrapper },
    setup() {
      return { loader: failingLoader };
    },
    template: `
      <AsyncComponentWrapper
        :componentLoader="loader"
        componentName="BrokenPanel"
        :maxRetries="1"
        loadingMessage="Attempting to load BrokenPanel..."
      />
    `,
  }),
};

export const WithPassthroughProps: Story = {
  render: () => ({
    components: { AsyncComponentWrapper },
    setup() {
      const loader = () => Promise.resolve({
        default: defineComponent({
          props: { title: String, count: Number },
          render() {
            return h('div', {
              style: 'padding:1rem;background:#fef9c3;border-radius:0.5rem;',
            }, [
              h('strong', this.title ?? 'Untitled'),
              h('span', { style: 'margin-left:0.5rem;' }, `(${this.count ?? 0} items)`),
            ]);
          },
        }),
      });
      return {
        loader,
        componentProps: { title: 'Knowledge Base', count: 42 },
      };
    },
    template: `
      <AsyncComponentWrapper
        :componentLoader="loader"
        componentName="KnowledgeList"
        :componentProps="componentProps"
        loadingMessage="Loading knowledge base..."
      />
    `,
  }),
};
