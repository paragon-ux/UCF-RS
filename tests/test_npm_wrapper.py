"""Tests for the npm launcher (bin/ucf-rs.js). Skipped when Node is not installed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY_ROOT / "bin" / "ucf-rs.js"
NODE = shutil.which("node")


def run_launcher(args: list[str], env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert NODE is not None
    env = os.environ.copy()
    env.pop("UCF_RS_PYTHON", None)
    env.update(env_extra)
    return subprocess.run(
        [NODE, str(LAUNCHER), *args],
        cwd=str(REPOSITORY_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@unittest.skipIf(NODE is None, "node is not installed")
class LauncherTests(unittest.TestCase):
    def test_help_runs_through_override(self) -> None:
        result = run_launcher(["--help"], {"UCF_RS_PYTHON": sys.executable})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("usage", result.stdout.lower())

    def test_exit_codes_pass_through(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {"UCF_RS_PYTHON": sys.executable}
            strict = run_launcher(["--root", directory, "status", "--strict"], env)
            self.assertEqual(strict.returncode, 1, msg=strict.stderr)
            self.assertIn("E_STORE_UNINITIALIZED", strict.stderr)
            invalid = run_launcher(["--root", directory, "no-such-command"], env)
            self.assertEqual(invalid.returncode, 2, msg=invalid.stderr)

    def test_arguments_are_not_interpreted_by_a_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "pwned"
            hostile = f"x & echo hi > {marker} ; touch {marker}"
            result = run_launcher(
                ["--root", directory, "resolve", "--path", hostile],
                {"UCF_RS_PYTHON": sys.executable},
            )
            # `resolve` on a path with no cited ranges succeeds with no overlays;
            # what matters is that the launcher reached Python and no shell ran.
            self.assertNotEqual(result.returncode, 127, msg=result.stderr)
            self.assertFalse(marker.exists())

    def test_bad_override_gives_clear_error_and_exit_127(self) -> None:
        missing = str(Path(tempfile.gettempdir()) / "definitely-not-a-python")
        result = run_launcher(["--help"], {"UCF_RS_PYTHON": missing})
        self.assertEqual(result.returncode, 127)
        self.assertIn("UCF_RS_PYTHON", result.stderr)
        self.assertIn("3.10", result.stderr)

    def test_discovery_order_by_platform(self) -> None:
        script = (
            "const m = require(process.argv[1]);"
            "const names = (env, p) => m.candidates(env, p).map(c => [c.command, ...c.args].join(' '));"
            "console.log(JSON.stringify({"
            "win: names({}, 'win32'), posix: names({}, 'linux'),"
            "override: names({UCF_RS_PYTHON: '/opt/py'}, 'linux')}));"
        )
        assert NODE is not None
        result = subprocess.run(
            [NODE, "-e", script, str(LAUNCHER)],
            capture_output=True,
            text=True,
            check=True,
        )
        order = json.loads(result.stdout)
        self.assertEqual(order["win"], ["py -3", "python"])
        self.assertEqual(order["posix"], ["python3", "python"])
        self.assertEqual(order["override"], ["/opt/py"])

    def test_launcher_never_uses_a_shell(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("shell:", source)
        self.assertNotIn("execSync", source)
        self.assertNotIn("exec(", source)


if __name__ == "__main__":
    unittest.main()
