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

python3 - \
  "$ROOT/resources/tests/fixtures/ghp-0.0.5.json" \
  "$APPROVED" \
  "$CANDIDATE" <<'PY'
import copy
import json
import sys

src, approved_path, candidate_path = sys.argv[1:]

base = json.load(open(src))

approved = copy.deepcopy(base)
candidate = copy.deepcopy(base)

a = approved["data"]["play_inspect"]
c = candidate["data"]["play_inspect"]

a["identity"]["owner"] = "pcrtest"
a["identity"]["name"] = "binding"
a["identity"]["version"] = "1.0.0"

# Deliberately WRONG. Caller will request 1.0.1.
c["identity"]["owner"] = "pcrtest"
c["identity"]["name"] = "binding"
c["identity"]["version"] = "9.9.9"

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
  approved=pcrtest/binding@1.0.0 \
  candidate=pcrtest/binding@1.0.1 \
  >"$OUT" 2>&1

cat "$OUT"

python3 - "$OUT" <<'PY'
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()

assert "VERDICT    BLOCKED" in text

assert (
    "CANDIDATE_INSPECTION_IDENTITY_MISMATCH"
    in text
)

assert (
    "Requested pcrtest/binding@1.0.1"
    in text
)

assert (
    "pcrtest/binding@9.9.9"
    in text
)

# Comparison must never proceed after transport evidence is wrong.
assert "MATERIAL_METHOD_CHANGE" not in text
assert "EXACT_MATCH" not in text

print()
print("PASS  mismatched inspection identity fails closed")
PY
