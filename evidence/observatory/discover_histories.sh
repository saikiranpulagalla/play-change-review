#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
POOL="$ROOT/candidate-pool.txt"
OUT="$ROOT/search"

mkdir -p "$OUT"

HELP="$(rote registry play search --help 2>&1 || true)"

if ! grep -q -- '--limit' <<<"$HELP"; then
  echo "ERROR: this Rote CLI does not advertise --limit for registry play search." >&2
  echo >&2
  echo "$HELP" >&2
  exit 2
fi

LIMIT=100

while IFS= read -r play; do
  [[ -n "$play" ]] || continue

  owner="${play%%/*}"
  name="${play#*/}"
  safe="${play//\//__}"
  dest="$OUT/${safe}.txt"

  echo
  echo "============================================================"
  echo "$play"
  echo "query short name: $name"
  echo "============================================================"

  rote registry play search "$name" \
    --limit "$LIMIT" \
    2>&1 \
    | tee "$dest"

done < "$POOL"
