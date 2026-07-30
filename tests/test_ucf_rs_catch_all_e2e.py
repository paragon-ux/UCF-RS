from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "ucf_rs.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ucf_rs_e2e_under_test", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
ucf = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = ucf
MODULE_SPEC.loader.exec_module(ucf)


class UcfRsCatchAllE2ETests(unittest.TestCase):
    def make_root(self) -> tempfile.TemporaryDirectory[str]:
        fixture_root = REPOSITORY_ROOT / ".tmp-test"
        fixture_root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=fixture_root)
        root = Path(temporary.name)
        (root / "docs").mkdir()
        (root / "src").mkdir()
        self.write(
            root / "docs" / "handle-registry.jsonl",
            json.dumps(
                {"handle": "AUTH-ROTATE", "type": "test", "source": "test"},
                sort_keys=True,
            )
            + "\n",
        )
        return temporary

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def activate(
        self,
        root: Path,
        path: str,
        lines: str,
    ) -> int:
        return ucf.main(
            [
                "--root",
                str(root),
                "activate",
                "--handle",
                "AUTH-ROTATE",
                "--path",
                path,
                "--lines",
                lines,
            ]
        )

    def status_by_partition(self, root: Path) -> dict[str, dict[str, object]]:
        report = ucf.status_report(
            root,
            ucf.store_paths(root, ucf.STORE_DEFAULT),
        )
        return {
            str(item["partition_id"]): item
            for item in report["partitions"]
        }

    def assert_store_integrity(self, root: Path) -> None:
        paths = ucf.store_paths(root, ucf.STORE_DEFAULT)
        _, _, diagnostics = ucf.read_store(paths)
        self.assertEqual(diagnostics, [])

    def test_full_multi_record_offline_replay_lifecycle(self) -> None:
        """Exercise queue, descendant replay, acceptance, export, and chain integrity."""
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)

            a_original = "header\nalpha\n"
            b_original = "beta\nfooter\n"
            c_original = "gamma\n"

            a_path = root / "src" / "a.py"
            b_path = root / "src" / "b.py"
            c_path = root / "src" / "c.py"

            self.write(a_path, a_original)
            self.write(b_path, b_original)
            self.write(c_path, c_original)

            self.assertEqual(
                ucf.main(["--root", str(root), "init"]),
                0,
            )
            self.assertEqual(
                self.activate(root, "src/a.py", "2:2"),
                0,
            )
            self.assertEqual(
                self.activate(root, "src/b.py", "1:1"),
                0,
            )

            a_insert_at = a_original.index("alpha")
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/a.py",
                        "--start",
                        str(a_insert_at),
                        "--end",
                        str(a_insert_at),
                        "--insert",
                        "offline-",
                        "--boundary-policy",
                        "inside",
                    ]
                ),
                0,
            )

            b_insert_at = b_original.index("beta") + 2
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/b.py",
                        "--start",
                        str(b_insert_at),
                        "--end",
                        str(b_insert_at),
                        "--insert",
                        "offline-",
                        "--boundary-policy",
                        "outside",
                    ]
                ),
                0,
            )

            queued = self.jsonl(paths.offline_queue)
            self.assertEqual(len(queued), 2)
            self.assertTrue(
                all(
                    isinstance(record.get("base_operation_hash"), str)
                    and record["base_operation_hash"]
                    for record in queued
                )
            )

            # Advance authority through an unrelated document.
            self.assertEqual(
                self.activate(root, "src/c.py", "1:1"),
                0,
            )

            before_replay_operations = len(self.jsonl(paths.operations))
            before_replay_index = len(self.jsonl(paths.index))

            self.assertEqual(
                ucf.main(["--root", str(root), "replay-offline"]),
                0,
            )

            self.assertEqual(
                paths.offline_queue.read_text(encoding="utf-8"),
                "",
            )
            self.assertEqual(
                len(self.jsonl(paths.offline_replayed)),
                2,
            )
            self.assertEqual(
                len(self.jsonl(paths.operations)),
                before_replay_operations + 2,
            )
            self.assertEqual(
                len(self.jsonl(paths.index)),
                before_replay_index + 2,
            )

            statuses = self.status_by_partition(root)
            self.assertEqual(
                statuses["AUTH-ROTATE/001"]["status"],
                "changed_unaccepted",
            )
            self.assertEqual(
                statuses["AUTH-ROTATE/002"]["status"],
                "changed_unaccepted",
            )
            self.assertEqual(
                statuses["AUTH-ROTATE/003"]["status"],
                "valid",
            )

            replay_operations = self.jsonl(paths.operations)[-2:]
            replay_policies = [
                operation["edits"][0]["boundary_policy"]
                for operation in replay_operations
            ]
            self.assertEqual(replay_policies, ["inside", "outside"])

            self.assert_store_integrity(root)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "accept",
                        "--partition-id",
                        "AUTH-ROTATE/001",
                    ]
                ),
                0,
            )
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "accept",
                        "--partition-id",
                        "AUTH-ROTATE/002",
                    ]
                ),
                0,
            )

            statuses = self.status_by_partition(root)
            self.assertTrue(
                all(item["status"] == "valid" for item in statuses.values())
            )

            self.assertEqual(
                ucf.main(["--root", str(root), "export", "ledger"]),
                0,
            )
            self.assertEqual(
                ucf.main(["--root", str(root), "status", "--strict"]),
                0,
            )
            self.assert_store_integrity(root)

    def test_conflict_preflight_prevents_partial_multi_record_replay(self) -> None:
        """A conflict in any queued record must prevent every replay mutation."""
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)

            a_original = "alpha\n"
            b_original = "beta\nfooter\n"
            a_path = root / "src" / "a.py"
            b_path = root / "src" / "b.py"
            self.write(a_path, a_original)
            self.write(b_path, b_original)

            self.assertEqual(
                self.activate(root, "src/a.py", "1:1"),
                0,
            )
            self.assertEqual(
                self.activate(root, "src/b.py", "1:1"),
                0,
            )

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/a.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "offline-a\n",
                    ]
                ),
                0,
            )
            a_offline_text = a_path.read_text(encoding="utf-8")

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/b.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "offline-b\n",
                    ]
                ),
                0,
            )

            queue_before = paths.offline_queue.read_text(encoding="utf-8")
            replay_archive_before = (
                paths.offline_replayed.read_text(encoding="utf-8")
                if paths.offline_replayed.exists()
                else ""
            )

            operations, index_records = ucf.read_store_for_mutation(paths)
            _, current_epoch_hash = ucf.last_epoch(index_records)

            # Simulate an authoritative same-document edit outside all active
            # partitions. It appends an operation but intentionally does not
            # advance the citation epoch.
            b_server_text = b_original + "server\n"
            self.write(b_path, b_server_text)
            ucf.append_operation(
                paths,
                operations,
                "edit",
                ucf.document_id(root, "src/b.py"),
                current_epoch_hash,
                ucf.document_hash_text(b_original),
                ucf.document_hash_text(b_server_text),
                [
                    ucf.edit_record(
                        len(b_original),
                        len(b_original),
                        "server\n",
                        "outside",
                    )
                ],
                [],
            )

            operation_count = len(self.jsonl(paths.operations))
            index_count = len(self.jsonl(paths.index))

            self.assertEqual(
                ucf.main(["--root", str(root), "replay-offline"]),
                2,
            )

            self.assertEqual(
                len(self.jsonl(paths.operations)),
                operation_count,
            )
            self.assertEqual(
                len(self.jsonl(paths.index)),
                index_count,
            )
            self.assertEqual(
                paths.offline_queue.read_text(encoding="utf-8"),
                queue_before,
            )
            current_replay_archive = (
                paths.offline_replayed.read_text(encoding="utf-8")
                if paths.offline_replayed.exists()
                else ""
            )
            self.assertEqual(
                current_replay_archive,
                replay_archive_before,
            )

            # No first-record replay occurred before the second-record conflict.
            self.assertEqual(
                a_path.read_text(encoding="utf-8"),
                a_offline_text,
            )
            self.assertEqual(
                b_path.read_text(encoding="utf-8"),
                b_server_text,
            )
            self.assert_store_integrity(root)

    def test_genesis_queue_with_unrelated_descendant_authority_succeeds(self) -> None:
        """A queue at genesis (None anchor) can replay across unrelated authority."""
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)

            source = root / "src" / "auth.py"
            other = root / "src" / "other.py"
            self.write(source, "alpha\nbeta\n")
            self.write(other, "gamma\n")

            # Queue before any authoritative operation exists.
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "offline\n",
                    ]
                ),
                0,
            )

            queued = self.jsonl(paths.offline_queue)
            self.assertEqual(len(queued), 1)
            self.assertIn("base_operation_hash", queued[0])
            self.assertIsNone(queued[0]["base_operation_hash"])

            # Advance authority through an unrelated document.
            self.assertEqual(
                self.activate(root, "src/other.py", "1:1"),
                0,
            )

            before_ops = len(self.jsonl(paths.operations))
            before_idx = len(self.jsonl(paths.index))

            self.assertEqual(
                ucf.main(["--root", str(root), "replay-offline"]),
                0,
            )

            self.assertEqual(
                paths.offline_queue.read_text(encoding="utf-8"),
                "",
            )
            self.assertEqual(
                len(self.jsonl(paths.operations)),
                before_ops + 1,
            )
            # Genesis queue has no active partitions to transform, so no new
            # index record is appended — only the operation log grows.
            self.assertEqual(
                len(self.jsonl(paths.index)),
                before_idx,
            )
            self.assert_store_integrity(root)

    def test_legacy_record_missing_base_operation_hash_is_rejected(self) -> None:
        """A preexisting queue record without the anchor field is safely rejected."""
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)

            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(
                self.activate(root, "src/auth.py", "1:2"),
                0,
            )

            legacy: dict[str, object] = {
                "schema_version": "ucf-rs.offline_operation.v1",
                "record_type": "offline_operation",
                "previous_offline_operation_hash": None,
                "project_id": ucf.project_id(root),
                "document_id": ucf.document_id(root, "src/auth.py"),
                "adapter": {"kind": "filesystem-text", "uri": "src/auth.py"},
                "base_server_epoch_hash": ucf.last_epoch(
                    ucf.read_store_for_mutation(paths)[1]
                )[1],
                "operation_type": "edit",
                "document_before_hash": ucf.document_hash_text("alpha\nbeta\n"),
                "document_after_hash": ucf.document_hash_text("offline\nalpha\nbeta\n"),
                "edits": [
                    {
                        "range_encoding": "unicode-scalar",
                        "start": 0,
                        "end": 0,
                        "inserted_text_hash": ucf.framed_hash(
                            "ucf.inserted_text.v1", b"offline\n"
                        ),
                        "inserted_text_length": 8,
                        "inserted_text": "offline\n",
                    }
                ],
                "affected_partitions": ["AUTH-ROTATE/001"],
                "document_after_text": "offline\nalpha\nbeta\n",
                "archive_policy": "offline-queue-text-v1",
                "created_at": ucf.utc_now(),
                "tool": {"name": "ucf-rs", "version": "0.2.0"},
            }
            legacy["offline_operation_hash"] = ucf.offline_operation_hash(legacy)

            ucf.append_jsonl(paths.offline_queue, legacy)

            operations_before = len(self.jsonl(paths.operations))
            index_before = len(self.jsonl(paths.index))

            self.assertEqual(
                ucf.main(["--root", str(root), "replay-offline"]),
                2,
            )

            self.assertEqual(
                len(self.jsonl(paths.operations)),
                operations_before,
            )
            self.assertEqual(
                len(self.jsonl(paths.index)),
                index_before,
            )
            self.assert_store_integrity(root)

    def test_mutating_command_obeys_cross_process_authority_lock(self) -> None:
        """Verify that a real decorated mutation blocks across processes."""
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\n")

            self.assertEqual(
                ucf.main(["--root", str(root), "init"]),
                0,
            )

            child_code = r"""
import importlib.util
import pathlib
import sys

module_path = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("ucf_rs_lock_child", module_path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

print("ready", flush=True)
rc = module.main(
    [
        "--root",
        str(root),
        "activate",
        "--handle",
        "AUTH-ROTATE",
        "--path",
        "src/auth.py",
        "--lines",
        "1:1",
    ]
)
raise SystemExit(rc)
"""

            process: subprocess.Popen[str] | None = None
            with ucf.authority_write_lock(paths):
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        child_code,
                        str(MODULE_PATH),
                        str(root),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                assert process.stdout is not None
                self.assertEqual(
                    process.stdout.readline().strip(),
                    "ready",
                )

                # The child has entered the decorated command and must remain
                # blocked until this process releases the authority lock.
                # Windows msvcrt.locking retries ~10 times at ~1 s intervals;
                # sleeping past the first retry attempt confirms genuine
                # contention, not a transient import delay.
                time.sleep(1.5)
                self.assertIsNone(
                    process.poll(),
                    "child mutation bypassed the cross-process authority lock",
                )

            assert process is not None
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(
                process.returncode,
                0,
                f"child stdout:\n{stdout}\nchild stderr:\n{stderr}",
            )
            self.assertIn("activated AUTH-ROTATE/001", stdout)
            self.assertEqual(
                self.status_by_partition(root)["AUTH-ROTATE/001"]["status"],
                "valid",
            )
            self.assert_store_integrity(root)


if __name__ == "__main__":
    unittest.main()
