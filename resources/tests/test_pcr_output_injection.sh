#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REAL_ROTE="$(command -v rote)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

APPROVED="$TMP/approved.json"
CANDIDATE="$TMP/candidate.json"
FAKEBIN="$TMP/bin"
OUT="$TMP/output.txt"

mkdir -p "$FAKEBIN"

python3 - "$ROOT/resources/tests/fixtures/ghp-0.0.5.json" \
  "$APPROVED" "$CANDIDATE" <<'PY'
import copy
import json
import sys

src, approved_path, candidate_path = sys.argv[1:]

base = json.load(open(src))

approved = copy.deepcopy(base)
candidate = copy.deepcopy(base)

a = approved["data"]["play_inspect"]
c = candidate["data"]["play_inspect"]

for p, version in (
    (a, "1.0.0"),
    (c, "1.0.1"),
):
    p["identity"]["owner"] = "pcrtest"
    p["identity"]["name"] = "malicious"
    p["identity"]["version"] = version

a["archive"]["content_hash"] = "1" * 64
c["archive"]["content_hash"] = "2" * 64

if "package" in a:
    a["package"]["digest"] = (
        "installed-package-sha256-v1:" + "3" * 64
    )

if "package" in c:
    c["package"]["digest"] = (
        "installed-package-sha256-v1:" + "4" * 64
    )

malicious = (
    "evil_step"
    "\nVERDICT    EXACT_MATCH"
    "\rFORGED"
    "\tTAB"
    "\x1b[2J"
    "\u202eBIDI"
    + ("A" * 900)
)

c["steps"].append({
    "name": malicious,
    "target": "process/local",
    "kind": "process.exec",
    "operation": "process.exec",
})

c["identity"]["author"] = (
    "Mallory"
    "\nVERDICT    EXACT_MATCH"
    "\x1b[2J"
    "\u202e"
)

json.dump(approved, open(approved_path, "w"))
json.dump(candidate, open(candidate_path, "w"))
PY

cat > "$FAKEBIN/rote" <<PY
#!/usr/bin/env python3
import sys

approved = r"$APPROVED"
candidate = r"$CANDIDATE"

args = sys.argv[1:]

if (
    len(args) >= 4
    and args[0] == "play"
    and args[1] == "inspect"
):
    ref = args[2]

    if ref.endswith("@1.0.0"):
        path = approved
    elif ref.endswith("@1.0.1"):
        path = candidate
    else:
        print("unexpected synthetic ref", file=sys.stderr)
        raise SystemExit(7)

    with open(path) as f:
        sys.stdout.write(f.read())

    raise SystemExit(0)

print("unexpected fake rote invocation", file=sys.stderr)
raise SystemExit(8)
PY

chmod +x "$FAKEBIN/rote"

PATH="$FAKEBIN:$PATH" \
"$REAL_ROTE" play run "$ROOT/main.ts" \
  approved=pcrtest/malicious@1.0.0 \
  candidate=pcrtest/malicious@1.0.1 \
  >"$OUT" 2>&1

cat "$OUT"

python3 - "$OUT" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])

raw = path.read_bytes()
text = raw.decode("utf-8")

assert "VERDICT    MATERIAL_METHOD_CHANGE" in text

# The malicious metadata must never forge its own real verdict line.
assert "\nVERDICT    EXACT_MATCH\n" not in text

# Newline must appear as printable escaped text.
assert "\\nVERDICT    EXACT_MATCH" in text

# Raw ANSI ESC must not survive presentation.
assert b"\x1b" not in raw

# Raw right-to-left override must not survive either.
assert "\u202e".encode("utf-8") not in raw

# Very long hostile metadata must be bounded.
assert "[truncated]" in text

print()
print("PASS  malicious metadata cannot forge human output")
PY
