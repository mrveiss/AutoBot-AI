# Measurement discipline — an empty result is not a true negative

> **Tracking:** [#15953](https://github.com/mrveiss/AutoBot-AI/issues/15953)

The same defect has been found here more than twenty times, by five sessions, in
one week. It is never the same code twice, which is why it keeps being filed as
new: **an instrument answers a narrower question than the one it is read as
answering, and the narrow answer is empty.**

Empty reads as *nothing is wrong*. It is also what *nothing was measured* looks
like.

## The law

> **If a query contains a selector — a field name, a path, a glob, an anchor, a
> marker, a prefix, a trigger condition — the sentence reporting its result must
> name that selector.**

A query that answers a narrower question does not fail. It succeeds, returns
nothing, and the nothing is indistinguishable from a true negative.

## Six families, six different remedies

Sorting the instances showed these are not one law. Conflating them produces the
wrong fix.

### A. The query is narrower than its reading

| Instrument | Read as | Actually answered |
|---|---|---|
| `gh pr checks --json bucket` | is this PR green | required contexts only; `python-suite shard 8/12` is not one |
| branch protection's ten contexts | the tests must pass | `python-suite` and its twelve shards are **not required at all** |
| `git log --oneline -3` per branch | how many bot pushes exist | the last three commits — the real count was 8, reported as 0 |
| `git merge-base --is-ancestor` | did this branch land | **NO for every squash merge**, by construction |
| check-runs on a merge commit | did this PR's checks pass | a squash creates a *new* commit that was never tested |
| `gh pr view --json headRefOid` | the head to test | a cached head that can lag the tip `gh pr merge` will land |
| a regex enumerating `ask\|allow\|deny` | find malformed decisions | only well-formed ones — an invalid value was unrepresentable |
| `systemctl show -p ActiveState` | is the unit healthy | `inactive` is also what a unit that does not exist returns |
| a guard matching `openssl req` anywhere in a role | does this role provision the shared keypair | it runs openssl — for a **different** keypair, in the same directory |

**Remedy: name the selector where the result is reported.**

The last row is the sharpest: the instrument answered an **adjacent** question and
returned the good answer. The others saw less than claimed; that one saw
something else, and it looked identical.

### B. Evidence that is a name rather than a behaviour

Nothing is narrowed. Authored prose describing what code does is taken as proof
that it does it.

- An acceptance criterion ticked against `test_the_second_agent_learns_before_editing_not_at_merge`. Read in full, the body used intent `"x"` for the second edit, so nothing expressed *non-overlapping* — and `_, found = await acquire_aware(...)` discarded the half that proves the claim is granted. **An implementation that refused the claim passed it unchanged.**
- A criterion nearly ticked on `grep -cE "class Interest|branch|intent"` returning **66** — word frequency in a 300-line file.
- An acceptance list written from a two-hook symptom while a third hook carried the same defect.

**Remedy: read the behaviour, not the label.**

Worse than A, because a blind instrument is caught when someone re-measures. **A
ticked box and a closed issue are what stop anyone measuring again.**

B is the narrowest and most frequent instance of **F** below — a name is a
correct answer to *what is this called*, read as *what does it do*. It keeps its
own entry because its remedy is sharper than F's: for a test, read the body.

### C. A result produced and consumed by nothing

The check ran, was correct, and reached no decision.

- `unpushed: 6` printed, and the removal ran on the next line regardless.
- Two SHAs printed before a branch deletion, neither compared.
- `git push | tail` returning the pipe's exit status rather than git's.
- A sweep printing `MERGEABLE` beside `shards={'queued': 12}` **on the same line**.

**Remedy: after producing evidence, ask which line of the next action reads it.
If none does, delete the check or wire it in.**

### D. The instrument is right, and its correct output supports two causes

Not narrow at all — exactly as wide as it claims, and still misleading.

A gate reported, correctly, for hours: *"verdict would be about the wrong
commit"*. Read as **waiting for the object to catch up**. It meant **nothing is
coming, ever** — pushes had landed on branches but never registered as
`synchronize` events, so no workflow was ever dispatched. Three branch tips sat
with **zero** check-runs while Actions scheduled normally.

*Wait* and *force a `reopened` event or the work is never tested* are not close
to each other, and nothing in the output distinguished them.

**Remedy: of any true refusal, ask what else produces this output, and whether it
wants the same action.**

A verdict that stops you acting feels safe in a way one telling you to act does
not. A gate saying WAIT is indistinguishable from a healthy queue, so it receives
less scrutiny than one saying MERGE.

### F. The output is correct, complete, and about a different question

Nothing is narrowed and nothing is stale. The instrument answers perfectly — a
question next to the one being asked.

**The discriminator: would more data have changed the answer?** If yes, it is A —
the instrument saw a subset of the truth. If no, it is F, and no amount of
additional data will help, because the output was never about the thing.

- `js-yaml [high] 4.0.0 - 4.3.1` read as *no fix exists*, and an allowance written on it. That line is an exact answer to **which versions are vulnerable**. It answers **which versions exist** not at all — 4.3.1 is the last *affected* release, 4.3.2 was already shipping, and dependabot was already carrying the bump.
- `git cherry` reporting 5, 3 and 2 commits "not in base" for three worktrees whose work had landed. Accurate about patch-id divergence under squash merges; silent about landedness.
- `gh pr list --author @me` returning six sessions' PRs. Every branch here is authored `mrveiss`, so it is a correct answer to *which PRs did this account author*, read as *which PRs are mine*.

**Remedy: name the field's actual question before building on it.**

**A positive control does not catch this one, and that is why it is separate.**
Asserting a known instance is the standard defence against A, and it works because
A's failure is an empty or truncated population. Here the control passes
cheerfully — the instrument is working. A family whose remedy is the negation of
the previous families' remedy has earned its own entry.

Note the direction of all three. *No fix, so allow it. Not landed, so keep the
worktree. These are mine, so take them.* **F's benign reading is the available
one, and it points toward more work or less safety, so nothing pushes back on
it.**

## Three gates, one shape

All three report two distinct states identically:

| gate | conflates |
|---|---|
| branch protection | *suite passed* with *suite never ran* (a `skipped` from a superseded run) |
| the stale-PR-object check | *waiting* with *nothing is coming* |
| same-scope batching | *should have been batched* with *deliberately sequenced on a recorded dependency* |

And a guard can fail in three escalating ways, in order of how hard they are to
notice — all producing the same green:

1. **The guard never ran.** A duplication guard scanned 2 of 5 trees, and the *trigger paths* excluded the other three, so it reported nothing rather than a passing number.
2. **The guard ran and answered an adjacent question.** A drift check enforced byte-identity between a directory and its mirror while nothing checked that every module was actually deployed. Content parity and shipping parity are different claims about the same two directories. A second, from a different domain: a dependency gate fails when an allowance names a finding the scanner *no longer reports* — a real property, verified and written up approvingly, and then read as covering a too-broad allowance. It does not. It fires only when the scanner **stops** reporting a package, so an over-broad allowance on a still-reported one never trips it. **Verifying an adjacent safety property and taking coverage from it is the same rung, not a new one.**
3. **The guard would have answered correctly and was never selected.** Three tests parse one file by path; the pre-push hook ran exactly one. It failed, which is the only reason the break was found. The guard is not defective — it is correct and loud. **The only observable is that it did not run, and "did not run" has no output.**

### E. The constraint was recorded, in-file, and the editor read past it

The families above are about instruments. This one is about reading, and it is
the one that costs most — because every remedy above assumes someone will read
what is written.

`models/database.py` sits at its size ceiling. Extracting an enum out of it hits
a two-step wall: a relative import fails because the migration runner execs the
file **by path**, and the obvious absolute fix fails one import deeper because
`models/__init__.py` pulls in `autobot_shared`, which that runner does not have.

**Both halves were already written down, in the tree, at the edit site:**

```python
# models/database.py:302
# ServiceStatus moved to top-level service_status.py (#16019) -- this file is
# AT its ceiling, and models/ would drag in autobot_shared. See that docstring.
```

and `service_status.py`'s docstring names the failing check by name. The wall was
hit twice in two months, in the same file, by two sessions — **and the comment
was already there both times.** The second author inserted an import twenty lines
away, using a script that spliced by line index, and never read the surrounding
region.

**So a better place to put the note is not the remedy.** It was in the best
possible place already: the file being edited, at the point of the edit, naming
the trap and the destination.

This is a real tension with context discipline, which says to read the slice and
not the set — locate the anchor, read a window, act. The cost is exactly this:
**a window wide enough to make the edit is not always wide enough to learn the
file is defended.**

**Remedy: prose is not a guard.** Where a file carries a constraint that a future
edit can violate, the constraint needs a mechanical check, not a comment. A test
asserting `models/database.py` imports nothing from `models.` fails at pre-push
on the first attempt and costs nobody a CI cycle. **A comment that has been read
past twice is evidence that it should be a test** — and a file that needs a
comment explaining what will break is a file that needs a test saying so.

**And the remedy has the same failure mode as the disease.** The first draft of
that guard flagged *every* first-party package import in a by-path-loaded module.
It **failed on base**: `migrations/runner.py` is loaded the same way and imports
`from migrations import utils` quite happily. Filed as written, it would have been
a test that fails on a clean tree — worse than the bug, because a guard that cries
wolf gets disabled rather than fixed.

Two facts had to be measured before the rule was right, and neither survives a
guess:

*Which loads are strict.* A `spec_from_file_location` with a **dotted** name
scaffolds a parent in `sys.modules`, so package imports resolve; one with **no
dot** has nothing behind it. Only the second is constrained — and deriving the
target list from the workflow means a fourth by-path load is covered without
anyone remembering.

*Which imports actually fail there.* Not "package imports" — only those whose
`__init__` chain reaches `autobot_shared`:

```
models       REACHES  via user_management.models.user
middleware   REACHES  via monitoring.prometheus_metrics
monitoring   REACHES
api, migrations, services, slm, user_management   clean
```

`user_management` is **clean** while `models` reaches *through*
`user_management.models.user` — a package's own `__init__` and its subpackage's
`__init__` are different files, and guessing gets that backwards.

**So a guard written from the same narrow read that caused the bug will encode the
bug.** What separated the two drafts was running the candidate against base and
finding it red on a clean tree — the second-derivation habit below, applied to the
remedy rather than to the finding.

## Two habits that catch most of it

**A known positive.** Before a count means anything, assert a case whose answer
you already have:

```python
assert found_control, "detector does not find the known instance — the result below is meaningless"
```

A floor on the *count* breaks when a population is legitimately empty, which is
every ratchet on the day it is introduced. A known positive is a claim about the
*instrument*, so it holds at any population size including zero — and it is the
one check on this page a lone author can apply.

**But one control is a control for one shape**, and that is a real limit on the
remedy this page recommends most. A narrowing pass over 136 anchored tests kept
87 and dropped one that mattered — and its positive control survived the
narrowing *because the control was of the surviving shape*:

```python
Path(__file__).parent / "nodes.py"     # the control — matched
SLM / "models" / "database.py"         # missed: the root is a module-level variable
```

A control witnesses only the form it is written in. So a control **set** needs
one case per *shape* the population takes, not one case — and a count published
after a narrowing is a count of "things in the forms I thought of".

**A second derivation, sharing neither enumeration nor matching.** Then compare
**sets, not counts**: two implementations can agree on a total and disagree on
membership.

## Why care is not the remedy

Every instance on this page was found by someone actively hunting this class of
error — usually in someone else's work, in the same hour they committed it in
their own. Three examples from one night:

- A session wrote up the "produced and consumed by nothing" rule, then an hour later shipped a sweep printing `MERGEABLE` beside `shards={'queued': 12}` on one line.
- Two sessions reasoned all evening from *"the required context is `python-suite`"*. Neither listed the required contexts. It was load-bearing for every conclusion and one API call away. **An unexamined premise shared by everyone stops looking like a premise** — agreement converts it into the ground the argument stands on.
- Two sessions produced wrong figures, both inside comments that carefully enumerated *other* unmeasured quantities. **The scrutiny went to the numbers each author already doubted; the number they were confident about got none** — which is anti-correlated with where the error was, because confidence is what buys the exemption from checking.

So the remedy is mechanical, not attitudinal: name the selector, read the
behaviour, consume the result, ask what else produces a refusal — and where a
constraint can be violated by a future edit, make it a test rather than a
sentence.

## An exemption is a blind spot you can read

A guard's blind spots and its exemptions are the same surface. **Only one of them
is written down.** An exemption is a line of code, so it gets a comment, a diff
and a reviewer. A blind spot is the *absence* of a line, so it gets none of the
three — and every mechanism we have for catching a bad decision operates on
things that were written down. That is why the trigger-path
half of a missed-trees guard mattered more than the scan half — a narrow scan
leaves a number someone can question, a trigger that never fires leaves no row at
all.

Which makes the direction of an exemption error worth stating:

| exemption error | consequence | lifetime |
|---|---|---|
| too **narrow** | a red | usually short |
| too **broad** | a **green** | indefinite |

**But "narrow fails loudly" is not the same as "narrow fails informatively", and
the difference decides whether it is self-correcting.** A batching gate rejected a
rationale section that was present and filled, because its parser treats any line
starting with `#` as the next heading and the section opened with an issue
reference — `#15961 alone…`. The hint said *add a section* to an author who had
added one. The natural response is to reword until green, which is what happened,
and that response leaves no trace: every previous author who hit it fixed it
silently, so the same gate taught the same wrong lesson twice.

A red with a misleading cause is repaired by working around it. So the loud half
of the asymmetry only pays out when the message names the real cause — which
means a gate must distinguish *no section found* from *section found but empty*,
and a failure explainer must distinguish *this failed* from *I cannot tell which
of these failed*.

**A failure explainer that guesses is worse than one that says it does not know.**
This codebase already says it better than this page can, in a shipped prompt:
*"Providing plausible-sounding but fabricated information is worse than saying
'I don't know.'"* Fabricating a cause makes the author look competent for
exactly as long as it takes someone to act on it; admitting the gap is what lets
a second person find the answer, which — as every entry on this page shows — is
the only thing that ever finds it.
One that asserted a threshold breach on *any* job failure printed a confident
wrong number to change, on top of a real failure. Manufacturing a false cause is
worse than reporting none, because **a guess laundered through an explainer stops
being a hypothesis and becomes an instruction.**

The escalation is what a reader then does with it. That explainer printed a wrong
number and was caught on the same run. A worse instance the same day: a check's
*name* was read as its cause — `Check same-scope batching` failing was diagnosed
as a missing rationale section, without reading the parser — and relayed to the
author as a fix. The section was already present; the parser was reading `#15961`
as a markdown heading. The advice would have produced a no-op commit and sent its
recipient hunting through their own prose for a defect that was in the gate.

One printed a wrong number. The other would have produced a wrong commit. **The
manufactured cause survived contact with a reader and directed real work**, which
is the property that makes this worth a section rather than a footnote.

## Checklist

- [ ] The sentence reporting a result names the selector that produced it
- [ ] A known positive is asserted before any count is read
- [ ] Any population that gates a decision was derived a second way, and the **sets** compared
- [ ] Every check's output is read by a following line, or deleted
- [ ] For any refusal: what else produces this, and does it want the same action?
- [ ] For any field read as evidence: would more data change this answer? If no, name the question it actually answers
- [ ] For any exemption: it is narrow, and the red it produces names its real cause
- [ ] For any acceptance criterion: ticked against a behaviour, never a name
- [ ] Before editing a file that carries a constraint comment: the constraint is a test, or you have read the region around your edit
- [ ] A new guard was run against a clean base and found green there, before it was trusted to find anything
