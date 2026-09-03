#!/usr/bin/env python3

import json
import sys
from pathlib import Path


# Keep canonical comparison output comfortably below the
# process-step capture boundary observed during adversarial
# scale testing.
#
# These limits affect evidence representation only.
# Verdicts, counts, and reason-code sets are computed from the
# complete comparison before evidence is bounded.
MAX_CHANGE_EVIDENCE = 24
MAX_CHANGE_DETAIL_CHARS = 240
MAX_FILE_EVIDENCE_PER_DIRECTION = 8
MAX_FILE_PATH_CHARS = 240
MAX_RESULT_BYTES = 32768


def bounded_text(value, limit):
    raw = str(value)

    if len(raw) <= limit:
        return raw

    return raw[:limit] + "...[truncated]"


def encode_result(value):
    return json.dumps(
        value,
        separators=(",", ":"),
    )


def emit_result(result):
    """
    Emit a comparison result within PCR's own output budget.

    Normal comparison semantics are computed before this function.
    This function may only reduce evidence samples; it must never
    alter the verdict, complete counts, or reason-code set.
    """

    encoded = encode_result(result)

    if len(encoded.encode("utf-8")) <= MAX_RESULT_BYTES:
        print(encoded)
        return

    # Emergency second-stage compaction.
    #
    # The normal evidence bounds should already keep ordinary
    # results well below MAX_RESULT_BYTES. This layer exists so
    # future schema/detail growth cannot silently cross Rote's
    # process-output boundary.
    evidence = result.get("change_evidence")

    if isinstance(evidence, dict):
        total = evidence.get(
            "total",
            len(result.get("changes") or []),
        )

        result["changes"] = []

        evidence["returned"] = 0
        evidence["omitted"] = total
        evidence["truncated"] = total > 0

    package_files = result.get("package_files")

    if isinstance(package_files, dict):
        added_total = package_files.get("added_total")
        removed_total = package_files.get("removed_total")

        package_files["added"] = []
        package_files["removed"] = []

        if isinstance(added_total, int):
            package_files["added_omitted"] = added_total

        if isinstance(removed_total, int):
            package_files["removed_omitted"] = removed_total

        package_files["truncated"] = bool(
            (isinstance(added_total, int) and added_total > 0)
            or
            (isinstance(removed_total, int) and removed_total > 0)
        )

    result["output_budget"] = {
        "compacted": True,
        "target_bytes": MAX_RESULT_BYTES,
        "detail": (
            "Evidence samples were removed to preserve the "
            "complete verdict, counts, and reason codes."
        ),
    }

    encoded = encode_result(result)

    if len(encoded.encode("utf-8")) <= MAX_RESULT_BYTES:
        print(encoded)
        return

    # Final fail-safe representation.
    #
    # Preserve semantic conclusions even if some future field
    # unexpectedly becomes enormous. Do not fall back to a fake
    # generic BLOCKED result merely because evidence was large.
    compact = {
        "schema": result.get(
            "schema",
            "play-change-review/v1",
        ),
        "ok": result.get("ok"),
        "verdict": result.get("verdict"),
        "comparison_performed": result.get(
            "comparison_performed"
        ),
        "approved": result.get("approved"),
        "candidate": result.get("candidate"),
        "declared_access_expansion_observed":
            result.get(
                "declared_access_expansion_observed"
            ),
        "counts": result.get("counts"),
        "reason_codes": result.get("reason_codes", []),
        "changes": [],
        "change_evidence": {
            "total": (
                result.get("counts", {})
                .get("total_findings", 0)
            ),
            "returned": 0,
            "omitted": (
                result.get("counts", {})
                .get("total_findings", 0)
            ),
            "truncated": True,
        },
        "reviewed_plays_executed":
            result.get(
                "reviewed_plays_executed",
                False,
            ),
        "limitations":
            result.get("limitations", []),
        "output_budget": {
            "compacted": True,
            "target_bytes": MAX_RESULT_BYTES,
            "detail": (
                "All individual evidence samples were removed "
                "to preserve complete semantic conclusions."
            ),
        },
    }

    encoded = encode_result(compact)

    if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
        # This should be unreachable with PCR-controlled fields.
        # If it ever happens, fail explicitly rather than allowing
        # Rote to silently lose process output.
        tiny = {
            "schema": "play-change-review/v1",
            "ok": False,
            "verdict": "BLOCKED",
            "error_code": "RESULT_BUDGET_EXCEEDED",
            "detail": (
                "PCR could not represent the comparison result "
                "within its bounded output contract."
            ),
            "reviewed_plays_executed": False,
        }

        print(encode_result(tiny))
        return

    print(encoded)


def fail(message):
    print(json.dumps({
        "schema": "play-change-review/v1",
        "ok": False,
        "verdict": "BLOCKED",
        "error": message,
    }, separators=(",", ":")))
    raise SystemExit(2)


def parse_inspection(raw, label):
    try:
        wrapper = json.loads(raw)
    except Exception:
        fail(f"{label}: inspect output was not valid JSON")

    if wrapper.get("ok") is not True:
        fail(f"{label}: inspection did not succeed")

    try:
        return wrapper["data"]["play_inspect"]
    except Exception:
        fail(f"{label}: play_inspect object missing")


def identity(play):
    value = play.get("identity", {})
    return {
        "owner": value.get("owner"),
        "name": value.get("name"),
        "version": value.get("version"),
    }


def identity_text(value):
    return (
        f"{value.get('owner')}/"
        f"{value.get('name')}@"
        f"{value.get('version')}"
    )


def emit_comparison_blocked(
    code,
    detail,
    approved_identity=None,
    candidate_identity=None,
):
    """
    Return a valid comparison-level BLOCKED result.

    This is distinct from fail(), which represents comparator
    execution/input failure and exits nonzero.

    Ambiguous inspection evidence is a valid review conclusion:
    PCR successfully inspected the releases but cannot compare
    contradictory semantic identities safely.
    """

    result = {
        "schema": "play-change-review/v1",
        "ok": False,
        "verdict": "BLOCKED",
        "comparison_performed": False,
        "error_code": code,
        "detail": bounded_text(
            detail,
            1000,
        ),
        "approved": {
            "identity": (
                identity_text(approved_identity)
                if approved_identity
                else "unavailable"
            ),
        },
        "candidate": {
            "identity": (
                identity_text(candidate_identity)
                if candidate_identity
                else "unavailable"
            ),
        },
        "reason_codes": [code],
        "reviewed_plays_executed": False,
        "limitations": [
            (
                "The inspected release structure was ambiguous, "
                "so no semantic comparison was performed."
            ),
            "Neither reviewed Play was executed.",
        ],
    }

    emit_result(result)
    raise SystemExit(0)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def disclosed_value(obj, field):
    """
    Distinguish unknown disclosure from an explicitly
    disclosed empty value.

    Missing key or explicit null => not disclosed.
    Any non-null value => disclosed.

    Type validation remains a separate hardening concern;
    this helper deliberately does not broaden Stage 2A.
    """
    if not isinstance(obj, dict):
        return False, None

    if field not in obj:
        return False, None

    value = obj[field]

    if value is None:
        return False, None

    return True, value


def normalized_valid_values(value):
    """
    valid_values is an acceptance set, not an ordered UI list.

    Preserve None/non-list shapes for compatibility, but
    compare actual lists as canonical value sets so ordering
    and duplicate entries do not create false method changes.
    """
    if not isinstance(value, list):
        return value

    return sorted({
        canonical(item)
        for item in value
    })


def set_map(values):
    result = {}
    for value in values or []:
        result[canonical(value)] = value
    return result


def set_delta(old_values, new_values):
    old_map = set_map(old_values)
    new_map = set_map(new_values)

    added = [
        new_map[key]
        for key in sorted(new_map.keys() - old_map.keys())
    ]

    removed = [
        old_map[key]
        for key in sorted(old_map.keys() - new_map.keys())
    ]

    return added, removed


def duplicate_identity(
    values,
    key,
    label,
    allow_string=False,
):
    """
    Detect ambiguous duplicate semantic identities without
    broadening this stage into general schema validation.

    Missing/unrecognized entries retain existing behavior.
    Only two recognized entries claiming the same semantic
    identity are rejected here.
    """

    if not isinstance(values, list):
        return None

    seen = set()

    for value in values:
        identity_value = None

        if (
            allow_string
            and isinstance(value, str)
            and value
        ):
            identity_value = value

        elif isinstance(value, dict):
            candidate = value.get(key)

            if candidate:
                identity_value = str(candidate)

        if identity_value is None:
            continue

        identity_value = str(identity_value)

        if identity_value in seen:
            return (
                f"{label} contains duplicate semantic "
                f"identity {identity_value!r}."
            )

        seen.add(identity_value)

    return None


def by_name(values, key="name"):
    result = {}
    for value in values or []:
        if isinstance(value, dict) and value.get(key):
            result[str(value[key])] = value
    return result


def endpoint_map(values):
    result = {}

    for value in values or []:
        # Some resolved contracts expose endpoints as plain strings.
        if isinstance(value, str) and value:
            result[value] = {
                "endpoint": value,
                "mcp_fingerprint": None,
            }
            continue

        # Newer/richer contracts may expose structured endpoint
        # identity including an MCP fingerprint.
        if not isinstance(value, dict):
            continue

        endpoint = value.get("endpoint")

        if not endpoint:
            continue

        endpoint = str(endpoint)

        result[endpoint] = {
            "endpoint": endpoint,
            "mcp_fingerprint": value.get("mcp_fingerprint"),
        }

    return result


def auth_adapter_map(values):
    """
    Normalize authentication adapters to declared contract only.

    Deliberately ignored as dynamic/reviewer-local state:
    - status
    - credentials
    - reason

    Compared as version semantics:
    - adapter
    - credential_names
    - protocols
    """
    result = {}

    for value in values or []:
        if isinstance(value, str) and value:
            result[value] = {
                "adapter": value,
                "credential_names": [],
                "protocols": [],
            }
            continue

        if not isinstance(value, dict):
            continue

        adapter = value.get("adapter")

        if not adapter:
            continue

        adapter = str(adapter)

        credential_names = sorted({
            str(item)
            for item in (value.get("credential_names") or [])
            if item is not None
        })

        protocols = sorted({
            str(item)
            for item in (value.get("protocols") or [])
            if item is not None
        })

        result[adapter] = {
            "adapter": adapter,
            "credential_names": credential_names,
            "protocols": protocols,
        }

    return result


def string_set(values):
    return {
        str(value)
        for value in (values or [])
        if value is not None
    }


def parameter_ui_choices(parameter):
    input_meta = parameter.get("input") or {}
    choices = input_meta.get("choices")

    if not isinstance(choices, list):
        return None

    values = []

    for choice in choices:
        if isinstance(choice, dict) and "value" in choice:
            values.append(choice["value"])

    return values


if len(sys.argv) == 4 and sys.argv[1] == "--files":
    approved_raw = Path(sys.argv[2]).read_text()
    candidate_raw = Path(sys.argv[3]).read_text()
elif len(sys.argv) == 3:
    approved_raw = sys.argv[1]
    candidate_raw = sys.argv[2]
else:
    fail("usage: compare_inspections.py OLD_JSON NEW_JSON or --files OLD_FILE NEW_FILE")

approved = parse_inspection(approved_raw, "approved")
candidate = parse_inspection(candidate_raw, "candidate")

aid = identity(approved)
cid = identity(candidate)


def check_ambiguous_structure(
    play,
    side,
    approved_identity,
    candidate_identity,
):
    requirements = play.get("requirements") or {}
    package = play.get("package") or {}
    authentication = play.get("authentication") or {}

    checks = (
        (
            play.get("parameters"),
            "name",
            f"{side}.parameters",
            False,
        ),
        (
            play.get("steps"),
            "name",
            f"{side}.steps",
            False,
        ),
        (
            requirements.get("runtimes"),
            "name",
            f"{side}.requirements.runtimes",
            False,
        ),
        (
            package.get("tools"),
            "id",
            f"{side}.package.tools",
            False,
        ),
        (
            requirements.get("endpoints"),
            "endpoint",
            f"{side}.requirements.endpoints",
            True,
        ),
        (
            authentication.get("adapters"),
            "adapter",
            f"{side}.authentication.adapters",
            True,
        ),
    )

    for values, key, label, allow_string in checks:
        detail = duplicate_identity(
            values,
            key,
            label,
            allow_string=allow_string,
        )

        if detail is not None:
            emit_comparison_blocked(
                "AMBIGUOUS_INSPECTION_STRUCTURE",
                detail,
                approved_identity,
                candidate_identity,
            )


check_ambiguous_structure(
    approved,
    "approved",
    aid,
    cid,
)

check_ambiguous_structure(
    candidate,
    "candidate",
    aid,
    cid,
)


changes = []


def add(code, domain, detail, material=True):
    changes.append({
        "code": code,
        "domain": domain,
        "material": material,
        "detail": bounded_text(
            detail,
            MAX_CHANGE_DETAIL_CHARS,
        ),
    })


def bounded_changes(values):
    """
    Return deterministic, diverse evidence.

    First preserve one representative for each reason-code type,
    then fill remaining capacity in original comparison order.

    Complete counts and reason_codes are computed from `changes`,
    never from this bounded sample.
    """

    if len(values) <= MAX_CHANGE_EVIDENCE:
        return list(values)

    selected = []
    selected_indexes = set()
    represented_codes = set()

    # One representative for each code while capacity remains.
    for index, change in enumerate(values):
        code = change.get("code")

        if code in represented_codes:
            continue

        selected.append(change)
        selected_indexes.add(index)
        represented_codes.add(code)

        if len(selected) >= MAX_CHANGE_EVIDENCE:
            return selected

    # Fill remaining capacity in original deterministic order.
    for index, change in enumerate(values):
        if len(selected) >= MAX_CHANGE_EVIDENCE:
            break

        if index in selected_indexes:
            continue

        selected.append(change)
        selected_indexes.add(index)

    return selected


def bounded_file_evidence(values):
    return [
        bounded_text(
            value,
            MAX_FILE_PATH_CHARS,
        )
        for value in values[
            :MAX_FILE_EVIDENCE_PER_DIRECTION
        ]
    ]


# ------------------------------------------------------------------
# Identity
# ------------------------------------------------------------------

same_play = (
    aid.get("owner") == cid.get("owner")
    and aid.get("name") == cid.get("name")
)

if not same_play:
    result = {
        "schema": "play-change-review/v1",
        "ok": True,
        "verdict": "IDENTITY_MISMATCH",
        "comparison_performed": False,
        "approved": {
            "identity": identity_text(aid),
        },
        "candidate": {
            "identity": identity_text(cid),
        },
        "reason_codes": ["IDENTITY_MISMATCH"],
        "changes": [],
        "reviewed_plays_executed": False,
        "limitations": [
            "Only releases of the same owner/name are compared.",
            "No behavioral equivalence or safety conclusion is made.",
        ],
    }

    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0)


# ------------------------------------------------------------------
# Artifact identity
# ------------------------------------------------------------------

old_hash = (approved.get("archive") or {}).get("content_hash")
new_hash = (candidate.get("archive") or {}).get("content_hash")

old_digest = (approved.get("package") or {}).get("digest")
new_digest = (candidate.get("package") or {}).get("digest")

hash_changed = (
    old_hash is not None
    and new_hash is not None
    and old_hash != new_hash
)

digest_changed = (
    old_digest is not None
    and new_digest is not None
    and old_digest != new_digest
)

hash_disclosure_changed = (
    (old_hash is None) != (new_hash is None)
)

digest_disclosure_changed = (
    (old_digest is None) != (new_digest is None)
)

implementation_changed = (
    hash_changed or digest_changed
)

artifact_identity_disclosure_changed = (
    hash_disclosure_changed
    or digest_disclosure_changed
)

same_version = aid.get("version") == cid.get("version")

if same_version and implementation_changed:
    add(
        "IMMUTABLE_RELEASE_IDENTITY_CHANGED",
        "artifact",
        (
            "The same owner/name@version resolved to different "
            "known content identity."
        ),
    )

elif implementation_changed:
    add(
        "IMPLEMENTATION_CHANGED",
        "artifact",
        "Known content hash and/or package digest changed.",
        material=False,
    )

if artifact_identity_disclosure_changed:
    parts = []

    if hash_disclosure_changed:
        parts.append(
            f"content_hash disclosure: {old_hash!r} -> {new_hash!r}"
        )

    if digest_disclosure_changed:
        parts.append(
            f"package digest disclosure: {old_digest!r} -> {new_digest!r}"
        )

    add(
        "ARTIFACT_IDENTITY_DISCLOSURE_CHANGED",
        "disclosure",
        "; ".join(parts),
        material=False,
    )


old_package = approved.get("package") or {}
new_package = candidate.get("package") or {}

old_files_disclosed, old_files = disclosed_value(
    old_package,
    "files",
)

new_files_disclosed, new_files = disclosed_value(
    new_package,
    "files",
)

files_comparison_available = (
    old_files_disclosed
    and new_files_disclosed
)

files_added = []
files_removed = []

if files_comparison_available:
    files_added, files_removed = set_delta(
        old_files,
        new_files,
    )

    if files_added or files_removed:
        add(
            "PACKAGE_FILESET_CHANGED",
            "artifact",
            (
                f"{len(files_added)} package file(s) added; "
                f"{len(files_removed)} removed."
            ),
            material=False,
        )

elif old_files_disclosed != new_files_disclosed:
    add(
        "PACKAGE_FILESET_DISCLOSURE_CHANGED",
        "disclosure",
        (
            "package.files disclosure changed: "
            f"approved="
            f"{'known' if old_files_disclosed else 'unknown'}, "
            f"candidate="
            f"{'known' if new_files_disclosed else 'unknown'}"
        ),
        material=False,
    )


old_authority = (approved.get("package") or {}).get("authority")
new_authority = (candidate.get("package") or {}).get("authority")

# Missing authority is unknown disclosure, not a negative trust claim.
#
# Both known + different:
#   actual declared authority changed.
#
# Known <-> missing:
#   disclosure changed; do not claim the package authority itself
#   became weaker or stronger.
if (
    old_authority is not None
    and new_authority is not None
    and old_authority != new_authority
):
    add(
        "PACKAGE_AUTHORITY_CHANGED",
        "artifact",
        f"{old_authority!r} -> {new_authority!r}",
    )

elif (old_authority is None) != (new_authority is None):
    add(
        "PACKAGE_AUTHORITY_DISCLOSURE_CHANGED",
        "disclosure",
        f"{old_authority!r} -> {new_authority!r}",
        material=False,
    )

# This is candidate trust state, not itself a version delta.
# Only make the statement when authority is explicitly present.
if (
    new_authority is not None
    and new_authority != "verified"
):
    add(
        "CANDIDATE_PACKAGE_NOT_VERIFIED",
        "artifact",
        f"Candidate package authority is {new_authority!r}.",
        material=False,
    )


# ------------------------------------------------------------------
# Parameters
# ------------------------------------------------------------------

old_params = by_name(approved.get("parameters"))
new_params = by_name(candidate.get("parameters"))

for name in sorted(old_params.keys() - new_params.keys()):
    add(
        "PARAMETER_REMOVED",
        "input",
        f"{name}: removed",
    )

for name in sorted(new_params.keys() - old_params.keys()):
    add(
        "PARAMETER_ADDED",
        "input",
        f"{name}: added",
    )

for name in sorted(old_params.keys() & new_params.keys()):
    old = old_params[name]
    new = new_params[name]

    for field, code in (
        ("type", "PARAMETER_TYPE_CHANGED"),
        ("required", "PARAMETER_REQUIRED_CHANGED"),
        ("default", "PARAMETER_DEFAULT_CHANGED"),
    ):
        if old.get(field) != new.get(field):
            add(
                code,
                "input",
                (
                    f"{name}.{field}: "
                    f"{old.get(field)!r} -> {new.get(field)!r}"
                ),
            )

    for field, code in (
        (
            "description",
            "PARAMETER_DESCRIPTION_CHANGED",
        ),
        (
            "example",
            "PARAMETER_EXAMPLE_CHANGED",
        ),
    ):
        if old.get(field) != new.get(field):
            add(
                code,
                "input",
                (
                    f"{name}.{field}: "
                    f"{old.get(field)!r} -> "
                    f"{new.get(field)!r}"
                ),
                material=False,
            )

    old_input = old.get("input") or {}
    new_input = new.get("input") or {}

    old_label = old_input.get("label")
    new_label = new_input.get("label")

    if old_label != new_label:
        add(
            "PARAMETER_LABEL_CHANGED",
            "input",
            (
                f"{name}.input.label: "
                f"{old_label!r} -> {new_label!r}"
            ),
            material=False,
        )

    old_valid = old.get("valid_values")
    new_valid = new.get("valid_values")

    old_valid_normalized = normalized_valid_values(
        old_valid
    )

    new_valid_normalized = normalized_valid_values(
        new_valid
    )

    if (
        old_valid_normalized
        != new_valid_normalized
    ):
        add(
            "PARAMETER_VALID_VALUES_CHANGED",
            "input",
            (
                f"{name}.valid_values: "
                f"{old_valid!r} -> {new_valid!r}"
            ),
        )

    old_choices = parameter_ui_choices(old)
    new_choices = parameter_ui_choices(new)

    if old_choices != new_choices:
        add(
            "PARAMETER_UI_CHOICES_CHANGED",
            "input",
            (
                f"{name}.input.choices: "
                f"{old_choices!r} -> {new_choices!r}"
            ),
            material=False,
        )

    old_allow_custom = (old.get("input") or {}).get("allow_custom")
    new_allow_custom = (new.get("input") or {}).get("allow_custom")

    if old_allow_custom != new_allow_custom:
        add(
            "PARAMETER_INPUT_UI_CHANGED",
            "input",
            (
                f"{name}.input.allow_custom: "
                f"{old_allow_custom!r} -> {new_allow_custom!r}"
            ),
            material=False,
        )


# ------------------------------------------------------------------
# Declared access and effects
# ------------------------------------------------------------------

old_exec = approved.get("execution") or {}
new_exec = candidate.get("execution") or {}

old_priv = old_exec.get("privileged_access")
new_priv = new_exec.get("privileged_access")

declared_access_expansion = False

if old_priv != new_priv:
    add(
        "PRIVILEGED_ACCESS_CHANGED",
        "access",
        f"{old_priv!r} -> {new_priv!r}",
    )

    if old_priv in (None, "", "none") and new_priv not in (
        None,
        "",
        "none",
    ):
        declared_access_expansion = True


old_req = approved.get("requirements") or {}
new_req = candidate.get("requirements") or {}

for field, domain, added_code, removed_code in (
    (
        "write_permissions",
        "access",
        "DECLARED_WRITE_EXPANDED",
        "DECLARED_WRITE_REDUCED",
    ),
    (
        "browser_binaries",
        "runtime",
        "BROWSER_REQUIREMENT_ADDED",
        "BROWSER_REQUIREMENT_REMOVED",
    ),
    (
        "npm_packages",
        "runtime",
        "NPM_REQUIREMENT_ADDED",
        "NPM_REQUIREMENT_REMOVED",
    ),
):
    added, removed = set_delta(
        old_req.get(field) or [],
        new_req.get(field) or [],
    )

    if added:
        add(
            added_code,
            domain,
            f"{field}: added {added!r}",
        )

        if field in ("write_permissions", "endpoints"):
            declared_access_expansion = True

    if removed:
        add(
            removed_code,
            domain,
            f"{field}: removed {removed!r}",
        )


# Endpoint identity is keyed by endpoint name.
# A fingerprint change is a material identity change, not an
# endpoint expansion.

old_endpoints_disclosed, old_endpoints_raw = (
    disclosed_value(
        old_req,
        "endpoints",
    )
)

new_endpoints_disclosed, new_endpoints_raw = (
    disclosed_value(
        new_req,
        "endpoints",
    )
)

endpoints_comparison_available = (
    old_endpoints_disclosed
    and new_endpoints_disclosed
)

if endpoints_comparison_available:
    old_endpoints = endpoint_map(
        old_endpoints_raw
    )

    new_endpoints = endpoint_map(
        new_endpoints_raw
    )

else:
    old_endpoints = {}
    new_endpoints = {}

    if (
        old_endpoints_disclosed
        != new_endpoints_disclosed
    ):
        add(
            "DECLARED_ENDPOINT_DISCLOSURE_CHANGED",
            "disclosure",
            (
                "requirements.endpoints disclosure changed: "
                f"approved="
                f"{'known' if old_endpoints_disclosed else 'unknown'}, "
                f"candidate="
                f"{'known' if new_endpoints_disclosed else 'unknown'}"
            ),
            material=False,
        )

for endpoint in sorted(
    old_endpoints.keys() - new_endpoints.keys()
):
    add(
        "DECLARED_ENDPOINT_REDUCED",
        "access",
        f"{endpoint}: removed",
    )

for endpoint in sorted(
    new_endpoints.keys() - old_endpoints.keys()
):
    add(
        "DECLARED_ENDPOINT_EXPANDED",
        "access",
        f"{endpoint}: added",
    )
    declared_access_expansion = True

for endpoint in sorted(
    old_endpoints.keys() & new_endpoints.keys()
):
    old_fp = old_endpoints[endpoint].get(
        "mcp_fingerprint"
    )

    new_fp = new_endpoints[endpoint].get(
        "mcp_fingerprint"
    )

    if (
        old_fp is not None
        and new_fp is not None
        and old_fp != new_fp
    ):
        add(
            "ENDPOINT_FINGERPRINT_CHANGED",
            "access",
            (
                f"{endpoint}: MCP fingerprint changed "
                f"from {old_fp!r} to {new_fp!r}"
            ),
        )

    elif (old_fp is None) != (new_fp is None):
        add(
            "ENDPOINT_FINGERPRINT_DISCLOSURE_CHANGED",
            "disclosure",
            (
                f"{endpoint}: MCP fingerprint disclosure changed "
                f"from {old_fp!r} to {new_fp!r}"
            ),
            material=False,
        )


old_auth = approved.get("authentication") or {}
new_auth = candidate.get("authentication") or {}

if old_auth.get("read_only") != new_auth.get("read_only"):
    add(
        "AUTHENTICATION_MODE_CHANGED",
        "access",
        (
            f"read_only: "
            f"{old_auth.get('read_only')!r} -> "
            f"{new_auth.get('read_only')!r}"
        ),
    )

    if (
        old_auth.get("read_only") is True
        and new_auth.get("read_only") is False
    ):
        declared_access_expansion = True


old_auth_adapters = auth_adapter_map(
    old_auth.get("adapters")
)

new_auth_adapters = auth_adapter_map(
    new_auth.get("adapters")
)

for adapter in sorted(
    old_auth_adapters.keys() -
    new_auth_adapters.keys()
):
    add(
        "AUTH_ADAPTER_REMOVED",
        "access",
        f"{adapter}: authentication adapter removed",
    )

for adapter in sorted(
    new_auth_adapters.keys() -
    old_auth_adapters.keys()
):
    add(
        "AUTH_ADAPTER_ADDED",
        "access",
        f"{adapter}: authentication adapter added",
    )
    declared_access_expansion = True

for adapter in sorted(
    old_auth_adapters.keys() &
    new_auth_adapters.keys()
):
    old_adapter = old_auth_adapters[adapter]
    new_adapter = new_auth_adapters[adapter]

    old_credentials = string_set(
        old_adapter.get("credential_names")
    )

    new_credentials = string_set(
        new_adapter.get("credential_names")
    )

    for credential in sorted(
        new_credentials - old_credentials
    ):
        add(
            "AUTH_CREDENTIAL_REQUIREMENT_ADDED",
            "authentication",
            (
                f"{adapter}: credential requirement "
                f"{credential!r} added"
            ),
        )

    for credential in sorted(
        old_credentials - new_credentials
    ):
        add(
            "AUTH_CREDENTIAL_REQUIREMENT_REMOVED",
            "authentication",
            (
                f"{adapter}: credential requirement "
                f"{credential!r} removed"
            ),
        )

    old_protocols = string_set(
        old_adapter.get("protocols")
    )

    new_protocols = string_set(
        new_adapter.get("protocols")
    )

    for protocol in sorted(
        new_protocols - old_protocols
    ):
        add(
            "AUTH_PROTOCOL_ADDED",
            "authentication",
            (
                f"{adapter}: authentication protocol "
                f"{protocol!r} added"
            ),
        )

    for protocol in sorted(
        old_protocols - new_protocols
    ):
        add(
            "AUTH_PROTOCOL_REMOVED",
            "authentication",
            (
                f"{adapter}: authentication protocol "
                f"{protocol!r} removed"
            ),
        )


# ------------------------------------------------------------------
# Runtime requirements
# ------------------------------------------------------------------

old_runtimes = by_name(old_req.get("runtimes"))
new_runtimes = by_name(new_req.get("runtimes"))

for name in sorted(old_runtimes.keys() - new_runtimes.keys()):
    add(
        "RUNTIME_REQUIREMENT_REMOVED",
        "runtime",
        f"{name}: removed",
    )

for name in sorted(new_runtimes.keys() - old_runtimes.keys()):
    add(
        "RUNTIME_REQUIREMENT_ADDED",
        "runtime",
        f"{name}: added",
    )

for name in sorted(old_runtimes.keys() & new_runtimes.keys()):
    old = old_runtimes[name]
    new = new_runtimes[name]

    comparable_old = {
        "required": old.get("required"),
        "managed_by": old.get("managed_by"),
        "reason": old.get("reason"),
    }

    comparable_new = {
        "required": new.get("required"),
        "managed_by": new.get("managed_by"),
        "reason": new.get("reason"),
    }

    if comparable_old != comparable_new:
        add(
            "RUNTIME_REQUIREMENT_CHANGED",
            "runtime",
            f"{name}: runtime contract changed",
        )


old_tools = by_name(
    (approved.get("package") or {}).get("tools"),
    key="id",
)

new_tools = by_name(
    (candidate.get("package") or {}).get("tools"),
    key="id",
)

for name in sorted(old_tools.keys() - new_tools.keys()):
    add(
        "TOOL_REQUIREMENT_REMOVED",
        "runtime",
        f"{name}: removed",
        material=False,
    )

for name in sorted(new_tools.keys() - old_tools.keys()):
    add(
        "TOOL_REQUIREMENT_ADDED",
        "runtime",
        f"{name}: added",
        material=False,
    )

for name in sorted(old_tools.keys() & new_tools.keys()):
    old = old_tools[name]
    new = new_tools[name]

    comparable_old = {
        "command": old.get("command"),
        "required": old.get("required"),
        "version_requirement": old.get("version_requirement"),
    }

    comparable_new = {
        "command": new.get("command"),
        "required": new.get("required"),
        "version_requirement": new.get("version_requirement"),
    }

    if comparable_old != comparable_new:
        add(
            "TOOL_REQUIREMENT_CHANGED",
            "runtime",
            f"{name}: tool requirement changed",
            material=False,
        )


# ------------------------------------------------------------------
# Execution graph
# ------------------------------------------------------------------

old_steps = by_name(approved.get("steps"))
new_steps = by_name(candidate.get("steps"))

graph_changed = False

for name in sorted(old_steps.keys() - new_steps.keys()):
    add(
        "STEP_REMOVED",
        "execution",
        f"{name}: removed",
    )
    graph_changed = True

for name in sorted(new_steps.keys() - old_steps.keys()):
    add(
        "STEP_ADDED",
        "execution",
        f"{name}: added",
    )
    graph_changed = True

for name in sorted(old_steps.keys() & new_steps.keys()):
    old = old_steps[name]
    new = new_steps[name]

    for field in ("kind", "target", "operation"):
        if old.get(field) != new.get(field):
            add(
                "STEP_CONTRACT_CHANGED",
                "execution",
                (
                    f"{name}.{field}: "
                    f"{old.get(field)!r} -> "
                    f"{new.get(field)!r}"
                ),
            )
            graph_changed = True

    old_deps = sorted(old.get("depends_on") or [])
    new_deps = sorted(new.get("depends_on") or [])

    if old_deps != new_deps:
        add(
            "STEP_DEPENDENCIES_CHANGED",
            "execution",
            (
                f"{name}.depends_on: "
                f"{old_deps!r} -> {new_deps!r}"
            ),
        )
        graph_changed = True

if graph_changed:
    add(
        "EXECUTION_GRAPH_CHANGED",
        "execution",
        (
            f"Step graph changed: "
            f"{len(old_steps)} -> {len(new_steps)} steps."
        ),
        material=False,
    )


# ------------------------------------------------------------------
# Disclosure completeness
# ------------------------------------------------------------------

unknown_disclosures = []

for side, play in (
    ("approved", approved),
    ("candidate", candidate),
):
    requirements = play.get("requirements") or {}

    for field in (
        "adapter_credentials",
        "browser_auth",
        "sensitivity",
    ):
        value = requirements.get(field)

        if isinstance(value, dict) and value.get("status") == "unknown":
            unknown_disclosures.append(f"{side}.{field}")

if unknown_disclosures:
    add(
        "DISCLOSURE_INCOMPLETE",
        "disclosure",
        (
            "Unknown disclosure field(s): "
            + ", ".join(sorted(unknown_disclosures))
        ),
        material=False,
    )


# ------------------------------------------------------------------
# Documentation only
# ------------------------------------------------------------------

old_description = (approved.get("identity") or {}).get("description")
new_description = (candidate.get("identity") or {}).get("description")

if old_description != new_description:
    add(
        "DOCUMENTATION_CHANGED",
        "documentation",
        "Play description changed.",
        material=False,
    )

old_identity_meta = approved.get("identity") or {}
new_identity_meta = candidate.get("identity") or {}

old_author = old_identity_meta.get("author")
new_author = new_identity_meta.get("author")

if old_author != new_author:
    add(
        "AUTHOR_CHANGED",
        "provenance",
        f"author: {old_author!r} -> {new_author!r}",
        material=False,
    )

old_visibility = old_identity_meta.get("visibility")
new_visibility = new_identity_meta.get("visibility")

if old_visibility != new_visibility:
    add(
        "VISIBILITY_CHANGED",
        "provenance",
        (
            f"visibility: "
            f"{old_visibility!r} -> {new_visibility!r}"
        ),
        material=False,
    )


# ------------------------------------------------------------------
# Immutable-release invariant
# ------------------------------------------------------------------

# These describe evidence quality rather than a difference between
# the approved and candidate release.
NON_DELTA_NOTICE_CODES = {
    "DISCLOSURE_INCOMPLETE",
    "CANDIDATE_PACKAGE_NOT_VERIFIED",
}

pre_verdict_delta_codes = {
    change["code"]
    for change in changes
    if change["code"] not in NON_DELTA_NOTICE_CODES
}

if (
    same_version
    and pre_verdict_delta_codes
    and "IMMUTABLE_RELEASE_IDENTITY_CHANGED"
        not in pre_verdict_delta_codes
):
    add(
        "IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED",
        "artifact",
        (
            "The same immutable owner/name@version exposed "
            "different compared release state."
        ),
    )


# ------------------------------------------------------------------
# Verdict
# ------------------------------------------------------------------

reason_codes = sorted({
    change["code"]
    for change in changes
})

material_changes = [
    change
    for change in changes
    if change["material"]
]

informational_changes = [
    change
    for change in changes
    if not change["material"]
]

delta_changes = [
    change
    for change in changes
    if change["code"] not in NON_DELTA_NOTICE_CODES
]

integrity_anomaly = (
    "IMMUTABLE_RELEASE_IDENTITY_CHANGED" in reason_codes
    or
    "IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED" in reason_codes
)

if integrity_anomaly:
    verdict = "INTEGRITY_ANOMALY"

elif (
    same_version
    and not implementation_changed
    and not delta_changes
):
    verdict = "EXACT_MATCH"

elif material_changes:
    verdict = "MATERIAL_METHOD_CHANGE"

elif implementation_changed:
    verdict = "IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT"

else:
    verdict = "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED"


bounded_change_list = bounded_changes(changes)

files_added_sample = bounded_file_evidence(
    files_added
)

files_removed_sample = bounded_file_evidence(
    files_removed
)


result = {
    "schema": "play-change-review/v1",
    "ok": True,
    "verdict": verdict,
    "comparison_performed": True,

    "approved": {
        "identity": identity_text(aid),
        "content_hash": old_hash,
        "package_digest": old_digest,
        "step_count": len(old_steps),
    },

    "candidate": {
        "identity": identity_text(cid),
        "content_hash": new_hash,
        "package_digest": new_digest,
        "step_count": len(new_steps),
    },

    "declared_access_expansion_observed":
        declared_access_expansion,

    "counts": {
        "material_types": len({
            change["code"] for change in material_changes
        }),
        "material_findings": len(material_changes),
        "informational_types": len({
            change["code"] for change in informational_changes
        }),
        "informational_findings": len(informational_changes),
        "total_findings": len(changes),
    },

    "reason_codes": reason_codes,

    # Evidence is deliberately bounded. Semantic totals above are
    # complete and are always computed before sampling.
    "changes": bounded_change_list,

    "change_evidence": {
        "total": len(changes),
        "returned": len(bounded_change_list),
        "omitted": (
            len(changes)
            - len(bounded_change_list)
        ),
        "truncated": (
            len(bounded_change_list)
            < len(changes)
        ),
    },

    "package_files": {
        "comparison_available":
            files_comparison_available,

        "approved_disclosed":
            old_files_disclosed,

        "candidate_disclosed":
            new_files_disclosed,

        "added_total": (
            len(files_added)
            if files_comparison_available
            else None
        ),

        "added": (
            files_added_sample
            if files_comparison_available
            else []
        ),

        "added_omitted": (
            (
                len(files_added)
                - len(files_added_sample)
            )
            if files_comparison_available
            else None
        ),

        "removed_total": (
            len(files_removed)
            if files_comparison_available
            else None
        ),

        "removed": (
            files_removed_sample
            if files_comparison_available
            else []
        ),

        "removed_omitted": (
            (
                len(files_removed)
                - len(files_removed_sample)
            )
            if files_comparison_available
            else None
        ),

        "truncated": (
            files_comparison_available
            and (
                len(files_added_sample)
                    < len(files_added)
                or
                len(files_removed_sample)
                    < len(files_removed)
            )
        ),
    },

    "disclosure_unknowns":
        sorted(unknown_disclosures),

    "reviewed_plays_executed": False,

    "limitations": [
        (
            "This compares registry-visible declared contracts and "
            "artifact identity; it does not establish behavioral "
            "equivalence."
        ),
        (
            "No safety or maliciousness conclusion is made from an "
            "unchanged declared contract."
        ),
        (
            "Unknown disclosure fields remain unknown; they are not "
            "treated as none."
        ),
    ],
}

emit_result(result)
