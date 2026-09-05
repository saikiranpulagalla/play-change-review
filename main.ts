#!/usr/bin/env -S rote play run
/**
 * Compare two immutable Rote Play releases before trusting the newer method.
 *
 * @rote-frontmatter
 * ---
 * name: play-change-review
 * source: https://github.com/saikiranpulagalla/play-change-review
 * tags:
 * - rote-playoffs
 * - play-inspection
 * - change-review
 * - agent-governance
 * - release-review
 * discoverability:
 *   tags:
 *   - rote-playoffs
 *   - play-inspection
 *   - change-review
 *   - agent-governance
 *   - release-review
 * description: "You trusted one Play version. What changed in the next one? Compares two immutable releases of the same Play across inputs, declared access, runtime requirements, registry-visible execution structure and artifact identity without executing either reviewed Play."
 * provenance:
 *   author: Sai
 * metadata:
 *   rote_version: 0.78.0
 *   version: 0.1.2
 *   status: released
 *   kind: atomic
 *   flow_type: parallel
 *   execution_model: steps_with_presentation
 *   format: typescript
 *   requires_endpoints: []
 *   requires_sessions: false
 *   contract:
 *     atomic: true
 *     input:
 *       type: none
 *     output:
 *       format: json
 *       destination: stdout
 *     composable: true
 *   discoverability:
 *     tags:
 *     - rote-playoffs
 *     - play-inspection
 *     - change-review
 *     - agent-governance
 *     - release-review
 * parameters:
 * - name: approved
 *   param_type: string
 *   required: true
 *   default: null
 *   description: "Exact immutable URI or owner/name@version for the Play release you already reviewed or trusted."
 *   example: "amaan-playoffs/git-handoff-snapshot@0.1.0"
 *   valid_values: null
 * - name: candidate
 *   param_type: string
 *   required: true
 *   default: null
 *   description: "Exact immutable URI or owner/name@version for the candidate release you want to review."
 *   example: "amaan-playoffs/git-handoff-snapshot@0.2.0"
 *   valid_values: null
 * steps:
 *   validate_approved:
 *     type: process.exec
 *     timeout_ms: 10000
 *     argv:
 *     - python3
 *     - resources/validate_ref.py
 *     - $approved
 *   validate_candidate:
 *     type: process.exec
 *     timeout_ms: 10000
 *     argv:
 *     - python3
 *     - resources/validate_ref.py
 *     - $candidate
 *   review_versions:
 *     type: process.exec
 *     timeout_ms: 200000
 *     depends_on:
 *     - validate_approved
 *     - validate_candidate
 *     argv:
 *     - python3
 *     - resources/review_refs.py
 *     - '@validate_approved{$.stdout.text}'
 *     - '@validate_candidate{$.stdout.text}'
 * presentation_fixtures:
 *   validate_approved: resources/presentation-fixtures/validate_approved/fixture.yaml
 *   validate_candidate: resources/presentation-fixtures/validate_candidate/fixture.yaml
 *   review_versions: resources/presentation-fixtures/review_versions/fixture.yaml
 * ---
 */


const {
  FlowOutput,
  isProcessExecBody,
  loadPresentationContext,
  stepName,
} = await import("__ROTE_PRESENTATION_SDK__");

const out = new FlowOutput();
const ctx = await loadPresentationContext();

function safeText(value: unknown, maxLength = 500): string {
  const raw = String(value ?? "");
  let rendered = "";

  for (const ch of raw) {
    const cp = ch.codePointAt(0) ?? 0;

    if (ch === "\n") {
      rendered += "\\n";
    } else if (ch === "\r") {
      rendered += "\\r";
    } else if (ch === "\t") {
      rendered += "\\t";
    } else if (
      cp < 0x20 ||
      (cp >= 0x7f && cp <= 0x9f) ||
      (cp >= 0x200b && cp <= 0x200f) ||
      (cp >= 0x202a && cp <= 0x202e) ||
      (cp >= 0x2060 && cp <= 0x2069) ||
      cp === 0xfeff
    ) {
      rendered += `\\u${cp.toString(16).padStart(4, "0")}`;
    } else {
      rendered += ch;
    }

    if (rendered.length >= maxLength) {
      rendered =
        rendered.slice(0, maxLength) +
        "…[truncated]";
      break;
    }
  }

  return rendered;
}

function readProcess(step: any) {
  const status = step?.outcome?.status ?? "unavailable";
  const body = step?.outcome?.output?.body;

  if (!body || !isProcessExecBody(body)) {
    return {
      status,
      ok: false,
      stdout: "",
      stderr: "",
    };
  }

  const exit = body.status?.exit;

  return {
    status,
    ok: exit?.kind === "code" && exit?.code === 0,
    stdout: body.stdout?.text ?? "",
    stderr: body.stderr?.text ?? "",
  };
}

const review = readProcess(
  ctx.step(stepName("review_versions"))
);

let comparison: any = null;

let comparisonParseFailed = false;

if (review.stdout.length > 0) {
  try {
    comparison = JSON.parse(review.stdout);
  } catch {
    comparisonParseFailed = true;
  }
}

// Presentation must never silently convert missing/truncated
// process evidence into an unexplained generic BLOCKED result.
if (comparison === null) {
  const reviewStepFailed = review.ok !== true;

  const errorCode = reviewStepFailed
    ? "REVIEW_STEP_FAILED"
    : comparisonParseFailed
      ? "REVIEW_OUTPUT_INVALID_JSON"
      : "REVIEW_OUTPUT_MISSING";

  const detail = reviewStepFailed
    ? (
        review.stderr ||
        "The review process step did not complete successfully."
      )
    : comparisonParseFailed
      ? (
          "The review step completed, but its recorded stdout " +
          "was not valid JSON."
        )
      : (
          "The review step completed, but no comparison result " +
          "was recorded."
        );

  comparison = {
    schema: "play-change-review/v1",
    ok: false,
    verdict: "BLOCKED",
    error_code: errorCode,
    detail,
    reviewed_plays_executed: false,
    limitations: [
      "No comparison conclusion was produced.",
      "Neither reviewed Play was executed.",
    ],
  };
}

const verdict = comparison?.verdict ?? "BLOCKED";

const humanVerdict =
  verdict === "IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT"
    ? "IMPLEMENTATION CHANGED"
    : verdict;

const approvedIdentity =
  comparison?.approved?.identity ??
  comparison?.approved_ref ??
  comparison?.approved_input ??
  "unavailable";

const candidateIdentity =
  comparison?.candidate?.identity ??
  comparison?.candidate_ref ??
  comparison?.candidate_input ??
  "unavailable";

const materialCount =
  comparison?.counts?.material_types ?? 0;

const informationalCount =
  comparison?.counts?.informational_types ?? 0;

const changes =
  Array.isArray(comparison?.changes)
    ? comparison.changes
    : [];

const reasonCodes =
  Array.isArray(comparison?.reason_codes)
    ? comparison.reason_codes
    : [];

const inspectionCoverage =
  comparison?.inspection_coverage ?? {};

const comparedStepFields =
  Array.isArray(
    inspectionCoverage?.execution_step_fields_compared
  )
    ? inspectionCoverage.execution_step_fields_compared
    : [];

const approvedUnknownDisclosures =
  Array.isArray(
    inspectionCoverage?.approved_unknown_disclosure_fields
  )
    ? inspectionCoverage.approved_unknown_disclosure_fields
    : [];

const candidateUnknownDisclosures =
  Array.isArray(
    inspectionCoverage?.candidate_unknown_disclosure_fields
  )
    ? inspectionCoverage.candidate_unknown_disclosure_fields
    : [];

const sameUnknownDisclosureCoverage =
  JSON.stringify(approvedUnknownDisclosures) ===
  JSON.stringify(candidateUnknownDisclosures);

const totalFindingCount =
  comparison?.counts?.total_findings ??
  changes.length;

const returnedEvidenceCount =
  comparison?.change_evidence?.returned ??
  changes.length;

const omittedEvidenceCount =
  comparison?.change_evidence?.omitted ??
  Math.max(
    0,
    totalFindingCount - returnedEvidenceCount
  );

const lines: string[] = [
  "PLAY CHANGE REVIEW",
  "",
  `APPROVED   ${safeText(approvedIdentity)}`,
  `CANDIDATE  ${safeText(candidateIdentity)}`,
  "",
  `VERDICT    ${humanVerdict}`,
  "",
];

if (
  verdict === "IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT"
) {
  lines.push(
    "No material change was observed in the registry-visible fields PCR can compare.",
    ""
  );
}

if (
  comparison?.ok === true &&
  comparison?.verdict === "IDENTITY_MISMATCH"
) {
  lines.push(
    "REVIEW STOPPED",
    "",
    "Approved and candidate refer to different Play identities.",
    "A version-to-version change comparison was not performed.",
    "",
    "REASON CODES",
    "- IDENTITY_MISMATCH"
  );
} else if (comparison?.ok === true) {
  lines.push(
    "DECLARED ACCESS",
    comparison.declared_access_expansion_observed === true
      ? "Expansion observed in compared declared fields."
      : "No declared access expansion observed in compared fields.",
    "",
    "CHANGES",
    `${materialCount} material change type(s) · ${informationalCount} informational type(s)`,
  );

  for (const change of changes.slice(0, 20)) {
    const marker = change.material === true ? "!" : "i";
    lines.push(
      `${marker} ${safeText(change.code, 120)} — ${safeText(change.detail)}`
    );
  }

  if (changes.length > 20) {
    lines.push(
      `… ${changes.length - 20} more sampled finding(s) in JSON output`
    );
  }

  if (omittedEvidenceCount > 0) {
    lines.push(
      `… ${omittedEvidenceCount} additional finding(s) omitted from bounded evidence; counts and reason codes remain complete.`
    );
  }

  lines.push(
    "",
    "INSPECTION COVERAGE",
    comparedStepFields.length
      ? (
          "Compared execution step fields: " +
          safeText(comparedStepFields.join(", "), 240) +
          "."
        )
      : "Compared execution step fields: unavailable.",
    inspectionCoverage?.step_command_argv_body_compared === false
      ? (
          "Step command argv/body: not exposed by the " +
          "inspection source and not compared."
        )
      : "Step command argv/body coverage: see JSON output.",
  );

  if (sameUnknownDisclosureCoverage) {
    lines.push(
      approvedUnknownDisclosures.length
        ? (
            "Unknown disclosure fields on both releases: " +
            safeText(
              approvedUnknownDisclosures.join(", "),
              240
            ) +
            "."
          )
        : "Unknown disclosure fields on both releases: none."
    );
  } else {
    lines.push(
      "Approved unknown disclosure fields: " +
        (
          approvedUnknownDisclosures.length
            ? safeText(
                approvedUnknownDisclosures.join(", "),
                240
              )
            : "none"
        ) +
        ".",
      "Candidate unknown disclosure fields: " +
        (
          candidateUnknownDisclosures.length
            ? safeText(
                candidateUnknownDisclosures.join(", "),
                240
              )
            : "none"
        ) +
        "."
    );
  }

  lines.push(
    "",
    "REASON CODES",
    ...(reasonCodes.length
      ? reasonCodes.map((code: string) => `- ${code}`)
      : ["- none"]),
  );
} else {
  lines.push(
    "REVIEW BLOCKED",
    `${safeText(
      comparison?.error_code ?? "REVIEW_DID_NOT_COMPLETE",
      120
    )}`,
    safeText(
      comparison?.detail ??
      review.stderr ??
      "No further detail available."
    ),
  );
}

lines.push(
  "",
  "BOUNDARY",
  "Neither reviewed Play was executed.",
  "This review does not establish behavioral equivalence or safety.",
  "Step command argv/body is not exposed by the current inspection source and is not compared.",
  "Unknown disclosure fields remain unknown; they are never treated as none.",
);

out.human(lines.join("\n"));

out.summary(
  comparison?.ok === true
    ? `${humanVerdict} — ${materialCount} material change type(s)`
    : `BLOCKED — ${comparison?.error_code ?? "review did not complete"}`
);

out.result({
  schema: "play-change-review/presentation-v1",
  verdict,
  comparison,
  stage_ledger: {
    review_versions: review.status,
  },
  representations: {
    human:
      "complete — verdict, identities, bounded findings, complete counts/reason codes, inspection coverage and review boundary",
    json:
      "canonical — complete verdict, counts and reason codes with bounded deterministic evidence or a structured blocked reason",
    summary:
      "intentionally lossy — verdict and material change-type count",
  },
});
