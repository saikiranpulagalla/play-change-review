#!/usr/bin/env python3

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

PAIRS = ROOT / "pairs.tsv"
SELECTION_HASHES = ROOT / "selection-sha256.txt"

PUBLIC_CONTROL = (
    ROOT
    / "controls"
    / "pcr-0.1.0-to-0.1.1-canonical.json"
)

RESULTS = ROOT / "results-attempt-1"

PLAY_WORKTREE = Path(
    "/tmp/pcr-observatory-v0.1.1"
)

PLAY_MAIN = PLAY_WORKTREE / "main.ts"

EXPECTED_COMMIT = (
    "bcfbece96f04470288f6d8c3c01e086093451055"
)

RUNS_PER_PAIR = 3
TIMEOUT_SECONDS = 180


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(obj) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def write_json(path: Path, obj) -> None:
    path.write_text(
        json.dumps(
            obj,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def to_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return str(value)


def verify_selection_hashes() -> None:
    failures = []

    for line in SELECTION_HASHES.read_text().splitlines():
        line = line.strip()

        if not line:
            continue

        expected, raw_path = line.split(
            None,
            1,
        )

        path = REPO / raw_path.strip()

        if not path.exists():
            failures.append(
                f"missing: {raw_path}"
            )
            continue

        actual = sha256_file(path)

        if actual != expected:
            failures.append(
                f"hash mismatch: {raw_path}"
            )

    if failures:
        raise RuntimeError(
            "Frozen selection integrity failed:\n"
            + "\n".join(
                f" - {x}"
                for x in failures
            )
        )


def verify_play_worktree() -> None:
    if not PLAY_MAIN.exists():
        raise RuntimeError(
            f"missing tagged Play source: {PLAY_MAIN}"
        )

    commit = subprocess.check_output(
        [
            "git",
            "-C",
            str(PLAY_WORKTREE),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()

    if commit != EXPECTED_COMMIT:
        raise RuntimeError(
            "wrong Play worktree commit: "
            f"{commit}"
        )

    status = subprocess.check_output(
        [
            "git",
            "-C",
            str(PLAY_WORKTREE),
            "status",
            "--porcelain",
        ],
        text=True,
    )

    if status.strip():
        raise RuntimeError(
            "tagged Play worktree is dirty:\n"
            + status
        )


def extract_presentation(stdout: str):
    candidates = []

    for line in stdout.splitlines():
        line = line.strip()

        if not line.startswith("{"):
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if (
            isinstance(obj, dict)
            and obj.get("schema")
            == "play-change-review/presentation-v1"
        ):
            candidates.append(obj)

    if len(candidates) != 1:
        raise ValueError(
            "expected exactly one PCR presentation JSON "
            f"object, found {len(candidates)}"
        )

    return candidates[0]


def semantic_projection(obj):
    comparison = obj.get("comparison") or {}
    approved = comparison.get("approved") or {}
    candidate = comparison.get("candidate") or {}
    package_files = (
        comparison.get("package_files") or {}
    )

    return {
        "verdict": obj.get("verdict"),
        "approved_identity": approved.get(
            "identity"
        ),
        "candidate_identity": candidate.get(
            "identity"
        ),
        "declared_access_expansion_observed":
            comparison.get(
                "declared_access_expansion_observed"
            ),
        "counts": comparison.get("counts"),
        "reason_codes": comparison.get(
            "reason_codes"
        ),
        "package_files": {
            "comparison_available":
                package_files.get(
                    "comparison_available"
                ),
            "approved_disclosed":
                package_files.get(
                    "approved_disclosed"
                ),
            "candidate_disclosed":
                package_files.get(
                    "candidate_disclosed"
                ),
            "added_total":
                package_files.get(
                    "added_total"
                ),
            "removed_total":
                package_files.get(
                    "removed_total"
                ),
            "truncated":
                package_files.get(
                    "truncated"
                ),
        },
        "blocked_error_code":
            comparison.get("error_code")
            or obj.get("error_code"),
    }


def semantic_hash(obj) -> str:
    return sha256_bytes(
        canonical_bytes(
            semantic_projection(obj)
        )
    )


def run_once(
    *,
    play: str,
    approved_version: str,
    candidate_version: str,
    outdir: Path,
):
    approved_ref = (
        f"{play}@{approved_version}"
    )

    candidate_ref = (
        f"{play}@{candidate_version}"
    )

    outdir.mkdir(
        parents=True,
        exist_ok=False,
    )

    cmd = [
        "rote",
        "play",
        "run",
        str(PLAY_MAIN),
        f"approved={approved_ref}",
        f"candidate={candidate_ref}",
        "--output=json",
        "--yes",
    ]

    env = os.environ.copy()
    env["NO_COLOR"] = "1"

    started = time.perf_counter()
    timeout = False

    try:
        proc = subprocess.run(
            cmd,
            cwd="/tmp",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr

    except subprocess.TimeoutExpired as exc:
        timeout = True
        returncode = None
        stdout = to_text(exc.stdout)
        stderr = to_text(exc.stderr)

    elapsed = time.perf_counter() - started

    (
        outdir / "raw.stdout.txt"
    ).write_text(stdout)

    (
        outdir / "raw.stderr.txt"
    ).write_text(stderr)

    presentation = None
    semantic = None
    sem_hash = None
    parse_error = None
    identity_ok = False
    boundary_ok = False
    comparison_performed = None

    try:
        presentation = extract_presentation(
            stdout
        )

        comparison = (
            presentation.get("comparison")
            or {}
        )

        comparison_performed = (
            comparison.get(
                "comparison_performed"
            )
        )

        approved_identity = (
            comparison.get("approved")
            or {}
        ).get("identity")

        candidate_identity = (
            comparison.get("candidate")
            or {}
        ).get("identity")

        identity_ok = (
            approved_identity
            in (None, approved_ref)
            and candidate_identity
            in (None, candidate_ref)
        )

        if comparison_performed is True:
            identity_ok = (
                identity_ok
                and approved_identity
                == approved_ref
                and candidate_identity
                == candidate_ref
            )

        boundary_ok = (
            comparison.get(
                "reviewed_plays_executed"
            )
            is False
        )

        semantic = semantic_projection(
            presentation
        )

        sem_hash = sha256_bytes(
            canonical_bytes(semantic)
        )

        write_json(
            outdir / "canonical.json",
            presentation,
        )

        write_json(
            outdir / "semantic.json",
            semantic,
        )

        (
            outdir / "semantic.sha256"
        ).write_text(
            sem_hash + "\n"
        )

    except Exception as exc:
        parse_error = (
            f"{type(exc).__name__}: {exc}"
        )

    valid = (
        not timeout
        and returncode == 0
        and parse_error is None
        and identity_ok
        and boundary_ok
    )

    meta = {
        "play": play,
        "approved_ref": approved_ref,
        "candidate_ref": candidate_ref,
        "command": cmd,
        "timeout_seconds":
            TIMEOUT_SECONDS,
        "timed_out": timeout,
        "returncode": returncode,
        "elapsed_seconds": round(
            elapsed,
            6,
        ),
        "stdout_bytes": len(
            stdout.encode("utf-8")
        ),
        "stderr_bytes": len(
            stderr.encode("utf-8")
        ),
        "parse_error": parse_error,
        "comparison_performed":
            comparison_performed,
        "identity_ok": identity_ok,
        "boundary_ok": boundary_ok,
        "semantic_sha256": sem_hash,
        "valid": valid,
    }

    write_json(
        outdir / "meta.json",
        meta,
    )

    return {
        "meta": meta,
        "canonical": presentation,
        "semantic": semantic,
    }


def classify_invalid(runs):
    for run in runs:
        m = run["meta"]

        if m["timed_out"]:
            return "RUNNER_FAILURE"

        if m["returncode"] != 0:
            return "RUNNER_FAILURE"

        if m["parse_error"]:
            return "PARSE_FAILURE"

        if not m["identity_ok"]:
            return "IDENTITY_FAILURE"

        if not m["boundary_ok"]:
            return "BOUNDARY_FAILURE"

    return None


def rate(n: int, d: int):
    return {
        "numerator": n,
        "denominator": d,
        "fraction": (
            n / d
            if d
            else None
        ),
    }


def p90(values):
    if not values:
        return None

    values = sorted(values)

    index = max(
        0,
        math.ceil(
            0.90 * len(values)
        ) - 1,
    )

    return values[index]


def main():
    verify_selection_hashes()
    verify_play_worktree()

    if RESULTS.exists():
        raise RuntimeError(
            f"{RESULTS} already exists. "
            "Refusing to overwrite the first "
            "experimental attempt."
        )

    RESULTS.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        rote_version = subprocess.check_output(
            ["rote", "--version"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception:
        rote_version = None

    environment = {
        "started_at":
            dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
        "hostname":
            platform.node(),
        "platform":
            platform.platform(),
        "python":
            sys.version,
        "rote_version":
            rote_version,
        "pcr_git_commit":
            EXPECTED_COMMIT,
        "pcr_main":
            str(PLAY_MAIN),
        "runs_per_pair":
            RUNS_PER_PAIR,
        "timeout_seconds":
            TIMEOUT_SECONDS,
    }

    write_json(
        RESULTS / "environment.json",
        environment,
    )

    #
    # Public -> local parity gate.
    #
    public_control = json.loads(
        PUBLIC_CONTROL.read_text()
    )

    public_semantic = (
        semantic_projection(
            public_control
        )
    )

    public_hash = sha256_bytes(
        canonical_bytes(
            public_semantic
        )
    )

    public_boundary = (
        (
            public_control.get(
                "comparison"
            )
            or {}
        ).get(
            "reviewed_plays_executed"
        )
        is False
    )

    preflight_dir = (
        RESULTS
        / "preflight"
        / "local-self-review"
    )

    local_control = run_once(
        play=(
            "saikiran-labs/"
            "play-change-review"
        ),
        approved_version="0.1.0",
        candidate_version="0.1.1",
        outdir=preflight_dir,
    )

    local_hash = (
        local_control["meta"][
            "semantic_sha256"
        ]
    )

    parity = (
        public_boundary
        and local_control["meta"][
            "valid"
        ]
        and local_hash
        == public_hash
    )

    preflight = {
        "public_semantic_sha256":
            public_hash,
        "local_semantic_sha256":
            local_hash,
        "public_boundary_ok":
            public_boundary,
        "local_boundary_ok":
            local_control["meta"][
                "boundary_ok"
            ],
        "parity":
            parity,
    }

    write_json(
        RESULTS
        / "preflight"
        / "parity.json",
        preflight,
    )

    print(
        "PUBLIC->LOCAL PARITY:",
        "PASS" if parity else "FAIL",
        flush=True,
    )

    if not parity:
        print(
            "Corpus not executed.",
            file=sys.stderr,
        )
        return 3

    #
    # Frozen pair load.
    #
    with PAIRS.open(
        newline=""
    ) as f:
        pairs = list(
            csv.DictReader(
                f,
                delimiter="\t",
            )
        )

    if len(pairs) != 17:
        raise RuntimeError(
            f"expected 17 frozen pairs, "
            f"found {len(pairs)}"
        )

    pair_results = []
    all_run_elapsed = []
    all_stdout_bytes = []

    for index, row in enumerate(
        pairs,
        start=1,
    ):
        play = row["play"]
        approved_version = (
            row["approved_version"]
        )
        candidate_version = (
            row["candidate_version"]
        )

        safe = (
            play.replace("/", "__")
            + "__"
            + approved_version
            + "__"
            + candidate_version
        )

        pair_dir = (
            RESULTS
            / "runs"
            / safe
        )

        print(
            f"[{index:02d}/17] "
            f"{play} "
            f"{approved_version}"
            " -> "
            f"{candidate_version}",
            flush=True,
        )

        runs = []

        for repetition in range(
            1,
            RUNS_PER_PAIR + 1,
        ):
            print(
                f"    run "
                f"{repetition}/"
                f"{RUNS_PER_PAIR}",
                flush=True,
            )

            result = run_once(
                play=play,
                approved_version=
                    approved_version,
                candidate_version=
                    candidate_version,
                outdir=(
                    pair_dir
                    / f"run-{repetition}"
                ),
            )

            runs.append(result)

            all_run_elapsed.append(
                result["meta"][
                    "elapsed_seconds"
                ]
            )

            all_stdout_bytes.append(
                result["meta"][
                    "stdout_bytes"
                ]
            )

        invalid = classify_invalid(
            runs
        )

        hashes = [
            r["meta"][
                "semantic_sha256"
            ]
            for r in runs
            if r["meta"][
                "semantic_sha256"
            ]
        ]

        if invalid:
            status = invalid

        elif (
            len(hashes)
            != RUNS_PER_PAIR
        ):
            status = "PARSE_FAILURE"

        elif len(set(hashes)) != 1:
            status = "NONDETERMINISTIC"

        else:
            status = "DETERMINISTIC"

        representative = None
        comparison_performed = None
        verdict = None
        material_types = None
        access_expansion = None
        reason_codes = None
        semantic_sha = None

        if status == "DETERMINISTIC":
            representative = runs[0][
                "canonical"
            ]

            comparison = (
                representative.get(
                    "comparison"
                )
                or {}
            )

            comparison_performed = (
                comparison.get(
                    "comparison_performed"
                )
            )

            verdict = representative.get(
                "verdict"
            )

            counts = (
                comparison.get(
                    "counts"
                )
                or {}
            )

            material_types = (
                counts.get(
                    "material_types"
                )
            )

            access_expansion = (
                comparison.get(
                    "declared_access_expansion_observed"
                )
            )

            reason_codes = (
                comparison.get(
                    "reason_codes"
                )
                or []
            )

            semantic_sha = hashes[0]

        pair_result = {
            "play": play,
            "approved_version":
                approved_version,
            "candidate_version":
                candidate_version,
            "status": status,
            "semantic_sha256":
                semantic_sha,
            "verdict": verdict,
            "comparison_performed":
                comparison_performed,
            "material_types":
                material_types,
            "declared_access_expansion_observed":
                access_expansion,
            "reason_codes":
                reason_codes,
            "run_semantic_hashes":
                hashes,
        }

        write_json(
            pair_dir
            / "pair-summary.json",
            pair_result,
        )

        pair_results.append(
            pair_result
        )

    #
    # Verify tagged source still clean.
    #
    verify_play_worktree()

    statuses = Counter(
        p["status"]
        for p in pair_results
    )

    deterministic = [
        p
        for p in pair_results
        if p["status"]
        == "DETERMINISTIC"
    ]

    performed = [
        p
        for p in deterministic
        if p[
            "comparison_performed"
        ]
        is True
    ]

    blocked = [
        p
        for p in deterministic
        if p["verdict"]
        == "BLOCKED"
    ]

    material = [
        p
        for p in performed
        if (
            p["material_types"]
            or 0
        ) > 0
    ]

    access_expanded = [
        p
        for p in performed
        if p[
            "declared_access_expansion_observed"
        ]
        is True
    ]

    material_without_access = [
        p
        for p in material
        if p[
            "declared_access_expansion_observed"
        ]
        is False
    ]

    implementation_changed = [
        p
        for p in performed
        if "IMPLEMENTATION_CHANGED"
        in (
            p["reason_codes"]
            or []
        )
    ]

    verdict_counts = Counter(
        p["verdict"]
        for p in deterministic
    )

    aggregate = {
        "candidate_pool": 23,
        "eligible_pairs": 17,
        "ineligible_pairs": 6,
        "scheduled_corpus_runs": (
            17 * RUNS_PER_PAIR
        ),
        "pair_status_counts":
            dict(sorted(
                statuses.items()
            )),
        "deterministic_pairs":
            len(deterministic),
        "comparison_performed_pairs":
            len(performed),
        "blocked_pairs":
            len(blocked),
        "verdict_counts":
            dict(sorted(
                verdict_counts.items()
            )),
        "material_change_pairs":
            len(material),
        "declared_access_expansion_pairs":
            len(access_expanded),
        "material_without_access_expansion_pairs":
            len(material_without_access),
        "implementation_changed_pairs":
            len(
                implementation_changed
            ),
        "rates": {
            "material_change_among_performed":
                rate(
                    len(material),
                    len(performed),
                ),
            "access_expansion_among_performed":
                rate(
                    len(access_expanded),
                    len(performed),
                ),
            "material_without_access_expansion_among_performed":
                rate(
                    len(
                        material_without_access
                    ),
                    len(performed),
                ),
            "material_without_access_expansion_among_material":
                rate(
                    len(
                        material_without_access
                    ),
                    len(material),
                ),
        },
        "runtime_seconds": {
            "median":
                statistics.median(
                    all_run_elapsed
                )
                if all_run_elapsed
                else None,
            "p90":
                p90(
                    all_run_elapsed
                ),
            "max":
                max(
                    all_run_elapsed
                )
                if all_run_elapsed
                else None,
        },
        "stdout_bytes": {
            "median":
                statistics.median(
                    all_stdout_bytes
                )
                if all_stdout_bytes
                else None,
            "p90":
                p90(
                    all_stdout_bytes
                ),
            "max":
                max(
                    all_stdout_bytes
                )
                if all_stdout_bytes
                else None,
        },
    }

    write_json(
        RESULTS / "aggregate.json",
        aggregate,
    )

    with (
        RESULTS / "pair-summary.tsv"
    ).open("w", newline="") as f:
        writer = csv.writer(
            f,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writerow([
            "play",
            "approved_version",
            "candidate_version",
            "status",
            "verdict",
            "comparison_performed",
            "material_types",
            "access_expansion",
            "semantic_sha256",
        ])

        for p in pair_results:
            writer.writerow([
                p["play"],
                p["approved_version"],
                p["candidate_version"],
                p["status"],
                p["verdict"],
                p[
                    "comparison_performed"
                ],
                p["material_types"],
                p[
                    "declared_access_expansion_observed"
                ],
                p["semantic_sha256"],
            ])

    print()
    print("OBSERVATORY COMPLETE")
    print(
        "eligible pairs:",
        17,
    )
    print(
        "deterministic:",
        len(deterministic),
    )
    print(
        "performed:",
        len(performed),
    )
    print(
        "blocked:",
        len(blocked),
    )
    print(
        "material:",
        len(material),
    )
    print(
        "access expansion:",
        len(access_expanded),
    )
    print(
        "material without access expansion:",
        len(material_without_access),
    )
    print()
    print(
        "aggregate:",
        RESULTS / "aggregate.json",
    )
    print(
        "pair summary:",
        RESULTS / "pair-summary.tsv",
    )

    if len(deterministic) != 17:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
