#!/usr/bin/env python3

import json
import re
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
        "inspection_coverage":
            result.get("inspection_coverage", {}),
        "disclosure_unknowns":
            result.get("disclosure_unknowns", []),
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
        "comparison_performed": False,
        "reviewed_plays_executed": False,
    }, separators=(",", ":")))
    raise SystemExit(2)


def parse_inspection(raw, label):
    try:
        wrapper = json.loads(raw)
    except Exception:
        fail(f"{label}: inspect output was not valid JSON")

    if not isinstance(wrapper, dict) or wrapper.get("ok") is not True:
        fail(f"{label}: inspection did not succeed")

    try:
        value = wrapper["data"]["play_inspect"]
        if not isinstance(value, dict):
            fail(f"{label}: play_inspect was not an object")
        return value
    except Exception:
        fail(f"{label}: play_inspect object missing")


def identity(play):
    value = play.get("identity")
    if not isinstance(value, dict) or not all(
        isinstance(value.get(key), str) and value[key].strip()
        for key in ("owner", "name", "version")
    ):
        fail("Inspection identity was unavailable or malformed")
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
    for value in values:
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
    for value in values:
        result[value[key]] = value
    return result


def endpoint_map(values):
    # Endpoint identities have been validated. Missing fingerprints remain
    # None and have their own unavailable coverage; they are never identities.
    result = {}
    for value in values:
        endpoint = value if isinstance(value, str) else value["endpoint"]
        fingerprint = value.get("mcp_fingerprint") if isinstance(value, dict) else None
        result[endpoint] = {"endpoint": endpoint,
                            "mcp_fingerprint": fingerprint if text_value(fingerprint) else None}
    return result


def auth_adapter_map(values):
    result = {}
    for value in values:
        if isinstance(value, str):
            result[value] = {"credential_names": None, "protocols": None}
        else:
            result[value["adapter"]] = {
                "credential_names": value.get("credential_names"),
                "protocols": value.get("protocols"),
            }
    return result


def string_set(values):
    # Called only for a validated, comparable credential/protocol domain.
    return set(values)


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


# Evidence is classified before normalization. Fixed domain names keep coverage
# bounded; no user-provided member names are copied into the coverage schema.
MISSING = object()
MALFORMED_PARENT = object()
KNOWN = "known_valid"
UNKNOWN = "unknown"
MALFORMED = "malformed"
UNSUPPORTED = "unsupported"
STEP_FIELDS = ["name", "kind", "target", "operation", "depends_on"]


def object_value(value):
    """Container access only; evidence_for classifies the original raw shape."""
    return value if isinstance(value, dict) else {}


def path_value(play, path):
    value = play
    for key in path.split("."):
        if value is MISSING or value is None:
            return value
        if not isinstance(value, dict):
            return MALFORMED_PARENT
        value = value.get(key, MISSING)
    return value


def text_value(value):
    return isinstance(value, str) and bool(value.strip())


def value_state(value, valid):
    if value is MISSING or value is None:
        return UNKNOWN
    return KNOWN if valid(value) else MALFORMED


def list_state(value, valid_member):
    return value_state(value, lambda v: isinstance(v, list) and all(valid_member(x) for x in v))


def named(value, key):
    return isinstance(value, dict) and text_value(value.get(key))


def parameter_valid(value):
    if not (named(value, "name") and text_value(value.get("type"))
            and type(value.get("required")) is bool):
        return False
    # These optional fields are omitted/null when no default/acceptance set/UI
    # was declared by the current provider. Their omission is not an empty
    # parameters collection. JSON defaults retain type-sensitive equality.
    if value.get("valid_values") is not None and not isinstance(value["valid_values"], list):
        return False
    ui = value.get("input")
    if ui is None:
        return True
    if not isinstance(ui, dict):
        return False
    choices = ui.get("choices")
    return choices is None or (isinstance(choices, list) and all(
        isinstance(x, dict) and "value" in x for x in choices))


def step_valid(value):
    return (named(value, "name") and all(text_value(value.get(k))
            for k in ("kind", "target", "operation"))
            # Rote omits depends_on for roots; explicit null/wrong types are
            # not that documented omission convention.
            and ("depends_on" not in value or list_state(value["depends_on"], text_value) == KNOWN))


def runtime_valid(value):
    return (named(value, "name") and type(value.get("required")) is bool
            and all(isinstance(value.get(k), str) for k in ("managed_by", "reason")))


def tool_valid(value):
    return (named(value, "id") and text_value(value.get("command"))
            and type(value.get("required")) is bool
            and (value.get("version_requirement") is None
                 or text_value(value["version_requirement"])))


def artifact_evidence(value, digest=False):
    state = value_state(value, text_value)
    if state != KNOWN:
        return {"state": state, "value": None}
    prefix = "installed-package-sha256-v1:" if digest else ""
    if digest and not value.startswith(prefix):
        state = UNSUPPORTED
    elif re.fullmatch(re.escape(prefix) + r"[0-9a-fA-F]{64}", value):
        return {"state": KNOWN, "value": value.lower()}
    else:
        state = MALFORMED
    return {"state": state, "value": None}


def privilege_state(value):
    state = value_state(value, text_value)
    if state == KNOWN and value not in ("none", "browser", "process", "process_and_browser"):
        return UNSUPPORTED
    return state


def nested_list_state(collection, identity_key, field):
    state = list_state(collection, lambda x: text_value(x) or named(x, identity_key))
    if state != KNOWN:
        return state
    states = [list_state(x.get(field, MISSING), text_value)
              if isinstance(x, dict) else UNKNOWN for x in collection]
    return MALFORMED if MALFORMED in states else UNKNOWN if UNKNOWN in states else KNOWN


def evidence_for(play):
    result = {}
    validators = {
        "parameters": parameter_valid,
        "steps": step_valid,
        "requirements.runtimes": runtime_valid,
        "package.tools": tool_valid,
        "package.files": text_value,
        "requirements.npm_packages": text_value,
        "requirements.browser_binaries": text_value,
        "requirements.write_permissions": lambda x: text_value(x) or (
            isinstance(x, dict) and all(text_value(x.get(k)) for k in ("tool", "adapter", "mode"))),
        "requirements.endpoints": lambda x: text_value(x) or named(x, "endpoint"),
        "authentication.adapters": lambda x: text_value(x) or named(x, "adapter"),
    }
    for domain, valid in validators.items():
        result[domain] = list_state(path_value(play, domain), valid)
    result["authentication.read_only"] = value_state(
        path_value(play, "authentication.read_only"), lambda x: type(x) is bool)
    result["execution.privileged_access"] = privilege_state(path_value(play, "execution.privileged_access"))
    for field in ("credential_names", "protocols"):
        result["authentication." + field] = nested_list_state(
            path_value(play, "authentication.adapters"), "adapter", field)
    endpoints = path_value(play, "requirements.endpoints")
    state = result["requirements.endpoints"]
    if state == KNOWN:
        states = [value_state(x.get("mcp_fingerprint", MISSING), text_value)
                  if isinstance(x, dict) else UNKNOWN for x in endpoints]
        state = MALFORMED if MALFORMED in states else UNKNOWN if UNKNOWN in states else KNOWN
    result["requirements.endpoint_fingerprints"] = state
    result["archive.content_hash"] = artifact_evidence(path_value(play, "archive.content_hash"))["state"]
    result["package.digest"] = artifact_evidence(path_value(play, "package.digest"), True)["state"]
    result["package.authority"] = value_state(path_value(play, "package.authority"), text_value)
    return result


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
    requirements = object_value(play.get("requirements"))
    package = object_value(play.get("package"))
    authentication = object_value(play.get("authentication"))

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

approved_evidence = evidence_for(approved)
candidate_evidence = evidence_for(candidate)


def comparable(domain):
    return approved_evidence[domain] == KNOWN and candidate_evidence[domain] == KNOWN


comparison_domains = {
    domain: {"approved": approved_evidence[domain], "candidate": candidate_evidence[domain],
             "comparable": comparable(domain)}
    for domain in sorted(approved_evidence)
}
comparison_complete = all(row["comparable"] for row in comparison_domains.values())
access_comparison_complete = all(comparable(domain) for domain in (
    "execution.privileged_access", "requirements.write_permissions", "requirements.endpoints",
    "authentication.read_only", "authentication.adapters", "authentication.credential_names",
    "authentication.protocols", "requirements.endpoint_fingerprints",
))


old_hash = artifact_evidence(path_value(approved, "archive.content_hash"))["value"]
new_hash = artifact_evidence(path_value(candidate, "archive.content_hash"))["value"]
old_digest = artifact_evidence(path_value(approved, "package.digest"), True)["value"]
new_digest = artifact_evidence(path_value(candidate, "package.digest"), True)["value"]

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


old_package = object_value(approved.get("package"))
new_package = object_value(candidate.get("package"))

old_files_disclosed = approved_evidence["package.files"] == KNOWN
old_files = old_package.get("files")

new_files_disclosed = candidate_evidence["package.files"] == KNOWN
new_files = new_package.get("files")

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


old_authority = (path_value(approved, "package.authority")
                 if approved_evidence["package.authority"] == KNOWN else None)
new_authority = (path_value(candidate, "package.authority")
                 if candidate_evidence["package.authority"] == KNOWN else None)

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

if comparable("parameters"):
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
            if canonical(old.get(field)) != canonical(new.get(field)):
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
            if canonical(old.get(field)) != canonical(new.get(field)):
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

old_exec = object_value(approved.get("execution"))
new_exec = object_value(candidate.get("execution"))

old_priv = old_exec.get("privileged_access")
new_priv = new_exec.get("privileged_access")


def privileged_access_capabilities(value):
    if value == "none":
        return frozenset()

    if value == "browser":
        return frozenset({"browser"})

    if value == "process":
        return frozenset({"process"})

    if value == "process_and_browser":
        return frozenset({
            "browser",
            "process",
        })

    # Unknown/future privilege declarations remain comparable
    # as changed values, but PCR must not invent component
    # semantics for them.
    return None


old_priv_capabilities = (
    privileged_access_capabilities(old_priv)
)

new_priv_capabilities = (
    privileged_access_capabilities(new_priv)
)


declared_access_expansion = False

if comparable("execution.privileged_access") and old_priv != new_priv:
    add(
        "PRIVILEGED_ACCESS_CHANGED",
        "access",
        f"{old_priv!r} -> {new_priv!r}",
    )

    if (
        old_priv_capabilities is not None
        and new_priv_capabilities is not None
        and (
            new_priv_capabilities
            - old_priv_capabilities
        )
    ):
        declared_access_expansion = True


old_req = object_value(approved.get("requirements"))
new_req = object_value(candidate.get("requirements"))

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
    if not comparable("requirements." + field):
        continue
    added, removed = set_delta(old_req[field], new_req[field])

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

old_endpoints_disclosed = approved_evidence["requirements.endpoints"] == KNOWN
new_endpoints_disclosed = candidate_evidence["requirements.endpoints"] == KNOWN
old_endpoints_raw = old_req.get("endpoints")
new_endpoints_raw = new_req.get("endpoints")

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


old_auth = object_value(approved.get("authentication"))
new_auth = object_value(candidate.get("authentication"))

if comparable("authentication.read_only") and old_auth.get("read_only") != new_auth.get("read_only"):
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


old_auth_adapters = (auth_adapter_map(old_auth["adapters"])
                     if comparable("authentication.adapters") else {})

new_auth_adapters = (auth_adapter_map(new_auth["adapters"])
                     if comparable("authentication.adapters") else {})

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

    if comparable("authentication.credential_names"):
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


    if comparable("authentication.protocols"):
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

if comparable("requirements.runtimes"):
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


if comparable("package.tools"):
    old_tools = by_name(
        object_value(approved.get("package")).get("tools"),
        key="id",
    )

    new_tools = by_name(
        object_value(candidate.get("package")).get("tools"),
        key="id",
    )

    for name in sorted(old_tools.keys() - new_tools.keys()):
        add(
            "TOOL_REQUIREMENT_REMOVED",
            "runtime",
            f"{name}: removed",
            material=old_tools[name]["required"],
        )

    for name in sorted(new_tools.keys() - old_tools.keys()):
        add(
            "TOOL_REQUIREMENT_ADDED",
            "runtime",
            f"{name}: added",
            material=new_tools[name]["required"],
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
                material=old["required"] or new["required"],
            )


# ------------------------------------------------------------------
# Execution graph
# ------------------------------------------------------------------

old_steps = by_name(approved["steps"]) if comparable("steps") else {}
new_steps = by_name(candidate["steps"]) if comparable("steps") else {}

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

    old_deps = sorted(old.get("depends_on", []))
    new_deps = sorted(new.get("depends_on", []))

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

DISCLOSURE_FIELDS = (
    "adapter_credentials",
    "browser_auth",
    "sensitivity",
)


def unknown_disclosure_fields(play):
    requirements = object_value(play.get("requirements"))

    return sorted(
        field
        for field in DISCLOSURE_FIELDS
        if (
            not isinstance(requirements.get(field), dict)
            or requirements[field].get("status") != "known"
        )
    )


approved_unknown_disclosures = sorted(set(unknown_disclosure_fields(approved)) | {
    domain for domain, state in approved_evidence.items() if state != KNOWN
})

candidate_unknown_disclosures = sorted(set(unknown_disclosure_fields(candidate)) | {
    domain for domain, state in candidate_evidence.items() if state != KNOWN
})


disclosure_unknowns = sorted(
    [
        f"approved.{field}"
        for field in approved_unknown_disclosures
    ]
    + [
        f"candidate.{field}"
        for field in candidate_unknown_disclosures
    ]
)


if (
    approved_unknown_disclosures
    != candidate_unknown_disclosures
):
    add(
        "DISCLOSURE_COVERAGE_CHANGED",
        "disclosure",
        (
            "Unknown disclosure-field coverage changed: "
            "approved=["
            + ", ".join(approved_unknown_disclosures)
            + "], candidate=["
            + ", ".join(candidate_unknown_disclosures)
            + "]."
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
    "CANDIDATE_PACKAGE_NOT_VERIFIED",
    "ARTIFACT_IDENTITY_DISCLOSURE_CHANGED",
    "PACKAGE_FILESET_DISCLOSURE_CHANGED",
    "PACKAGE_AUTHORITY_DISCLOSURE_CHANGED",
    "DECLARED_ENDPOINT_DISCLOSURE_CHANGED",
    "ENDPOINT_FINGERPRINT_DISCLOSURE_CHANGED",
    "DISCLOSURE_COVERAGE_CHANGED",
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

elif not comparison_complete:
    verdict = "COMPARISON_INCOMPLETE"

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
    "comparison_performed": any(row["comparable"] for row in comparison_domains.values()),

    "approved": {
        "identity": identity_text(aid),
        "content_hash": old_hash,
        "package_digest": old_digest,
        "step_count": len(old_steps) if comparable("steps") else None,
    },

    "candidate": {
        "identity": identity_text(cid),
        "content_hash": new_hash,
        "package_digest": new_digest,
        "step_count": len(new_steps) if comparable("steps") else None,
    },

    "declared_access_expansion_observed":
        declared_access_expansion if access_comparison_complete else None,

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

    "inspection_coverage": {
        "source": "rote play inspect --json",

        "comparison_complete": comparison_complete,
        "access_comparison_complete": access_comparison_complete,
        "domains": comparison_domains,
        "execution_step_fields_compared": STEP_FIELDS if comparable("steps") else [],
        "additional_disclosure_contents_compared": False,

        "step_command_argv_body_compared": False,

        "step_command_argv_body_status":
            "not_exposed_by_inspection_source",

        "approved_unknown_disclosure_fields":
            approved_unknown_disclosures,

        "candidate_unknown_disclosure_fields":
            candidate_unknown_disclosures,
    },

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
        disclosure_unknowns,

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
            "Step command argv/body is not exposed by the current "
            "inspection source and is not compared."
        ),
        (
            "Unknown disclosure fields remain unknown; they are not "
            "treated as none."
        ),
    ],
}

emit_result(result)
