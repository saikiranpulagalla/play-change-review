# Observatory Execution Protocol — Attempt 2 Amendment

Attempt 1 stopped during the public-to-local parity preflight before any
Observatory corpus pair executed.

## Attempt 1 cause

The exact tagged local PCR source was invoked with `--yes`.

Rote rejected that invocation because local Play runs have no registry
consent gate.

PCR did not execute and no local semantic result was produced.

## Independent smoke test

The same exact tagged source was then invoked without `--yes`.

Public PCR 0.1.1 and local tagged v0.1.1 produced:

- identical verdict
- identical semantic SHA-256
- reviewed_plays_executed = false

Semantic SHA-256:

0354115126b0a502560eb5046ad6bf5372394cd729076bc4158d8ae5fc535f0f

## Attempt 2 changes

Only two runner changes are permitted:

1. remove `--yes` from the local Play invocation
2. write results to `results-attempt-2`

## Unchanged

The following remain frozen:

- 23 preregistered candidate Plays
- 17 eligible upgrade pairs
- 6 ineligible candidates
- exact pair selection
- PCR v0.1.1
- PCR source commit:
  bcfbece96f04470288f6d8c3c01e086093451055
- public parity control
- semantic projection
- semantic hashing
- identity validation
- reviewed-Play non-execution boundary
- three repetitions per pair
- sequential execution
- 180 second timeout
- no result-driven retries
- aggregation rules
- prevalence denominators
- primary statistic
- no-overclaim boundaries

Attempt 2 must still pass the public-to-local parity gate before any corpus
pair executes.
