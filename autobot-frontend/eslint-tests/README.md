# ESLint rule test fixtures

Manual-verification fixtures for the custom ESLint rules added by this project. These files are excluded from the normal lint scope (see `eslint.config.ts` `globalIgnores`) because they contain intentional rule violations.

## How to run

```bash
cd autobot-frontend
npx eslint --no-ignore eslint-tests/
```

Expected output:

* `no-hardcoded-vm-ip-deny.test.ts` — **6 errors** (one per `// EXPECT-ERROR` line)
* `no-hardcoded-vm-ip-allow.test.ts` — **0 errors**
* `no-deprecated-design-tokens-deny.test.vue` — **8 errors** (one per `<!-- EXPECT-ERROR -->` line)
* `no-deprecated-design-tokens-allow.test.vue` — **0 errors**

## When to add fixtures here

When introducing a new custom ESLint rule, add a deny + allow fixture pair so future maintainers can:

1. See concrete examples of what the rule catches and what it lets through.
2. Verify rule selectors still work after ESLint or plugin upgrades.

## Issue references

* `no-restricted-syntax`: hardcoded VM-IP rule — `#6784`
* `vue/no-restricted-static-attribute` + `vue/no-restricted-syntax`: deprecated design tokens — MVA-192
