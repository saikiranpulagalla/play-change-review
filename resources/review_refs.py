#!/usr/bin/env python3

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def emit_blocked(
    code,
    detail,
    approved_input=None,
    candidate_input=None,
):
    print(json.dumps({
        "schema": "play-change-review/v1",
        "ok": False,
        "verdict": "BLOCKED",
        "error_code": code,
        "detail": str(detail)[:2000],
        "approved_input": approved_input,
        "candidate_input": candidate_input,
        "reviewed_plays_executed": False,
        "limitations": [
            "No comparison conclusion was produced.",
            "Neither reviewed Play was executed.",
        ],
    }, separators=(",", ":")))
    raise SystemExit(0)


if len(sys.argv) != 3:
    emit_blocked(
        "INVALID_ARGUMENTS",
        "Expected approved and candidate validation records.",
    )


def decode_validation(raw, side):
    try:
        value = json.loads(raw)
    except Exception:
        emit_blocked(
            f"{side.upper()}_VALIDATION_INVALID_JSON",
            f"{side} validation did not produce valid JSON.",
        )

    if not isinstance(value, dict):
        emit_blocked(
            f"{side.upper()}_VALIDATION_INVALID",
            f"{side} validation did not produce an object.",
        )

    return value


approved_validation = decode_validation(
    sys.argv[1],
    "approved",
)

candidate_validation = decode_validation(
    sys.argv[2],
    "candidate",
)

approved_input = approved_validation.get("input")
candidate_input = candidate_validation.get("input")


def require_valid(validation, side):
    if validation.get("ok") is not True:
        reason = (
            validation.get("error")
            or "INPUT_INVALID"
        )

        detail = (
            validation.get("detail")
            or f"{side} Play reference is invalid."
        )

        emit_blocked(
            f"{side.upper()}_{reason}",
            detail,
            approved_input,
            candidate_input,
        )

    canonical = validation.get("canonical")

    if not isinstance(canonical, str) or not canonical:
        emit_blocked(
            f"{side.upper()}_CANONICAL_REFERENCE_MISSING",
            f"{side} validation returned no canonical exact reference.",
            approved_input,
            candidate_input,
        )

    return canonical


approved_ref = require_valid(
    approved_validation,
    "approved",
)

candidate_ref = require_valid(
    candidate_validation,
    "candidate",
)


def expected_identity(validation):
    return {
        "owner": validation.get("owner"),
        "name": validation.get("name"),
        "version": validation.get("version"),
    }


approved_expected = expected_identity(
    approved_validation
)

candidate_expected = expected_identity(
    candidate_validation
)

rote = shutil.which("rote")

if not rote:
    emit_blocked(
        "ROTE_NOT_FOUND",
        "The rote executable is not available on PATH.",
        approved_input,
        candidate_input,
    )


TRANSIENT_INSPECT_MARKERS = (
    "could not resolve play",
    "workspace busy",
    "temporarily unavailable",
    "temporary failure",
)


def inspect_error_detail(result):
    raw = (
        result.stderr.strip()
        or result.stdout.strip()
        or f"rote play inspect exited {result.returncode}"
    )

    try:
        parsed = json.loads(raw)
        error = parsed.get("error", {})

        if isinstance(error, dict):
            return (
                error.get("message")
                or error.get("kind")
                or raw
            )
    except Exception:
        pass

    return raw


def is_transient_inspect_failure(detail):
    lowered = str(detail).lower()

    return any(
        marker in lowered
        for marker in TRANSIENT_INSPECT_MARKERS
    )


def inspect(ref, side, expected):
    max_attempts = 2

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()

        try:
            result = subprocess.run(
                [rote, "play", "inspect", ref, "--json"],
                capture_output=True,
                text=True,
                timeout=90,
            )

            elapsed = time.monotonic() - started

        except subprocess.TimeoutExpired:
            # A full inspection timeout has already consumed substantial
            # time. Fail closed instead of repeating another long wait.
            emit_blocked(
                f"{side.upper()}_INSPECTION_TIMEOUT",
                f"Inspection of {ref} timed out.",
                approved_input,
                candidate_input,
            )

        except Exception as exc:
            emit_blocked(
                f"{side.upper()}_INSPECTION_ERROR",
                str(exc),
                approved_input,
                candidate_input,
            )

        if result.returncode != 0:
            detail = inspect_error_detail(result)

            if (
                attempt < max_attempts
                and elapsed < 10
                and is_transient_inspect_failure(detail)
            ):
                time.sleep(1)
                continue

            emit_blocked(
                f"{side.upper()}_INSPECTION_FAILED",
                (
                    f"{detail} "
                    f"(attempt {attempt}/{max_attempts})"
                ),
                approved_input,
                candidate_input,
            )

        try:
            parsed = json.loads(result.stdout)
        except Exception:
            emit_blocked(
                f"{side.upper()}_INSPECTION_INVALID_JSON",
                "rote play inspect did not return valid JSON.",
                approved_input,
                candidate_input,
            )

        if parsed.get("ok") is not True:
            emit_blocked(
                f"{side.upper()}_INSPECTION_UNSUCCESSFUL",
                "Inspection returned ok=false.",
                approved_input,
                candidate_input,
            )

        inspected = (
            parsed.get("data", {})
            .get("play_inspect", {})
        )

        actual_identity = (
            inspected.get("identity", {})
            if isinstance(inspected, dict)
            else {}
        )

        actual = {
            "owner": actual_identity.get("owner"),
            "name": actual_identity.get("name"),
            "version": actual_identity.get("version"),
        }

        if actual != expected:
            emit_blocked(
                f"{side.upper()}_INSPECTION_IDENTITY_MISMATCH",
                (
                    f"Requested "
                    f"{expected.get('owner')}/"
                    f"{expected.get('name')}@"
                    f"{expected.get('version')} "
                    f"but inspection returned "
                    f"{actual.get('owner')}/"
                    f"{actual.get('name')}@"
                    f"{actual.get('version')}."
                ),
                approved_input,
                candidate_input,
            )

        return result.stdout

    raise AssertionError("unreachable")


# Intentionally sequential because concurrent nested
# Rote inspections were empirically unreliable.
approved_json = inspect(
    approved_ref,
    "approved",
    approved_expected,
)

candidate_json = inspect(
    candidate_ref,
    "candidate",
    candidate_expected,
)

comparator = Path(__file__).with_name(
    "compare_inspections.py"
)

with tempfile.TemporaryDirectory(
    prefix="play-change-review-"
) as tmp:
    tmp = Path(tmp)

    approved_file = tmp / "approved.json"
    candidate_file = tmp / "candidate.json"

    approved_file.write_text(approved_json)
    candidate_file.write_text(candidate_json)

    result = subprocess.run(
        [
            sys.executable,
            str(comparator),
            "--files",
            str(approved_file),
            str(candidate_file),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

if result.returncode != 0:
    emit_blocked(
        "COMPARISON_FAILED",
        result.stderr.strip()
        or result.stdout.strip()
        or f"comparator exited {result.returncode}",
        approved_input,
        candidate_input,
    )

try:
    json.loads(result.stdout)
except Exception:
    emit_blocked(
        "COMPARISON_INVALID_JSON",
        "Comparator did not return valid JSON.",
        approved_input,
        candidate_input,
    )

print(result.stdout.strip())
