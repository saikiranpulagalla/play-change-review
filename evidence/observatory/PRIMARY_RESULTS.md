# PCR Play Upgrade Observatory — Primary Result

## Frozen population

- 23 Plays preregistered
- 17 had at least two stable releases at the frozen snapshot
- 6 were ineligible because they had only one stable release
- frozen histories contained 68 stable releases
- those histories contained 45 adjacent stable-version transitions

## Preregistered primary comparison

The primary analysis compared, for every eligible Play:

    immediately previous stable release
    ->
    frozen snapshot head

17 upgrade pairs were analyzed.

Each pair was executed three times through the exact PCR v0.1.1 source.

Total corpus executions:

    51

## Reliability

- 17 / 17 pairs were semantically deterministic across all three runs
- 17 / 17 comparisons completed
- 0 BLOCKED pairs
- 0 identity failures
- 0 reviewed-Play execution-boundary failures

## Primary results

- 17 / 17 changed known implementation identity
- 16 / 17 were classified as
  IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT
- 1 / 17 was classified as
  MATERIAL_METHOD_CHANGE
- 0 / 17 showed declared access expansion

The single material-method-change result occurred without a declared
access expansion.

This is descriptive evidence from the preregistered field sample. It is
not presented as an estimate of the prevalence of material changes across
all Rote Plays.

## Performance

- median runtime: approximately 1.22 seconds
- p90 runtime: approximately 1.34 seconds
- maximum observed runtime: approximately 4.57 seconds

## Interpretation

The experiment does not show that material registry-visible changes are
common.

It shows that PCR deterministically distinguishes immutable implementation
changes from registry-visible material method changes while preserving an
explicit non-execution and no-safety-claim boundary.

## Boundaries

PCR does not establish:

- safety to upgrade
- behavioral equivalence
- maliciousness
- absence of permission risk
- correctness of arbitrary application behavior

Detailed per-Play results are withheld until they can be released without
providing active competitors with potentially actionable review information.
Their exact contents are cryptographically committed separately.

## Aggregate change profile

Across the 17 deterministic adjacent-version comparisons:

- 17 reported IMPLEMENTATION_CHANGED
- 4 reported DOCUMENTATION_CHANGED
- 1 reported PARAMETER_DESCRIPTION_CHANGED
- 1 reported PACKAGE_FILESET_CHANGED
- 1 reported PARAMETER_DEFAULT_CHANGED

All 17 also reported DISCLOSURE_INCOMPLETE because some registry-visible
disclosure fields remained unknown. Unknown fields were retained as unknown;
they were not interpreted as absent.

The sole material-method-change case contained a parameter default change.
No compared pair showed a declared access expansion.

This matters because a release can change what happens by default without
expanding its declared access surface.
