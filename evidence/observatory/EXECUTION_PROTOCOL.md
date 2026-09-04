# PCR Observatory Execution Protocol

## Frozen inputs

Corpus selection is frozen at commit e9f1897.

Candidate pool:

23 Plays

Eligible immediately-previous -> frozen-snapshot-head pairs:

17

Ineligible single-release-at-snapshot Plays:

6

No pair may be added, removed, replaced or reordered because of PCR output.

## PCR implementation under test

The corpus runner uses the exact source snapshot tagged:

v0.1.1

Expected Git commit:

bcfbece96f04470288f6d8c3c01e086093451055

The source is materialized as a detached clean Git worktree and executed
locally through Rote.

The 51 corpus runs intentionally do NOT invoke PCR through its public URI,
so automated evaluation cannot be confused with organic adoption or Reach.

PCR itself still performs its normal read-only `rote play inspect` operations
against the two exact immutable reviewed versions.

## Public-to-local parity gate

Before any corpus pair runs, the local tagged PCR performs:

saikiran-labs/play-change-review@0.1.0
->
saikiran-labs/play-change-review@0.1.1

Its canonical semantic projection must hash identically to the already
captured public PCR 0.1.1 self-review.

If parity fails, the corpus MUST NOT run.

The boundary must also remain:

reviewed_plays_executed = false

## Runs

Every frozen eligible pair executes exactly three times.

17 pairs x 3 runs = 51 corpus runs.

Runs are sequential.

There are no result-driven retries.

A timeout, non-zero exit, malformed result, identity mismatch or execution
boundary violation remains part of the first attempt.

## Per-run timeout

180 seconds.

A timeout is retained as a runner failure. It is not silently retried.

## Semantic determinism projection

Only these fields contribute to the semantic SHA-256:

- verdict
- approved identity
- candidate identity
- declared_access_expansion_observed
- counts
- reason_codes
- package-files comparison/disclosure state and totals
- structured blocked error code when present

Run IDs, timestamps, runtime, paths, evidence samples and formatting do not
contribute to the semantic hash.

## Pair classification

DETERMINISTIC:
all three runs completed validly and have one identical semantic hash.

NONDETERMINISTIC:
all three runs completed validly but semantic hashes differ.

RUNNER_FAILURE:
one or more runs timed out or returned non-zero.

PARSE_FAILURE:
one or more runs failed to produce exactly one canonical PCR presentation
JSON object.

IDENTITY_FAILURE:
PCR claims comparison_performed=true but the returned immutable identities
do not equal the frozen requested identities, or a returned identity conflicts
with the requested identity.

BOUNDARY_FAILURE:
reviewed_plays_executed is not exactly false.

BLOCKED is a valid PCR semantic outcome. A deterministic BLOCKED result is
not a runner failure.

## Prevalence denominators

All 17 eligible pairs remain in total corpus accounting.

Core semantic prevalence uses deterministic pairs where
comparison_performed=true.

BLOCKED, nondeterministic and runner-failure pairs are separately reported
and are never silently discarded.

The report must expose numerator and denominator for every rate.

## Primary statistic

Among deterministic performed comparisons:

How many upgrades have:

material_types > 0

while:

declared_access_expansion_observed == false

## No overclaim

The Observatory does not establish:

- safety to upgrade
- behavioral equivalence
- maliciousness
- absence of permission risk
- correctness of arbitrary application behavior
