from __future__ import annotations

import contextlib
import http.client
import io
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "ucf_rs.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ucf_rs_under_test", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
ucf = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = ucf
MODULE_SPEC.loader.exec_module(ucf)


class UcfRsDemoTests(unittest.TestCase):
    def make_root(self) -> tempfile.TemporaryDirectory[str]:
        fixture_root = REPOSITORY_ROOT / ".tmp-test"
        fixture_root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=fixture_root)
        root = Path(temporary.name)
        (root / "docs").mkdir()
        (root / "src").mkdir()
        self.write(
            root / "docs" / "handle-registry.jsonl",
            json.dumps({"handle": "AUTH-ROTATE", "type": "test", "source": "test"}) + "\n",
        )
        return temporary

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def status(self, root: Path) -> dict[str, object]:
        return ucf.status_report(root, ucf.store_paths(root, ucf.STORE_DEFAULT))

    def jsonl(self, path: Path) -> list[dict[str, object]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def write_jsonl(self, path: Path, records: list[dict[str, object]]) -> None:
        self.write(
            path,
            "\n".join(
                json.dumps(record, sort_keys=True, separators=(",", ":"))
                for record in records
            )
            + "\n",
        )

    def rewrite_second_operation_and_index(
        self,
        root: Path,
        operation_update: dict[str, object],
    ) -> None:
        operation_path = root / ".ucf-rs" / "operation-log.jsonl"
        index_path = root / ".ucf-rs" / "citation-index.jsonl"
        operations = self.jsonl(operation_path)
        index = self.jsonl(index_path)
        operations[1].update(operation_update)
        operations[1].pop("operation_hash")
        operations[1]["operation_hash"] = ucf.operation_hash(operations[1])
        index[1]["operation_hash"] = operations[1]["operation_hash"]
        index[1]["server_epoch_hash"] = ucf.epoch_hash(
            index[0]["server_epoch_hash"],
            operations[1]["operation_hash"],
        )
        index[1].pop("index_record_hash")
        index[1]["index_record_hash"] = ucf.index_record_hash(index[1])
        self.write_jsonl(operation_path, operations)
        self.write_jsonl(index_path, index)

    def run_json(self, argv: list[str]) -> dict[str, object]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = ucf.main(argv + ["--format", "json"])
        self.assertEqual(rc, 0, output.getvalue())
        return json.loads(output.getvalue())

    @contextlib.contextmanager
    def fault_phase(self, phase: str) -> object:
        previous = os.environ.get("UCF_RS_FAIL_AFTER_PHASE")
        os.environ["UCF_RS_FAIL_AFTER_PHASE"] = phase
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("UCF_RS_FAIL_AFTER_PHASE", None)
            else:
                os.environ["UCF_RS_FAIL_AFTER_PHASE"] = previous

    def activate(self, root: Path, path: str, lines: str = "1:2") -> int:
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

    def test_authority_write_lock_serializes_threads(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)
            first_entered = threading.Event()
            release_first = threading.Event()
            second_entered = threading.Event()
            errors: list[BaseException] = []

            def first_writer() -> None:
                try:
                    with ucf.authority_write_lock(paths):
                        first_entered.set()
                        release_first.wait(timeout=2)
                except BaseException as error:
                    errors.append(error)

            def second_writer() -> None:
                try:
                    first_entered.wait(timeout=2)
                    with ucf.authority_write_lock(paths):
                        second_entered.set()
                except BaseException as error:
                    errors.append(error)

            first = threading.Thread(target=first_writer)
            second = threading.Thread(target=second_writer)
            first.start()
            self.assertTrue(first_entered.wait(timeout=2))
            second.start()
            self.assertFalse(second_entered.wait(timeout=0.1))
            release_first.set()
            self.assertTrue(second_entered.wait(timeout=2))
            first.join(timeout=2)
            second.join(timeout=2)
            self.assertEqual(errors, [])

            for command in (
                ucf.command_init,
                ucf.command_activate,
                ucf.command_apply_edit,
                ucf.command_queue_offline_edit,
                ucf.command_replay_offline,
                ucf.command_accept,
                ucf.command_reconcile,
                ucf.command_deactivate,
                ucf.command_reactivate,
                ucf.command_import_registry,
            ):
                self.assertTrue(getattr(command, "_ucf_authority_mutation", False))

    def test_activation_keeps_source_clean_and_resolves_overlay(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "def rotate():\n    return 'ok'\n"
            self.write(source, original)

            self.assertEqual(self.activate(root, "src/auth.py"), 0)

            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertNotIn("REQTRACE", source.read_text(encoding="utf-8"))
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

            resolve = ucf.status_report(root, ucf.store_paths(root, ucf.STORE_DEFAULT))
            partition = resolve["partitions"][0]
            self.assertEqual(partition["partition_id"], "AUTH-ROTATE/001")
            self.assertEqual(partition["citation"]["display"], "[AUTH-ROTATE/001]")
            self.assertTrue((root / ".ucf-rs" / "citation-index.jsonl").exists())
            self.assertTrue((root / ".ucf-rs" / "operation-log.jsonl").exists())

    def test_managed_edit_before_partition_moves_overlay_without_acceptance(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "header\nalpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "2:3"), 0)
            original_range = self.status(root)["partitions"][0]["range"]

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "intro\n",
                    ]
                ),
                0,
            )

            moved = self.status(root)
            self.assertEqual(moved["summary"], {"valid": 1})
            moved_range = moved["partitions"][0]["range"]
            self.assertEqual(moved_range["start"], original_range["start"] + len("intro\n"))
            self.assertEqual(moved_range["end"], original_range["end"] + len("intro\n"))

    def test_managed_edit_inside_partition_requires_accept_then_valid(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            insert_at = original.index("beta")

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(insert_at),
                        "--end",
                        str(insert_at),
                        "--insert",
                        "new-",
                    ]
                ),
                0,
            )

            changed = self.status(root)
            self.assertEqual(changed["summary"], {"changed_unaccepted": 1})
            self.assertEqual(changed["partitions"][0]["action"], "accept_current")

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
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

    def test_unmanaged_external_change_is_not_implicitly_accepted(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.write(source, "alpha\nchanged\n")

            status = self.status(root)
            self.assertEqual(status["summary"], {"unmanaged_external_change": 1})
            self.assertEqual(status["partitions"][0]["action"], "reconcile_or_redeclare")
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "managed\n",
                    ]
                ),
                2,
            )

    def test_tampered_index_hash_is_reported(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            index_path = root / ".ucf-rs" / "citation-index.jsonl"
            record = json.loads(index_path.read_text(encoding="utf-8").splitlines()[0])
            record["range"]["start"] = 1
            self.write(index_path, json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

            status = self.status(root)
            self.assertEqual(status["diagnostics"][0]["code"], "E_INDEX_RECORD_HASH")

    def test_export_ledger_is_deterministic(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            command = [
                "--root",
                str(root),
                "export-ledger",
                "--output",
                "docs/ucf-trace-ledger.jsonl",
            ]
            self.assertEqual(ucf.main(command), 0)
            first = (root / "docs" / "ucf-trace-ledger.jsonl").read_bytes()
            self.assertEqual(ucf.main(command), 0)
            second = (root / "docs" / "ucf-trace-ledger.jsonl").read_bytes()

            self.assertEqual(first, second)
            exported = json.loads(first.decode("utf-8").splitlines()[0])
            self.assertEqual(exported["status"], "valid")
            self.assertEqual(exported["partition_id"], "AUTH-ROTATE/001")

    def test_init_imports_reqtrace_registry_and_preflight_does_not_mutate(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")

            self.assertEqual(ucf.main(["--root", str(root), "init"]), 0)
            handles = (root / ".ucf-rs" / "handle-cache.jsonl").read_text(encoding="utf-8")
            self.assertIn("AUTH-ROTATE", handles)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "preflight",
                        "--handle",
                        "AUTH-ROTATE",
                        "--path",
                        "src/auth.py",
                        "--lines",
                        "1:2",
                    ]
                ),
                0,
            )
            self.assertEqual((root / ".ucf-rs" / "citation-index.jsonl").read_text(encoding="utf-8"), "")

    def test_exact_unmanaged_move_reports_valid_moved_and_reconcile_updates_locator(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            original = root / "src" / "auth.py"
            moved = root / "src" / "moved_auth.py"
            self.write(original, "header\nalpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "2:3"), 0)

            self.write(original, "header\n")
            self.write(moved, "alpha\nbeta\n")
            moved_status = self.status(root)
            self.assertEqual(moved_status["summary"], {"valid_moved": 1})
            self.assertEqual(moved_status["partitions"][0]["action"], "relocate")

            self.assertEqual(
                ucf.main(["--root", str(root), "reconcile", "--partition-id", "AUTH-ROTATE/001"]),
                0,
            )
            reconciled = self.status(root)
            self.assertEqual(reconciled["summary"], {"valid": 1})
            self.assertEqual(reconciled["partitions"][0]["adapter"]["uri"], "src/moved_auth.py")

    def test_reconcile_commits_relocation_and_document_record_atomically(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)
            original = root / "src" / "auth.py"
            moved = root / "src" / "moved_auth.py"
            self.write(original, "header\nalpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "2:3"), 0)
            self.write(original, "header\n")
            self.write(moved, "alpha\nbeta\n")
            self.assertEqual(self.status(root)["summary"], {"valid_moved": 1})

            operation_count = len(self.jsonl(paths.operations))
            index_count = len(self.jsonl(paths.index))
            document_count = len(self.jsonl(paths.documents))
            with self.fault_phase("committed"):
                rc = ucf.main(["--root", str(root), "reconcile", "--partition-id", "AUTH-ROTATE/001"])
            self.assertEqual(rc, 2)

            self.assertEqual(len(self.jsonl(paths.operations)), operation_count + 1)
            self.assertEqual(len(self.jsonl(paths.index)), index_count + 1)
            self.assertEqual(len(self.jsonl(paths.documents)), document_count + 1)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 0)
            self.assertEqual(
                ucf.main(["--root", str(root), "reconcile", "--partition-id", "AUTH-ROTATE/001"]),
                1,
            )
            self.assertEqual(len(self.jsonl(paths.operations)), operation_count + 1)
            self.assertEqual(len(self.jsonl(paths.index)), index_count + 1)
            self.assertEqual(len(self.jsonl(paths.documents)), document_count + 1)

    def test_lifecycle_deactivate_and_reactivate(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(["--root", str(root), "deactivate", "--partition-id", "AUTH-ROTATE/001"]),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {})

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "reactivate",
                        "--partition-id",
                        "AUTH-ROTATE/001",
                        "--path",
                        "src/auth.py",
                        "--lines",
                        "1:2",
                    ]
                ),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

    def test_accept_rejects_stale_previous_index_record_hash(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            insert_at = original.index("beta")
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(insert_at),
                        "--end",
                        str(insert_at),
                        "--insert",
                        "new-",
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
                        "AUTH-ROTATE/001",
                        "--previous-index-record-hash",
                        "sha256:" + "0" * 64,
                    ]
                ),
                2,
            )

    def test_render_discover_and_serve_dispatch(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "# @reqtrace AUTH-ROTATE\nalpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "2:3"), 0)

            self.assertEqual(ucf.main(["--root", str(root), "render"]), 0)
            self.assertTrue((root / "docs" / "ucf-trace-status.json").exists())
            self.assertIn("UCF-RS Trace Report", (root / "docs" / "ucf-trace-report.md").read_text(encoding="utf-8"))

            candidates = []
            for path in ucf.iter_text_files(root, ucf.store_paths(root, ucf.STORE_DEFAULT)):
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if "@reqtrace" in line:
                        candidates.append((path.name, line_number))
            self.assertEqual(candidates, [("auth.py", 1)])

            response = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {"method": "citation.resolve", "params": {"path": "src/auth.py"}},
            )
            self.assertEqual(response["overlays"][0]["partition_id"], "AUTH-ROTATE/001")

    def test_unknown_handle_requires_registry_cache_or_explicit_task_context(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "activate",
                        "--handle",
                        "AUTH-MISSING",
                        "--path",
                        "src/auth.py",
                        "--lines",
                        "1:2",
                    ]
                ),
                2,
            )
            self.assertFalse((root / ".ucf-rs" / "citation-index.jsonl").exists())

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "activate",
                        "--handle",
                        "AUTH-MISSING",
                        "--path",
                        "src/auth.py",
                        "--lines",
                        "1:2",
                        "--task-context",
                    ]
                ),
                0,
            )
            status = self.status(root)
            self.assertEqual(status["summary"], {"valid": 1})
            self.assertEqual(status["partitions"][0]["upstream_handle"], "AUTH-MISSING")

    def test_expected_content_hash_guard_prevents_activation_mutation(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "activate",
                        "--handle",
                        "AUTH-ROTATE",
                        "--path",
                        "src/auth.py",
                        "--lines",
                        "1:2",
                        "--expected-content-hash",
                        "sha256:" + "0" * 64,
                    ]
                ),
                2,
            )
            self.assertFalse((root / ".ucf-rs" / "citation-index.jsonl").exists())

    def test_operation_index_and_epoch_chains_reflect_real_transitions(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(original.index("beta")),
                        "--end",
                        str(original.index("beta")),
                        "--insert",
                        "new-",
                    ]
                ),
                0,
            )
            self.assertEqual(
                ucf.main(["--root", str(root), "accept", "--partition-id", "AUTH-ROTATE/001"]),
                0,
            )

            operations = self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")
            index = self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")
            self.assertEqual([record["operation_type"] for record in operations], ["activate", "edit", "accept"])
            self.assertEqual([record["transition"] for record in index], ["activate", "edit-transform", "accept"])
            self.assertEqual(operations[1]["affected_partitions"], ["AUTH-ROTATE/001"])
            self.assertNotIn("refreshed_partitions", operations[1])
            self.assertIsNone(operations[0]["previous_operation_hash"])
            self.assertEqual(operations[1]["previous_operation_hash"], operations[0]["operation_hash"])
            self.assertEqual(operations[2]["previous_operation_hash"], operations[1]["operation_hash"])
            self.assertIsNone(index[0]["previous_index_record_hash"])
            self.assertEqual(index[1]["previous_index_record_hash"], index[0]["index_record_hash"])
            self.assertEqual(index[2]["previous_index_record_hash"], index[1]["index_record_hash"])
            self.assertEqual([record["server_epoch"] for record in index], [1, 2, 3])
            self.assertEqual(index[-1]["accepted_content_hash"], index[-1]["current_content_hash"])

    def test_managed_edit_after_partition_preserves_valid_partition_without_relocation(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(len(original)),
                        "--end",
                        str(len(original)),
                        "--insert",
                        "tail\n",
                    ]
                ),
                0,
            )

            status = self.status(root)
            self.assertEqual(status["summary"], {"valid": 1})
            self.assertEqual(status["partitions"][0]["action"], "none")
            index = self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")
            operations = self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")
            self.assertEqual(len(index), 2)
            self.assertEqual(len(operations), 2)
            self.assertEqual(index[-1]["transition"], "edit-refresh")
            self.assertEqual(index[-1]["transform_status"], "unaffected")
            self.assertEqual(operations[-1]["affected_partitions"], [])
            self.assertEqual(operations[-1]["refreshed_partitions"], ["AUTH-ROTATE/001"])

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "head\n",
                    ]
                ),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {"valid": 1})
            index = self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")
            operations = self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")
            self.assertEqual(len(index), 3)
            self.assertEqual(len(operations), 3)
            self.assertEqual(index[-1]["transition"], "edit-transform")
            self.assertEqual(operations[-1]["affected_partitions"], ["AUTH-ROTATE/001"])
            self.assertNotIn("refreshed_partitions", operations[-1])

    def test_edit_index_records_must_be_covered_by_matching_operation_fields(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(len(original)),
                        "--end",
                        str(len(original)),
                        "--insert",
                        "tail\n",
                    ]
                ),
                0,
            )

            index_path = root / ".ucf-rs" / "citation-index.jsonl"
            index = self.jsonl(index_path)
            self.assertEqual(index[-1]["transition"], "edit-refresh")
            index[-1]["transition"] = "edit-transform"
            index[-1].pop("index_record_hash")
            index[-1]["index_record_hash"] = ucf.index_record_hash(index[-1])
            self.write(
                index_path,
                "\n".join(
                    json.dumps(record, sort_keys=True, separators=(",", ":"))
                    for record in index
                )
                + "\n",
            )

            status = self.status(root)
            codes = {diagnostic["code"] for diagnostic in status["diagnostics"]}
            self.assertIn("E_INDEX_OPERATION_COVERAGE", codes)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

    def test_edit_transform_index_requires_edit_operation_type(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(original.index("beta")),
                        "--end",
                        str(original.index("beta")),
                        "--insert",
                        "new-",
                    ]
                ),
                0,
            )

            self.rewrite_second_operation_and_index(root, {"operation_type": "activate"})

            codes = {diagnostic["code"] for diagnostic in self.status(root)["diagnostics"]}
            self.assertIn("E_INDEX_OPERATION_COVERAGE", codes)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

    def test_edit_refresh_index_requires_edit_operation_type(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(len(original)),
                        "--end",
                        str(len(original)),
                        "--insert",
                        "tail\n",
                    ]
                ),
                0,
            )

            self.rewrite_second_operation_and_index(root, {"operation_type": "activate"})

            codes = {diagnostic["code"] for diagnostic in self.status(root)["diagnostics"]}
            self.assertIn("E_INDEX_OPERATION_COVERAGE", codes)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

    def test_edit_transform_operation_partition_fields_must_be_strings(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(original.index("beta")),
                        "--end",
                        str(original.index("beta")),
                        "--insert",
                        "new-",
                    ]
                ),
                0,
            )

            self.rewrite_second_operation_and_index(root, {"affected_partitions": [123]})

            codes = {diagnostic["code"] for diagnostic in self.status(root)["diagnostics"]}
            self.assertIn("E_INDEX_OPERATION_COVERAGE", codes)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

    def test_edit_refresh_operation_partition_fields_must_be_strings(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(len(original)),
                        "--end",
                        str(len(original)),
                        "--insert",
                        "tail\n",
                    ]
                ),
                0,
            )

            self.rewrite_second_operation_and_index(root, {"refreshed_partitions": [123]})

            codes = {diagnostic["code"] for diagnostic in self.status(root)["diagnostics"]}
            self.assertIn("E_INDEX_OPERATION_COVERAGE", codes)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

    def test_boundary_insert_policies_distinguish_outside_from_inside(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            outside = root / "src" / "outside.py"
            inside = root / "src" / "inside.py"
            original = "alpha\nbeta\n"
            self.write(outside, original)
            self.write(inside, original)
            self.assertEqual(self.activate(root, "src/outside.py", "1:2"), 0)
            self.assertEqual(self.activate(root, "src/inside.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/outside.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "outside\n",
                        "--boundary-policy",
                        "outside",
                    ]
                ),
                0,
            )
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/inside.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "inside\n",
                        "--boundary-policy",
                        "inside",
                    ]
                ),
                0,
            )

            statuses = {
                partition["adapter"]["uri"]: partition["status"]
                for partition in self.status(root)["partitions"]
            }
            self.assertEqual(statuses["src/outside.py"], "valid")
            self.assertEqual(statuses["src/inside.py"], "changed_unaccepted")

    def test_managed_whole_partition_deletion_reports_missing_not_changed(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        str(len(original)),
                    ]
                ),
                0,
            )

            status = self.status(root)
            self.assertEqual(status["summary"], {"missing": 1})
            self.assertEqual(status["partitions"][0]["action"], "redeclare_partition")
            self.assertEqual(
                ucf.main(["--root", str(root), "accept", "--partition-id", "AUTH-ROTATE/001"]),
                2,
            )
            self.assertEqual(self.status(root)["summary"], {"missing": 1})

    def test_duplicate_exact_unmanaged_recovery_is_ambiguous(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            original = root / "src" / "auth.py"
            copy_one = root / "src" / "copy_one.py"
            copy_two = root / "src" / "copy_two.py"
            self.write(original, "header\nalpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "2:3"), 0)

            self.write(original, "header\n")
            self.write(copy_one, "alpha\nbeta\n")
            self.write(copy_two, "alpha\nbeta\n")

            status = self.status(root)
            self.assertEqual(status["summary"], {"ambiguous": 1})
            self.assertEqual(status["partitions"][0]["action"], "disambiguate")
            self.assertEqual(len(status["partitions"][0]["matches"]), 2)

    def test_reconcile_refuses_changed_external_evidence(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.write(source, "alpha\nchanged\n")

            self.assertEqual(
                ucf.main(["--root", str(root), "reconcile", "--partition-id", "AUTH-ROTATE/001"]),
                1,
            )
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")), 1)

    def test_tampered_operation_chain_blocks_mutation_and_strict_status(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            operation_path = root / ".ucf-rs" / "operation-log.jsonl"
            operation = self.jsonl(operation_path)[0]
            operation["operation_type"] = "edit"
            self.write(operation_path, json.dumps(operation, sort_keys=True, separators=(",", ":")) + "\n")

            status = self.status(root)
            self.assertEqual(status["diagnostics"][0]["code"], "E_OPERATION_HASH")
            self.assertEqual(
                ucf.main(["--root", str(root), "activate", "--handle", "AUTH-ROTATE", "--path", "src/auth.py", "--lines", "1:2"]),
                2,
            )

    def test_offline_queue_replay_preserves_explicit_acceptance_boundary(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(original.index("beta")),
                        "--end",
                        str(original.index("beta")),
                        "--insert",
                        "offline-",
                    ]
                ),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {"unmanaged_external_change": 1})
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")), 1)

            self.assertEqual(ucf.main(["--root", str(root), "replay-offline"]), 0)
            replayed = self.status(root)
            self.assertEqual(replayed["summary"], {"changed_unaccepted": 1})
            self.assertEqual((root / ".ucf-rs" / "offline-queue.jsonl").read_text(encoding="utf-8"), "")
            self.assertIn("offline_operation", (root / ".ucf-rs" / "offline-replayed.jsonl").read_text(encoding="utf-8"))

            self.assertEqual(
                ucf.main(["--root", str(root), "accept", "--partition-id", "AUTH-ROTATE/001"]),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

    def test_offline_replay_allows_unrelated_descendant_epoch(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            other = root / "src" / "other.py"
            self.write(source, "alpha\nbeta\n")
            self.write(other, "gamma\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

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
            self.assertEqual(self.activate(root, "src/other.py", "1:1"), 0)
            self.assertEqual(ucf.main(["--root", str(root), "replay-offline"]), 0)
            self.assertEqual((root / ".ucf-rs" / "offline-queue.jsonl").read_text(encoding="utf-8"), "")
            statuses = {
                partition["adapter"]["uri"]: partition["status"]
                for partition in self.status(root)["partitions"]
            }
            self.assertEqual(statuses["src/auth.py"], "valid")
            self.assertEqual(statuses["src/other.py"], "valid")

    def test_offline_replay_rejects_same_document_descendant_epoch(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

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
            self.assertEqual(self.activate(root, "src/auth.py", "1:1"), 0)
            self.assertEqual(ucf.main(["--root", str(root), "replay-offline"]), 2)
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)

    def test_offline_replay_preserves_boundary_policy(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

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
                        "inside\n",
                        "--boundary-policy",
                        "inside",
                    ]
                ),
                0,
            )
            self.assertEqual(ucf.main(["--root", str(root), "replay-offline"]), 0)
            self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})
            operations = self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")
            self.assertEqual(operations[-1]["edits"][0]["boundary_policy"], "inside")

    def test_offline_replay_rejects_same_document_operation_without_epoch_advance(
        self,
    ) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            paths = ucf.store_paths(root, ucf.STORE_DEFAULT)
            source = root / "src" / "auth.py"

            original = "alpha\nbeta\n"
            server_after = "alpha\nbeta\nserver\n"

            self.write(source, original)
            self.assertEqual(
                self.activate(root, "src/auth.py", "1:1"),
                0,
            )

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

            operations, index_records = ucf.read_store_for_mutation(paths)
            _, current_epoch_hash = ucf.last_epoch(index_records)

            self.write(source, server_after)

            ucf.append_operation(
                paths,
                operations,
                "edit",
                ucf.document_id(root, "src/auth.py"),
                current_epoch_hash,
                ucf.document_hash_text(original),
                ucf.document_hash_text(server_after),
                [
                    ucf.edit_record(
                        len(original),
                        len(original),
                        "server\n",
                        "outside",
                    )
                ],
                [],
            )

            operation_count = len(operations)
            index_count = len(index_records)

            self.assertEqual(
                ucf.main(["--root", str(root), "replay-offline"]),
                2,
            )

            final_operations, final_index = (
                ucf.read_store_for_mutation(paths)
            )
            self.assertEqual(len(final_operations), operation_count)
            self.assertEqual(len(final_index), index_count)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                server_after,
            )
            self.assertEqual(
                len(self.jsonl(paths.offline_queue)),
                1,
            )

    def test_offline_replay_refreshes_unaffected_partition_revision(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(len(original)),
                        "--end",
                        str(len(original)),
                        "--insert",
                        "tail\n",
                    ]
                ),
                0,
            )
            queued_records = self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")
            self.assertEqual(queued_records[-1]["affected_partitions"], [])
            self.assertEqual(queued_records[-1]["refreshed_partitions"], ["AUTH-ROTATE/001"])
            self.assertEqual(self.status(root)["summary"], {"valid": 1})
            self.assertEqual(ucf.main(["--root", str(root), "replay-offline"]), 0)
            self.assertEqual(self.status(root)["summary"], {"valid": 1})
            index_after_replay = self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")
            operations_after_replay = self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")
            self.assertEqual(len(index_after_replay), 2)
            self.assertEqual(index_after_replay[-1]["transition"], "edit-refresh")
            self.assertEqual(index_after_replay[-1]["transform_status"], "unaffected")
            self.assertEqual(operations_after_replay[-1]["affected_partitions"], [])
            self.assertEqual(operations_after_replay[-1]["refreshed_partitions"], ["AUTH-ROTATE/001"])

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "0",
                        "--end",
                        "0",
                        "--insert",
                        "head\n",
                    ]
                ),
                0,
            )
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

    def test_offline_replay_conflicts_on_refreshed_partition_suffix(self) -> None:
        queued = {
            "base_server_epoch_hash": ucf.GENESIS_EPOCH_HASH,
            "base_operation_hash": None,
            "document_id": "doc-a",
            "affected_partitions": [],
            "refreshed_partitions": ["AUTH-ROTATE/001"],
        }
        operations = [
            {
                "operation_hash": "sha256:" + "1" * 64,
                "document_id": "doc-b",
                "operation_type": "edit",
                "affected_partitions": [],
                "refreshed_partitions": ["AUTH-ROTATE/001"],
            }
        ]

        with self.assertRaises(ucf.DemoError):
            ucf.validate_offline_replay_base(
                operations,
                [],
                queued,
                ucf.GENESIS_EPOCH_HASH,
            )

    def test_stale_export_is_a_strict_status_failure_until_regenerated(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(ucf.main(["--root", str(root), "export", "ledger"]), 0)
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 0)

            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "apply-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        str(original.index("beta")),
                        "--end",
                        str(original.index("beta")),
                        "--insert",
                        "new-",
                    ]
                ),
                0,
            )
            report = self.status(root)
            self.assertIn("E_EXPORT_STALE", report["summary"])
            self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)

            exported = self.run_json(["--root", str(root), "export", "ledger"])
            self.assertTrue(exported["status_valid"])
            fresh = self.status(root)
            self.assertNotIn("E_EXPORT_STALE", fresh["summary"])

    def test_server_mutating_api_drives_authority_lifecycle(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)

            preflight = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "partition.preflight",
                    "params": {"handle": "AUTH-ROTATE", "path": "src/auth.py", "lines": "1:2"},
                },
            )
            self.assertEqual(preflight["partition_id"], "AUTH-ROTATE/001")
            self.assertEqual(preflight["source_mutated"], False)
            self.assertFalse((root / ".ucf-rs" / "citation-index.jsonl").exists())
            self.assertEqual(source.read_text(encoding="utf-8"), original)

            activated = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "partition.activate",
                    "params": {"handle": "AUTH-ROTATE", "path": "src/auth.py", "lines": "1:2"},
                },
            )
            self.assertEqual(activated["partition_id"], "AUTH-ROTATE/001")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

            edited = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "document.apply_edit",
                    "params": {
                        "path": "src/auth.py",
                        "start": original.index("beta"),
                        "end": original.index("beta"),
                        "insert": "api-",
                    },
                },
            )
            self.assertEqual(edited["affected_partitions"], ["AUTH-ROTATE/001"])
            changed = self.status(root)
            self.assertEqual(changed["summary"], {"changed_unaccepted": 1})
            self.assertEqual(changed["partitions"][0]["action"], "accept_current")

            stale_accept = {
                "method": "partition.accept",
                "params": {
                    "partition_id": "AUTH-ROTATE/001",
                    "previous_index_record_hash": "sha256:" + "0" * 64,
                },
            }
            with self.assertRaises(ucf.DemoError):
                ucf.serve_dispatch(root, ucf.STORE_DEFAULT, stale_accept)
            self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})

            accepted = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "partition.accept",
                    "params": {
                        "partition_id": "AUTH-ROTATE/001",
                        "previous_index_record_hash": changed["partitions"][0]["index_record_hash"],
                    },
                },
            )
            self.assertEqual(accepted["partition_id"], "AUTH-ROTATE/001")
            self.assertEqual(self.status(root)["summary"], {"valid": 1})

            exported = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "export.ledger",
                    "params": {"output": "docs/ucf-trace-ledger.jsonl"},
                },
            )
            self.assertEqual(exported["record_count"], 1)
            self.assertTrue((root / "docs" / "ucf-trace-ledger.jsonl").exists())
            self.assertEqual(
                [record["operation_type"] for record in self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")],
                ["activate", "edit", "accept"],
            )

    def test_server_offline_api_preserves_epoch_replay_boundary(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            original = "alpha\nbeta\n"
            self.write(source, original)
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            queued = ucf.serve_dispatch(
                root,
                ucf.STORE_DEFAULT,
                {
                    "method": "document.queue_offline_edit",
                    "params": {
                        "path": "src/auth.py",
                        "start": original.index("beta"),
                        "end": original.index("beta"),
                        "insert": "server-",
                    },
                },
            )
            self.assertEqual(queued["affected_partitions"], ["AUTH-ROTATE/001"])
            self.assertEqual(self.status(root)["summary"], {"unmanaged_external_change": 1})
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")), 1)

            replayed = ucf.serve_dispatch(root, ucf.STORE_DEFAULT, {"method": "offline.replay"})
            self.assertEqual(replayed["queued_operations"], 1)
            self.assertEqual(replayed["affected_partitions"], ["AUTH-ROTATE/001"])
            self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})
            self.assertEqual((root / ".ucf-rs" / "offline-queue.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual(
                [record["operation_type"] for record in self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")],
                ["activate", "edit"],
            )

    def test_http_transport_serves_same_citation_resolution_api(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            server = ucf.make_http_server(root, ucf.STORE_DEFAULT, "127.0.0.1", 0)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                body = json.dumps(
                    {"method": "citation.resolve", "params": {"path": "src/auth.py"}}
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["result"]["overlays"][0]["partition_id"], "AUTH-ROTATE/001")

    def test_http_transport_supports_json_rpc_envelope(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            server = ucf.make_http_server(root, ucf.STORE_DEFAULT, "127.0.0.1", 0)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "resolve-1",
                        "method": "citation.resolve",
                        "params": {"path": "src/auth.py"},
                    }
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(payload["jsonrpc"], "2.0")
            self.assertEqual(payload["id"], "resolve-1")
            self.assertEqual(payload["result"]["overlays"][0]["partition_id"], "AUTH-ROTATE/001")

    def test_http_transport_reports_malformed_mutating_params_as_json_error(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            server = ucf.make_http_server(root, ucf.STORE_DEFAULT, "127.0.0.1", 0)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                body = json.dumps(
                    {"method": "document.apply_edit", "params": {"path": "src/auth.py"}}
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=5)
                payload = json.loads(raised.exception.read().decode("utf-8"))
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertFalse(payload["ok"])
            self.assertIn("document.apply_edit requires integer params.start", payload["error"])

    def post_raw_http(
        self,
        server: object,
        content_length: str,
        body: bytes,
    ) -> tuple[int, dict[str, object]]:
        port = server.server_address[1]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.putrequest("POST", "/")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", content_length)
            connection.endheaders()
            if body:
                connection.send(body)
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()

    def test_http_rejects_invalid_negative_and_oversized_content_length(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)

            cases = [
                ("abc", b"{}", 400, "invalid Content-Length"),
                ("-1", b"{}", 400, "invalid Content-Length"),
                ("9", b'{"x": 1}', 413, "request body too large"),
            ]
            for content_length, body, expected_status, expected_error in cases:
                server = ucf.make_http_server(
                    root,
                    ucf.STORE_DEFAULT,
                    "127.0.0.1",
                    0,
                    max_request_bytes=8,
                )
                thread = threading.Thread(target=server.handle_request)
                thread.start()
                try:
                    status, payload = self.post_raw_http(server, content_length, body)
                finally:
                    thread.join(timeout=5)
                    server.server_close()

                self.assertEqual(status, expected_status)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], expected_error)

    def test_http_remote_binding_requires_explicit_unsafe_opt_in(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = ucf.main(["serve", "--transport", "http", "--host", "0.0.0.0", "--once"])
        self.assertEqual(rc, 2)
        self.assertIn("non-loopback host", stderr.getvalue())
        self.assertTrue(ucf.is_loopback_host("127.0.0.1"))
        self.assertTrue(ucf.is_loopback_host("::1"))
        self.assertTrue(ucf.is_loopback_host("localhost"))
        self.assertFalse(ucf.is_loopback_host("0.0.0.0"))

    def test_apply_edit_transaction_recovers_each_phase_without_duplicate_records(self) -> None:
        for phase in ("before_preparation", "prepared", "source_applied", "authority_applied"):
            with self.make_root() as directory:
                root = Path(directory)
                source = root / "src" / "auth.py"
                self.write(source, "alpha\nbeta\n")
                self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

                with self.fault_phase(phase):
                    rc = ucf.main(
                        [
                            "--root",
                            str(root),
                            "apply-edit",
                            "--path",
                            "src/auth.py",
                            "--start",
                            "1",
                            "--end",
                            "2",
                            "--insert",
                            "L",
                        ]
                    )
                self.assertEqual(rc, 2)

                if phase == "before_preparation":
                    self.assertEqual(source.read_text(encoding="utf-8"), "alpha\nbeta\n")
                    self.assertEqual(
                        [record["operation_type"] for record in self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")],
                        ["activate"],
                    )
                    continue

                self.assertEqual(ucf.main(["--root", str(root), "status", "--strict"]), 1)
                recovered = self.run_json(["--root", str(root), "recover"])
                self.assertEqual(len(recovered["recovered"]), 1)
                self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})
                self.assertEqual(self.run_json(["--root", str(root), "recover"])["recovered"], [])
                self.assertEqual(
                    [record["operation_type"] for record in self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")],
                    ["activate", "edit"],
                )
                self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "citation-index.jsonl")), 2)

    def test_queue_offline_transaction_recovery_appends_queue_once(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)

            with self.fault_phase("source_applied"):
                rc = ucf.main(
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
            )
            self.assertEqual(rc, 2)
            queue_path = root / ".ucf-rs" / "offline-queue.jsonl"
            self.assertTrue(not queue_path.exists() or queue_path.read_text(encoding="utf-8") == "")

            recovered = self.run_json(["--root", str(root), "recover"])
            self.assertEqual(len(recovered["recovered"]), 1)
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)
            self.assertEqual(self.run_json(["--root", str(root), "recover"])["recovered"], [])
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)
            self.assertEqual(self.status(root)["summary"], {"valid_moved": 1})

    def test_replay_offline_transaction_recovery_consumes_queue_once(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            self.assertEqual(
                ucf.main(
                    [
                        "--root",
                        str(root),
                        "queue-offline-edit",
                        "--path",
                        "src/auth.py",
                        "--start",
                        "1",
                        "--end",
                        "2",
                        "--insert",
                        "L",
                    ]
                ),
                0,
            )

            with self.fault_phase("source_applied"):
                rc = ucf.main(["--root", str(root), "replay-offline"])
            self.assertEqual(rc, 2)
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-queue.jsonl")), 1)

            recovered = self.run_json(["--root", str(root), "recover"])
            self.assertEqual(len(recovered["recovered"]), 1)
            self.assertEqual((root / ".ucf-rs" / "offline-queue.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-replayed.jsonl")), 1)
            self.assertEqual(self.run_json(["--root", str(root), "recover"])["recovered"], [])
            self.assertEqual(len(self.jsonl(root / ".ucf-rs" / "offline-replayed.jsonl")), 1)
            self.assertEqual(
                [record["operation_type"] for record in self.jsonl(root / ".ucf-rs" / "operation-log.jsonl")],
                ["activate", "edit"],
            )
            self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})

    def test_recover_after_subprocess_crash_restart(self) -> None:
        with self.make_root() as directory:
            root = Path(directory)
            source = root / "src" / "auth.py"
            self.write(source, "alpha\nbeta\n")
            self.assertEqual(self.activate(root, "src/auth.py", "1:2"), 0)
            environment = os.environ.copy()
            environment["UCF_RS_CRASH_AFTER_PHASE"] = "source_applied"
            crashed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--root",
                    str(root),
                    "apply-edit",
                    "--path",
                    "src/auth.py",
                    "--start",
                    "1",
                    "--end",
                    "2",
                    "--insert",
                    "L",
                ],
                cwd=str(REPOSITORY_ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(crashed.returncode, 97)

            recovered = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--root",
                    str(root),
                    "recover",
                    "--format",
                    "json",
                ],
                cwd=str(REPOSITORY_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            self.assertEqual(len(json.loads(recovered.stdout)["recovered"]), 1)
            self.assertEqual(self.status(root)["summary"], {"changed_unaccepted": 1})


if __name__ == "__main__":
    unittest.main()
