# Ratchet Baselines

> **Tracking:** [#15897](https://github.com/mrveiss/AutoBot-AI/issues/15897)

A ratchet freezes a baseline that its own detector produced. At the moment of
freezing, that baseline cannot distinguish **"the tree contains N instances"**
from **"the detector can see N instances"** — and nothing in the pattern ever
forces the difference to surface.

Five baselines were re-derived by implementations sharing neither enumeration nor
matching with their detectors. **Four had a boundary a reader cannot see. The one
that passes is the one that declares and guards it.**

## What goes wrong

Whatever the detector is blind to becomes permanently exempt **without appearing
in the baseline** — the list whose entire purpose is to record exemptions. An
exemption you can read is a decision. An exemption caused by a blind spot is
invisible, and the ratchet reports clean forever.

There are two independent directions, and only one of them is checkable with the
detector alone. That is why only one of them ever gets built:

| Direction | Question | Checkable by the detector? |
|---|---|---|
| **Staleness** | Does every baseline entry still match something? | Yes — hence `--audit-baseline`, and #15896's `test_the_baseline_still_describes_real_citations` |
| **Blindness** | Does the detector's population equal the tree's? | **No, by definition** — a census performed by the instrument inherits the instrument's blind spot |

## The rules

### 1. State the boundary where a reader meets the baseline

Every guard is scoped, and a narrow scope is not the defect. **An undeclared
scope is.** A file type never opened is indistinguishable, in the baseline, from
one opened and found clean.

Write the boundary into the baseline file or the detector's docstring, in the
place someone lands when they read the number.

### 2. A test must fail when the boundary moves

A stated boundary that drifts silently is a stale comment. `check_python_file_size.py`
declares `EXCLUDED_PREFIXES` **and** pins it with
`test_excluded_prefixes_mirror_the_pre_commit_config`, which fails if the audit's
scope and the hook's `exclude:` diverge. That pairing is what makes the exclusion
a decision rather than an accident.

### 3. Derive the population a second way before freezing it

Once, at freeze time, and again whenever the matcher changes — not a permanently
maintained second implementation. A change to *what the detector matches*
invalidates the cross-check; a change to formatting or messaging does not.

Do **not** build a shared harness for this. A generic harness reintroduces the
shared implementation this whole page is about. The second derivation has to be
ad hoc by construction; independence is the property doing the work.

### 4. Compare sets, not counts

Two implementations can agree on a total and disagree on membership. #15896's
cross-check compared the sets and found the symmetric difference empty — that is
the assertion worth making, not `26 = 26`.

### 5. The second implementation must replicate the *predicate*, exemptions included

This is the rule most likely to catch whoever follows this page, because it was
found by hitting it.

A re-derivation of the commit-trailer gate first reported **3,444** and **8,010**
violations. Both were wrong: the log had been flattened with `tr -d '\n'` before
matching, destroying the `^[[:space:]]*` anchoring the gate's regexes depend on,
and neither the owner nor the bot exemption had been applied. The numbers were
large, plausible, and nearly published.

**A re-derivation that drops the original's anchoring or exemptions is not
measuring the same predicate.** It answers a looser question and reports the
answer as though it were the same one.

The predicate is the pattern **and its invocation**, not the pattern alone. A
second re-derivation of this same gate read `coauthor_re='^[[:space:]]*Co-authored-by:'`
as case-sensitive and reported **2,426** against the correct 7,087. The `-i` is
on the `grep` seventy lines below the assignment
(`.github/workflows/no-commit-trailers.yml:165`), and the trailer's dominant
spelling in history is `Co-Authored-By:` — 7,373 against 5,033 — so dropping the
flag silently discards the majority case. The wrong number was reached twice, by
two readers, from the same true regex.

### 6. Give the re-derivation its own non-vacuity floor

The instrument checking the instrument is an instrument. A re-derivation of the
file-size ratchet first reported **497 over-limit files with no baseline entry** —
a catastrophic-looking finding produced by parsing `KNOWN_LARGE` as an
`ast.Assign` when it is annotated and therefore an `ast.AnnAssign`. The parse
returned zero entries, so every file read as missing.

The tell was the number: 497 missing and 497 over-limit are the same number,
which is what comparing against an empty set looks like. A floor asserting the
baseline parsed to more than zero entries would have caught it before the result
was ever read.

## Worked example — the one that passes

`repo_tests/python_file_size_ratchet_baseline.py`, measured against
`origin/Dev_new_gui`:

| | |
|---|---|
| tracked `.py` | 5,574 |
| in the walk's declared scope | 5,244 |
| in scope and over `MAX_LINES` (600) | **497** |
| `KNOWN_LARGE` entries | **497** |
| over the limit with no entry | **0** |
| entries whose file is now compliant | **0** |

Exact congruence in both directions — the only one of the five satisfying
staleness *and* blindness.

It is not luck. The blindness was here, was severe, and was found:
`scripts/check_python_file_size.py:34-40` records that `audit_ceilings` used to
iterate `KNOWN_LARGE.items()`, so it *"could re-verify a file someone remembered
to list, never discover one nobody did"* — and a repo-wide walk then found **509
files already over the limit with no entry at all**. `reconciler.py` surfaced it
at over 2,000 lines, absent from the list entirely.

47 `.py` files over the limit still sit outside the walk. That is **not**
blindness, and the difference is the whole point: the exclusion is declared
(`EXCLUDED_PREFIXES`), justified (it mirrors the hook's own `exclude:`), and
guarded (a test fails if the two drift). A reader can discover the boundary by
reading it, and the boundary cannot move silently.

## Worked example — the shape of the failure

**#15896, citation guard: baseline 8, true population 26.**

The scan matched lines starting with `#`, or — for Python — lines *containing* a
triple quote. That matches the line opening or closing a docstring, never a line
*inside* one, and in this codebase the citations live in docstring bodies. Across
246 `repo_tests/*.py` there were 35 occurrences; the filter saw 4.

The PR's justification for its rule was *"it costs nothing, because the form is
already rare — 8 instances in 464 files."* **That 8 was produced by the same
filter**, so it counted what the filter could see. Freezing it would have made 18
citations permanently exempt with no record that they existed.

It was caught by deriving the population a second way — `git ls-tree` enumeration
instead of `Path.glob`, `tokenize.STRING` tokens instead of AST docstring spans —
and comparing the sets. Both implementations now agree at 26 with an empty
symmetric difference.

## Evidence across the five

| Ratchet | Boundary | Declared? | Guarded? | Baseline vs population |
|---|---|---|---|---|
| file-size | `EXCLUDED_PREFIXES` | yes | yes | **497 vs 497** |
| citations (#15896) | docstring bodies unreadable by the filter | no | no | 8 vs 26 |
| commit-trailer | history unexamined; only PR ranges | no | no | 4 vs 7,087 |
| `inline_generics` | counter matches inside comments (#15771) | no | no | 577 vs 573 |
| hardcoded-values | `HV_SCAN_EXTENSIONS`; systemd units unreachable (#15903) | partly | no | congruent by construction |

### Why commit-trailer is the clearest case

Its remedy is *nothing*. The gate is correct — `pull_request`, `rev-list
BASE..HEAD`, forward-only — and the alternative, rewriting 12,786 commits, is
worse than the problem. The 7,083 unbaselined violations are not outstanding
work.

The defect is entirely in what the number **4** communicates. Under a header
reading *"a RATCHET, not an allowlist… entries may only be REMOVED"*, a reader
takes four outstanding violations in a nearly-clean tree. It is four gate events.
The fix is one paragraph saying what the count is a count of.

That case separates **"the boundary is invisible"** from **"the code is wrong"**
more cleanly than any of the others, and it is why rule 1 is about disclosure
rather than coverage.

## Checklist for a new ratchet

- [ ] The population boundary is stated where a reader meets the baseline
- [ ] A test fails when that boundary moves
- [ ] The population was derived a second way before freezing, sharing neither enumeration nor matching
- [ ] That comparison was over **sets**, not counts
- [ ] The second derivation replicated the predicate — anchoring, exemptions, and all
- [ ] Both the detector and the re-derivation have non-vacuity floors bound to *what was examined*, never to *what was found*
