# PCR Play Upgrade Observatory

Released PCR under test:

saikiran-labs/play-change-review@0.1.1

Release source:

Git tag v0.1.1

Snapshot:

2026-09-04T13:28:00+05:30

## Question

When real immutable Rote Plays publish a new version, how often does
their registry-visible method materially change, and how often is that
change visible from declared access expansion alone?

## Candidate-pool rule

The candidate pool is fixed before examining version histories or PCR
results.

It contains canonical public owner/name Plays visible in the captured
Playoffs field snapshot, plus PCR itself and the already-established
Amaan external control.

No Play is included or excluded because of the PCR result it produces.

## Pair-selection rule

For every candidate with at least two immutable released versions
available at the snapshot:

    approved  = immediately previous released version
    candidate = latest released version at the snapshot

Do not substitute a more interesting older pair after results are seen.

## Execution rule

Every eligible pair is run three times through the exact public PCR:

https://play.modiqo.ai/saikiran-labs/play-change-review@0.1.1

The reviewed Plays are never executed by PCR.

## Determinism

For each run, hash only the canonical semantic conclusion:

- verdict
- approved identity
- candidate identity
- declared_access_expansion_observed
- counts
- reason_codes
- package-files disclosure/comparison state
- structured blocked error code when applicable

Runner IDs, timestamps, elapsed time and temporary paths are excluded
from the semantic hash.

## Reporting rule

All eligible pairs count.

Failures and BLOCKED results are retained.

No unsuccessful or boring pair may be removed after execution.

## Controls

Controls are reported separately from ecosystem prevalence:

- exact same immutable release -> expected EXACT_MATCH
- malformed exact version -> expected BLOCKED
- ambiguous fixture behavior remains covered by PCR's development tests

## Claims PCR will NOT make

PCR does not establish:

- safety to upgrade
- behavioral equivalence
- maliciousness
- absence of permission risk
- correctness of arbitrary application behavior
