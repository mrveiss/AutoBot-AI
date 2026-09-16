# Source Analysis: Self-Hosted NAS/Homelab OS with an App Marketplace

## What It Is

The reference work is a standalone Linux-based operating system built for
home-server and small-business NAS hardware (compact single-board devices and
generic x86-64 boxes). It evolved out of an earlier open-source "personal
cloud" layer from the same vendor — that predecessor ran as a Docker-management
UI on top of any existing Linux distro, while the reference work is now a full
installable OS image in its own right (own installer, storage/RAID stack,
update mechanism). It ships a curated "App Store" of 800+ one-click,
Dockerized self-hosted apps, has passed 1M+ downloads, and is under active
development (its most recent point release added a rebuilt "App Store 2.0").
Maturity: production-grade for home/SMB self-hosting, actively maintained,
sizeable community app catalog, still primarily single-node (no clustering).

## Architecture & Key Patterns

- **OS layer**: full Linux distro image, x86-64 only for the OS itself (ARM
  support is mentioned as a target for select installers, not the primary
  path); requires glibc 2.28+; ships its own storage/RAID/SMB stack.
- **App layer**: every installable app is plain **Docker Compose**. The OS
  contributes no app-runtime abstraction beyond Compose itself — apps are
  ordinary multi-container `docker-compose.yml` stacks.
- **Store-specific metadata is a Compose extension field** (`x-casaos:`), not
  a separate manifest format. Compose stays 100% standard; the OS reads one
  additional top-level block to render the store listing and installer UI.
- **Store distribution is static-file, not a package registry**: a "store" is
  just a `store-config.json` + `supported-languages.json` + `Apps/<name>/` tree,
  compiled by a build pipeline into a `dist/` of localized JSON indexes and
  per-app asset folders. The OS's app-store client fetches that static tree
  over HTTP — there is no server-side registry API to integrate with.
- **Multiple stores can be registered on one instance.** The built-in store is
  just the default; users can add additional store URLs (official or
  third-party) through the UI or a documented REST endpoint
  (`POST /v3/app_store/repo`), and the OS merges their catalogs in the same
  browse UI.
- **CI-gated submission for the official/curated store**: PRs against the
  official store repo run a GitHub Actions pipeline that validates Compose
  syntax, the presence of required `x-casaos` fields (`id`, categories, etc.),
  and a full store build — broken submissions fail CI rather than reaching
  users.

## Notable Implementation Details

- **Dynamic port allocation via a magic env var**: apps declare
  `"${WEBUI_PORT:-<default>}"` and the platform substitutes a free host port
  at install time instead of every app fighting over fixed ports.
- **One designated "main" service per stack**: `x-casaos.main` names which
  Compose service is the browser-facing entry point; `index` + `port_map`
  complete the URL the dashboard links to. Multi-service stacks (app + DB +
  cache) are fully supported — only one service needs the UI-facing metadata.
- **Locale-keyed metadata fields** (`title`, `tagline`, `description`,
  `tips`, `release_notes` are all `{locale: string}` objects, `en_US`
  mandatory) so one Compose file drives a localized store listing without a
  separate i18n system.
- **A fixed nine-category taxonomy** (Media, Productivity, Home, Networking,
  **AI**, Finance, Social, Developer, Others) — notably, "AI" is already a
  first-class store category, not something that would need to be added.
- **Host-service and GPU escape hatches are documented patterns, not core
  features**: reaching the host network needs
  `extra_hosts: ["host.docker.internal:host-gateway"]`; GPU passthrough needs
  `runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES` env vars set manually in the
  Compose file. The docs explicitly flag that flexible device assignment
  (e.g. arbitrary accelerator passthrough) is a current platform gap adaptors
  have to work around by hand.
- **The official store's import protocol changed recently** (a fixed "v2"
  `store.json`/`index.json` static format replaced an older GitHub-zip-archive
  import method) — an observed third-party store had to migrate off the zip
  method because that path is now closed for *new* sources. This shows the
  add-a-store mechanism is still evolving and not fully stable across
  versions.

## Strengths

- Zero-friction distribution: a third-party developer can stand up their own
  store (a handful of static JSON files on GitHub Pages) and any user adds it
  by pasting one URL — no approval gate, no waiting on the maintainers.
  Reaching users does not require going through the curated store at all.
- The packaging format is Compose plus one metadata block — nothing
  proprietary to learn, and an app that is already Docker-Composable is
  "trivial" difficulty per the platform's own adaptation-difficulty rubric.
- CI validation on the official store catches broken submissions before they
  ship, which keeps the curated catalog's baseline quality high.
- "AI" is an established first-class category, suggesting AI/agent tooling is
  an expected and normal submission type for this audience, not a novelty.

## Weaknesses / Limitations

- Single-node only — no clustering/HA story; a store app is exactly as
  available as the one box it's installed on.
- No first-class abstraction for GPU/accelerator device assignment; anything
  beyond basic Nvidia GPU passthrough is manual Compose surgery with no
  platform-level guarantee it keeps working across OS updates.
- The add-a-store/import mechanism has already broken backward compatibility
  once (zip import retired in favor of the v2 static-JSON protocol) — a
  distribution channel built against today's mechanism carries real
  drift risk.
- The curated store's review is community/maintainer PR review — capacity-
  gated, informal, no documented SLA.
- Runtime is Docker-only: nothing that needs a non-containerized host process,
  a kernel module, or capabilities Docker itself can't grant will fit,
  regardless of which store carries it.

## Visible vs Hidden Metrics

- **Visible:** 800+ apps in the curated store, 1M+ downloads of the OS itself,
  a freshly rebuilt "App Store 2.0" UI (all vendor-reported; no independent
  figures found for actual active-install counts or per-app usage).
- **Hidden:** the real cost of appearing in the *curated* store is an
  indefinite wait on a community PR-review queue with no SLA, plus ongoing
  maintenance to keep Compose/`x-casaos` metadata compliant across store-schema
  revisions (the zip→v2 migration already forced at least one third-party
  store to rebuild its whole pipeline). The real cost of the *self-hosted
  third-party store* path is much lower per app — no review queue — but pushes
  discovery entirely onto the app owner (no listing in the default catalog,
  users must be told to paste a URL) and the format is documented as actively
  evolving, so it can require re-work on short notice.
- **Weighing:** for a project that just wants *a* reachable path onto this
  platform, the hidden discovery cost of a self-hosted store is a perfectly
  acceptable trade against the hidden review-latency cost of the curated
  store's PR queue — the two paths aren't mutually exclusive, and starting
  with a self-hosted store while a curated-store PR is separately in flight
  captures both the flooring for "day one" and the long-term default-catalog visibility.

**Verdict:** the bottom-line conclusion — this platform's app-distribution
model has no gate that would block a Docker-Composable project from reaching
its users; the only real question is whether the project's runtime needs fit
what Compose + the platform's documented escape hatches can express. Confidence: high on the mechanism (multiple official docs plus an
observed working third-party store cross-confirm it); no independent
data on how much real user traffic that reach actually delivers.

## AutoBot Comparison: the reference NAS platform → AutoBot

### Already-exists audit

Read directly: [docker-compose.yml](../../docker-compose.yml) (840 lines, 12
services + 3 optional-profile services), [docker/backend/Dockerfile](../../docker/backend/Dockerfile),
[docker/frontend/Dockerfile](../../docker/frontend/Dockerfile),
[docker/slm/Dockerfile](../../docker/slm/Dockerfile),
[.github/workflows/image-sign.yml](../../.github/workflows/image-sign.yml).
Greps run: `devices:|privileged` and `npu|openvino|/dev/accel` across
`docker/` and the compose files (zero hits — confirmed, not assumed);
`ghcr.io|ARM|platforms:` across `.github/workflows/`; `COPY` in each
Dockerfile; `git ls-files` on the three repo-relative files the compose
bind-mounts (`docker/.env.docker`, `docker/with-secrets.sh`,
`docker/secrets-init.sh` — all three are committed, non-secret defaults).
Searched `docs/` and root `*.md` for prior art (`casaos|zimaos|unraid|truenas|
portainer stack`) — only this file has ever mentioned it; this is new ground.

### What We Already Do Better / Already Have

- **Pre-built, signed, published images already exist.** `image-sign.yml`
  builds `autobot-backend`, `autobot-slm`, `autobot-frontend` from the exact
  same three Dockerfiles the compose file uses, pushes them to
  `ghcr.io/mrveiss/autobot-{backend,slm,frontend}:<tag>` on every `v*` release
  tag, and cosign-signs each digest. `autobot-worker` and
  `autobot-celery-beat` reuse the backend image (different command/entrypoint
  override), so **the entire stack needs exactly 3 published images**, and 2
  of the 3 already ship. This is most of the work a from-scratch adoption
  would need to do — it's already done for an unrelated reason (supply-chain
  signing, #6597).
- **No NPU/accelerator coupling in the containerized path at all.** Grepped
  clean: zero `devices:`, zero `privileged:`, zero NPU/OpenVINO references
  anywhere under `docker/`. `AUTOBOT_AI_STACK_ENABLED` defaults to `false`,
  and the "AI Stack" is a documented separate fleet node
  ([AUTOBOT_REFERENCE.md](../developer/AUTOBOT_REFERENCE.md)), not something
  `docker compose up` ever touches. The reference platform's own docs flag
  device/accelerator passthrough as a rough, manual, per-app edge case — but
  AutoBot's core stack simply never needs that edge case in the first place.
  A NAS-store deployment target only ever exercises the plain-CPU path.
- **The frontend image is already self-sufficient.** `docker/frontend/Dockerfile`
  already `COPY`s `nginx.conf`, `nginx-common.conf`, and `nginx-locations.conf`
  into the image at build time (lines 108-110). The compose file's bind-mounts
  of those same paths are a dev-time override convenience, not a hard
  dependency — the frontend container already boots correctly with nothing
  bind-mounted.
- **Architecture matches for free.** The reference platform's primary/native
  target is x86-64 (its own hardware line plus generic PCs); AutoBot's images
  build on `python:*-slim-bookworm` / `node:20-bookworm-slim` /
  `ubuntu:22.04`, and `image-sign.yml` runs on `ubuntu-latest` with no
  `platforms:` matrix — i.e. already amd64-only, already matching the
  platform's primary architecture. Nothing to change here.

### What We Can Adopt

**1. A distribution-flavored compose file that references published images instead of `build:`.**
- Applies to: a new `docker-compose.zimaos.yml` (or a `docker-compose.override.dist.yml`
  layered on the base file) alongside the existing [docker-compose.yml](../../docker-compose.yml).
- Gap confirmed by the audit above: every one of the 5 custom services
  (`autobot-backend`, `autobot-worker`, `autobot-celery-beat`, `autobot-slm`,
  `autobot-frontend`) currently declares `build: context: . / dockerfile: ...`
  — a NAS app-store distribution never has the AutoBot git checkout on disk,
  so `build:` cannot resolve. Swapping to
  `image: ghcr.io/mrveiss/autobot-backend:${AUTOBOT_VERSION:-latest}` (etc.,
  reusing the same tags `image-sign.yml` already produces) is the fix.
- Visible benefit: unlocks every distribution path (curated store,
  self-hosted store, or just "paste this compose file") at once, not just
  ZimaOS specifically — any Docker-Compose-consuming platform.
  Hidden cost: a second compose file to keep in sync with the first every
  time a service, port, or env var changes; some drift risk unless a CI
  check diffs the two (mirrors the existing `docker-compose.hardened.yml`
  maintenance burden, which is a known, accepted pattern here already).
- Verdict: **adopt**. Effort: **moderate** (new file + a CI parity check;
  no image changes needed for 2 of the 3 images).

**2. Bake the two helper scripts into the images instead of bind-mounting them from the repo.**
- Applies to: [docker/backend/Dockerfile](../../docker/backend/Dockerfile) (add
  `COPY docker/with-secrets.sh /usr/local/bin/with-secrets.sh` and reuse for
  the `autobot-slm` image), and the `autobot-secrets-init` service definition
  (currently `alpine:3.20` + a bind-mounted `docker/secrets-init.sh`).
- Gap confirmed by audit: `with-secrets.sh` and `secrets-init.sh` are both
  git-tracked, non-secret, but are wired in purely via
  `./docker/<script>:/path:ro` bind mounts (docker-compose.yml lines 192,
  222, 373, 562) — neither is `COPY`'d into any image. Same issue for
  `docker/postgres/init-databases.sql` (line 90) and the default
  `docker/nginx/nginx.conf` path override variable (already solved for the
  *built-in* default per point above, but the override mechanism itself is
  still bind-mount-only). None of these resolve without the repo checked out.
- Visible benefit: the distribution compose file becomes fully
  self-contained — no repo checkout required anywhere in the path, which is
  the actual requirement for a NAS app-store listing (the store ships a
  compose file, nothing else). Hidden cost: two ~2-3KB shell scripts move
  from "edit in place, no rebuild" to "edit requires an image rebuild" for
  anyone doing local dev on them — small, since they change rarely (both
  predate the last several dozen commits touching the compose file).
- Verdict: **adopt**. Effort: **trivial** (three `COPY` lines + a
  custom tiny image for `autobot-secrets-init` instead of bare `alpine`, or
  fold that init logic into the backend entrypoint and drop the service).

**3. Publish `autobot-worker` and `autobot-celery-beat` under their own image tags (or just document the reuse).**
- Applies to: [.github/workflows/image-sign.yml](../../.github/workflows/image-sign.yml)
  — no code change needed, since both already run the same
  `autobot-backend` image with a different `command:`/`entrypoint:`.
- Gap confirmed by audit: nothing missing here — flagged only so a
  distribution compose file's authors don't mistakenly assume a 5th and 6th
  image need building. Already-exists, moved out of "gaps."
- Verdict: **already have it** — no action.

### Gaps & Opportunities

- **Registry/store submission itself is unstarted**: no `x-casaos` metadata
  block exists anywhere in the repo, and no store repository (curated PR or
  self-hosted `store.json`) has been created. This is pure net-new packaging
  work, not a codebase gap — see file list below.
- **Resource footprint is home-NAS-heavy.** Summing the core (non-optional)
  services' `deploy.resources.limits.memory`: redis 1G + postgres 1G +
  chromadb 1G + backend 2G + worker 2G + celery-beat 512M + slm 1G + frontend
  512M ≈ **9GB RAM minimum**, before the optional `ollama` profile's 8G. That
  fits the higher-end hardware this platform's own vendor sells (their
  higher-RAM boards/cube units) but would be a rough fit on a low-end 4-8GB
  box — worth a plain "minimum 16GB RAM recommended" note in any store
  listing rather than a code change.
- **The `autobot-mgmt` network hardcodes `subnet: 172.30.0.0/24`**
  ([docker-compose.yml:837-839](../../docker-compose.yml#L837)) with no env
  override. Low risk (an unusual-enough private range), but on a shared
  multi-app NAS host running many Compose stacks side by side, a fixed
  subnet is the one thing that can produce a hard Docker network-creation
  conflict with some other app's stack. Parameterizing it
  (`${AUTOBOT_MGMT_SUBNET:-172.30.0.0/24}`) is a one-line, low-cost
  hardening move independent of any NAS-store ambition.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `docker-compose.zimaos.yml` (new) | Distribution-flavored compose: `image:` instead of `build:` for all 5 custom services, reusing `ghcr.io/mrveiss/autobot-*` tags |
| `docker/backend/Dockerfile` | `COPY docker/with-secrets.sh /usr/local/bin/with-secrets.sh`; same for the SLM image if it uses a separate Dockerfile stage |
| `docker/secrets-init.sh` handling | Either a tiny purpose-built image (`COPY` the script in) or fold into the backend entrypoint and drop the standalone service |
| `docker-compose.yml` | Parameterize the `autobot-mgmt` subnet via an env var with the current value as default |
| `Apps/AutoBot/docker-compose.yml` + `icon.svg`/`thumbnail.png` (new, in a *separate* store repo) | The actual `x-casaos` submission artifact — `main: autobot-frontend`, `port_map` from `WEBUI_PORT`, `category: AI`, `architectures: [amd64]` |
| New static store repo (`store-config.json` + `supported-languages.json` + `Apps/`) — self-hosted path | Lowest-friction reach: publish via GitHub Pages, no PR-review wait, addable by any ZimaOS user pasting the URL |

**Bottom line:** yes, technically reachable — most of the hard part (signed,
published, correctly-architected images) already exists for an unrelated
reason. What's missing is packaging, not capability: a `build:`→`image:`
distribution compose variant, baking two small scripts into images instead
of bind-mounting them from a repo checkout, and the `x-casaos` metadata
submission itself. Effort for the codebase-side prerequisites: **moderate**
overall (mostly the two adopt items above); the store submission afterward is
pure packaging/writing, not engineering.

### Generalization: this is a class of platforms, not one

A second, larger self-hosted NAS/homelab OS independently arrived at the same
underlying model: after previously running app installs on a Kubernetes
layer, its current release line rebuilt its app runtime on **plain Docker
Compose** — a curated GitHub-hosted catalog organized into "trains," plus a
no-catalog path where a user pastes any Compose YAML directly into an
"install via YAML" screen and the platform handles orchestration, health
checks, and log access itself. That no-catalog path has no PR-review gate at
all — it is strictly lower-friction than either path on the first platform
analyzed above.

This means the two codebase-side prerequisites (a build-free, image-only
compose variant; no bind-mounted config from a repo checkout) are not
single-platform work — they are the generic precondition for *any*
Compose-consuming NAS/homelab platform. The curated-catalog metadata format
differs per platform (this platform's exact metadata-block equivalent to the
first platform's `x-casaos` needs its own field-level research at submission
time — not assumed to match), but the "install via pasted Compose YAML with
zero review" path is already usable today, on both platforms, the moment the
compose variant exists.

