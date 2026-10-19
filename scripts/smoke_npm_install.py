#!/usr/bin/env python3
"""Smoke test the packed npm tarball.

Packs the project, installs the tarball into an empty temporary project, and runs
the installed `ucf-rs` command: `--help`, plus a `status --strict` on an empty
folder to confirm that exit codes pass through the launcher (expects 1).

Nothing is published. Exit code 0 on success, 1 on a failure.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)


def fail(message: str, result: subprocess.CompletedProcess[str] | None = None) -> int:
    print(f"error: {message}", file=sys.stderr)
    if result is not None:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
    return 1


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        return fail("npm was not found on PATH")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        pack_dir = work / "pack"
        project = work / "project"
        empty = work / "empty"
        for folder in (pack_dir, project, empty):
            folder.mkdir()

        packed = run([npm, "pack", "--json", "--ignore-scripts", "--pack-destination", str(pack_dir)], REPOSITORY)
        if packed.returncode != 0:
            return fail("npm pack failed", packed)
        tarball = pack_dir / json.loads(packed.stdout)[0]["filename"]
        print(f"packed {tarball.name} ({tarball.stat().st_size} bytes)")

        (project / "package.json").write_text('{"name":"smoke","version":"0.0.0","private":true}\n', encoding="utf-8")
        installed = run(
            [npm, "install", "--ignore-scripts", "--no-audit", "--no-fund", "--no-package-lock", str(tarball)],
            project,
        )
        if installed.returncode != 0:
            return fail("npm install of the tarball failed", installed)

        helped = run([npm, "exec", "--no-install", "--", "ucf-rs", "--help"], project)
        if helped.returncode != 0 or "usage" not in helped.stdout.lower():
            return fail("`ucf-rs --help` failed", helped)
        print("ucf-rs --help: OK")

        strict = run([npm, "exec", "--no-install", "--", "ucf-rs", "--root", str(empty), "status", "--strict"], project)
        if strict.returncode != 1 or "E_STORE_UNINITIALIZED" not in strict.stderr:
            return fail("expected exit 1 with E_STORE_UNINITIALIZED from `status --strict`", strict)
        print("ucf-rs status --strict on an empty folder: exit 1 as expected")
    print("tarball smoke test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
