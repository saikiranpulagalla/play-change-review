#!/usr/bin/env python3

import json
import re
import sys

raw = sys.argv[1].strip() if len(sys.argv) > 1 else ""

if len(raw) > 512:
    print(json.dumps({
        "ok": False,
        "error": "REFERENCE_TOO_LONG",
        "input": raw[:512] + "...[truncated]",
        "detail": "Play references must be 512 characters or fewer.",
    }))
    raise SystemExit(0)

pattern = re.compile(
    r"^(?:https://play\.modiqo\.ai/)?"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9_-]*)/"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_-]*)@"
    r"(?P<version>"
    # SemVer 2.0.0 core numeric identifiers:
    # zero, or a non-zero digit followed by digits.
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    # Pre-release identifiers are dot-separated and non-empty.
    # Purely numeric identifiers must not have leading zeroes.
    # Non-numeric identifiers may contain ASCII alphanumerics
    # and hyphens and must contain at least one non-digit.
    r"(?:-"
    r"(?:0|[1-9][0-9]*|"
    r"[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\."
    r"(?:0|[1-9][0-9]*|"
    r"[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*"
    r")?"
    # Build identifiers are dot-separated and non-empty.
    # Unlike numeric pre-release identifiers, leading zeroes
    # are valid in build metadata.
    r"(?:\+"
    r"[0-9A-Za-z-]+"
    r"(?:\.[0-9A-Za-z-]+)*"
    r")?"
    r")$"
)

match = pattern.fullmatch(raw)

if not match:
    print(json.dumps({
        "ok": False,
        "error": "EXACT_VERSION_REQUIRED",
        "input": raw,
        "detail": (
            "Use owner/name@version or the canonical "
            "https://play.modiqo.ai/owner/name@version URI."
        ),
    }))
    raise SystemExit(0)

owner = match.group("owner")
name = match.group("name")
version = match.group("version")

print(json.dumps({
    "ok": True,
    "input": raw,
    "owner": owner,
    "name": name,
    "version": version,
    "canonical": (
        f"https://play.modiqo.ai/{owner}/{name}@{version}"
    ),
}, separators=(",", ":")))
