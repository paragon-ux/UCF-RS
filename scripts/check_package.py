#!/usr/bin/env python3
"""Check what `npm pack` would publish.

Runs `npm pack --dry-run --json`, then verifies:

* the file list is exactly the allowlist below (nothing extra, nothing missing);
* no test, fixture, store, scratch, or cache paths are included;
* no packed file mentions a personal or machine-specific path.

Prints the file list and size. Exit code 0 on success, 1 on a problem, 2 if npm
could not be run.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

EXPECTED = {
    "LICENSE",
    "README.md",
    "README.dev.md",
    "bin/ucf-rs.js",
    "docs/agent-guide.md",
    "docs/commands.md",
    "docs/user-guide.md",
    "package.json",
    "scripts/ucf_rs.py",
}
FORBIDDEN_PATH = re.compile(
    r"(^|/)(tests?|examples|scratch|\.github|\.ucf-rs|\.waymark|\.tmp[^/]*|__pycache__|node_modules|site)(/|$)|\.pyc$|\.tgz$"
)
PERSONAL = re.compile(
    r"C:\\Users|C:/Users|/Users/[A-Za-z]|/home/[A-Za-z]|\.gemini|antigravity|[\\/]brain[\\/]|\bscratch[\\/]",
    re.IGNORECASE,
)


def run_pack(root: Path) -> list[dict]:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm was not found on PATH")
    result = subprocess.run(
        [npm, "pack", "--dry-run", "--json", "--ignore-scripts"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"npm pack failed ({result.returncode}): {result.stderr.strip()}")
    return json.loads(result.stdout)


def check(root: Path, report: dict) -> list[str]:
    problems: list[str] = []
    paths = {entry["path"].replace("\\", "/") for entry in report["files"]}
    for path in sorted(paths - EXPECTED):
        problems.append(f"unexpected file in package: {path}")
    for path in sorted(EXPECTED - paths):
        problems.append(f"expected file missing from package: {path}")
    for path in sorted(paths):
        if FORBIDDEN_PATH.search(path):
            problems.append(f"forbidden path in package: {path}")
        file = root / path
        if file.is_file():
            try:
                text = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if PERSONAL.search(line):
                    problems.append(f"personal or machine path in {path}:{number}: {line.strip()[:80]}")
    return problems


def main() -> int:
    try:
        report = run_pack(REPOSITORY)[0]
    except (RuntimeError, OSError, json.JSONDecodeError, IndexError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"{report['name']}@{report['version']}")
    for entry in sorted(report["files"], key=lambda item: item["path"]):
        print(f"  {entry['size']:>8}  {entry['path']}")
    print(f"files: {report['entryCount']}  packed: {report['size']} bytes  unpacked: {report['unpackedSize']} bytes")
    problems = check(REPOSITORY, report)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print("package contents OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
