#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

VALIDATOR = ROOT / "resources/validate_ref.py"


def validate(value):
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            value,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, (
        result.stderr or result.stdout
    )

    parsed = json.loads(result.stdout)

    return parsed


VALID = [
    "owner/name@0.0.0",
    "owner/name@1.2.3",
    "owner/name@10.20.30",
    "owner/name@1.0.0-alpha",
    "owner/name@1.0.0-alpha.1",
    "owner/name@1.0.0-0.3.7",
    "owner/name@1.0.0-x.7.z.92",
    "owner/name@1.0.0-alpha+001",
    "owner/name@1.0.0+20130313144700",
    "owner/name@1.0.0+build.01",
    "owner/name@1.0.0-beta+exp.sha.5114f85",
    (
        "https://play.modiqo.ai/"
        "owner/name@1.2.3-alpha.1+build.7"
    ),
]


INVALID = [
    # Leading zeroes in SemVer core.
    "owner/name@01.2.3",
    "owner/name@1.02.3",
    "owner/name@1.2.03",

    # Numeric pre-release identifiers may not have
    # leading zeroes.
    "owner/name@1.2.3-01",
    "owner/name@1.2.3-alpha.01",

    # Empty pre-release/build identifiers.
    "owner/name@1.2.3-alpha..1",
    "owner/name@1.2.3-.alpha",
    "owner/name@1.2.3+build..1",
    "owner/name@1.2.3-",
    "owner/name@1.2.3+",

    # Not exact SemVer references.
    "owner/name@v1.2.3",
    "owner/name@1.2",
    "owner/name",
    "owner/name@1.2.3?x=1",
    "owner/name@1.2.3#frag",

    # Invalid characters.
    "owner/name@1.2.3-alpha_1",
    "owner/name@1.2.3+build_1",
]


for value in VALID:
    result = validate(value)

    assert result["ok"] is True, (
        value,
        result,
    )

    assert (
        result["version"]
        in value
    ), (
        value,
        result,
    )

    assert result["canonical"].startswith(
        "https://play.modiqo.ai/"
    )

    print(
        "PASS valid   ",
        value,
    )


for value in INVALID:
    result = validate(value)

    assert result["ok"] is False, (
        value,
        result,
    )

    assert (
        result["error"]
        == "EXACT_VERSION_REQUIRED"
    ), (
        value,
        result,
    )

    print(
        "PASS invalid ",
        value,
    )


# Preserve reference-length protection.
oversized = (
    "owner/name@1.2.3"
    + ("x" * 600)
)

result = validate(oversized)

assert result["ok"] is False
assert result["error"] == "REFERENCE_TOO_LONG"

print(
    "PASS invalid  oversized reference"
)


print()
print(
    f"ALL {len(VALID) + len(INVALID) + 1} "
    "PCR SEMVER TESTS PASSED"
)
