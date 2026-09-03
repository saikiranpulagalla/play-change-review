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
    r"[0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?"
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
