#!/usr/bin/env python3

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COMPARATOR = ROOT / "resources/compare_inspections.py"
FIXTURE = (
    ROOT
    / "resources/tests/fixtures/ghp-0.0.5.json"
)

MAX_EXPECTED_RESULT_BYTES = 32768


def load():
    return json.loads(FIXTURE.read_text())


def play(wrapper):
    return wrapper["data"]["play_inspect"]


def compare(approved, candidate):
    with tempfile.TemporaryDirectory(
        prefix="pcr-budget-test-"
    ) as tmp:
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

        assert result.returncode == 0, (
            result.stderr or result.stdout
        )

        raw = result.stdout.strip()
        parsed = json.loads(raw)

        return raw, parsed


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


def make_version_pair():
    approved = load()
    candidate = copy.deepcopy(approved)

    a = play(approved)
    c = play(candidate)

    a["identity"]["owner"] = "pcrbudget"
    a["identity"]["name"] = "synthetic"
    a["identity"]["version"] = "1.0.0"

    c["identity"]["owner"] = "pcrbudget"
    c["identity"]["name"] = "synthetic"
    c["identity"]["version"] = "1.0.1"

    return approved, candidate


def test_large_package_fileset_is_bounded():
    approved, candidate = make_version_pair()

    a = play(approved)
    c = play(candidate)

    a["archive"]["content_hash"] = "1" * 64
    c["archive"]["content_hash"] = "2" * 64

    a["package"]["digest"] = (
        "installed-package-sha256-v1:"
        + "3" * 64
    )

    c["package"]["digest"] = (
        "installed-package-sha256-v1:"
        + "4" * 64
    )

    original_count = len(c["package"]["files"])

    for i in range(9990 - original_count):
        c["package"]["files"].append(
            "synthetic/"
            + f"{i:05d}-"
            + ("x" * 90)
            + ".txt"
        )

    raw, result = compare(
        approved,
        candidate,
    )

    expected_added = (
        len(c["package"]["files"])
        - len(a["package"]["files"])
    )

    package_files = result["package_files"]

    check(
        result["verdict"]
        == "IMPLEMENTATION_CHANGED_SAME_VISIBLE_CONTRACT",
        result["verdict"],
    )

    check(
        package_files["added_total"]
        == expected_added,
        (
            package_files["added_total"],
            expected_added,
        ),
    )

    check(
        len(package_files["added"]) <= 8,
        "package-file evidence was not bounded",
    )

    check(
        package_files["added_omitted"]
        == (
            expected_added
            - len(package_files["added"])
        ),
        "package-file omission count is wrong",
    )

    check(
        package_files["truncated"] is True,
        "large package fileset did not declare truncation",
    )

    check(
        len(raw.encode("utf-8"))
        <= MAX_EXPECTED_RESULT_BYTES,
        (
            "large fileset result exceeded PCR budget: "
            f"{len(raw.encode('utf-8'))}"
        ),
    )


def test_many_findings_keep_complete_counts():
    approved, candidate = make_version_pair()

    c = play(candidate)

    for i in range(5000):
        c["steps"].append({
            "name": f"synthetic_step_{i:05d}",
            "target": "process/local",
            "kind": "process.exec",
            "operation": "process.exec",
            "depends_on": [],
        })

    raw, result = compare(
        approved,
        candidate,
    )

    check(
        result["verdict"]
        == "MATERIAL_METHOD_CHANGE",
        result["verdict"],
    )

    check(
        result["counts"]["material_findings"]
        == 5000,
        (
            "material count lost during bounding: "
            f"{result['counts']}"
        ),
    )

    evidence = result["change_evidence"]

    check(
        evidence["total"]
        == result["counts"]["total_findings"],
        "change evidence total disagrees with complete count",
    )

    check(
        evidence["returned"] <= 24,
        "change evidence was not bounded",
    )

    check(
        evidence["omitted"]
        == evidence["total"] - evidence["returned"],
        "change omission count is wrong",
    )

    check(
        evidence["truncated"] is True,
        "many-finding result did not declare truncation",
    )

    check(
        "STEP_ADDED" in result["reason_codes"],
        "complete reason-code set was lost",
    )

    check(
        len(raw.encode("utf-8"))
        <= MAX_EXPECTED_RESULT_BYTES,
        (
            "many-finding result exceeded PCR budget: "
            f"{len(raw.encode('utf-8'))}"
        ),
    )


def test_large_detail_is_bounded():
    approved, candidate = make_version_pair()

    c = play(candidate)

    c["steps"][0]["operation"] = (
        "synthetic."
        + ("Z" * 100000)
    )

    raw, result = compare(
        approved,
        candidate,
    )

    check(
        result["verdict"]
        == "MATERIAL_METHOD_CHANGE",
        result["verdict"],
    )

    details = [
        change["detail"]
        for change in result["changes"]
    ]

    check(
        any(
            "[truncated]" in detail
            for detail in details
        ),
        "large detail was not explicitly truncated",
    )

    check(
        len(raw.encode("utf-8"))
        <= MAX_EXPECTED_RESULT_BYTES,
        "large detail escaped output budget",
    )


def test_bounded_result_is_deterministic():
    approved, candidate = make_version_pair()

    c = play(candidate)

    for i in range(1000):
        c["steps"].append({
            "name": f"deterministic_{i:05d}",
            "target": "process/local",
            "kind": "process.exec",
            "operation": "process.exec",
            "depends_on": [],
        })

    raw1, result1 = compare(
        approved,
        candidate,
    )

    raw2, result2 = compare(
        approved,
        candidate,
    )

    check(
        raw1 == raw2,
        "bounded canonical output is nondeterministic",
    )

    check(
        result1 == result2,
        "parsed bounded result is nondeterministic",
    )


TESTS = [
    (
        "9990-file evidence stays bounded",
        test_large_package_fileset_is_bounded,
    ),
    (
        "5000 findings preserve complete counts",
        test_many_findings_keep_complete_counts,
    ),
    (
        "individual details stay bounded",
        test_large_detail_is_bounded,
    ),
    (
        "bounded result remains deterministic",
        test_bounded_result_is_deterministic,
    ),
]


for name, fn in TESTS:
    run(name, fn)


print()
print(
    f"ALL {len(TESTS)} PCR OUTPUT-BUDGET TESTS PASSED"
)
