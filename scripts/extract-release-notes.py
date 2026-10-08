#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one release section from CHANGELOG.md."
    )
    parser.add_argument("--version", required=True, help="Version such as v1.0.0")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the changelog file.",
    )
    parser.add_argument("--output", required=True, help="Output notes file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not re.fullmatch(r"v\d+\.\d+\.\d+", args.version):
        raise SystemExit(f"Invalid semantic version tag: {args.version}")

    bare_version = args.version.removeprefix("v")
    changelog = Path(args.changelog)
    output = Path(args.output)

    lines = changelog.read_text(encoding="utf-8").splitlines()
    header = re.compile(rf"^## \[{re.escape(bare_version)}\] - .+$")

    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        raise SystemExit(f"No changelog entry found for {bare_version}")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ["):
            end = i
            break

    notes = "\n".join(lines[start + 1 : end]).strip()
    if not notes:
        raise SystemExit(f"Changelog entry for {bare_version} is empty")

    output.write_text(notes + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
