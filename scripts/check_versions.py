#!/usr/bin/env python3
"""Check that every place UCF-RS records its version agrees.

The source of truth is TOOL_VERSION in scripts/ucf_rs.py: it is the version
written into every authority record, and it ships inside the npm package.
pyproject.toml and package.json must match it. Bump all three together.

Usage:
    python scripts/check_versions.py
    python scripts/check_versions.py --tag v0.3.0

Exit code 0 when everything agrees, 1 on a mismatch, 2 on a file that cannot be
read or parsed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def tool_version(root: Path) -> str:
    text = (root / "scripts" / "ucf_rs.py").read_text(encoding="utf-8")
    match = re.search(r'^TOOL_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("TOOL_VERSION not found in scripts/ucf_rs.py")
    return match.group(1)


def pyproject_version(root: Path) -> str:
    # tomllib needs Python 3.11; requires-python is 3.10, so read the one key.
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    if not section:
        raise ValueError("[project] table not found in pyproject.toml")
    match = re.search(r'^version\s*=\s*"([^"]+)"', section.group(1), re.MULTILINE)
    if not match:
        raise ValueError("[project] version not found in pyproject.toml")
    return match.group(1)


def package_json_version(root: Path) -> str:
    data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str):
        raise ValueError("package.json has no string version")
    return version


def collect(root: Path) -> dict[str, str]:
    return {
        "scripts/ucf_rs.py (TOOL_VERSION)": tool_version(root),
        "pyproject.toml": pyproject_version(root),
        "package.json": package_json_version(root),
    }


def problems(versions: dict[str, str], tag: str | None) -> list[str]:
    found: list[str] = []
    for name, value in versions.items():
        if not SEMVER.match(value):
            found.append(f"{name}: {value!r} is not a semantic version")
    if len(set(versions.values())) > 1:
        found.append("versions disagree: " + ", ".join(f"{k}={v}" for k, v in versions.items()))
    if tag is not None:
        expected = "v" + next(iter(versions.values()))
        if tag != expected:
            found.append(f"tag {tag!r} does not match version (expected {expected!r})")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="release tag to compare, for example v0.3.0")
    parser.add_argument("--root", default=str(REPOSITORY), help="repository root")
    args = parser.parse_args(argv)
    try:
        versions = collect(Path(args.root))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for name, value in versions.items():
        print(f"{name}: {value}")
    found = problems(versions, args.tag)
    for message in found:
        print(f"error: {message}", file=sys.stderr)
    if not found:
        print("versions agree" + (f" and match tag {args.tag}" if args.tag else ""))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
