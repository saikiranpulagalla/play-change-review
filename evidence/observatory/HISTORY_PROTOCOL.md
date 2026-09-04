# Observatory History Discovery Protocol

This protocol clarifies history discovery after the candidate pool and
snapshot heads were preregistered, but before histories for the full
candidate pool are collected and before Observatory PCR comparisons run.

## Snapshot boundary

The candidate version for each Play is the version captured by:

    rote registry play info <owner/name>

in the committed 2026-09-04 head snapshot.

A version published after that snapshot MUST NOT replace the recorded
candidate version.

## History source

Historical releases are discovered with:

    rote registry play search <short-name>

Registry search results enumerate version, namespace and approval status.

Only results satisfying ALL of the following belong to a candidate's
history:

- short name exactly equals the candidate Play name
- namespace exactly equals the candidate owner
- status is approved
- version is valid SemVer
- version has no prerelease component
- version is not newer than the preregistered snapshot candidate

Search results from another namespace are ignored even when the short
Play name is identical.

## Stable releases

Observatory prevalence uses stable SemVer releases only.

Prerelease identifiers such as:

    1.2.0-alpha.1
    1.2.0-rc.1

are excluded.

Build metadata is permitted. If multiple released references have the
same SemVer precedence but differ only in build metadata, selection is
treated as ambiguous rather than silently choosing one.

## Pair selection

candidate = preregistered snapshot head

approved = immediately preceding stable approved version by SemVer
           precedence

If fewer than two stable approved versions exist at or before the
snapshot head, the Play is INELIGIBLE.

An ineligible Play remains in the candidate-pool accounting and is not
replaced.

## Completeness

History discovery MUST request a search limit larger than the default
10.

If the search reports total_results greater than the requested limit,
history discovery fails closed for that Play. It must not guess that all
relevant versions were returned.

The preregistered snapshot candidate itself must appear in the filtered
history. If it does not, history discovery fails closed.

## Example discovered before the full sweep

Search for git-handoff-snapshot exposed:

amaan-playoffs:
    0.1.0
    0.2.0
    0.2.1
    0.2.2

chetan:
    0.2.0
    0.2.1

The namespaces are distinct.

For the Observatory snapshot:

    approved  = amaan-playoffs/git-handoff-snapshot@0.2.1
    candidate = amaan-playoffs/git-handoff-snapshot@0.2.2

The historical 0.1.0 -> 0.2.0 comparison remains useful as a demo but
is NOT the preregistered Observatory prevalence pair.
