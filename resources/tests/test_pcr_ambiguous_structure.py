#!/usr/bin/env python3

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COMP = ROOT / "resources/compare_inspections.py"
REVIEW = ROOT / "resources/review_refs.py"

FIXTURE = (
    ROOT
    / "resources/tests/fixtures/ghp-0.0.5.json"
)


def load():
    return json.loads(FIXTURE.read_text())


def play(wrapper):
    return wrapper["data"]["play_inspect"]


def compare(approved, candidate):
    with tempfile.TemporaryDirectory(
        prefix="pcr-ambiguous-"
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


def assert_blocked(result, expected_fragment):
    assert result["ok"] is False, result
    assert result["verdict"] == "BLOCKED", result

    assert (
        result["error_code"]
        == "AMBIGUOUS_INSPECTION_STRUCTURE"
    ), result

    assert expected_fragment in result["detail"], (
        result["detail"],
        expected_fragment,
    )

    assert (
        result["reviewed_plays_executed"]
        is False
    )


def version_pair():
    approved = load()
    candidate = copy.deepcopy(approved)

    play(approved)["identity"]["version"] = "1.0.0"
    play(candidate)["identity"]["version"] = "1.0.1"

    return approved, candidate


def test_duplicate_parameter_blocks():
    approved, candidate = version_pair()

    params = play(candidate)["parameters"]

    duplicate = copy.deepcopy(params[0])
    duplicate["type"] = "integer"

    params.append(duplicate)

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.parameters",
    )


def test_duplicate_step_blocks():
    approved, candidate = version_pair()

    steps = play(candidate)["steps"]

    duplicate = copy.deepcopy(steps[0])
    duplicate["operation"] = "evil.operation"

    steps.append(duplicate)

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.steps",
    )


def test_duplicate_runtime_blocks():
    approved, candidate = version_pair()

    runtimes = (
        play(candidate)
        .setdefault("requirements", {})
        .setdefault("runtimes", [])
    )

    if runtimes:
        duplicate = copy.deepcopy(runtimes[0])
        runtimes.append(duplicate)
    else:
        runtimes.extend([
            {
                "name": "python3",
                "required": True,
            },
            {
                "name": "python3",
                "required": False,
            },
        ])

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.requirements.runtimes",
    )


def test_duplicate_tool_blocks():
    approved, candidate = version_pair()

    tools = (
        play(candidate)
        .setdefault("package", {})
        .setdefault("tools", [])
    )

    if tools:
        duplicate = copy.deepcopy(tools[0])
        tools.append(duplicate)
    else:
        tools.extend([
            {
                "id": "git",
                "command": "git",
            },
            {
                "id": "git",
                "command": "evil-git",
            },
        ])

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.package.tools",
    )


def test_duplicate_endpoint_blocks():
    approved, candidate = version_pair()

    play(candidate).setdefault(
        "requirements",
        {},
    )["endpoints"] = [
        "github",
        {
            "endpoint": "github",
            "mcp_fingerprint": "different",
        },
    ]

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.requirements.endpoints",
    )


def test_duplicate_auth_adapter_blocks():
    approved, candidate = version_pair()

    play(candidate)["authentication"] = {
        "read_only": True,
        "adapters": [
            {
                "adapter": "gmail",
                "credential_names": ["a"],
            },
            {
                "adapter": "gmail",
                "credential_names": ["b"],
            },
        ],
    }

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.authentication.adapters",
    )


def test_identical_duplicate_still_blocks():
    approved, candidate = version_pair()

    params = play(candidate)["parameters"]

    params.append(
        copy.deepcopy(params[0])
    )

    result = compare(approved, candidate)

    assert_blocked(
        result,
        "candidate.parameters",
    )


def test_review_refs_preserves_block_reason():
    approved, candidate = version_pair()

    a = play(approved)
    c = play(candidate)

    a["identity"]["owner"] = "pcramb"
    a["identity"]["name"] = "duplicate"
    a["identity"]["version"] = "1.0.0"

    c["identity"]["owner"] = "pcramb"
    c["identity"]["name"] = "duplicate"
    c["identity"]["version"] = "1.0.1"

    c["parameters"].append(
        copy.deepcopy(c["parameters"][0])
    )

    with tempfile.TemporaryDirectory(
        prefix="pcr-ambiguous-review-"
    ) as td:
        td = Path(td)

        old = td / "approved.json"
        new = td / "candidate.json"
        fakebin = td / "bin"

        fakebin.mkdir()

        old.write_text(json.dumps(approved))
        new.write_text(json.dumps(candidate))

        fake = fakebin / "rote"

        fake.write_text(
            f"""#!/usr/bin/env python3
import sys

approved = {str(old)!r}
candidate = {str(new)!r}

args = sys.argv[1:]

if (
    len(args) >= 3
    and args[0] == "play"
    and args[1] == "inspect"
):
    ref = args[2]

    if ref.endswith("@1.0.0"):
        path = approved
    elif ref.endswith("@1.0.1"):
        path = candidate
    else:
        raise SystemExit(7)

    with open(path) as f:
        sys.stdout.write(f.read())

    raise SystemExit(0)

raise SystemExit(8)
"""
        )

        fake.chmod(0o755)

        approved_validation = {
            "ok": True,
            "input": "pcramb/duplicate@1.0.0",
            "canonical":
                "pcramb/duplicate@1.0.0",
            "owner": "pcramb",
            "name": "duplicate",
            "version": "1.0.0",
        }

        candidate_validation = {
            "ok": True,
            "input": "pcramb/duplicate@1.0.1",
            "canonical":
                "pcramb/duplicate@1.0.1",
            "owner": "pcramb",
            "name": "duplicate",
            "version": "1.0.1",
        }

        env = os.environ.copy()

        env["PATH"] = (
            str(fakebin)
            + os.pathsep
            + env["PATH"]
        )

        result = subprocess.run(
            [
                sys.executable,
                str(REVIEW),
                json.dumps(approved_validation),
                json.dumps(candidate_validation),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            result.stderr or result.stdout
        )

        parsed = json.loads(result.stdout)

        assert_blocked(
            parsed,
            "candidate.parameters",
        )

        assert (
            parsed["error_code"]
            != "COMPARISON_FAILED"
        ), parsed


TESTS = [
    (
        "duplicate parameter blocks",
        test_duplicate_parameter_blocks,
    ),
    (
        "duplicate step blocks",
        test_duplicate_step_blocks,
    ),
    (
        "duplicate runtime blocks",
        test_duplicate_runtime_blocks,
    ),
    (
        "duplicate tool blocks",
        test_duplicate_tool_blocks,
    ),
    (
        "duplicate endpoint blocks",
        test_duplicate_endpoint_blocks,
    ),
    (
        "duplicate auth adapter blocks",
        test_duplicate_auth_adapter_blocks,
    ),
    (
        "identical duplicate still blocks",
        test_identical_duplicate_still_blocks,
    ),
    (
        "review_refs preserves ambiguity reason",
        test_review_refs_preserves_block_reason,
    ),
]


for name, fn in TESTS:
    fn()
    print(f"PASS  {name}")


print()
print(
    f"ALL {len(TESTS)} PCR AMBIGUOUS-STRUCTURE TESTS PASSED"
)
