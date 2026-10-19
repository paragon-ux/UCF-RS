"""Release metadata checks: versions agree and package.json stays minimal."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_check_versions():
    path = REPOSITORY_ROOT / "scripts" / "check_versions.py"
    spec = importlib.util.spec_from_file_location("check_versions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_versions = load_check_versions()


class VersionConsistencyTests(unittest.TestCase):
    def test_repository_versions_agree(self) -> None:
        versions = check_versions.collect(REPOSITORY_ROOT)
        self.assertEqual(check_versions.problems(versions, None), [], msg=versions)

    def test_disagreement_is_reported(self) -> None:
        found = check_versions.problems({"a": "0.3.0", "b": "0.2.0", "c": "0.3.0"}, None)
        self.assertTrue(any("disagree" in message for message in found))

    def test_tag_must_be_v_plus_version(self) -> None:
        versions = {"a": "0.3.0", "b": "0.3.0"}
        self.assertEqual(check_versions.problems(versions, "v0.3.0"), [])
        self.assertTrue(check_versions.problems(versions, "0.3.0"))
        self.assertTrue(check_versions.problems(versions, "v0.3.1"))

    def test_non_semver_is_reported(self) -> None:
        self.assertTrue(check_versions.problems({"a": "0.3"}, None))


class PackageJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))

    def test_repository_url_matches_trusted_publishing_requirement(self) -> None:
        # npm trusted publishing and provenance compare this string exactly.
        self.assertEqual(
            self.package["repository"]["url"],
            "git+https://github.com/paragon-ux/UCF-RS.git",
        )

    def test_no_dependencies_and_no_lifecycle_scripts(self) -> None:
        for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            self.assertNotIn(key, self.package)
        scripts = self.package.get("scripts", {})
        for hook in ("preinstall", "install", "postinstall", "prepare", "prepublish", "prepublishOnly"):
            self.assertNotIn(hook, scripts)

    def test_files_allowlist_excludes_tests_and_state(self) -> None:
        files = self.package["files"]
        for entry in files:
            for banned in ("tests", ".ucf-rs", "scratch", "examples", ".github"):
                self.assertNotIn(banned, entry)
        self.assertIn("scripts/ucf_rs.py", files)
        self.assertEqual(self.package["bin"], {"ucf-rs": "bin/ucf-rs.js"})

    def test_license_matches_license_file(self) -> None:
        self.assertEqual(self.package["license"], "MIT")
        self.assertTrue((REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))


if __name__ == "__main__":
    unittest.main()
