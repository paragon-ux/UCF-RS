#!/usr/bin/env python3
"""Build and validate a temporary initialized UCF-RS status fixture."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    example = repository / "examples" / "managed-edit"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "managed-edit"
        shutil.copytree(example, root)
        cli = [sys.executable, str(repository / "scripts" / "ucf_rs.py"), "--root", str(root)]
        run(cli + ["init"])
        run(
            cli
            + [
                "activate",
                "--handle",
                "AUTH-ROTATE",
                "--path",
                "src/auth.py",
                "--lines",
                "1:2",
            ]
        )
        run(cli + ["status", "--strict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
