#!/usr/bin/env python3

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COMP = ROOT / "resources/compare_inspections.py"

GHP = (
    ROOT
    / "resources/tests/fixtures/ghp-0.0.5.json"
)


def load():
    return json.loads(GHP.read_text())


def play(wrapper):
    return wrapper["data"]["play_inspect"]


def compare(approved, candidate):
    with tempfile.TemporaryDirectory(
        prefix="pcr-semantic-hardening-"
    ) as td:
        td = Path(td)

        old = td / "approved.json"
        new = td / "candidate.json"

        old.write_text(json.dumps(approved))
        new.write_text(json.dumps(candidate))

        result = subprocess.run(
            [
                sys.executable,
                str(COMP),
                "--files",
                str(old),
                str(new),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            result.stderr or result.stdout
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


def version_pair():
    approved = load()
    candidate = copy.deepcopy(approved)

    play(approved)["identity"]["version"] = "1.0.0"
    play(candidate)["identity"]["version"] = "1.0.1"

    return approved, candidate


def test_package_files_loss_is_disclosure_change():
    approved, candidate = version_pair()

    c = play(candidate)

    assert (
        "files" in c["package"]
    ), "fixture must disclose package.files"

    c["package"].pop("files")

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        "PACKAGE_FILESET_DISCLOSURE_CHANGED"
        in codes,
        codes,
    )

    check(
        "PACKAGE_FILESET_CHANGED"
        not in codes,
        codes,
    )

    check(
        result["package_files"][
            "comparison_available"
        ] is False,
        result["package_files"],
    )

    check(
        result["package_files"][
            "added_total"
        ] is None,
        result["package_files"],
    )

    check(
        result["package_files"][
            "removed_total"
        ] is None,
        result["package_files"],
    )


def test_package_files_appearance_is_disclosure_change():
    approved, candidate = version_pair()

    a = play(approved)

    assert (
        "files" in a["package"]
    ), "fixture must disclose package.files"

    a["package"].pop("files")

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        "PACKAGE_FILESET_DISCLOSURE_CHANGED"
        in codes,
        codes,
    )

    check(
        "PACKAGE_FILESET_CHANGED"
        not in codes,
        codes,
    )


def test_endpoint_loss_is_not_reduction():
    approved, candidate = version_pair()

    a = play(approved)
    c = play(candidate)

    a.setdefault(
        "requirements",
        {},
    )["endpoints"] = []

    c.setdefault(
        "requirements",
        {},
    ).pop(
        "endpoints",
        None,
    )

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        "DECLARED_ENDPOINT_DISCLOSURE_CHANGED"
        in codes,
        codes,
    )

    check(
        "DECLARED_ENDPOINT_REDUCED"
        not in codes,
        codes,
    )

    check(
        "DECLARED_ENDPOINT_EXPANDED"
        not in codes,
        codes,
    )

    check(
        result[
            "declared_access_expansion_observed"
        ] is False,
        result,
    )


def test_parameter_description_same_version_is_anomaly():
    approved = load()
    candidate = copy.deepcopy(approved)

    old = play(approved)["parameters"][0]
    new = play(candidate)["parameters"][0]

    new["description"] = (
        str(old.get("description"))
        + " changed"
    )

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        result["verdict"]
        == "INTEGRITY_ANOMALY",
        result["verdict"],
    )

    check(
        "PARAMETER_DESCRIPTION_CHANGED"
        in codes,
        codes,
    )

    check(
        "IMMUTABLE_RELEASE_VISIBLE_STATE_CHANGED"
        in codes,
        codes,
    )


def test_parameter_example_same_version_is_anomaly():
    approved = load()

    play(approved)["parameters"][0][
        "example"
    ] = "old-example"

    candidate = copy.deepcopy(approved)

    play(candidate)["parameters"][0][
        "example"
    ] = "new-example"

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        result["verdict"]
        == "INTEGRITY_ANOMALY",
        result["verdict"],
    )

    check(
        "PARAMETER_EXAMPLE_CHANGED"
        in codes,
        codes,
    )


def test_parameter_label_same_version_is_anomaly():
    approved = load()

    param = play(approved)["parameters"][0]

    param.setdefault(
        "input",
        {},
    )["label"] = "Old label"

    candidate = copy.deepcopy(approved)

    play(candidate)["parameters"][0][
        "input"
    ]["label"] = "New label"

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        result["verdict"]
        == "INTEGRITY_ANOMALY",
        result["verdict"],
    )

    check(
        "PARAMETER_LABEL_CHANGED"
        in codes,
        codes,
    )


def test_parameter_metadata_across_versions_is_informational():
    approved, candidate = version_pair()

    old = play(approved)["parameters"][0]
    new = play(candidate)["parameters"][0]

    new["description"] = (
        str(old.get("description"))
        + " changed"
    )

    result = compare(
        approved,
        candidate,
    )

    change = next(
        c
        for c in result["changes"]
        if c["code"]
        == "PARAMETER_DESCRIPTION_CHANGED"
    )

    check(
        change["material"] is False,
        change,
    )

    check(
        result["verdict"]
        == "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED",
        result["verdict"],
    )


def test_valid_values_reorder_is_not_material():
    approved, candidate = version_pair()

    play(approved)["parameters"][0][
        "valid_values"
    ] = [
        "alpha",
        "beta",
        "gamma",
    ]

    play(candidate)["parameters"][0][
        "valid_values"
    ] = [
        "gamma",
        "alpha",
        "beta",
    ]

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        "PARAMETER_VALID_VALUES_CHANGED"
        not in codes,
        codes,
    )

    check(
        result["verdict"]
        == "NO_MATERIAL_VISIBLE_CHANGE_OBSERVED",
        result["verdict"],
    )


def test_valid_values_content_change_remains_material():
    approved, candidate = version_pair()

    play(approved)["parameters"][0][
        "valid_values"
    ] = [
        "alpha",
        "beta",
    ]

    play(candidate)["parameters"][0][
        "valid_values"
    ] = [
        "alpha",
        "gamma",
    ]

    result = compare(
        approved,
        candidate,
    )

    codes = set(result["reason_codes"])

    check(
        "PARAMETER_VALID_VALUES_CHANGED"
        in codes,
        codes,
    )

    check(
        result["verdict"]
        == "MATERIAL_METHOD_CHANGE",
        result["verdict"],
    )


TESTS = [
    (
        "package files loss is disclosure change",
        test_package_files_loss_is_disclosure_change,
    ),
    (
        "package files appearance is disclosure change",
        test_package_files_appearance_is_disclosure_change,
    ),
    (
        "endpoint loss is not endpoint reduction",
        test_endpoint_loss_is_not_reduction,
    ),
    (
        "parameter description mutation is visible",
        test_parameter_description_same_version_is_anomaly,
    ),
    (
        "parameter example mutation is visible",
        test_parameter_example_same_version_is_anomaly,
    ),
    (
        "parameter label mutation is visible",
        test_parameter_label_same_version_is_anomaly,
    ),
    (
        "parameter metadata is informational across versions",
        test_parameter_metadata_across_versions_is_informational,
    ),
    (
        "valid_values reorder is ignored",
        test_valid_values_reorder_is_not_material,
    ),
    (
        "valid_values content change remains material",
        test_valid_values_content_change_remains_material,
    ),
]


for name, fn in TESTS:
    run(name, fn)


print()
print(
    f"ALL {len(TESTS)} PCR SEMANTIC-HARDENING TESTS PASSED"
)
