#!/usr/bin/env -S rote play run
/**
 * Compare two immutable Rote Play releases before trusting the newer method.
 *
 * @rote-frontmatter
 * ---
 * name: play-change-review
 * description: "You trusted one Play version. What changed in the next one? Compares two immutable releases of the same Play across inputs, declared access, runtime requirements, execution structure and artifact identity without executing either reviewed Play."
 * provenance:
 *   author: Sai
 * metadata:
 *   rote_version: 0.78.0
 *   version: 0.1.0
 *   status: draft
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

if (review.stdout.length > 0) {
  try {
    comparison = JSON.parse(review.stdout);
  } catch {}
}

const verdict = comparison?.verdict ?? "BLOCKED";

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

const lines: string[] = [
  "PLAY CHANGE REVIEW",
  "",
  `APPROVED   ${safeText(approvedIdentity)}`,
  `CANDIDATE  ${safeText(candidateIdentity)}`,
  "",
  `VERDICT    ${verdict}`,
  "",
];

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
      `… ${changes.length - 20} more finding(s) in JSON output`
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
  "Unknown disclosure fields remain unknown; they are never treated as none.",
);

out.human(lines.join("\n"));

out.summary(
  comparison?.ok === true
    ? `${verdict} — ${materialCount} material change type(s)`
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
      "complete — verdict, identities, findings, reason codes and review boundary",
    json:
      "canonical — full comparison evidence or structured blocked reason",
    summary:
      "intentionally lossy — verdict and material change-type count",
  },
});
