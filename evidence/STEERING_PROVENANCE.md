# Play Change Review — Steering Provenance

This document records genuine engineering wrong turns and corrections that
shaped `saikiran-labs/play-change-review@0.1.1`.

It does not reconstruct or invent a development story for presentation.
Every item below corresponds to preserved repository history or committed
experiment evidence.

## 1. Missing evidence was initially too easy to interpret as empty evidence

### Problem

A comparison system must distinguish:

    missing disclosure

from:

    explicitly disclosed empty value

For example, if `package.files` is present in one inspection and missing in
the other, treating the missing value as `[]` creates fictional semantic
evidence:

    known files -> missing disclosure

could incorrectly appear as:

    all files removed

The same problem applies to other registry-visible disclosure fields such as
declared endpoints.

### Correction

PCR introduced explicit disclosure-awareness and stopped converting missing
evidence into empty evidence.

Core rule:

    MISSING != NONE

A known-to-missing transition is classified as a disclosure change rather
than a fabricated resource removal.

Examples now include:

- `PACKAGE_FILESET_DISCLOSURE_CHANGED`
- `DECLARED_ENDPOINT_DISCLOSURE_CHANGED`

The comparison is unavailable when both sides do not provide comparable
evidence.

### Preserved history

Commit:

    2a999d4afab848577ac3bbde4f7fe7f9fa1a7671
    Fix PCR disclosure and visible-contract semantics

Regression coverage verifies, among other cases:

- package file disclosure loss is not reported as file removal
- package file disclosure appearance is not reported as file addition
- endpoint disclosure loss is not reported as endpoint reduction
- unknown evidence is preserved as unknown

### Steering lesson

> Absence of evidence cannot become evidence of absence.

This is one of PCR's central trust boundaries.

---

## 2. A semantically correct large result could disappear at the process boundary

### Problem

Adversarial scale testing produced a comparison with approximately 9,990
changed package files.

The comparison semantics themselves were correct, but the serialized result
grew to roughly 1.1 MB.

That result exceeded the outer process-output/capture boundary.

The downstream presentation layer could then lose the comparison and fall
back toward a generic blocked state.

This exposed an important distinction:

    correct internal computation

does not imply:

    trustworthy externally observable result

### Correction

PCR was redesigned so semantic conclusions are computed first and evidence
presentation is bounded afterward.

The current contract preserves:

- verdict
- complete counts
- complete reason-code set
- comparison identities
- review boundary

while bounding individual evidence samples.

PCR now has:

- deterministic evidence sampling
- bounded finding detail
- bounded package-file samples
- emergency compaction
- a final explicit fail-safe rather than silently losing output

### Preserved history

Commit:

    a4fb99356f3c4974799967b198e35327e0beeb0b
    Harden PCR bounded evidence output

Regression coverage includes:

- 9,990 changed package files
- 5,000 findings
- complete counts with bounded evidence
- deterministic bounded output

### Steering lesson

> A complete denominator and verdict matter more than printing every row.

Bounding presentation must never silently change the semantic conclusion.

---

## 3. Duplicate semantic identities made comparison ambiguous

### Problem

An inspection structure can contain two recognized entries claiming the same
semantic identity.

Examples:

- two parameters with the same name
- two steps with the same name
- two runtimes with the same name
- two tools with the same id
- two endpoints with the same identity
- two authentication adapters with the same identity

A naive dictionary conversion would make one entry overwrite the other.

That produces a deterministic-looking result from ambiguous evidence.

Even identical duplicates are still ambiguous because PCR has no authority
to decide which occurrence is canonical.

### Correction

PCR explicitly detects duplicate semantic identities and returns:

    BLOCKED
    AMBIGUOUS_INSPECTION_STRUCTURE

No semantic comparison is performed.

Neither reviewed Play is executed.

### Preserved history

Commit:

    3f12499e52aaf6e4087684dc75c8eb2a78da7c6f
    Reject ambiguous PCR inspection structures

Eight regression cases cover the ambiguous structures and verify that the
blocked reason survives through the complete PCR review path.

### Steering lesson

> Deterministic guessing is still guessing.

When the evidence structure itself is contradictory, PCR refuses to choose
an interpretation.

---

## 4. Observatory Attempt 1 failed before the corpus ran

### Goal

The PCR Play Upgrade Observatory was designed to execute the exact released
PCR `0.1.1` source locally while first proving semantic parity with the
public registry artifact.

The corpus was not allowed to run until that parity gate passed.

### Wrong turn

Attempt 1 invoked the local tagged Play with:

    --yes

Rote rejected the invocation because `--yes` is a registry-Play consent flag
and local Play runs have no such consent gate.

Observed:

- local process exit code: `2`
- local PCR presentation objects: `0`
- local semantic hash: unavailable
- public semantic hash: available
- corpus executed: `no`

The failure occurred at the preflight gate.

No Observatory pair was executed.

### Preserved history

Commit:

    53eb0ae91a1fc2bf1bdae9c103951b628973fd77
    Record failed Observatory parity preflight

The failure, stderr, metadata, parity object and hashes were preserved rather
than deleted or overwritten.

### Correction

The local tagged source was manually smoke-tested without `--yes`.

Public PCR `0.1.1` and local tagged PCR `0.1.1` then produced the same
semantic SHA-256:

    0354115126b0a502560eb5046ad6bf5372394cd729076bc4158d8ae5fc535f0f

Attempt 2 was allowed exactly two runner changes:

1. remove `--yes` from the local invocation
2. write results to a new `results-attempt-2` location

Everything material to the experiment remained frozen, including:

- candidate population
- upgrade-pair selection
- exact PCR release commit
- semantic projection
- three repetitions per pair
- sequential execution
- timeout
- no result-driven retries
- aggregation rules

Commit:

    fe8a5ff60343003468a2584b5c984afc8605fb1b
    Amend Observatory local execution preflight

Attempt 2 subsequently passed parity and completed the frozen corpus.

### Steering lesson

> A failed preflight is evidence that the guard worked.

The correct response was not to weaken the gate or rerun silently.
The failed attempt was preserved, the minimal invocation error was corrected,
and the experiment continued under the original frozen methodology.

---

## 5. The released Play remained frozen while evidence work continued

Released PCR:

    saikiran-labs/play-change-review@0.1.1

Release commit:

    bcfbece96f04470288f6d8c3c01e086093451055

After release, Observatory methodology, results, cross-dogfood evidence and
communication guardrails were developed on:

    evidence/playoffs-observatory

The released Play itself was not modified merely to improve the competition
story.

This separates:

    product changes

from:

    post-release evidence gathering

and prevents experiment results from feeding back into the tested artifact.

---

## 6. Evidence layers

PCR currently has four distinct evidence layers.

### Product regression and adversarial tests

Used to validate semantics and failure boundaries.

### Self-dogfood

PCR reviewed:

    play-change-review@0.1.0
        ->
    play-change-review@0.1.1

Result:

    IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT

### Preregistered Observatory

Frozen population:

    23 public Plays

Eligible frozen latest-adjacent pairs:

    17

Executions:

    17 pairs x 3 = 51

Result:

    17 / 17 deterministic
    16 implementation changes with same material visible contract
     1 material method change
     0 declared access expansions observed

### Post-hoc GHP cross-dogfood

PCR separately reviewed:

    git-handoff-proof@0.0.5
        ->
    git-handoff-proof@0.0.6

Result:

    IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT

This occurred after the Observatory was frozen and is explicitly excluded
from the 17-pair / 51-run Observatory statistics.

---

## 7. Presentation boundary

The strongest steering examples for a Director's Cut are:

1. `MISSING != NONE`
2. large correct output disappearing at the process boundary
3. ambiguous duplicate identities -> `BLOCKED`
4. Observatory Attempt 1 failing its own parity gate

Not all of them need to appear in the final presentation.

The purpose of preserving all four here is to make the final story traceable
to real evidence rather than selecting or embellishing undocumented
development anecdotes.

## Final principle

PCR's engineering direction repeatedly converged on the same rule:

> When evidence is missing, ambiguous, oversized, or operationally invalid,
> do not manufacture certainty.

That principle is reflected in the released product as well as in the way
the Observatory itself was conducted.
