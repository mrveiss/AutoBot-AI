# AutoBot Release System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automated SemVer releases on merge to main using git-cliff for changelog generation and version bumping.

**Architecture:** git-cliff analyzes conventional commits since last tag, determines bump type (feat=minor, fix=patch, BREAKING=major), generates changelog, creates git tag + GitHub Release. Single-step — no intermediate Release PR.

**Tech Stack:** git-cliff (Rust binary), GitHub Actions, orhun/git-cliff-action@v4, softprops/action-gh-release@v2

**Issue:** #1296

---

## Design Reference

| Decision | Choice |
|----------|--------|
| Versioning | SemVer (semver.org) |
| Starting version | v0.1.0 (alpha stage) |
| Trigger | Push to main |
| Artifacts | Git tag + auto-changelog + GitHub Release |
| Changelog source | Auto-generated from conventional commits |
| Bump logic | Commit-based (feat=minor, fix=patch, BREAKING=major) |
| Tool | git-cliff via orhun/git-cliff-action@v4 |

---

### Task 1: Create cliff.toml configuration

**Files:**
- Create: `cliff.toml`

**Step 1: Create the git-cliff configuration file**

```toml
[remote.github]
owner = "mrveiss"
repo = "AutoBot-AI"

[changelog]
header = """
# Changelog\n
All notable changes to this project will be documented in this file.\n
"""
body = """
{%- macro remote_url() -%}
  https://github.com/{{ remote.github.owner }}/{{ remote.github.repo }}
{%- endmacro -%}

{% if version -%}
    ## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
{% else -%}
    ## [Unreleased]
{% endif -%}

{% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | striptags | trim | upper_first }}
    {% for commit in commits %}
        - {% if commit.scope %}*({{ commit.scope }})* {% endif %}\
          {{ commit.message | split(pat="\n") | first | upper_first | trim }}\
          {% if commit.remote.pr_number %} \
            ([#{{ commit.remote.pr_number }}]({{ self::remote_url() }}/pull/{{ commit.remote.pr_number }}))\
          {% endif %}
    {% endfor %}
{% endfor %}

"""
footer = ""
trim = true

[git]
conventional_commits = true
filter_unconventional = true
split_commits = false
commit_preprocessors = [
    { pattern = '\\(#(\\d+)\\)', replace = "" },
]
commit_parsers = [
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    { message = "^refactor", group = "Refactoring" },
    { message = "^perf", group = "Performance" },
    { message = "^doc", group = "Documentation" },
    { message = "^ci", group = "CI/CD" },
    { message = "^chore", group = "Miscellaneous" },
    { message = "^style", group = "Styling" },
    { message = "^test", group = "Testing" },
    { message = "^revert", group = "Reverted" },
]
protect_breaking_commits = false
filter_commits = false
tag_pattern = "v[0-9].*"
topo_order = false
sort_commits = "newest"

[bump]
features_always_bump_minor = true
breaking_always_bump_major = true
initial_tag = "0.1.0"
```

**Step 2: Verify the file was created**

Run: `head -5 cliff.toml`
Expected: Shows `[remote.github]` header

**Step 3: Commit**

```bash
git add cliff.toml
git commit -m "ci(release): add git-cliff configuration (#1296)"
```

---

### Task 2: Create release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Step 1: Create the GitHub Actions release workflow**

```yaml
# AutoBot Release Workflow
# Automatically creates releases on merge to main using git-cliff
# Analyzes conventional commits to determine version bump and generate changelog
#
# Issue: #1296

name: Release

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  release:
    runs-on: self-hosted
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Determine next version
        id: version
        uses: orhun/git-cliff-action@v4
        with:
          config: cliff.toml
          args: --bumped-version
        env:
          GITHUB_REPO: ${{ github.repository }}

      - name: Check if release needed
        id: check
        run: |
          NEXT_VERSION="${{ steps.version.outputs.version }}"
          if [ -z "$NEXT_VERSION" ]; then
            echo "No version bump needed (no conventional commits since last tag)"
            echo "release_needed=false" >> $GITHUB_OUTPUT
          else
            echo "Next version: $NEXT_VERSION"
            echo "release_needed=true" >> $GITHUB_OUTPUT
            echo "version=$NEXT_VERSION" >> $GITHUB_OUTPUT
          fi

      - name: Generate release notes
        if: steps.check.outputs.release_needed == 'true'
        id: changelog
        uses: orhun/git-cliff-action@v4
        with:
          config: cliff.toml
          args: --latest --strip header
        env:
          OUTPUT: RELEASE_NOTES.md
          GITHUB_REPO: ${{ github.repository }}

      - name: Update CHANGELOG.md
        if: steps.check.outputs.release_needed == 'true'
        uses: orhun/git-cliff-action@v4
        with:
          config: cliff.toml
          args: --verbose
        env:
          OUTPUT: CHANGELOG.md
          GITHUB_REPO: ${{ github.repository }}

      - name: Commit changelog and tag
        if: steps.check.outputs.release_needed == 'true'
        run: |
          VERSION="${{ steps.check.outputs.version }}"
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add CHANGELOG.md
          git diff --staged --quiet && echo "No changelog changes" || \
            git commit -m "chore(release): update changelog for ${VERSION}"
          git tag -a "${VERSION}" -m "Release ${VERSION}"
          git push origin main --follow-tags

      - name: Create GitHub Release
        if: steps.check.outputs.release_needed == 'true'
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.check.outputs.version }}
          name: ${{ steps.check.outputs.version }}
          body_path: RELEASE_NOTES.md
          prerelease: true
          generate_release_notes: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Notes:
- `prerelease: true` — change to `false` when reaching v1.0.0
- `--latest --strip header` — release notes contain only the latest version's changes
- `self-hosted` runner matches existing CI workflows
- Skips release if no conventional commits found since last tag

**Step 2: Verify**

Run: `head -5 .github/workflows/release.yml`
Expected: Shows workflow header comment

**Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): add automated release workflow (#1296)"
```

---

### Task 3: Install git-cliff locally and dry-run test

**Files:** None (verification only)

**Step 1: Install git-cliff**

```bash
# Download pre-built binary (check latest version at https://github.com/orhun/git-cliff/releases/latest)
curl -sSfL https://github.com/orhun/git-cliff/releases/latest/download/git-cliff-2.7.0-x86_64-unknown-linux-gnu.tar.gz | tar xz
sudo mv git-cliff-2.7.0/git-cliff /usr/local/bin/
rm -rf git-cliff-2.7.0
git-cliff --version
```

Expected: `git-cliff 2.7.0` (or latest)

**Step 2: Test changelog generation (dry run)**

```bash
git cliff --bump --unreleased | head -40
```

Expected: Commits grouped under Features, Bug Fixes, Refactoring, etc.

**Step 3: Test version bump detection**

```bash
git cliff --bumped-version
```

Expected: A version string like `0.2.0` based on commits

**Step 4: Verify commit type mapping**

Spot-check that:
- `feat(monitoring): ...` appears under Features section
- `fix(ci): ...` appears under Bug Fixes section
- `refactor(cache): ...` appears under Refactoring section

---

### Task 4: Create initial v0.1.0 tag on main

**Files:** None (git operation)

This task must happen AFTER Tasks 1-2 are merged to main.

**Step 1: Verify main state**

```bash
git log --oneline origin/main -5
```

**Step 2: Tag current main HEAD**

```bash
git tag -a v0.1.0 origin/main -m "Initial alpha release - AutoBot v0.1.0"
git push origin v0.1.0
```

**Step 3: Create initial GitHub Release**

```bash
gh release create v0.1.0 --title "v0.1.0" --notes "Initial alpha release of AutoBot." --prerelease
```

**Step 4: Verify**

```bash
git tag -l "v*"
gh release view v0.1.0
```

Expected: Tag exists, release visible on GitHub

---

### Task 5: Replace manual CHANGELOG.md with generated version

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Generate full changelog from git history**

```bash
git cliff -o CHANGELOG.md
```

**Step 2: Review**

```bash
head -40 CHANGELOG.md
```

Expected: Proper Keep a Changelog format with grouped sections

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore(release): replace manual changelog with git-cliff generated version (#1296)"
```
