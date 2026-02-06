module.exports = {
  root: true,
  env: {
    node: true,
    browser: true
  },
  extends: [
    'plugin:vue/vue3-essential',
    '@vue/eslint-config-typescript',
    'eslint:recommended'
  ],
  rules: {
    // FORTUNE 500 QUALITY: Zero tolerance for hardcoded configuration values
    'no-restricted-syntax': [
      'error',
      {
        selector: 'Literal[value=8001]',
        message: 'Hardcoded port 8001 is not allowed. Use configService.get("backend.port") instead.'
      },
      {
        selector: 'Literal[value=11434]',
        message: 'Hardcoded port 11434 is not allowed. Use configService.get("services.ollama.port") instead.'
      },
      {
        selector: 'Literal[value=5173]',
        message: 'Hardcoded port 5173 is not allowed. Use configService.get("frontend.port") instead.'
      },
      {
        selector: 'Literal[value=6379]',
        message: 'Hardcoded port 6379 is not allowed. Use configService.get("memory.redis.port") instead.'
      },
      {
        selector: 'Literal[value=3000]',
        message: 'Hardcoded port 3000 is not allowed. Use configService.get("services.playwright.port") instead.'
      },
      {
        selector: 'Literal[value=/^127\\.0\\.0\\.\\d+$/]',
        message: 'Hardcoded IP address is not allowed. Use configService.get() with proper configuration path.'
      },
      {
        selector: 'Literal[value="localhost"]',
        message: 'Hardcoded "localhost" is not allowed. Use configService.get("services.host") instead.'
      },
      {
        selector: 'Literal[value=/^http:\\/\\/localhost/]',
        message: 'Hardcoded localhost URL is not allowed. Use configService.get() to build URLs dynamically.'
      },
      {
        selector: 'Literal[value=/^http:\\/\\/127\\.0\\.0\\.\\d+/]',
        message: 'Hardcoded IP URL is not allowed. Use configService.get() to build URLs dynamically.'
      }
    ],

    // Additional quality rules for Fortune 500 standards
    'no-console': 'warn', // Use proper logging instead
    'no-debugger': 'error',
    'no-unused-vars': 'error',
    'prefer-const': 'error',
    'no-var': 'error'
  },

  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
    parser: '@typescript-eslint/parser'
  }
};
