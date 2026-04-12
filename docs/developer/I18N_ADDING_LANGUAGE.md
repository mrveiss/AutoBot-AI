# Adding a New Language to AutoBot

This guide explains how to add a new locale to the AutoBot frontend.
All locale files live in `autobot-frontend/src/i18n/locales/`.

## Prerequisites

- `vue-i18n` is already installed and configured in `autobot-frontend/`.
- The `en.json` file in `autobot-frontend/src/i18n/locales/` is the single
  source of truth for all message keys.

## Steps

### 1. Create the locale file

Copy `en.json` to `<code>.json` where `<code>` is the BCP 47 language tag
(lowercase), for example `ja.json` for Japanese or `zh.json` for Chinese.

```bash
cp autobot-frontend/src/i18n/locales/en.json \
   autobot-frontend/src/i18n/locales/<code>.json
```

### 2. Translate the strings

Open the new file and replace each English value with the translated string.
Do **not** change the keys — only the values.

Update the `_meta` block at the top to reflect the new locale:

```json
{
  "_meta": {
    "dir": "ltr",
    "generated": "YYYY-MM-DD",
    "issue": "#XXXX"
  },
  ...
}
```

Set `"dir"` to `"rtl"` for right-to-left scripts (Arabic, Hebrew, Persian,
Urdu) and `"ltr"` for all others. This value is read by `getLocaleDir()` in
`autobot-frontend/src/i18n/index.ts` to set the `html[dir]` attribute.

### 3. Register the locale (automatic)

No manual registration is needed. The i18n module uses `import.meta.glob` to
discover every `*.json` file inside `locales/` at build time:

```ts
// autobot-frontend/src/i18n/index.ts
const localeModules = import.meta.glob('./locales/*.json')
export const SUPPORTED_LOCALES = Object.keys(localeModules)
  .map(path => path.replace('./locales/', '').replace('.json', ''))
  .sort()
```

Adding the file is sufficient for it to appear in `SUPPORTED_LOCALES`, which
populates the language switcher and the Settings panel automatically.

### 4. Verify coverage

Run the key-coverage check to confirm the new file has every key from
`en.json`:

```bash
python3 - << 'EOF'
import json, os
path = 'autobot-frontend/src/i18n/locales'

def flatten(d, prefix=''):
    out = {}
    for k, v in d.items():
        key = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out

with open(f'{path}/en.json', encoding='utf-8') as f:
    en_flat = set(flatten(json.load(f)).keys())

for fname in sorted(os.listdir(path)):
    if fname == 'en.json':
        continue
    with open(f'{path}/{fname}', encoding='utf-8') as f:
        locale_flat = set(flatten(json.load(f)).keys())
    missing = en_flat - locale_flat
    status = 'OK' if not missing else f'{len(missing)} missing'
    print(f'{fname}: {status}')
EOF
```

All files should report `OK`. If a file reports missing keys, add them (using
English values as temporary placeholders until a translator fills them in).

### 5. Run the tests

```bash
cd autobot-frontend
npm run test -- src/i18n src/composables/__tests__/useAvailableLanguages
```

All tests must pass before submitting a PR.

## Supported locales (current)

| Code | Language      | Direction |
|------|---------------|-----------|
| ar   | Arabic        | RTL       |
| de   | German        | LTR       |
| en   | English       | LTR       |
| es   | Spanish       | LTR       |
| fa   | Persian       | RTL       |
| fr   | French        | LTR       |
| he   | Hebrew        | RTL       |
| lv   | Latvian       | LTR       |
| pl   | Polish        | LTR       |
| pt   | Portuguese    | LTR       |
| ur   | Urdu          | RTL       |

## Adding a new message key

When you add a new visible string to a component:

1. Add the key and English value to `en.json` first.
2. Add the same key (with a translated value, or the English value as a
   placeholder) to every other locale file.
3. Run the coverage check above to confirm zero missing keys.
4. Use `t('your.key')` in the component template or `useI18n()` in the
   `<script setup>` block.

## Date and number formatting

Use the `Intl` API with the active locale for all date, time, and number
formatting. The active locale is always available via `useI18n().locale`.

```ts
const { locale } = useI18n()
const formatted = new Intl.DateTimeFormat(locale.value, {
  dateStyle: 'medium',
  timeStyle: 'short',
}).format(new Date(timestamp))
```

This ensures output automatically respects the user's selected language.
