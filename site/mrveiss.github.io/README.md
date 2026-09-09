# Root site — `mrveiss.github.io`

Source of truth for the landing page served at **https://mrveiss.github.io/**.

## Why it lives here and deploys elsewhere

GitHub Pages serves the **user root** only from a repository literally named
`mrveiss.github.io`. A project repository always serves under its own path — which is
why AutoBot's site is at `/AutoBot-AI/` and why the root was a 404 until this page
existed.

So the page is authored here, where it gets review and CI like anything else, and the
`mrveiss.github.io` repository holds a copy of `index.html` and nothing else.

## What actually deploys

**Deployed** — these must be byte-identical in both places:

```
index.html      the landing page
_config.yml     Jekyll config; the theme, and the exclude that keeps README unpublished
robots.txt      crawler policy, including named AI agents
llms.txt        llmstxt.org summary for agents
```

**Not deployed** — `README.md`. The two repositories' READMEs are *deliberately
different*: this one is the deploy contract for people working in AutoBot-AI, and
the one in `mrveiss.github.io` is that repository's public front page. A checker
comparing the two would report a difference that is not a defect, so it must
compare the deployed set above and nothing else.

## Deploying a change

1. Edit `index.html` here, in a PR.
2. After it merges, copy the file into the `mrveiss.github.io` repository root.

The copy is deliberate rather than automated: the root site is the first thing a
visitor sees, and a push that reaches it without a human reading the diff is a worse
failure than a page that is a few minutes stale.

## Design

Palette, type scale and theming are taken from `docs/index.html` so the root and the
AutoBot site read as one property — the same orange/wax/plum tokens, Fraunces for
display, Schibsted Grotesk for body, JetBrains Mono for commands, and the same
three-state theme handling (explicit light, explicit dark, and the unstamped default
that follows `prefers-color-scheme`).
