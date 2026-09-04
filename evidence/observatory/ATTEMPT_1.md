# Observatory Attempt 1

Attempt 1 stopped during the public-to-local parity preflight.

No Observatory corpus pair was executed.

## Cause

The runner invoked the local tagged Play with:

    --yes

Rote rejected the invocation before PCR executed:

    --yes applies to registry plays; a local play run has no consent gate

Observed preflight state:

- local process exit code: 2
- local PCR presentation objects: 0
- local semantic hash: unavailable
- public semantic hash: available
- corpus executed: no

This is an execution-harness error, not a PCR semantic mismatch.

Attempt 1 is preserved without deletion or overwrite.

Attempt 2 may change only the local invocation semantics necessary to run
a local Play: omit --yes. Corpus selection, PCR source commit, semantic
projection, run count, timeout and reporting rules remain unchanged.
