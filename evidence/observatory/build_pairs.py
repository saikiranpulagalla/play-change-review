#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POOL = ROOT / "candidate-pool.txt"
INFO = ROOT / "info"
SEARCH = ROOT / "search"

OUT_HISTORY = ROOT / "version-history.tsv"
OUT_PAIRS = ROOT / "pairs.tsv"


SEMVER = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

ITEM = re.compile(
    r"^\s*\d+\.\s+([a-z0-9-]+)\s+\("
)

FIELD = re.compile(
    r"^\s*(version|namespace|status):\s*(\S+)\s*$"
)

TOTAL = re.compile(r"^\s*total_results:\s*(\d+)\s*$")
LIMIT = re.compile(r"^\s*limit:\s*(\d+)\s*$")
HEAD_VERSION = re.compile(r"^\s*version:\s*(\S+)\s*$")


def parse_semver(value: str):
    m = SEMVER.fullmatch(value)
    if not m:
        return None

    major, minor, patch, prerelease, build = m.groups()

    return {
        "value": value,
        "core": (int(major), int(minor), int(patch)),
        "prerelease": prerelease,
        "build": build,
    }


def safe_name(play: str) -> str:
    return play.replace("/", "__")


def snapshot_version(play: str) -> str:
    p = INFO / f"{safe_name(play)}.txt"

    if not p.exists():
        raise RuntimeError(
            f"{play}: missing committed head snapshot {p}"
        )

    versions = []

    for line in p.read_text().splitlines():
        m = HEAD_VERSION.match(line)
        if m:
            versions.append(m.group(1))

    if len(versions) != 1:
        raise RuntimeError(
            f"{play}: expected exactly one snapshot version, "
            f"found {versions!r}"
        )

    return versions[0]


def parse_search(play: str):
    owner, wanted_name = play.split("/", 1)

    p = SEARCH / f"{safe_name(play)}.txt"

    if not p.exists():
        raise RuntimeError(
            f"{play}: missing search capture {p}"
        )

    lines = p.read_text().splitlines()

    total = None
    limit = None

    for line in lines:
        m = TOTAL.match(line)
        if m:
            total = int(m.group(1))

        m = LIMIT.match(line)
        if m:
            limit = int(m.group(1))

    if total is None or limit is None:
        raise RuntimeError(
            f"{play}: search output missing total_results/limit"
        )

    if total > limit:
        raise RuntimeError(
            f"{play}: search truncated "
            f"(total_results={total}, limit={limit})"
        )

    entries = []
    current = None

    def finish():
        nonlocal current

        if current is None:
            return

        if (
            current.get("name") == wanted_name
            and current.get("namespace") == owner
            and current.get("status") == "approved"
            and current.get("version")
        ):
            entries.append(current)

        current = None

    for line in lines:
        m = ITEM.match(line)

        if m:
            finish()
            current = {"name": m.group(1)}
            continue

        if current is None:
            continue

        m = FIELD.match(line)

        if m:
            current[m.group(1)] = m.group(2)

    finish()

    return entries, total, limit


def main():
    plays = [
        line.strip()
        for line in POOL.read_text().splitlines()
        if line.strip()
    ]

    histories = []
    pairs = []
    fatal = []

    for play in plays:
        try:
            snap = snapshot_version(play)
            snap_sv = parse_semver(snap)

            if snap_sv is None:
                raise RuntimeError(
                    f"snapshot candidate is not valid SemVer: {snap}"
                )

            if snap_sv["prerelease"] is not None:
                histories.append(
                    (
                        play,
                        snap,
                        "INELIGIBLE",
                        "snapshot candidate is prerelease",
                        "",
                    )
                )
                continue

            entries, total, limit = parse_search(play)

            stable = {}

            for entry in entries:
                value = entry["version"]
                sv = parse_semver(value)

                if sv is None:
                    continue

                if sv["prerelease"] is not None:
                    continue

                # Ignore anything released after the frozen
                # snapshot candidate.
                if sv["core"] > snap_sv["core"]:
                    continue

                stable.setdefault(sv["core"], []).append(value)

            # Build metadata does not affect SemVer precedence.
            ambiguous = {
                core: values
                for core, values in stable.items()
                if len(set(values)) > 1
            }

            if ambiguous:
                raise RuntimeError(
                    "ambiguous versions sharing SemVer precedence: "
                    + repr(ambiguous)
                )

            ordered = [
                values[0]
                for core, values in sorted(stable.items())
            ]

            if snap not in ordered:
                raise RuntimeError(
                    f"snapshot candidate {snap} absent from "
                    f"filtered registry search history {ordered!r}"
                )

            # Snapshot candidate must be the highest allowed version.
            if ordered[-1] != snap:
                raise RuntimeError(
                    f"snapshot candidate {snap} is not highest "
                    f"history version at/below snapshot: {ordered!r}"
                )

            rendered = ",".join(ordered)

            if len(ordered) < 2:
                histories.append(
                    (
                        play,
                        snap,
                        "INELIGIBLE",
                        "only one stable approved release",
                        rendered,
                    )
                )
                continue

            approved = ordered[-2]
            candidate = ordered[-1]

            histories.append(
                (
                    play,
                    snap,
                    "ELIGIBLE",
                    "",
                    rendered,
                )
            )

            pairs.append(
                (
                    play,
                    approved,
                    candidate,
                )
            )

        except Exception as exc:
            fatal.append(
                f"{play}: {exc}"
            )

    if fatal:
        print(
            "HISTORY DISCOVERY FAILED CLOSED",
            file=sys.stderr,
        )

        for item in fatal:
            print(
                f" - {item}",
                file=sys.stderr,
            )

        return 2

    with OUT_HISTORY.open("w") as f:
        f.write(
            "play\tsnapshot_candidate\teligibility"
            "\treason\tdiscovered_stable_versions\n"
        )

        for row in histories:
            f.write("\t".join(row) + "\n")

    with OUT_PAIRS.open("w") as f:
        f.write(
            "play\tapproved_version\tcandidate_version\n"
        )

        for row in pairs:
            f.write("\t".join(row) + "\n")

    print(
        f"candidate_pool={len(plays)}"
    )
    print(
        f"eligible_pairs={len(pairs)}"
    )
    print(
        f"ineligible={len(plays) - len(pairs)}"
    )
    print(
        f"history={OUT_HISTORY}"
    )
    print(
        f"pairs={OUT_PAIRS}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
