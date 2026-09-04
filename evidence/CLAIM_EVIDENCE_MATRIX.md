# Play Change Review — Claim → Evidence Matrix

This document defines what may and may not be claimed about
`saikiran-labs/play-change-review@0.1.1`.

It is a communication guardrail, not a new experiment.

## 1. Core product claim

### Allowed

> Play Change Review compares two exact immutable releases of the same Play across registry-visible inputs, declared access, runtime requirements, execution structure, and artifact identity without executing either reviewed Play.

### Evidence

- released Play: `saikiran-labs/play-change-review@0.1.1`
- release commit: `bcfbece96f04470288f6d8c3c01e086093451055`
- public canonical runs
- `reviewed_plays_executed=false` in canonical comparison output

### Do not say

- PCR observes runtime behavior of the reviewed Plays
- PCR executes candidate Plays in a sandbox
- PCR proves two releases behave equivalently

## 2. Exact-version requirement

### Allowed

> PCR requires exact version references so the two reviewed artifacts are immutable and reproducible.

### Evidence

Strict SemVer validation covers valid and invalid references.

Malformed examples such as:

`owner/name@01.2.3`

are rejected with:

`CANDIDATE_EXACT_VERSION_REQUIRED`

The review is blocked before either reviewed Play is executed.

### Do not say

- PCR automatically chooses the latest version
- floating references are equivalent to exact references
- PCR resolves an upgrade decision from `owner/name` alone

## 3. Unknown evidence

### Allowed

> Missing disclosure is preserved as unknown rather than interpreted as absence.

### Evidence

PCR reports:

`DISCLOSURE_INCOMPLETE`

when registry-visible fields such as adapter credentials, browser authentication, or sensitivity are unknown.

Semantic hardening explicitly tests disclosure appearance and loss.

### Core rule

> `MISSING != NONE`

### Do not say

- unknown means no permission is required
- unknown means safe
- missing disclosure means capability removal

## 4. Ambiguous inspection structures

### Allowed

> PCR fails closed when inspection evidence contains duplicate semantic identities that would make comparison ambiguous.

### Evidence

Eight ambiguity regression cases cover duplicate:

- parameters
- steps
- runtimes
- tools
- endpoints
- authentication adapters

including identical duplicates.

### Do not say

- PCR guesses which duplicate is authoritative
- duplicate entries are silently deduplicated

## 5. Large comparisons

### Allowed

> PCR bounds presentation size while preserving complete verdicts, counts, and reason codes.

### Evidence

Regression coverage includes:

- 9,990 changed package files
- 5,000 findings
- deterministic bounded result
- complete counts retained while individual evidence is bounded

The original large-output failure was discovered after a semantically
correct result exceeded an outer capture boundary and was then redesigned.

### Do not say

- PCR returns every individual finding regardless of size
- presentation truncation means semantic counts are truncated
- PCR has no output limits

## 6. PCR self-dogfood

### Allowed

> PCR reviewed its own public `0.1.0 → 0.1.1` upgrade and classified it as `IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT`.

Observed:

- material change types: `0`
- informational change types: `4`
- declared access expansion: `false`
- reviewed Plays executed: `false`

### Interpretation

The new release changed implementation/artifact identity and added
hardening files while preserving the compared material registry-visible
contract.

### Do not say

- 0.1.0 and 0.1.1 are behaviorally equivalent
- 0.1.1 is therefore safe
- implementation did not change

## 7. Observatory methodology

### Allowed

> PCR preregistered 23 public Plays at a frozen snapshot and reviewed every eligible latest adjacent stable upgrade under the preregistered selection rule.

Frozen population:

- candidate Plays: `23`
- eligible Plays with a previous stable release: `17`
- ineligible at the frozen snapshot: `6`
- stable releases represented in frozen histories: `68`
- adjacent stable upgrade events in those histories: `45`

Execution:

- frozen upgrade pairs: `17`
- executions per pair: `3`
- scheduled corpus executions: `51`

### Do not say

- 23 upgrades were compared
- all 45 historical transitions were executed
- the corpus represents the entire Rote ecosystem statistically

## 8. Observatory determinism

### Allowed

> All 17 frozen upgrade pairs produced the same semantic PCR result across three executions each.

Observed:

- deterministic pairs: `17 / 17`
- completed pairs: `17 / 17`
- BLOCKED pairs: `0`
- identity failures: `0`

### Do not say

- PCR is mathematically deterministic for every possible future input
- 51 runs prove PCR can never fail
- the sample is a formal reliability estimate

## 9. Observatory classification result

### Allowed

> Across the 17 frozen latest-adjacent upgrades, PCR separated 16 implementation changes with the same material registry-visible contract from one material method change.

Observed:

- `16 / 17` — `IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT`
- `1 / 17` — `MATERIAL_METHOD_CHANGE`
- `17 / 17` — implementation identity changed
- `0 / 17` — declared access expansion observed

### Do not say

- material Play changes are common
- only one meaningful implementation change occurred
- the other sixteen upgrades did nothing
- unchanged visible contract means unchanged behavior

## 10. Material change without access expansion

### Allowed

> The sole material-method-change case in the preregistered sample contained a parameter default change, while no compared pair showed declared access expansion.

Or:

> The only material upgrade in the frozen latest-version sample changed what a parameter does by default without expanding its declared access surface.

### Evidence

Aggregate reason-code profile:

- `PARAMETER_DEFAULT_CHANGED`: `1`
- declared access expansion pairs: `0`

### Do not say

- access declarations are useless
- parameter-default changes are always dangerous
- this proves most material upgrades happen without permission changes

## 11. Disclosure profile

### Allowed

> All 17 Observatory comparisons retained some registry-visible disclosure fields as unknown rather than interpreting them as absent.

Observed aggregate:

- `DISCLOSURE_INCOMPLETE`: `17`

### Do not say

- all 17 Plays had security defects
- all 17 Plays hid credentials
- `DISCLOSURE_INCOMPLETE` means unsafe

It means only that PCR did not have complete evidence for every modeled disclosure field.

## 12. Performance observations

### Allowed

For this frozen Observatory corpus:

- median runtime: approximately `1.22 s`
- p90 runtime: approximately `1.34 s`
- maximum runtime: approximately `4.57 s`

### Do not say

- PCR always runs in 1.2 seconds
- these figures are universal benchmarks
- performance was measured across all possible Play sizes

## 13. GHP cross-dogfood

### Allowed

> In a separate post-hoc cross-dogfood example, PCR reviewed Git Handoff Proof `0.0.5 → 0.0.6` and reported `IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT`.

Observed:

- material change types: `0`
- informational change types: `2`
- declared access expansion observed: `false`
- reviewed Plays executed: `false`

Evidence:

`evidence/cross-dogfood/ghp-0.0.5-to-0.0.6/`

Canonical JSON SHA-256:

`5ca76d38bf6b4549fb543599c370a7f75d24186899bf87b9dabbb11d122a3789`

### Important boundary

This comparison happened after the Observatory was frozen.

It is NOT part of:

- the 17 Observatory pairs
- the 51 Observatory executions
- Observatory prevalence claims

### Do not say

- 18 Observatory pairs
- 54 Observatory runs
- GHP validates the Observatory
- PCR proves GHP 0.0.6 behavior is equivalent to 0.0.5

## 14. Non-execution boundary

### Allowed

> PCR does not execute either Play being reviewed.

### Evidence

Canonical outputs explicitly report:

`reviewed_plays_executed=false`

PCR reviews registry-visible inspection evidence instead.

### Do not say

- PCR dynamically tests candidate behavior
- PCR sandboxes the candidate
- PCR observes its network behavior at runtime

## 15. Safety boundary

### Allowed

> PCR is a change-review tool, not a safety oracle.

Or:

> PCR tells you what changed in the evidence it can observe; the human still decides whether to upgrade.

### Do not say

- safe to upgrade
- unsafe to upgrade
- malicious
- secure
- vulnerability-free
- behavioral equivalence

unless independent evidence outside PCR establishes such a claim.

## 16. Best product positioning

Primary:

> **PCR is the review gate before moving an immutable Play version pin.**

Simple question:

> **You trusted one Play version. What changed in the next one?**

Workflow:

`new Play version → keep current pin → PCR comparison → human review → decide whether to move pin`

PCR is best described as **event-driven hygiene**, not daily hygiene.

## 17. Best Observatory claim

Preferred wording:

> I preregistered 23 public Plays and reviewed every eligible latest adjacent upgrade at a frozen snapshot. Across 51 executions PCR was semantically deterministic on all 17 pairs; it separated 16 implementation changes with the same material registry-visible contract from one material method change — a parameter-default change that occurred without any declared access expansion.

This is descriptive evidence from the frozen corpus.

It is not a population estimate.

## 18. Claims that must never appear

Do not say:

- PCR proves an upgrade is safe.
- PCR proves behavioral equivalence.
- PCR found malicious Plays.
- PCR found vulnerabilities in the Observatory corpus.
- Material upgrades are common.
- Most upgrades change behavior.
- Access expansion is irrelevant.
- 17 of 17 Plays were risky.
- 17 of 17 upgrades were material.
- PCR executed reviewed Plays.
- The Observatory measured adoption.
- The Observatory is statistically representative of the entire ecosystem.
- The GHP cross-dogfood belongs to the Observatory.
- `UNKNOWN` means `NONE`.
- `MISSING` means empty.
- implementation unchanged when artifact identity changed.

## Final discipline

When evidence is narrower than the desired sentence, narrow the sentence.

The strongest PCR story is not that it knows everything.

The strongest PCR story is that it **refuses to turn missing, ambiguous,
or bounded evidence into certainty**.
