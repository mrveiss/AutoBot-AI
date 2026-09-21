# Social preview cards

The Open Graph images GitHub serves when a link to one of the skills marketplaces is
pasted into Slack, X, LinkedIn or a chat. Without one, a repository link renders as a
grey block with the repo name — which is what both of these did until now, while being
linked from the public root landing page.

| File | Repository |
|---|---|
| `claude-dev-skills-card.png` | [Claude-Dev-Skills](https://github.com/mrveiss/Claude-Dev-Skills) |
| `autobot-dev-skills-card.png` | [AutoBot-AI-Claude-dev-skills](https://github.com/mrveiss/AutoBot-AI-Claude-dev-skills) |

Both are 1280×640, the size GitHub recommends, and well under the 1 MB limit.

## Why they are uploaded by hand

**A social preview is a repository setting, not a file GitHub reads from the tree**, and
there is no REST or GraphQL endpoint for it. Committing a PNG to a repository does
nothing on its own. So the cards are authored here, where they get review and version
history, and uploaded once through the web UI — the same author-here / deploy-elsewhere
split used for the root landing page in `site/mrveiss.github.io/`.

### Uploading

For each repository:

1. **Settings → General → Social preview → Edit → Upload an image**
2. Choose the matching file from the table above.

It takes effect immediately. Link previews are cached by each platform, so an already
posted link may keep showing the old grey block for a while — that is the cache, not a
failed upload. Verify with a freshly pasted link.

## Regenerating

`make_cards.py` renders both cards and needs three fonts it does not vendor. Fetch them
into `fonts/` under these exact names:

| Save as | Family (Google Fonts) |
|---|---|
| `fonts/Fraunces.ttf` | Fraunces, `opsz,wght@144,600` |
| `fonts/Schibsted.ttf` | Schibsted Grotesk, `wght@500` |
| `fonts/JetBrainsMono.ttf` | JetBrains Mono, `wght@400` |

Then:

```
python3 make_cards.py --fonts ./fonts --out .
```

The script makes no network calls; if a font is missing it fails rather than silently
substituting one, because a substituted face would change the card without changing the
code.

## Design

Palette and type come from `site/mrveiss.github.io/index.html` — plum ground, wax and
cream text, the orange accent, Fraunces for display, Schibsted Grotesk for body,
JetBrains Mono for the install command — so a pasted repository link reads as the same
property as the site.

**The cards carry no counts, no metrics and no badges, deliberately.** A social preview
is a setting nobody revisits; a skill count baked into one becomes false the first time
a skill is added, and these are repositories whose whole subject is working honestly.
The cards name domains instead, which stays true as the sets grow.
