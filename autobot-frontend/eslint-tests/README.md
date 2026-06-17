# ESLint rule test fixtures

Manual-verification fixtures for the custom ESLint rules added by this project. These files are excluded from the normal lint scope (see `eslint.config.ts` `globalIgnores`) because they contain intentional rule violations.

Each `*-deny.test.*` file carries a top-of-file `/* eslint-disable */` so that an accidental full-tree `eslint . --no-ignore` does not fail on the intentional violations. To actually exercise a rule, strip that directive on a throwaway copy and lint it (see below).

## How to run

```bash
cd autobot-frontend
# Copy a deny fixture WITHOUT the eslint-disable banner into the linted scope,
# lint it, then remove it. (The banner suppresses the very rule we want to test.)
cp eslint-tests/no-apiclient-envelope-misuse-deny.test.ts src/__probe.ts
sed -i 's|/\* eslint-disable \*/||' src/__probe.ts
npx eslint --no-ignore src/__probe.ts
rm -f src/__probe.ts
```

Expected output (deny fixtures count one error per `// EXPECT-ERROR` line; allow fixtures count zero rule errors):

* `no-hardcoded-vm-ip-deny.test.ts` — **6 errors**
* `no-hardcoded-vm-ip-allow.test.ts` — **0 errors**
* `no-deprecated-design-tokens-deny.test.vue` — **8 errors** (one per `<!-- EXPECT-ERROR -->` line)
* `no-deprecated-design-tokens-allow.test.vue` — **0 errors**
* `no-apiclient-envelope-misuse-deny.test.ts` — **10 `no-restricted-syntax` errors** (one per `// EXPECT-ERROR` line)
* `no-apiclient-envelope-misuse-allow.test.ts` — **0 `no-restricted-syntax` errors**

## When to add fixtures here

When introducing a new custom ESLint rule, add a deny + allow fixture pair so future maintainers can:

1. See concrete examples of what the rule catches and what it lets through.
2. Verify rule selectors still work after ESLint or plugin upgrades.

## Issue references

* `no-restricted-syntax`: hardcoded VM-IP rule — `#6784`
* `vue/no-restricted-static-attribute` + `vue/no-restricted-syntax`: deprecated design tokens — MVA-192
* `no-restricted-syntax`: ApiClient envelope misuse (`.json()`/`.data` on parsed results) — `#10025`
