#!/usr/bin/env python3

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COMPARATOR = ROOT / "resources" / "compare_inspections.py"
VALIDATOR = ROOT / "resources" / "validate_ref.py"

FIXTURES = ROOT / "resources" / "tests" / "fixtures"

GHP = FIXTURES / "ghp-0.0.5.json"
OTHER = FIXTURES / "git-handoff-snapshot-0.2.0.json"
AUTH = FIXTURES / "auth-gmail-0.1.8.json"


def load(path):
    return json.loads(path.read_text())


def play(wrapper):
    return wrapper["data"]["play_inspect"]


def compare(approved, candidate):
    with tempfile.TemporaryDirectory(prefix="pcr-test-") as tmp:
        tmp = Path(tmp)

        old = tmp / "approved.json"
        new = tmp / "candidate.json"

        old.write_text(json.dumps(approved))
        new.write_text(json.dumps(candidate))

        result = subprocess.run(
            [
                sys.executable,
                str(COMPARATOR),
                "--files",
                str(old),
                str(new),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise AssertionError(
                f"comparator exited {result.returncode}: "
                f"{result.stderr or result.stdout}"
            )

        return json.loads(result.stdout)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
    except Exception as exc:
        print(f"FAIL  {name}")
        print(f"      {exc}")
        raise


base = load(GHP)
auth_base = load(AUTH)


# ------------------------------------------------------------
# 1. Exact same immutable release
# ------------------------------------------------------------

def test_exact_match():
    result = compare(base, base)

    check(
        result["verdict"] == "EXACT_MATCH",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        result["comparison_performed"] is True,
        "comparison_performed should be true",
    )

    check(
        result["reviewed_plays_executed"] is False,
        "reviewed play execution must remain false",
    )


# ------------------------------------------------------------
# 2. Dynamic reviewer/registry state must not create a delta
# ------------------------------------------------------------

def test_dynamic_noise_ignored():
    candidate = copy.deepcopy(base)

    p = play(candidate)

    p["archive"]["download_count"] = 999999
    p["archive"]["install_count"] = 888888

    if "host" in p:
        p["host"]["daemon"] = "synthetic-different-state"

    if "convergence" in p:
        p["convergence"]["requirement_source"] = (
            "synthetic-different-state"
        )

    result = compare(base, candidate)

    check(
        result["verdict"] == "EXACT_MATCH",
        (
            "dynamic host/registry state affected semantic comparison: "
            f"{result['verdict']}"
        ),
    )


# ------------------------------------------------------------
# 3. Documentation delta must prevent EXACT_MATCH
# ------------------------------------------------------------

def test_documentation_delta_not_exact():
    candidate = copy.deepcopy(base)

    p = play(candidate)
    p["identity"]["version"] = "0.0.6"
    p["identity"]["description"] += " Synthetic documentation edit."

    result = compare(base, candidate)

    check(
        result["verdict"] == "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED",
        f"unexpected docs-only verdict: {result['verdict']}",
    )

    check(
        "DOCUMENTATION_CHANGED" in result["reason_codes"],
        "DOCUMENTATION_CHANGED missing",
    )


# ------------------------------------------------------------
# 4. Implementation-only version upgrade
# ------------------------------------------------------------

def make_implementation_only_candidate():
    candidate = copy.deepcopy(base)

    p = play(candidate)

    p["identity"]["version"] = "0.0.6"

    p["archive"]["content_hash"] = "a" * 64

    p["package"]["digest"] = (
        "installed-package-sha256-v1:" + ("b" * 64)
    )

    return candidate


def test_implementation_only():
    candidate = make_implementation_only_candidate()

    result = compare(base, candidate)

    check(
        result["verdict"]
        == "IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        result["declared_access_expansion_observed"] is False,
        "implementation-only update falsely expanded access",
    )

    check(
        result["counts"]["material_types"] == 0,
        "implementation-only update produced material contract changes",
    )

    check(
        "IMPLEMENTATION_CHANGED" in result["reason_codes"],
        "implementation change was not detected",
    )


# ------------------------------------------------------------
# 5. Declared capability/access expansion
# ------------------------------------------------------------

def test_access_expansion():
    candidate = make_implementation_only_candidate()

    p = play(candidate)

    requirements = p["requirements"]

    requirements.setdefault("endpoints", []).append(
        "adapter/github"
    )

    requirements.setdefault("write_permissions", []).append({
        "tool": "adapter/github",
        "adapter": "github",
        "mode": "write",
    })

    p["authentication"].setdefault("adapters", []).append(
        "github"
    )

    result = compare(base, candidate)

    check(
        result["verdict"] == "MATERIAL_METHOD_CHANGE",
        f"unexpected access-expansion verdict: {result['verdict']}",
    )

    check(
        result["declared_access_expansion_observed"] is True,
        "access expansion flag was not raised",
    )

    required = {
        "DECLARED_ENDPOINT_EXPANDED",
        "DECLARED_WRITE_EXPANDED",
        "AUTH_ADAPTER_ADDED",
    }

    missing = required - set(result["reason_codes"])

    check(
        not missing,
        f"missing expansion reasons: {sorted(missing)}",
    )


# ------------------------------------------------------------
# 6. Same immutable version, different artifact identity
# ------------------------------------------------------------

def test_integrity_anomaly():
    candidate = copy.deepcopy(base)

    p = play(candidate)

    # Version deliberately remains 0.0.5.
    p["archive"]["content_hash"] = "c" * 64

    p["package"]["digest"] = (
        "installed-package-sha256-v1:" + ("d" * 64)
    )

    result = compare(base, candidate)

    check(
        result["verdict"] == "INTEGRITY_ANOMALY",
        f"unexpected integrity verdict: {result['verdict']}",
    )

    check(
        "IMMUTABLE_RELEASE_IDENTITY_CHANGED"
        in result["reason_codes"],
        "immutable identity anomaly reason missing",
    )


# ------------------------------------------------------------
# 7. Different owner/name must stop comparison
# ------------------------------------------------------------

def test_identity_mismatch():
    candidate = load(OTHER)

    result = compare(base, candidate)

    check(
        result["verdict"] == "IDENTITY_MISMATCH",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        result["comparison_performed"] is False,
        "different Plays must not be treated as version comparison",
    )


# ------------------------------------------------------------
# 8. Exact-version validation
# ------------------------------------------------------------

def validator(value):
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            value,
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )

    check(
        result.returncode == 0,
        f"validator unexpectedly failed DAG-style: {result.returncode}",
    )

    return json.loads(result.stdout)


def test_exact_input_validation():
    result = validator(
        "saikiranpulagalla/git-handoff-proof@0.0.5"
    )

    check(result["ok"] is True, "exact version rejected")

    check(
        result["canonical"]
        == (
            "https://play.modiqo.ai/"
            "saikiranpulagalla/git-handoff-proof@0.0.5"
        ),
        "canonical reference incorrect",
    )


def test_floating_input_rejected():
    result = validator(
        "saikiranpulagalla/git-handoff-proof"
    )

    check(
        result["ok"] is False,
        "floating reference was accepted",
    )

    check(
        result["error"] == "EXACT_VERSION_REQUIRED",
        f"wrong validation reason: {result.get('error')}",
    )


def test_malformed_input_rejected():
    result = validator("not-a-play-reference")

    check(
        result["ok"] is False,
        "malformed reference was accepted",
    )

    check(
        result["error"] == "EXACT_VERSION_REQUIRED",
        "malformed reference produced wrong reason",
    )



# ------------------------------------------------------------
# Same immutable version with changed visible release state
# ------------------------------------------------------------

def test_same_version_visible_mutation():
    candidate = copy.deepcopy(base)

    p = play(candidate)

    # Keep owner/name/version identical, but mutate a registry-visible
    # release field without changing content hash/digest.
    p["identity"]["description"] += " Mutated in place."

    result = compare(base, candidate)

    check(
        result["verdict"] == "INTEGRITY_ANOMALY",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        "IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED"
        in result["reason_codes"],
        "visible immutable-state anomaly reason missing",
    )



def test_oversized_reference_rejected():
    result = validator("a" * 5000)

    check(
        result["ok"] is False,
        "oversized reference was accepted",
    )

    check(
        result["error"] == "REFERENCE_TOO_LONG",
        f"wrong oversized-reference reason: {result.get('error')}",
    )



# ------------------------------------------------------------
# Authentication inspection/setup state is dynamic noise
# ------------------------------------------------------------

def test_auth_runtime_state_ignored():
    candidate = copy.deepcopy(auth_base)

    adapter = (
        play(candidate)
        ["authentication"]
        ["adapters"][0]
    )

    adapter["status"] = "synthetic-healthy"
    adapter["credentials"] = [
        {"synthetic": "current-local-state"}
    ]
    adapter["reason"] = "synthetic local inspection state"

    result = compare(auth_base, candidate)

    check(
        result["verdict"] == "EXACT_MATCH",
        (
            "dynamic authentication inspection state "
            f"affected semantics: {result['verdict']}"
        ),
    )

    semantic_codes = (
        set(result["reason_codes"]) -
        {"DISCLOSURE_INCOMPLETE"}
    )

    check(
        not semantic_codes,
        (
            "dynamic authentication state produced "
            f"semantic deltas: {sorted(semantic_codes)}"
        ),
    )


def make_auth_upgrade():
    candidate = copy.deepcopy(auth_base)

    p = play(candidate)

    # Isolate authentication/endpoint semantics.
    #
    # Do not invent archive/package identity fields: valid inspect
    # payloads may omit them, and artifact-change behavior is tested
    # independently elsewhere.
    p["identity"]["version"] = "0.1.9"

    return candidate


# ------------------------------------------------------------
# New declared credential requirement
# ------------------------------------------------------------

def test_auth_credential_requirement_added():
    candidate = make_auth_upgrade()

    adapter = (
        play(candidate)
        ["authentication"]
        ["adapters"][0]
    )

    adapter["credential_names"].append(
        "GMAIL_REFRESH_TOKEN"
    )

    result = compare(auth_base, candidate)

    check(
        result["verdict"] == "MATERIAL_METHOD_CHANGE",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        "AUTH_CREDENTIAL_REQUIREMENT_ADDED"
        in result["reason_codes"],
        "credential requirement addition not detected",
    )

    check(
        result["declared_access_expansion_observed"]
        is False,
        (
            "credential setup change was incorrectly "
            "called an access expansion"
        ),
    )


# ------------------------------------------------------------
# Same endpoint, different MCP fingerprint
# ------------------------------------------------------------

def test_endpoint_fingerprint_change():
    candidate = make_auth_upgrade()

    endpoint = (
        play(candidate)
        ["requirements"]
        ["endpoints"][0]
    )

    endpoint["mcp_fingerprint"] = (
        "mcp_SYNTHETIC_DIFFERENT_FINGERPRINT"
    )

    result = compare(auth_base, candidate)

    check(
        result["verdict"] == "MATERIAL_METHOD_CHANGE",
        f"unexpected verdict: {result['verdict']}",
    )

    check(
        "ENDPOINT_FINGERPRINT_CHANGED"
        in result["reason_codes"],
        "endpoint fingerprint change not detected",
    )

    check(
        "DECLARED_ENDPOINT_EXPANDED"
        not in result["reason_codes"],
        (
            "fingerprint replacement incorrectly "
            "reported as endpoint expansion"
        ),
    )

    check(
        result["declared_access_expansion_observed"]
        is False,
        (
            "endpoint identity replacement incorrectly "
            "called access expansion"
        ),
    )


# ------------------------------------------------------------
# Provenance/distribution metadata
# ------------------------------------------------------------

def test_provenance_metadata_changes():
    candidate = copy.deepcopy(base)

    p = play(candidate)

    p["identity"]["version"] = "0.0.6"
    p["identity"]["author"] = "Different Author"
    p["identity"]["visibility"] = "private"

    result = compare(base, candidate)

    check(
        "AUTHOR_CHANGED" in result["reason_codes"],
        "author change was not detected",
    )

    check(
        "VISIBILITY_CHANGED" in result["reason_codes"],
        "visibility change was not detected",
    )



# ------------------------------------------------------------
# Missing package authority is unknown, not "not verified"
# ------------------------------------------------------------

def test_missing_package_authority_not_negative():
    approved = copy.deepcopy(auth_base)
    candidate = copy.deepcopy(auth_base)

    # The real authenticated fixture currently omits package.authority.
    # Identical missing disclosure must not become a negative trust claim.
    play(approved).setdefault("package", {}).pop(
        "authority",
        None,
    )

    play(candidate).setdefault("package", {}).pop(
        "authority",
        None,
    )

    result = compare(approved, candidate)

    check(
        result["verdict"] == "EXACT_MATCH",
        f"missing authority changed verdict: {result['verdict']}",
    )

    check(
        "CANDIDATE_PACKAGE_NOT_VERIFIED"
        not in result["reason_codes"],
        "missing authority was falsely interpreted as not verified",
    )

    check(
        "IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED"
        not in result["reason_codes"],
        "missing authority created false immutable-state anomaly",
    )



# ------------------------------------------------------------
# Artifact identity known <-> missing is disclosure, not change
# ------------------------------------------------------------

def test_content_hash_disclosure_loss():
    candidate = copy.deepcopy(base)

    p = play(candidate)
    p["identity"]["version"] = "0.0.6"

    p["archive"].pop("content_hash", None)

    result = compare(base, candidate)

    check(
        "ARTIFACT_IDENTITY_DISCLOSURE_CHANGED"
        in result["reason_codes"],
        "content-hash disclosure loss was not detected",
    )

    check(
        "IMPLEMENTATION_CHANGED"
        not in result["reason_codes"],
        "missing content hash was falsely called implementation change",
    )

    check(
        result["verdict"]
        == "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED",
        f"unexpected verdict: {result['verdict']}",
    )


def test_package_digest_disclosure_loss():
    candidate = copy.deepcopy(base)

    p = play(candidate)
    p["identity"]["version"] = "0.0.6"

    p["package"].pop("digest", None)

    result = compare(base, candidate)

    check(
        "ARTIFACT_IDENTITY_DISCLOSURE_CHANGED"
        in result["reason_codes"],
        "package-digest disclosure loss was not detected",
    )

    check(
        "IMPLEMENTATION_CHANGED"
        not in result["reason_codes"],
        "missing package digest was falsely called implementation change",
    )

    check(
        result["verdict"]
        == "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED",
        f"unexpected verdict: {result['verdict']}",
    )


TESTS = [
    ("exact immutable match", test_exact_match),
    ("dynamic state ignored", test_dynamic_noise_ignored),
    ("documentation delta not exact", test_documentation_delta_not_exact),
    ("implementation-only upgrade", test_implementation_only),
    ("declared access expansion", test_access_expansion),
    ("immutable identity anomaly", test_integrity_anomaly),
    ("same-version visible mutation", test_same_version_visible_mutation),
    ("different Play identity", test_identity_mismatch),
    ("exact reference accepted", test_exact_input_validation),
    ("floating reference rejected", test_floating_input_rejected),
    ("malformed reference rejected", test_malformed_input_rejected),
    ("oversized reference rejected", test_oversized_reference_rejected),
    ("auth runtime state ignored", test_auth_runtime_state_ignored),
    ("missing package authority stays unknown", test_missing_package_authority_not_negative),
    ("auth credential requirement added", test_auth_credential_requirement_added),
    ("endpoint fingerprint changed", test_endpoint_fingerprint_change),
    ("provenance metadata changed", test_provenance_metadata_changes),
    ("content hash disclosure loss", test_content_hash_disclosure_loss),
    ("package digest disclosure loss", test_package_digest_disclosure_loss),
]


for name, fn in TESTS:
    run(name, fn)


print()
print(f"ALL {len(TESTS)} PCR REGRESSION TESTS PASSED")
