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

## Four families, four different remedies

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
2. **The guard ran and answered an adjacent question.** A drift check enforced byte-identity between a directory and its mirror while nothing checked that every module was actually deployed. Content parity and shipping parity are different claims about the same two directories.
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

## Checklist

- [ ] The sentence reporting a result names the selector that produced it
- [ ] A known positive is asserted before any count is read
- [ ] Any population that gates a decision was derived a second way, and the **sets** compared
- [ ] Every check's output is read by a following line, or deleted
- [ ] For any refusal: what else produces this, and does it want the same action?
- [ ] For any acceptance criterion: ticked against a behaviour, never a name
- [ ] Before editing a file that carries a constraint comment: the constraint is a test, or you have read the region around your edit
