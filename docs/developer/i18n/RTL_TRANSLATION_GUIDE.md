# RTL Language Translation Guide (Persian, Hebrew, Urdu)

## Overview

This document outlines the translation requirements for three right-to-left (RTL) languages in AutoBot:
- **Persian (Farsi)** — `fa.json`
- **Hebrew** — `he.json`
- **Urdu** — `ur.json`

As of 2026-04-12, each language file is missing **445 flat-key translations** compared to the English baseline. These keys were added to the English locale (`en.json`) but have not yet been translated to the RTL languages.

## Translation Status

| Language | Missing Keys | Total Keys | Coverage |
|----------|--------------|-----------|----------|
| Persian (fa)  | 445 | 6439 | 93.1% |
| Hebrew (he)   | 445 | 6439 | 93.1% |
| Urdu (ur)     | 445 | 6439 | 93.1% |

## Missing Translation Categories

All 445 missing keys belong to the `knowledge.*` namespace (Knowledge Base management system). The breakdown is:

### Knowledge Management (445 keys)

- **knowledge.mainCategories** (3 keys) — KB category types
- **knowledge.maintenance** (18 keys) — Database health & optimization
- **knowledge.manager** (8 keys) — KB interface tabs & UI labels
- **knowledge.memoryOrphan** (14 keys) — Orphaned entity cleanup
- **knowledge.persistence** (41 keys) — Conversation persistence features
- **knowledge.promptEditor** (32 keys) — System prompt editing interface
- **knowledge.qualityScore** (1 key) — Quality metrics
- **knowledge.research** (28 keys) — Web research integration
- **knowledge.scopeSelector** (7 keys) — Scope/team selection
- **knowledge.search** (50 keys) — Advanced search interface
- **knowledge.sessionOrphan** (17 keys) — Orphaned session cleanup
- **knowledge.share** (16 keys) — Document sharing & permissions
- **knowledge.stats** (80 keys) — Knowledge statistics dashboard
- **knowledge.systemDocs** (17 keys) — System documentation browser
- **knowledge.systemKnowledge** (26 keys) — System knowledge initialization
- **knowledge.treeNode** (2 keys) — Tree view utilities
- **knowledge.upload** (37 keys) — Document upload interface
- **knowledge.vectorization** (13 keys) — Vector generation UI
- **knowledge.verification** (17 keys) — Knowledge approval workflow

## Priority Tiers

### Tier 1 (Critical UI) — 48 keys

High-impact user-facing strings that appear frequently in the interface:

```
knowledge.manager.*                    (8 keys)  — Tab labels
knowledge.search.searchPlaceholder     (1 key)   — Main search input
knowledge.search.noResults             (1 key)   — Empty state
knowledge.search.searchBtn             (1 key)   — Button
knowledge.upload.uploadFiles           (1 key)   — Button
knowledge.upload.dragAndDrop           (1 key)   — UI instruction
knowledge.upload.category              (1 key)   — Form label
knowledge.upload.tags                  (1 key)   — Form label
knowledge.stats.title                  (assumed) (1 key)   — Dashboard heading
knowledge.persistence.title            (assumed) (1 key)   — Feature heading
knowledge.promptEditor.title           (1 key)   — Feature heading
knowledge.research.btnResearch         (1 key)   — Button
knowledge.research.btnStop             (1 key)   — Button
+ 29 additional high-frequency strings
```

### Tier 2 (Important UI) — 180 keys

Secondary UI elements, form labels, dialogs, confirmations:

- Upload: file type errors, category selection, visibility levels (16 keys)
- Search: filters, result display, confidence scores (18 keys)
- Knowledge Stats: metrics labels, data visualization (35 keys)
- Sharing: permission levels, user search (16 keys)
- Prompt Editor: history, version control, save states (20 keys)
- Research: browser connection, query interface (20 keys)
- Other KB management features (55 keys)

### Tier 3 (Support UI) — 217 keys

Error messages, technical details, advanced options, system messages:

- Orphan cleanup: scan descriptions, error handling (14 keys)
- System knowledge: initialization steps, completion messages (26 keys)
- Database maintenance: optimization, health diagnostics (18 keys)
- Vectorization: progress tracking, technical labels (13 keys)
- Verification: approval workflow states, quality thresholds (17 keys)
- Help text and tooltips throughout (129 keys)

## Translation Requirements

### Linguistic Considerations

**Persian (فارسی):**
- RTL text direction (bidi support required)
- Persian numerals: convert 0-9 to ۰-۹ in UI contexts
- Formal/informal register: use formal (مودب) for system messages
- Complex word order: some English compound terms need restructuring
- Specialized terminology for "Knowledge Base," "Vectorization," "RAG" (may use English transliterations)

**Hebrew (עברית):**
- RTL text direction with complex bidi algorithm requirements
- Hebrew numerals: use Arabic numerals (0-9) in modern UI
- Formal/informal: use formal register for system UI
- Short forms preferred due to space constraints in RTL layouts
- Scientific terms often transliterated (RAG, Vector, Embedding)

**Urdu (اردو):**
- RTL text direction (similar to Persian, uses Arabic script)
- Urdu numerals: ۰-۹ (same as Arabic/Persian)
- Formal/informal: Urdu has complex honorific system; use standard formal
- Many technical terms borrowed from English
- Space handling: Urdu text may require wider UI in RTL context

### RTL Rendering Requirements

After translation, verify these aspects:

1. **Text Direction**: All translated strings must render RTL
   - Labels should align to the right edge
   - No automatic bidi isolation issues (already handled by Vue i18n + Tailwind)

2. **Bidirectional Text**: Mixed English/RTL text (e.g., "RAG: نتایج")
   - Use Unicode directional marks if needed: RLM (U+200F), LRM (U+200E)
   - Test with terms: "RAG", "Vector", "Embedding", "Redis", "ChromaDB"

3. **Numbers in RTL Context**:
   - Persian: Use Persian numerals (۰-۹) in user-facing labels
   - Hebrew: Use Arabic numerals (0-9) per modern standard
   - Urdu: Use Urdu numerals (۰-۹) in user-facing labels
   - Database stats/metrics: May keep English numerals for clarity

4. **Space Constraints**:
   - RTL languages require ~20-30% more space than English
   - Hebrew is particularly compact; Persian/Urdu expand more
   - Button labels and table headers should be tested for overflow
   - Test at 1920x1080 and narrower viewports (mobile)

## Translation Format

All keys are flat strings at the root level of the JSON files. Example:

```json
{
  "knowledge.manager.tabSearch": "Search",
  "knowledge.manager.tabCategories": "Categories",
  "knowledge.search.searchPlaceholder": "Search in knowledge base...",
  "knowledge.stats.title": "Statistics"
}
```

### File Locations

```
autobot-frontend/src/i18n/locales/fa.json   (Persian)
autobot-frontend/src/i18n/locales/he.json   (Hebrew)
autobot-frontend/src/i18n/locales/ur.json   (Urdu)
```

### Validation

Each language file must:
1. Be valid JSON (no syntax errors)
2. Contain exactly 6439 root-level keys (matching en.json)
3. Have all 445 knowledge.* keys properly translated
4. Avoid using English fallback values (current state uses auto-fallback during feature development)

## Translator Requirements

### Skills Needed

- **Native fluency**: 10+ years experience in each target language
- **Technical background**: Familiarity with software UI terminology (vectors, embeddings, knowledge graphs, etc.)
- **RTL expertise**: Experience translating for RTL applications (RTL text layout, bidi handling)
- **Quality assurance**: Ability to test translations in-app and validate RTL rendering

### Recommended Workflow

1. **Setup**: Clone repo, find `docs/developer/I18N_ADDING_LANGUAGE.md` for i18n structure
2. **Tier 1 First**: Translate critical 48 keys first (highest user impact)
3. **Testing**: Build frontend, test at `/settings?lang=fa` (or `he`, `ur`)
4. **Tier 2 & 3**: Translate remaining 397 keys in batches
5. **Review**: Have 2nd native speaker review before final submission
6. **RTL Validation**: Test number rendering, bidi text, button overflow at multiple viewports

### Expected Timeline

- Tier 1 (Critical): 1-2 hours per language (48 keys)
- Tier 2 (Important): 4-6 hours per language (180 keys)
- Tier 3 (Support): 6-8 hours per language (217 keys)
- RTL testing & refinement: 2-4 hours per language

**Total per language: ~15-25 hours** (native speaker with technical background)

## Resources

### Language-Specific References

**Persian:**
- [Rafti: Persian Online Translator](https://en.rafti.ir/) — general reference
- [Persian Wikipedia Technical Terms](https://fa.wikipedia.org/) — for standardized translations
- [PersianTools.js](https://github.com/persiandecimal/persian-tools) — Persian numeral/bidi utilities

**Hebrew:**
- [Hebrew Academy Dictionary](https://www.academy.ac.il/) — official Hebrew terminology
- [Israeli Tech Glossary](https://www.gov.il/) — government standardized terms
- [Right-to-Left Text in HTML](https://www.w3.org/International/questions/qa-scripts) — W3C guide

**Urdu:**
- [Urdu Academy](https://www.crulp.org/) — official terminology resource
- [Urdu Wikipedia](https://ur.wikipedia.org/) — community translations
- [Nastaliq Standards](https://www.unicode.org/reports/tr9/) — Urdu script rendering

### Technical I18N References

- [Vue I18n Documentation](https://vue-i18n.intlify.dev/) — how translations are loaded
- [Tailwind CSS RTL](https://tailwindcss.com/docs/configuration#important-modifier) — RTL class support
- [Mozilla Localization Guide](https://developer.mozilla.org/en-US/docs/Mozilla/Localization) — general best practices
- [Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/) — for handling mixed text

## Next Steps

1. **Engage translators**: Post job on Upwork, Fiverr, or local tech communities
   - Budget: $800-1200 per language (professional translation with testing)
   - Timeline: 2-4 weeks per language

2. **Alternative (Community)**: Post i18n issues to:
   - Persian: GitHub Issues (tag `translation`, `i18n`)
   - Hebrew: Open source communities in Israel
   - Urdu: Pakistani tech communities, universities

3. **Testing**: Once translations arrive:
   - Add keys to `fa.json`, `he.json`, `ur.json`
   - Run `npm run test:unit` (i18n tests)
   - Run `npm run lint` (JSON syntax check)
   - Test in-app at `/settings` language selector
   - Validate RTL rendering, number formats, button overflow

4. **Integration**: Create PRs for each language, review with native speakers, merge to `Dev_new_gui`

## Current Status

This guide documents the translation gap as of 2026-04-12. The feature is fully functional with English fallbacks in place (from PR #4224). Translation is a polish enhancement — not blocking user functionality.

See GitHub Issue #4225 for coordination and updates.
