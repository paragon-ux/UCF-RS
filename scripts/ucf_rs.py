#!/usr/bin/env python3
"""UCF-RS local authority runtime.

UCF-RS is an overlay-first traceability runtime. It keeps citations out of
source files and makes a durable citation index plus operation log the authority
surface. This reference implementation stays intentionally small and uses only
the Python standard library, following Reqtrace 2.1.7's implementation style.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TOOL_NAME = "ucf-rs"
TOOL_VERSION = "0.2.0"

STORE_DEFAULT = ".ucf-rs"
EXPORT_LEDGER_DEFAULT = "docs/ucf-trace-ledger.jsonl"
EXPORT_STATUS_DEFAULT = "docs/ucf-trace-status.json"
EXPORT_REPORT_DEFAULT = "docs/ucf-trace-report.md"

PROJECT_SCHEMA = "ucf-rs.project.v1"
INDEX_SCHEMA = "ucf-rs.index.v1"
OPERATION_SCHEMA = "ucf-rs.operation.v1"
DOCUMENT_SCHEMA = "ucf-rs.document.v1"
HANDLE_SCHEMA = "ucf-rs.handle_cache.v1"
OFFLINE_SCHEMA = "ucf-rs.offline_operation.v1"
PREFLIGHT_SCHEMA = "ucf-rs.preflight.v1"
STATUS_SCHEMA = "ucf-rs.status.v1"
RESOLVE_SCHEMA = "ucf-rs.resolve.v1"
EXPORT_SCHEMA = "ucf-rs.export.v1"

HANDLE_PATTERN = r"[A-Z][A-Z0-9_.-]*"
HANDLE_RE = re.compile(rf"^{HANDLE_PATTERN}$")
REQTRACE_MARKER_RE = re.compile(rf"@reqtrace\s+({HANDLE_PATTERN})\b")
SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class DemoError(Exception):
    """A user-facing command failure."""


@dataclass(frozen=True)
class StorePaths:
    root: Path
    store: Path
    project: Path
    index: Path
    operations: Path
    offline_queue: Path
    offline_replayed: Path
    documents: Path
    handles: Path
    snapshots: Path


@dataclass(frozen=True)
class Range:
    start: int
    end: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class TransformResult:
    start: int
    end: int
    status: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def framed_hash(domain: str, *fields: bytes | str) -> str:
    payload = bytearray()
    payload.extend(b"REQTRACE\0")
    payload.extend(domain.encode("ascii"))
    payload.extend(b"\0")
    for field in fields:
        raw = field.encode("utf-8") if isinstance(field, str) else field
        payload.extend(str(len(raw)).encode("ascii"))
        payload.extend(b":")
        payload.extend(raw)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


GENESIS_EPOCH_HASH = framed_hash("ucf.epoch.genesis.v1")


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def content_hash_text(text: str) -> str:
    return framed_hash("ucf.content.text.v1", normalize_text(text).encode("utf-8"))


def text_lines(text: str) -> list[str]:
    return normalize_text(text).splitlines(keepends=True)


def line_hashes(text: str) -> list[str]:
    return [framed_hash("ucf.line.v1", line.encode("utf-8")) for line in text_lines(text)]


def document_hash_text(text: str) -> str:
    return framed_hash("ucf.document.text.v1", normalize_text(text).encode("utf-8"))


def block_hash(partition_id: str, content: str) -> str:
    return framed_hash("ucf.block.v1", partition_id, normalize_text(content).encode("utf-8"))


def partition_hash(partition_id: str, accepted_content_hash: str) -> str:
    return framed_hash("ucf.partition.v1", partition_id, accepted_content_hash)


def project_id(root: Path) -> str:
    return framed_hash("ucf.project.v1", root.resolve().as_posix())


def document_id(root: Path, relative_uri: str) -> str:
    return framed_hash("ucf.document.v1", project_id(root), relative_uri, "filesystem-text")


def citation_id(root: Path, partition_id: str) -> str:
    return framed_hash("ucf.citation.v1", project_id(root), partition_id, "ucf.v1")


def operation_hash(record_without_hash: dict[str, Any]) -> str:
    return framed_hash("ucf.operation.v1", canonical_json_bytes(record_without_hash))


def index_record_hash(record_without_hash: dict[str, Any]) -> str:
    return framed_hash("ucf.index_record.v1", canonical_json_bytes(record_without_hash))


def epoch_hash(previous_epoch_hash: str, committed_operation_hash: str) -> str:
    return framed_hash("ucf.epoch.v1", previous_epoch_hash, committed_operation_hash)


def export_ledger_hash(content: bytes) -> str:
    return framed_hash("ucf.export_ledger.v1", content)


def offline_operation_hash(record_without_hash: dict[str, Any]) -> str:
    return framed_hash("ucf.offline_operation.v1", canonical_json_bytes(record_without_hash))


def project_path(root: Path, configured_path: str) -> Path:
    if not configured_path:
        raise DemoError("path must not be empty")
    raw = Path(configured_path.replace("\\", "/"))
    if raw.is_absolute():
        raise DemoError(f"path must be project-relative: {configured_path}")
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise DemoError(f"path escapes the project root: {configured_path}") from error
    return candidate


def relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def store_paths(root: Path, configured_store: str) -> StorePaths:
    store = project_path(root, configured_store)
    return StorePaths(
        root=root,
        store=store,
        project=store / "project.json",
        index=store / "citation-index.jsonl",
        operations=store / "operation-log.jsonl",
        offline_queue=store / "offline-queue.jsonl",
        offline_replayed=store / "offline-replayed.jsonl",
        documents=store / "document-index.jsonl",
        handles=store / "handle-cache.jsonl",
        snapshots=store / "snapshots",
    )


def read_text_document(path: Path) -> str:
    try:
        return normalize_text(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        raise DemoError(f"{path.as_posix()} is not UTF-8 text") from error
    except OSError as error:
        raise DemoError(f"cannot read {path.as_posix()}: {error}") from error


def write_text_document(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_text(content), encoding="utf-8", newline="\n")


def line_offsets(text: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(text):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def line_for_offset(text: str, offset: int) -> int:
    if offset < 0 or offset > len(text):
        raise DemoError(f"offset {offset} is outside the document")
    return text.count("\n", 0, offset) + 1


def range_from_offsets(text: str, start: int, end: int) -> Range:
    if start < 0 or end < start or end > len(text):
        raise DemoError(f"range {start}:{end} is outside the document")
    end_anchor = end - 1 if end > start else start
    return Range(start=start, end=end, start_line=line_for_offset(text, start), end_line=line_for_offset(text, end_anchor))


def range_from_line_selection(text: str, start_line: int, end_line: int) -> Range:
    if start_line < 1 or end_line < start_line:
        raise DemoError("--lines must use 1-based inclusive START:END syntax")
    offsets = line_offsets(text)
    line_count = len(text.splitlines())
    if text.endswith("\n"):
        line_count = len(text.splitlines())
    elif text:
        line_count = len(text.splitlines())
    else:
        line_count = 0
    if end_line > line_count:
        raise DemoError(f"line range {start_line}:{end_line} exceeds {line_count} line(s)")
    start = offsets[start_line - 1]
    end = offsets[end_line] if end_line < len(offsets) else len(text)
    return Range(start=start, end=end, start_line=start_line, end_line=end_line)


def parse_line_range(value: str | None) -> tuple[int, int]:
    if value is None:
        raise DemoError("--lines is required")
    match = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", value)
    if not match:
        raise DemoError("--lines must use 1-based inclusive START:END syntax")
    return int(match.group(1)), int(match.group(2))


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def read_hashed_jsonl(path: Path, hash_field: str, hash_fn: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return [], []
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DemoError(f"cannot read {path.as_posix()}: {error}") from error
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            diagnostics.append(
                {
                    "code": "E_JSON",
                    "severity": "fatal",
                    "message": error.msg,
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        if not isinstance(record, dict):
            diagnostics.append(
                {
                    "code": "E_SCHEMA",
                    "severity": "fatal",
                    "message": "JSONL record must be an object",
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        stored_hash = record.get(hash_field)
        without_hash = {key: value for key, value in record.items() if key != hash_field}
        expected_hash = hash_fn(without_hash)
        if not isinstance(stored_hash, str) or not SHA_RE.fullmatch(stored_hash):
            diagnostics.append(
                {
                    "code": f"E_{hash_field.upper()}",
                    "severity": "fatal",
                    "message": f"missing or invalid {hash_field}",
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        if stored_hash != expected_hash:
            diagnostics.append(
                {
                    "code": f"E_{hash_field.upper()}",
                    "severity": "fatal",
                    "message": f"{hash_field} does not match canonical record bytes",
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        records.append(record)
    return records, diagnostics


def read_offline_queue(paths: StorePaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records, diagnostics = read_hashed_jsonl(
        paths.offline_queue, "offline_operation_hash", offline_operation_hash
    )
    previous_hash: str | None = None
    for index, record in enumerate(records, start=1):
        if record.get("previous_offline_operation_hash") != previous_hash:
            diagnostics.append(
                {
                    "code": "E_OFFLINE_QUEUE_CHAIN",
                    "severity": "fatal",
                    "message": "offline queue previous hash does not match append order",
                    "path": relative_path(paths.root, paths.offline_queue),
                    "line": index,
                }
            )
        previous_hash = (
            record.get("offline_operation_hash")
            if isinstance(record.get("offline_operation_hash"), str)
            else None
        )
    return records, diagnostics


def read_operations(paths: StorePaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records, diagnostics = read_hashed_jsonl(paths.operations, "operation_hash", operation_hash)
    previous_hash: str | None = None
    for index, record in enumerate(records, start=1):
        if record.get("previous_operation_hash") != previous_hash:
            diagnostics.append(
                {
                    "code": "E_OPERATION_CHAIN",
                    "severity": "fatal",
                    "message": "operation previous hash does not match append order",
                    "path": relative_path(paths.root, paths.operations),
                    "line": index,
                }
            )
        previous_hash = record.get("operation_hash") if isinstance(record.get("operation_hash"), str) else None
    return records, diagnostics


def read_index(paths: StorePaths, operations: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records, diagnostics = read_hashed_jsonl(paths.index, "index_record_hash", index_record_hash)
    operation_hashes = {record.get("operation_hash") for record in operations}
    previous_index_hash: str | None = None
    current_epoch = 0
    current_epoch_hash = GENESIS_EPOCH_HASH
    for line_number, record in enumerate(records, start=1):
        if record.get("previous_index_record_hash") != previous_index_hash:
            diagnostics.append(
                {
                    "code": "E_INDEX_CHAIN",
                    "severity": "fatal",
                    "message": "index previous hash does not match append order",
                    "path": relative_path(paths.root, paths.index),
                    "line": line_number,
                }
            )
        record_operation_hash = record.get("operation_hash")
        if record_operation_hash not in operation_hashes:
            diagnostics.append(
                {
                    "code": "E_INDEX_OPERATION",
                    "severity": "fatal",
                    "message": "index record references a missing operation",
                    "path": relative_path(paths.root, paths.index),
                    "line": line_number,
                }
            )
        server_epoch = record.get("server_epoch")
        server_epoch_hash = record.get("server_epoch_hash")
        if server_epoch == current_epoch + 1 and isinstance(record_operation_hash, str):
            expected_epoch_hash = epoch_hash(current_epoch_hash, record_operation_hash)
            if server_epoch_hash != expected_epoch_hash:
                diagnostics.append(
                    {
                        "code": "E_SERVER_EPOCH",
                        "severity": "fatal",
                        "message": "server epoch hash does not match operation chain",
                        "path": relative_path(paths.root, paths.index),
                        "line": line_number,
                    }
                )
            current_epoch = int(server_epoch)
            current_epoch_hash = expected_epoch_hash
        elif server_epoch == current_epoch:
            if server_epoch_hash != current_epoch_hash:
                diagnostics.append(
                    {
                        "code": "E_SERVER_EPOCH",
                        "severity": "fatal",
                        "message": "co-epoch index record has a different epoch hash",
                        "path": relative_path(paths.root, paths.index),
                        "line": line_number,
                    }
                )
        else:
            diagnostics.append(
                {
                    "code": "E_SERVER_EPOCH",
                    "severity": "fatal",
                    "message": "server epoch is not append-ordered",
                    "path": relative_path(paths.root, paths.index),
                    "line": line_number,
                }
            )
        previous_index_hash = (
            record.get("index_record_hash") if isinstance(record.get("index_record_hash"), str) else None
        )
    return records, diagnostics


def read_store(paths: StorePaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    operations, operation_diagnostics = read_operations(paths)
    index, index_diagnostics = read_index(paths, operations)
    return operations, index, operation_diagnostics + index_diagnostics


def read_store_for_mutation(paths: StorePaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations, index, diagnostics = read_store(paths)
    if diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in diagnostics}))
        raise DemoError(f"cannot mutate invalid UCF-RS store ({codes})")
    return operations, index


def latest_index_records(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        partition_id = record.get("partition_id")
        if isinstance(partition_id, str):
            latest[partition_id] = record
    return latest


def last_epoch(records: list[dict[str, Any]]) -> tuple[int, str]:
    if not records:
        return 0, GENESIS_EPOCH_HASH
    last = records[-1]
    return int(last["server_epoch"]), str(last["server_epoch_hash"])


def read_handle_records(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if not path.exists():
        return records, diagnostics
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            diagnostics.append(
                {
                    "code": "E_HANDLE_CACHE_JSON",
                    "severity": "error",
                    "message": error.msg,
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        if not isinstance(record, dict) or not isinstance(record.get("handle"), str):
            diagnostics.append(
                {
                    "code": "E_HANDLE_CACHE_SCHEMA",
                    "severity": "error",
                    "message": "handle cache record must contain a string handle",
                    "path": path.as_posix(),
                    "line": line_number,
                }
            )
            continue
        records.append(record)
    return records, diagnostics


def registry_path(root: Path, configured: str | None = None) -> Path:
    return project_path(root, configured or "docs/handle-registry.jsonl")


def load_known_handles(paths: StorePaths, registry: Path | None = None) -> tuple[set[str], list[dict[str, Any]]]:
    handles: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    for path in (paths.handles, registry or registry_path(paths.root)):
        records, path_diagnostics = read_handle_records(path)
        diagnostics.extend(path_diagnostics)
        handles.update(str(record["handle"]) for record in records)
    return handles, diagnostics


def import_registry(paths: StorePaths, source: Path) -> int:
    records, diagnostics = read_handle_records(source)
    if diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in diagnostics}))
        raise DemoError(f"cannot import invalid registry ({codes})")
    existing, _ = read_handle_records(paths.handles)
    known = {str(record["handle"]) for record in existing}
    count = 0
    for record in records:
        handle = str(record["handle"])
        if handle in known:
            continue
        cached = {
            "schema_version": HANDLE_SCHEMA,
            "handle": handle,
            "type": record.get("type", "unknown"),
            "source": record.get("source"),
            "imported_from": relative_path(paths.root, source)
            if source.resolve().is_relative_to(paths.root.resolve())
            else source.as_posix(),
            "imported_at": utc_now(),
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        }
        append_jsonl(paths.handles, cached)
        known.add(handle)
        count += 1
    return count


def validate_handle(paths: StorePaths, handle: str, task_context: bool) -> None:
    if not HANDLE_RE.fullmatch(handle):
        raise DemoError(f"handle must match {HANDLE_PATTERN}: {handle!r}")
    if task_context:
        return
    handles, diagnostics = load_known_handles(paths)
    if diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in diagnostics}))
        raise DemoError(f"handle registry/cache is invalid ({codes})")
    if handle not in handles:
        raise DemoError(
            f"handle {handle!r} is not in UCF-RS cache or docs/handle-registry.jsonl; use --task-context for an explicit task-context handle"
        )


def allocate_partition_id(index_records: Iterable[dict[str, Any]], handle: str) -> str:
    used: set[int] = set()
    prefix = handle + "/"
    for record in index_records:
        partition_id = record.get("partition_id")
        if isinstance(partition_id, str) and partition_id.startswith(prefix):
            suffix = partition_id[len(prefix) :]
            if suffix.isdigit():
                used.add(int(suffix))
    ordinal = 1
    while ordinal in used:
        ordinal += 1
    return f"{handle}/{ordinal:03d}"


def make_citation(root: Path, partition_id: str) -> dict[str, str]:
    return {
        "format": "ucf.v1",
        "label": partition_id,
        "display": f"[{partition_id}]",
        "target": f"ucf://partition/{partition_id}",
        "citation_id": citation_id(root, partition_id),
    }


def range_payload(selected_range: Range) -> dict[str, int | str]:
    return {
        "encoding": "unicode-scalar",
        "start": selected_range.start,
        "end": selected_range.end,
        "start_line": selected_range.start_line,
        "end_line": selected_range.end_line,
    }


def append_operation(
    paths: StorePaths,
    operations: list[dict[str, Any]],
    operation_type: str,
    document_record_id: str,
    base_server_epoch_hash: str,
    document_before_hash: str,
    document_after_hash: str,
    edits: list[dict[str, Any]],
    affected_partitions: list[str],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": OPERATION_SCHEMA,
        "record_type": "operation",
        "previous_operation_hash": operations[-1]["operation_hash"] if operations else None,
        "project_id": project_id(paths.root),
        "document_id": document_record_id,
        "base_server_epoch_hash": base_server_epoch_hash,
        "operation_type": operation_type,
        "source": {"kind": "cli", "client_id": TOOL_NAME, "session_id": "embedded"},
        "document_before_hash": document_before_hash,
        "document_after_hash": document_after_hash,
        "edits": edits,
        "affected_partitions": affected_partitions,
        "created_at": utc_now(),
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
    }
    record["operation_hash"] = operation_hash(record)
    append_jsonl(paths.operations, record)
    operations.append(record)
    return record


def append_document_record(
    paths: StorePaths,
    relative_uri: str,
    document_record_id: str,
    revision_hash: str,
    server_epoch_value_hash: str,
) -> None:
    append_jsonl(
        paths.documents,
        {
            "schema_version": DOCUMENT_SCHEMA,
            "record_type": "document_revision",
            "document_id": document_record_id,
            "project_id": project_id(paths.root),
            "adapter": {"kind": "filesystem-text", "uri": relative_uri},
            "current_document_revision_hash": revision_hash,
            "last_server_epoch_hash": server_epoch_value_hash,
            "line_ending_policy": "lf-normalized",
            "encoding": "utf-8",
            "updated_at": utc_now(),
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        },
    )


def project_record(root: Path) -> dict[str, Any]:
    return {
        "schema_version": PROJECT_SCHEMA,
        "project_id": project_id(root),
        "root": root.resolve().as_posix(),
        "created_at": utc_now(),
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "authority": {
            "source_files": "current projection only",
            "citation_index": ".ucf-rs/citation-index.jsonl",
            "operation_log": ".ucf-rs/operation-log.jsonl",
        },
    }


def append_index_record(
    paths: StorePaths,
    index_records: list[dict[str, Any]],
    operation_record: dict[str, Any],
    server_epoch: int,
    server_epoch_value_hash: str,
    transition: str,
    state: str,
    relative_uri: str,
    partition_id: str,
    upstream_handle: str,
    accepted_hash: str,
    current_hash: str,
    document_revision_hash: str,
    selected_range: Range,
    current_content: str,
    transform_status: str,
    accepted_line_hashes: list[str] | None = None,
    accepted_line_count: int | None = None,
    accepted_byte_count: int | None = None,
) -> dict[str, Any]:
    latest = latest_index_records(index_records).get(partition_id)
    accepted_lines = accepted_line_hashes if accepted_line_hashes is not None else line_hashes(current_content)
    accepted_bytes = (
        accepted_byte_count
        if accepted_byte_count is not None
        else len(normalize_text(current_content).encode("utf-8"))
    )
    accepted_lines_count = accepted_line_count if accepted_line_count is not None else len(accepted_lines)
    record: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA,
        "record_type": "citation_index_record",
        "previous_index_record_hash": index_records[-1]["index_record_hash"] if index_records else None,
        "previous_partition_record_hash": latest["index_record_hash"] if latest else None,
        "operation_hash": operation_record["operation_hash"],
        "server_epoch": server_epoch,
        "server_epoch_hash": server_epoch_value_hash,
        "transition": transition,
        "state": state,
        "project_id": project_id(paths.root),
        "document_id": document_id(paths.root, relative_uri),
        "adapter": {"kind": "filesystem-text", "uri": relative_uri},
        "upstream_handle": upstream_handle,
        "handle_token": upstream_handle,
        "partition_id": partition_id,
        "citation_id": citation_id(paths.root, partition_id),
        "accepted_content_hash": accepted_hash,
        "current_content_hash": current_hash,
        "partition_hash": partition_hash(partition_id, accepted_hash),
        "document_revision_hash": document_revision_hash,
        "evidence": {
            "kind": "text",
            "canonicalization": "text-utf8-lf-v1",
            "line_count": accepted_lines_count,
            "byte_count": accepted_bytes,
            "line_hashes": accepted_lines,
        },
        "range": range_payload(selected_range),
        "blocks": [
            {
                "block_id": f"{partition_id}#0",
                "block_hash": block_hash(partition_id, current_content),
                "start": selected_range.start,
                "end": selected_range.end,
            }
        ],
        "citation": make_citation(paths.root, partition_id),
        "transform_status": transform_status,
        "created_at": utc_now(),
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
    }
    record["index_record_hash"] = index_record_hash(record)
    append_jsonl(paths.index, record)
    index_records.append(record)
    return record


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    paths.store.mkdir(parents=True, exist_ok=True)
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    if not paths.project.exists():
        paths.project.write_text(
            json.dumps(project_record(root), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    for path in (paths.index, paths.operations, paths.offline_queue, paths.offline_replayed, paths.documents, paths.handles):
        path.touch(exist_ok=True)
    imported = 0
    default_registry = registry_path(root)
    if default_registry.exists():
        imported = import_registry(paths, default_registry)
    print(f"initialized {relative_path(root, paths.store)} imported_handles={imported}")
    return 0


def preflight_activation(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    validate_handle(paths, args.handle, args.task_context)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    text = read_text_document(source_path)
    start_line, end_line = parse_line_range(args.lines)
    selected_range = range_from_line_selection(text, start_line, end_line)
    selected_text = text[selected_range.start : selected_range.end]
    accepted_hash = content_hash_text(selected_text)
    if getattr(args, "expected_content_hash", None) and args.expected_content_hash != accepted_hash:
        raise DemoError(
            f"expected content hash {args.expected_content_hash} does not match selected content {accepted_hash}"
        )
    doc_hash = document_hash_text(text)
    document_record_id = document_id(root, relative_uri)
    operations, index_records = read_store_for_mutation(paths)
    partition_id = allocate_partition_id(index_records, args.handle)
    current_epoch, current_epoch_hash = last_epoch(index_records)
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "project_id": project_id(root),
        "document_id": document_record_id,
        "adapter": {"kind": "filesystem-text", "uri": relative_uri},
        "handle": args.handle,
        "partition_id": partition_id,
        "range": range_payload(selected_range),
        "content_hash": accepted_hash,
        "document_revision_hash": doc_hash,
        "line_hashes": line_hashes(selected_text),
        "base_server_epoch": current_epoch,
        "base_server_epoch_hash": current_epoch_hash,
        "source_mutated": False,
        "_paths": paths,
        "_operations": operations,
        "_index_records": index_records,
        "_selected_text": selected_text,
        "_selected_range": selected_range,
    }


def command_preflight(args: argparse.Namespace) -> int:
    output = {
        key: value
        for key, value in preflight_activation(args).items()
        if not key.startswith("_")
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def command_activate(args: argparse.Namespace) -> int:
    plan = preflight_activation(args)
    root = Path(args.root).resolve()
    paths: StorePaths = plan["_paths"]
    operations: list[dict[str, Any]] = plan["_operations"]
    index_records: list[dict[str, Any]] = plan["_index_records"]
    selected_range: Range = plan["_selected_range"]
    selected_text: str = plan["_selected_text"]
    current_epoch = int(plan["base_server_epoch"])
    current_epoch_hash = str(plan["base_server_epoch_hash"])
    relative_uri = str(plan["adapter"]["uri"])
    accepted_hash = str(plan["content_hash"])
    doc_hash = str(plan["document_revision_hash"])
    document_record_id = str(plan["document_id"])
    partition_id = str(plan["partition_id"])
    operation_record = append_operation(
        paths,
        operations,
        "activate",
        document_record_id,
        current_epoch_hash,
        doc_hash,
        doc_hash,
        [],
        [partition_id],
    )
    new_epoch_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    index_record = append_index_record(
        paths,
        index_records,
        operation_record,
        current_epoch + 1,
        new_epoch_hash,
        "activate",
        "active",
        relative_uri,
        partition_id,
        str(plan["handle"]),
        accepted_hash,
        accepted_hash,
        doc_hash,
        selected_range,
        selected_text,
        "valid",
    )
    append_document_record(paths, relative_uri, document_record_id, doc_hash, new_epoch_hash)
    output = {
        "partition_id": partition_id,
        "citation": index_record["citation"],
        "range": index_record["range"],
        "source_mutated": False,
        "index_record_hash": index_record["index_record_hash"],
        "server_epoch_hash": new_epoch_hash,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"activated {partition_id} citation={index_record['citation']['display']}")
    return 0


def transform_range(
    start: int,
    end: int,
    edit_start: int,
    edit_end: int,
    inserted_length: int,
    boundary_policy: str,
) -> TransformResult:
    delta = inserted_length - (edit_end - edit_start)
    if edit_start <= start and edit_end >= end and inserted_length == 0:
        return TransformResult(edit_start, edit_start, "missing")
    if edit_start == edit_end == start:
        if boundary_policy == "inside":
            return TransformResult(start, end + inserted_length, "inside_changed")
        return TransformResult(start + inserted_length, end + inserted_length, "range_shifted")
    if edit_start == edit_end == end:
        if boundary_policy == "inside":
            return TransformResult(start, end + inserted_length, "inside_changed")
        return TransformResult(start, end, "unaffected")
    if edit_end <= start:
        return TransformResult(start + delta, end + delta, "range_shifted")
    if edit_start >= end:
        return TransformResult(start, end, "unaffected")
    if edit_start > start and edit_end < end:
        return TransformResult(start, end + delta, "inside_changed")
    if edit_start >= start and edit_end <= end:
        if edit_start == start or edit_end == end:
            return TransformResult(start, max(start, end + delta), "boundary_touched")
        return TransformResult(start, end + delta, "inside_changed")
    return TransformResult(min(start, edit_start), max(min(start, edit_start), end + delta), "boundary_touched")


def edit_record(start: int, end: int, inserted_text: str) -> dict[str, Any]:
    normalized_insert = normalize_text(inserted_text)
    return {
        "range_encoding": "unicode-scalar",
        "start": start,
        "end": end,
        "inserted_text_hash": framed_hash("ucf.inserted_text.v1", normalized_insert.encode("utf-8")),
        "inserted_text_length": len(normalized_insert),
    }


def document_active_records(
    root: Path, index_records: Iterable[dict[str, Any]], relative_uri: str
) -> list[dict[str, Any]]:
    target_document_id = document_id(root, relative_uri)
    return [
        record
        for record in latest_index_records(index_records).values()
        if record.get("state") == "active" and record.get("document_id") == target_document_id
    ]


def append_edit_index_record(
    paths: StorePaths,
    index_records: list[dict[str, Any]],
    operation_record: dict[str, Any],
    server_epoch: int,
    server_epoch_value_hash: str,
    relative_uri: str,
    document_revision_hash: str,
    document_text: str,
    record: dict[str, Any],
    result: TransformResult,
) -> dict[str, Any]:
    selected_range = range_from_offsets(document_text, result.start, result.end)
    current_text = document_text[selected_range.start : selected_range.end]
    evidence = record.get("evidence", {})
    accepted_line_hashes = evidence.get("line_hashes") if isinstance(evidence, dict) else None
    return append_index_record(
        paths,
        index_records,
        operation_record,
        server_epoch,
        server_epoch_value_hash,
        "edit-transform",
        "active",
        relative_uri,
        str(record["partition_id"]),
        str(record["upstream_handle"]),
        str(record["accepted_content_hash"]),
        content_hash_text(current_text),
        document_revision_hash,
        selected_range,
        current_text,
        result.status,
        accepted_line_hashes if isinstance(accepted_line_hashes, list) else None,
        evidence.get("line_count") if isinstance(evidence, dict) else None,
        evidence.get("byte_count") if isinstance(evidence, dict) else None,
    )


def command_apply_edit(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    old_text = read_text_document(source_path)
    edit_start = args.start
    edit_end = args.end
    if edit_start < 0 or edit_end < edit_start or edit_end > len(old_text):
        raise DemoError(f"edit range {edit_start}:{edit_end} is outside the document")
    inserted_text = normalize_text(args.insert)
    new_text = old_text[:edit_start] + inserted_text + old_text[edit_end:]
    before_hash = document_hash_text(old_text)
    after_hash = document_hash_text(new_text)
    operations, index_records = read_store_for_mutation(paths)
    document_record_id = document_id(root, relative_uri)
    active_records = document_active_records(root, index_records, relative_uri)
    stale_records = [
        str(record["partition_id"])
        for record in active_records
        if record.get("document_revision_hash") != before_hash
    ]
    if stale_records:
        raise DemoError(
            "document has unmanaged changes for active partition(s): "
            + ", ".join(stale_records)
            + "; run status and reconcile or redeclare before applying a managed edit"
        )
    transformed: list[tuple[dict[str, Any], TransformResult]] = []
    for record in active_records:
        record_range = record.get("range", {})
        if not isinstance(record_range, dict):
            continue
        result = transform_range(
            int(record_range["start"]),
            int(record_range["end"]),
            edit_start,
            edit_end,
            len(inserted_text),
            args.boundary_policy,
        )
        transformed.append((record, result))
    write_text_document(source_path, new_text)
    current_epoch, current_epoch_hash = last_epoch(index_records)
    affected = [
        str(record["partition_id"])
        for record, result in transformed
        if result.status != "unaffected"
    ]
    operation_record = append_operation(
        paths,
        operations,
        "edit",
        document_record_id,
        current_epoch_hash,
        before_hash,
        after_hash,
        [edit_record(edit_start, edit_end, inserted_text)],
        affected,
    )
    server_epoch = current_epoch
    server_epoch_value_hash = current_epoch_hash
    if transformed:
        server_epoch += 1
        server_epoch_value_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    emitted: list[dict[str, Any]] = []
    for record, result in transformed:
        emitted.append(
            append_edit_index_record(
                paths,
                index_records,
                operation_record,
                server_epoch,
                server_epoch_value_hash,
                relative_uri,
                after_hash,
                new_text,
                record,
                result,
            )
        )
    append_document_record(paths, relative_uri, document_record_id, after_hash, server_epoch_value_hash)
    output = {
        "operation_hash": operation_record["operation_hash"],
        "affected_partitions": affected,
        "server_epoch_hash": server_epoch_value_hash,
        "overlays": [
            {
                "partition_id": record["partition_id"],
                "range": record["range"],
                "transform_status": record["transform_status"],
                "current_content_hash": record["current_content_hash"],
            }
            for record in emitted
        ],
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"applied edit affected={len(affected)}")
    return 0


def append_offline_operation(
    paths: StorePaths,
    queued: list[dict[str, Any]],
    relative_uri: str,
    document_record_id: str,
    base_server_epoch_hash: str,
    before_hash: str,
    after_hash: str,
    edit: dict[str, Any],
    affected: list[str],
    document_after_text: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": OFFLINE_SCHEMA,
        "record_type": "offline_operation",
        "previous_offline_operation_hash": queued[-1]["offline_operation_hash"] if queued else None,
        "project_id": project_id(paths.root),
        "document_id": document_record_id,
        "adapter": {"kind": "filesystem-text", "uri": relative_uri},
        "base_server_epoch_hash": base_server_epoch_hash,
        "operation_type": "edit",
        "document_before_hash": before_hash,
        "document_after_hash": after_hash,
        "edits": [edit],
        "affected_partitions": affected,
        "document_after_text": normalize_text(document_after_text),
        "archive_policy": "offline-queue-text-v1",
        "created_at": utc_now(),
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
    }
    record["offline_operation_hash"] = offline_operation_hash(record)
    append_jsonl(paths.offline_queue, record)
    queued.append(record)
    return record


def command_queue_offline_edit(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    old_text = read_text_document(source_path)
    edit_start = args.start
    edit_end = args.end
    if edit_start < 0 or edit_end < edit_start or edit_end > len(old_text):
        raise DemoError(f"edit range {edit_start}:{edit_end} is outside the document")
    inserted_text = normalize_text(args.insert)
    new_text = old_text[:edit_start] + inserted_text + old_text[edit_end:]
    before_hash = document_hash_text(old_text)
    after_hash = document_hash_text(new_text)
    operations, index_records, diagnostics = read_store(paths)
    if diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in diagnostics}))
        raise DemoError(f"cannot queue against invalid UCF-RS store ({codes})")
    queued, queue_diagnostics = read_offline_queue(paths)
    if queue_diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in queue_diagnostics}))
        raise DemoError(f"cannot append to invalid offline queue ({codes})")
    active_records = document_active_records(root, index_records, relative_uri)
    stale_records = [
        str(record["partition_id"])
        for record in active_records
        if record.get("document_revision_hash") != before_hash
    ]
    if stale_records:
        raise DemoError(
            "document has unmanaged changes for active partition(s): "
            + ", ".join(stale_records)
            + "; run status and reconcile or redeclare before queuing an offline edit"
        )
    affected: list[str] = []
    for record in active_records:
        record_range = record.get("range", {})
        if not isinstance(record_range, dict):
            continue
        result = transform_range(
            int(record_range["start"]),
            int(record_range["end"]),
            edit_start,
            edit_end,
            len(inserted_text),
            args.boundary_policy,
        )
        if result.status != "unaffected":
            affected.append(str(record["partition_id"]))
    _, base_epoch_hash = last_epoch(index_records)
    write_text_document(source_path, new_text)
    record = append_offline_operation(
        paths,
        queued,
        relative_uri,
        document_id(root, relative_uri),
        base_epoch_hash,
        before_hash,
        after_hash,
        edit_record(edit_start, edit_end, inserted_text) | {"inserted_text": inserted_text},
        affected,
        new_text,
    )
    output = {
        "offline_operation_hash": record["offline_operation_hash"],
        "affected_partitions": affected,
        "base_server_epoch_hash": base_epoch_hash,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"queued offline edit affected={len(affected)}")
    return 0


def replay_offline_record(
    paths: StorePaths,
    operations: list[dict[str, Any]],
    index_records: list[dict[str, Any]],
    record: dict[str, Any],
    initial_epoch_hash: str,
) -> list[str]:
    if record.get("base_server_epoch_hash") != initial_epoch_hash:
        raise DemoError("offline queue base epoch does not match the current server epoch")
    adapter = record.get("adapter", {})
    relative_uri = adapter.get("uri") if isinstance(adapter, dict) else None
    if not isinstance(relative_uri, str):
        raise DemoError("offline operation is missing a filesystem URI")
    edits = record.get("edits")
    if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
        raise DemoError("offline replay currently requires exactly one edit per queued operation")
    edit = edits[0]
    inserted_text = edit.get("inserted_text")
    if not isinstance(inserted_text, str):
        raise DemoError("offline operation lacks replay text")
    document_after_text = record.get("document_after_text")
    if not isinstance(document_after_text, str):
        raise DemoError("offline operation lacks replay document text")
    after_hash = document_hash_text(document_after_text)
    if after_hash != record.get("document_after_hash"):
        raise DemoError("offline operation document text does not match its recorded after hash")
    source_path = project_path(paths.root, relative_uri)
    write_text_document(source_path, document_after_text)
    current_epoch, current_epoch_hash = last_epoch(index_records)
    operation_record = append_operation(
        paths,
        operations,
        "edit",
        str(record["document_id"]),
        current_epoch_hash,
        str(record["document_before_hash"]),
        str(record["document_after_hash"]),
        [edit_record(int(edit["start"]), int(edit["end"]), inserted_text)],
        [str(item) for item in record.get("affected_partitions", [])],
    )
    server_epoch = current_epoch
    server_epoch_value_hash = current_epoch_hash
    active_records = document_active_records(paths.root, index_records, relative_uri)
    transformed: list[tuple[dict[str, Any], TransformResult]] = []
    for active in active_records:
        record_range = active.get("range", {})
        if not isinstance(record_range, dict):
            continue
        result = transform_range(
            int(record_range["start"]),
            int(record_range["end"]),
            int(edit["start"]),
            int(edit["end"]),
            len(normalize_text(inserted_text)),
            "outside",
        )
        transformed.append((active, result))
    if transformed:
        server_epoch += 1
        server_epoch_value_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    emitted: list[str] = []
    for active, result in transformed:
        appended = append_edit_index_record(
            paths,
            index_records,
            operation_record,
            server_epoch,
            server_epoch_value_hash,
            relative_uri,
            str(record["document_after_hash"]),
            document_after_text,
            active,
            result,
        )
        if result.status != "unaffected":
            emitted.append(str(appended["partition_id"]))
    append_document_record(
        paths,
        relative_uri,
        str(record["document_id"]),
        str(record["document_after_hash"]),
        server_epoch_value_hash,
    )
    return emitted


def command_replay_offline(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    operations, index_records = read_store_for_mutation(paths)
    queued, queue_diagnostics = read_offline_queue(paths)
    if queue_diagnostics:
        codes = ", ".join(sorted({str(diagnostic["code"]) for diagnostic in queue_diagnostics}))
        raise DemoError(f"cannot replay invalid offline queue ({codes})")
    initial_epoch_hash = last_epoch(index_records)[1]
    replayed: list[str] = []
    for record in queued:
        replayed.extend(replay_offline_record(paths, operations, index_records, record, initial_epoch_hash))
    if queued:
        with paths.offline_replayed.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(paths.offline_queue.read_text(encoding="utf-8"))
        paths.offline_queue.write_text("", encoding="utf-8", newline="\n")
    output = {"queued_operations": len(queued), "affected_partitions": replayed}
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"replayed {len(queued)} offline operation(s)")
    return 0


def is_within_store(path: Path, paths: StorePaths) -> bool:
    try:
        path.resolve().relative_to(paths.store.resolve())
        return True
    except ValueError:
        return False


def iter_text_files(root: Path, paths: StorePaths) -> Iterable[Path]:
    excluded = {".git", ".venv", "venv", "node_modules", "dist", "build", "site", "__pycache__"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        if is_within_store(path, paths):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        yield path


def sequence_matches(haystack: list[str], needle: list[str]) -> list[int]:
    if not needle or len(needle) > len(haystack):
        return []
    return [
        index
        for index in range(0, len(haystack) - len(needle) + 1)
        if haystack[index : index + len(needle)] == needle
    ]


def scan_accepted_text_matches(root: Path, paths: StorePaths, record: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = record.get("evidence", {})
    expected_hashes = evidence.get("line_hashes") if isinstance(evidence, dict) else None
    if not isinstance(expected_hashes, list) or not all(isinstance(item, str) for item in expected_hashes):
        return []
    matches: list[dict[str, Any]] = []
    for path in iter_text_files(root, paths):
        text = read_text_document(path)
        lines = text_lines(text)
        hashes = [framed_hash("ucf.line.v1", line.encode("utf-8")) for line in lines]
        offsets = line_offsets(text)
        for index in sequence_matches(hashes, expected_hashes):
            start = offsets[index]
            end_index = index + len(expected_hashes)
            end = offsets[end_index] if end_index < len(offsets) else len(text)
            content = text[start:end]
            if content_hash_text(content) != record.get("accepted_content_hash"):
                continue
            selected_range = range_from_offsets(text, start, end)
            matches.append(
                {
                    "path": relative_path(root, path),
                    "document_id": document_id(root, relative_path(root, path)),
                    "range": range_payload(selected_range),
                    "content_hash": content_hash_text(content),
                    "document_revision_hash": document_hash_text(text),
                }
            )
    return matches


def recovered_status(root: Path, paths: StorePaths, record: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    matches = scan_accepted_text_matches(root, paths, record)
    if len(matches) == 1:
        match = matches[0]
        base["observed_document_revision_hash"] = match["document_revision_hash"]
        base["observed_current_content_hash"] = match["content_hash"]
        base["recovered_locator"] = {
            "adapter": {"kind": "filesystem-text", "uri": match["path"]},
            "document_id": match["document_id"],
            "range": match["range"],
        }
        base["status"] = "valid_moved"
        base["action"] = "relocate"
        return base
    if len(matches) > 1:
        base["matches"] = matches
        base["status"] = "ambiguous"
        base["action"] = "disambiguate"
        return base
    base["status"] = "unmanaged_external_change"
    base["action"] = "reconcile_or_redeclare"
    return base


def partition_status(root: Path, paths: StorePaths, record: dict[str, Any]) -> dict[str, Any]:
    adapter = record.get("adapter", {})
    relative_uri = adapter.get("uri") if isinstance(adapter, dict) else None
    base = {
        "partition_id": record.get("partition_id"),
        "upstream_handle": record.get("upstream_handle"),
        "document_id": record.get("document_id"),
        "adapter": adapter,
        "citation": record.get("citation"),
        "range": record.get("range"),
        "accepted_content_hash": record.get("accepted_content_hash"),
        "current_content_hash": record.get("current_content_hash"),
        "index_record_hash": record.get("index_record_hash"),
        "server_epoch_hash": record.get("server_epoch_hash"),
        "diagnostics": [],
    }
    if not isinstance(relative_uri, str):
        base["status"] = "index_hash_invalid"
        base["action"] = "repair_index"
        return base
    path = project_path(root, relative_uri)
    if not path.exists():
        recovered = recovered_status(root, paths, record, base)
        if recovered["status"] == "unmanaged_external_change":
            recovered["status"] = "missing"
            recovered["action"] = "redeclare_partition"
        return recovered
    text = read_text_document(path)
    current_document_hash = document_hash_text(text)
    record_range = record.get("range", {})
    if not isinstance(record_range, dict):
        base["status"] = "index_hash_invalid"
        base["action"] = "repair_index"
        return base
    start = int(record_range["start"])
    end = int(record_range["end"])
    if end > len(text):
        return recovered_status(root, paths, record, base)
    actual_current_hash = content_hash_text(text[start:end])
    base["observed_document_revision_hash"] = current_document_hash
    base["observed_current_content_hash"] = actual_current_hash
    if actual_current_hash != record.get("current_content_hash"):
        if current_document_hash != record.get("document_revision_hash"):
            recovered = recovered_status(root, paths, record, base)
            base["diagnostics"].append(
                {
                    "code": "E_DOCUMENT_HASH_MISMATCH",
                    "severity": "error",
                    "message": "Document changed without matching UCF operation records.",
                }
            )
            return recovered
        base["status"] = "unmanaged_external_change"
        base["action"] = "reconcile_or_redeclare"
        return base
    if record.get("transform_status") == "missing":
        base["status"] = "missing"
        base["action"] = "redeclare_partition"
    elif record.get("transform_status") == "boundary_touched":
        base["status"] = "boundary_touched"
        base["action"] = "confirm_boundary"
    elif record.get("current_content_hash") == record.get("accepted_content_hash"):
        base["status"] = "valid"
        base["action"] = "none"
    else:
        base["status"] = "changed_unaccepted"
        base["action"] = "accept_current"
    return base


def status_report(root: Path, paths: StorePaths) -> dict[str, Any]:
    operations, index_records, diagnostics = read_store(paths)
    latest = latest_index_records(index_records)
    partitions = [
        partition_status(root, paths, record)
        for record in latest.values()
        if record.get("state") == "active"
    ]
    diagnostics = diagnostics + export_freshness_diagnostics(root, partitions)
    summary: dict[str, int] = {}
    for partition in partitions:
        status = str(partition["status"])
        summary[status] = summary.get(status, 0) + 1
    for diagnostic in diagnostics:
        code = str(diagnostic["code"])
        summary[code] = summary.get(code, 0) + 1
    return {
        "schema_version": STATUS_SCHEMA,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "store": relative_path(root, paths.store),
        "ledger": {
            "index": relative_path(root, paths.index),
            "operations": relative_path(root, paths.operations),
            "index_records": len(index_records),
            "operation_records": len(operations),
            "valid": not diagnostics,
        },
        "summary": summary,
        "partitions": sorted(partitions, key=lambda item: str(item["partition_id"])),
        "diagnostics": diagnostics,
    }


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    report = status_report(root, paths)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for partition in report["partitions"]:
            print(
                f"{partition['partition_id']} status={partition['status']} action={partition['action']}"
            )
        for diagnostic in report["diagnostics"]:
            print(f"{diagnostic['code']}: {diagnostic['message']}", file=sys.stderr)
    failing = {
        "ambiguous",
        "boundary_touched",
        "changed_unaccepted",
        "missing",
        "unmanaged_external_change",
        "valid_moved",
    }
    failed = bool(report["diagnostics"]) or any(
        partition["status"] in failing for partition in report["partitions"]
    )
    return 1 if args.strict and failed else 0


def command_resolve(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    target_document_id = document_id(root, relative_uri)
    report = status_report(root, paths)
    overlays = [
        {
            "partition_id": partition["partition_id"],
            "citation": partition["citation"],
            "range": partition["range"],
            "status": partition["status"],
            "action": partition["action"],
        }
        for partition in report["partitions"]
        if partition.get("document_id") == target_document_id
    ]
    output = {
        "schema_version": RESOLVE_SCHEMA,
        "document": {"kind": "filesystem-text", "uri": relative_uri, "document_id": target_document_id},
        "overlays": overlays,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        for overlay in overlays:
            print(
                f"{overlay['citation']['display']} {overlay['range']['start']}:{overlay['range']['end']} "
                f"status={overlay['status']}"
            )
    return 0


def require_latest_active(index_records: list[dict[str, Any]], partition_id: str) -> dict[str, Any]:
    record = latest_index_records(index_records).get(partition_id)
    if not record or record.get("state") != "active":
        raise DemoError(f"active partition not found: {partition_id}")
    return record


def append_state_record(
    paths: StorePaths,
    operations: list[dict[str, Any]],
    index_records: list[dict[str, Any]],
    record: dict[str, Any],
    transition: str,
    state: str,
    relative_uri: str,
    selected_range: Range,
    current_text: str,
    document_revision: str,
    accepted_hash: str,
    current_hash: str,
    transform_status: str,
) -> dict[str, Any]:
    current_epoch, current_epoch_hash = last_epoch(index_records)
    document_record_id = document_id(paths.root, relative_uri) if relative_uri else str(record["document_id"])
    operation_record = append_operation(
        paths,
        operations,
        transition,
        document_record_id,
        current_epoch_hash,
        document_revision,
        document_revision,
        [],
        [str(record["partition_id"])],
    )
    new_epoch_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    evidence = record.get("evidence", {})
    accepted_line_hashes = evidence.get("line_hashes") if isinstance(evidence, dict) else None
    return append_index_record(
        paths,
        index_records,
        operation_record,
        current_epoch + 1,
        new_epoch_hash,
        transition,
        state,
        relative_uri,
        str(record["partition_id"]),
        str(record["upstream_handle"]),
        accepted_hash,
        current_hash,
        document_revision,
        selected_range,
        current_text,
        transform_status,
        accepted_line_hashes if isinstance(accepted_line_hashes, list) else None,
        evidence.get("line_count") if isinstance(evidence, dict) else None,
        evidence.get("byte_count") if isinstance(evidence, dict) else None,
    )


def command_reconcile(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    operations, index_records = read_store_for_mutation(paths)
    latest = latest_index_records(index_records)
    report = status_report(root, paths)
    requested = {args.partition_id} if args.partition_id else {
        str(partition["partition_id"])
        for partition in report["partitions"]
        if partition.get("status") == "valid_moved"
    }
    reconciled: list[str] = []
    for partition in report["partitions"]:
        partition_id = str(partition["partition_id"])
        if partition_id not in requested or partition.get("status") != "valid_moved":
            continue
        record = latest[partition_id]
        recovered = partition.get("recovered_locator")
        if not isinstance(recovered, dict):
            continue
        adapter = recovered.get("adapter", {})
        relative_uri = adapter.get("uri") if isinstance(adapter, dict) else None
        recovered_range = recovered.get("range")
        if not isinstance(relative_uri, str) or not isinstance(recovered_range, dict):
            continue
        path = project_path(root, relative_uri)
        text = read_text_document(path)
        selected_range = range_from_offsets(text, int(recovered_range["start"]), int(recovered_range["end"]))
        current_text = text[selected_range.start : selected_range.end]
        current_hash = content_hash_text(current_text)
        doc_hash = document_hash_text(text)
        append_state_record(
            paths,
            operations,
            index_records,
            record,
            "relocate",
            "active",
            relative_uri,
            selected_range,
            current_text,
            doc_hash,
            str(record["accepted_content_hash"]),
            current_hash,
            "valid",
        )
        append_document_record(paths, relative_uri, document_id(root, relative_uri), doc_hash, last_epoch(index_records)[1])
        reconciled.append(partition_id)
    output = {"reconciled": reconciled, "count": len(reconciled)}
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"reconciled {len(reconciled)} partition(s)")
    return 0 if reconciled or args.partition_id is None else 1


def command_deactivate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    operations, index_records = read_store_for_mutation(paths)
    record = require_latest_active(index_records, args.partition_id)
    adapter = record.get("adapter", {})
    relative_uri = adapter.get("uri") if isinstance(adapter, dict) else ""
    text = read_text_document(project_path(root, str(relative_uri))) if relative_uri else ""
    record_range = record.get("range", {})
    selected_range = range_from_offsets(text, int(record_range["start"]), int(record_range["end"])) if text else Range(0, 0, 1, 1)
    current_text = text[selected_range.start : selected_range.end] if text else ""
    doc_hash = document_hash_text(text)
    appended = append_state_record(
        paths,
        operations,
        index_records,
        record,
        "deactivate",
        "inactive",
        str(relative_uri),
        selected_range,
        current_text,
        doc_hash,
        str(record["accepted_content_hash"]),
        content_hash_text(current_text),
        "inactive",
    )
    if args.format == "json":
        print(json.dumps({"partition_id": args.partition_id, "index_record_hash": appended["index_record_hash"]}, indent=2, sort_keys=True))
    else:
        print(f"deactivated {args.partition_id}")
    return 0


def command_reactivate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    operations, index_records = read_store_for_mutation(paths)
    record = latest_index_records(index_records).get(args.partition_id)
    if not record or record.get("state") != "inactive":
        raise DemoError(f"inactive partition not found: {args.partition_id}")
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    text = read_text_document(source_path)
    start_line, end_line = parse_line_range(args.lines)
    selected_range = range_from_line_selection(text, start_line, end_line)
    current_text = text[selected_range.start : selected_range.end]
    current_hash = content_hash_text(current_text)
    doc_hash = document_hash_text(text)
    current_epoch, current_epoch_hash = last_epoch(index_records)
    operation_record = append_operation(
        paths,
        operations,
        "reactivate",
        document_id(root, relative_uri),
        current_epoch_hash,
        doc_hash,
        doc_hash,
        [],
        [args.partition_id],
    )
    new_epoch_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    appended = append_index_record(
        paths,
        index_records,
        operation_record,
        current_epoch + 1,
        new_epoch_hash,
        "reactivate",
        "active",
        relative_uri,
        args.partition_id,
        str(record["upstream_handle"]),
        current_hash,
        current_hash,
        doc_hash,
        selected_range,
        current_text,
        "valid",
    )
    append_document_record(paths, relative_uri, document_id(root, relative_uri), doc_hash, new_epoch_hash)
    if args.format == "json":
        print(json.dumps({"partition_id": args.partition_id, "index_record_hash": appended["index_record_hash"]}, indent=2, sort_keys=True))
    else:
        print(f"reactivated {args.partition_id}")
    return 0


def command_accept(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    operations, index_records = read_store_for_mutation(paths)
    latest = latest_index_records(index_records)
    record = latest.get(args.partition_id)
    if not record or record.get("state") != "active":
        raise DemoError(f"active partition not found: {args.partition_id}")
    if args.previous_index_record_hash and args.previous_index_record_hash != record.get("index_record_hash"):
        raise DemoError("previous index record hash does not match the latest partition state")
    adapter = record.get("adapter", {})
    relative_uri = adapter.get("uri") if isinstance(adapter, dict) else None
    if not isinstance(relative_uri, str):
        raise DemoError(f"partition has no filesystem URI: {args.partition_id}")
    source_path = project_path(root, relative_uri)
    text = read_text_document(source_path)
    doc_hash = document_hash_text(text)
    if doc_hash != record.get("document_revision_hash"):
        raise DemoError("document has unmanaged changes; reconcile or redeclare before accepting")
    current_status = partition_status(root, paths, record)
    if current_status.get("action") not in {"accept_current", "confirm_boundary"}:
        raise DemoError(
            f"partition status {current_status.get('status')} cannot be accepted; "
            f"required action is {current_status.get('action')}"
        )
    record_range = record.get("range", {})
    selected_range = range_from_offsets(text, int(record_range["start"]), int(record_range["end"]))
    current_hash = content_hash_text(text[selected_range.start : selected_range.end])
    if current_hash != record.get("current_content_hash"):
        raise DemoError("current content hash does not match the latest managed range")
    current_epoch, current_epoch_hash = last_epoch(index_records)
    operation_record = append_operation(
        paths,
        operations,
        "accept",
        str(record["document_id"]),
        current_epoch_hash,
        doc_hash,
        doc_hash,
        [],
        [args.partition_id],
    )
    new_epoch_hash = epoch_hash(current_epoch_hash, operation_record["operation_hash"])
    accepted_record = append_index_record(
        paths,
        index_records,
        operation_record,
        current_epoch + 1,
        new_epoch_hash,
        "accept",
        "active",
        relative_uri,
        args.partition_id,
        str(record["upstream_handle"]),
        current_hash,
        current_hash,
        doc_hash,
        selected_range,
        text[selected_range.start : selected_range.end],
        "valid",
    )
    append_document_record(paths, relative_uri, str(record["document_id"]), doc_hash, new_epoch_hash)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "partition_id": args.partition_id,
                    "accepted_content_hash": current_hash,
                    "index_record_hash": accepted_record["index_record_hash"],
                    "server_epoch_hash": new_epoch_hash,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"accepted {args.partition_id}")
    return 0


def export_records_from_partitions(partitions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for partition in partitions:
        records.append(
            {
                "schema_version": EXPORT_SCHEMA,
                "partition_id": partition["partition_id"],
                "upstream_handle": partition["upstream_handle"],
                "adapter": partition["adapter"],
                "citation": partition["citation"],
                "range": partition["range"],
                "accepted_content_hash": partition["accepted_content_hash"],
                "current_content_hash": partition["current_content_hash"],
                "status": partition["status"],
                "action": partition["action"],
                "index_record_hash": partition["index_record_hash"],
                "server_epoch_hash": partition["server_epoch_hash"],
            }
        )
    return sorted(records, key=lambda item: str(item["partition_id"]))


def export_content_from_partitions(partitions: Iterable[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in export_records_from_partitions(partitions)
    ).encode("utf-8")


def export_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    return export_records_from_partitions(report["partitions"])


def export_freshness_diagnostics(root: Path, partitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output_path = project_path(root, EXPORT_LEDGER_DEFAULT)
    if not output_path.exists():
        return []
    try:
        current = output_path.read_bytes()
    except OSError as error:
        return [
            {
                "code": "E_EXPORT_UNREADABLE",
                "severity": "error",
                "message": f"cannot read exported ledger: {error}",
                "path": relative_path(root, output_path),
            }
        ]
    expected = export_content_from_partitions(partitions)
    if current == expected:
        return []
    return [
        {
            "code": "E_EXPORT_STALE",
            "severity": "error",
            "message": "exported ledger differs from current UCF-RS status projection",
            "path": relative_path(root, output_path),
            "details": {
                "expected_export_ledger_hash": export_ledger_hash(expected),
                "actual_export_ledger_hash": export_ledger_hash(current),
            },
        }
    ]


def command_export_ledger(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    output_path = project_path(root, args.output)
    report = status_report(root, paths)
    records = export_records(report)
    content = export_content_from_partitions(report["partitions"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    refreshed_report = status_report(root, paths)
    output = {
        "path": relative_path(root, output_path),
        "record_count": len(records),
        "export_ledger_hash": export_ledger_hash(content),
        "status_valid": not refreshed_report["diagnostics"],
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"exported {output['record_count']} record(s) to {output['path']}")
    return 0


def command_virtual_blocks(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    target_document_id = document_id(root, relative_uri)
    text = read_text_document(source_path)
    report = status_report(root, paths)
    blocks: list[dict[str, Any]] = []
    for partition in report["partitions"]:
        if partition.get("document_id") != target_document_id:
            continue
        record_range = partition["range"]
        start = int(record_range["start"])
        end = int(record_range["end"])
        blocks.append(
            {
                "partition_id": partition["partition_id"],
                "citation": partition["citation"],
                "range": record_range,
                "status": partition["status"],
                "content": text[start:end],
            }
        )
    output = {
        "document": {"kind": "filesystem-text", "uri": relative_uri, "document_id": target_document_id},
        "virtual_blocks": blocks,
        "authoritative": False,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        for block in blocks:
            print(f"UCF_BEGIN {block['partition_id']}")
            print(block["content"], end="" if block["content"].endswith("\n") else "\n")
            print(f"UCF_END {block['partition_id']}")
    return 0


def command_import_registry(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    paths.store.mkdir(parents=True, exist_ok=True)
    paths.handles.touch(exist_ok=True)
    count = import_registry(paths, project_path(root, args.path))
    if args.format == "json":
        print(json.dumps({"imported": count, "handle_cache": relative_path(root, paths.handles)}, indent=2, sort_keys=True))
    else:
        print(f"imported {count} handle(s)")
    return 0


def command_discover_reqtrace(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    candidates: list[dict[str, Any]] = []
    for path in iter_text_files(root, paths):
        text = read_text_document(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in REQTRACE_MARKER_RE.finditer(line):
                candidates.append(
                    {
                        "handle": match.group(1),
                        "path": relative_path(root, path),
                        "line": line_number,
                        "marker": "@reqtrace",
                        "advisory": True,
                    }
                )
    output = {
        "schema_version": "ucf-rs.reqtrace_discovery.v1",
        "count": len(candidates),
        "candidates": candidates,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        for candidate in candidates:
            print(f"{candidate['handle']} {candidate['path']}:{candidate['line']}")
    return 0


def command_session_open(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    source_path = project_path(root, args.path)
    relative_uri = relative_path(root, source_path)
    text = read_text_document(source_path)
    _, index_records, diagnostics = read_store(paths)
    _, current_epoch_hash = last_epoch(index_records)
    target_document_id = document_id(root, relative_uri)
    active = [
        make_citation(root, str(record["partition_id"]))
        for record in latest_index_records(index_records).values()
        if record.get("state") == "active" and record.get("document_id") == target_document_id
    ]
    output = {
        "schema_version": "ucf-rs.session.v1",
        "session_id": framed_hash("ucf.session.v1", target_document_id, document_hash_text(text), utc_now()),
        "server_epoch_hash": current_epoch_hash,
        "document_id": target_document_id,
        "document_revision_hash": document_hash_text(text),
        "active_partitions": active,
        "diagnostics": diagnostics,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if diagnostics else 0


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# UCF-RS Trace Report\n",
        "\n",
        "Generated from the UCF-RS citation index and current filesystem projection. This file is not authoritative.\n",
        "\n",
        f"- Store valid: {report['ledger']['valid']}\n",
        f"- Index records: {report['ledger']['index_records']}\n",
        f"- Operation records: {report['ledger']['operation_records']}\n",
        "\n",
        "| Partition | Handle | Status | Action | Document |\n",
        "| --- | --- | --- | --- | --- |\n",
    ]
    for partition in report["partitions"]:
        adapter = partition.get("adapter", {})
        uri = adapter.get("uri", "") if isinstance(adapter, dict) else ""
        lines.append(
            f"| {partition['partition_id']} | {partition['upstream_handle']} | {partition['status']} | {partition['action']} | {uri} |\n"
        )
    return "".join(lines)


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = store_paths(root, args.store)
    status_path = project_path(root, args.status_output)
    report_path = project_path(root, args.report_output)
    report = status_report(root, paths)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report_path.write_text(render_report(report), encoding="utf-8", newline="\n")
    print(f"rendered {relative_path(root, status_path)} and {relative_path(root, report_path)}")
    return 0


def command_json_result(command: Any, args: argparse.Namespace) -> dict[str, Any]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = command(args)
    if rc != 0:
        raise DemoError(f"command failed with exit code {rc}")
    text = output.getvalue().strip()
    if not text:
        return {"exit_code": rc}
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise DemoError(f"command did not emit JSON: {text}") from error
    if not isinstance(result, dict):
        raise DemoError("command JSON result must be an object")
    return result


def require_server_string(params: dict[str, Any], method: str, name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str):
        raise DemoError(f"{method} requires string params.{name}")
    return value


def optional_server_string(
    params: dict[str, Any], method: str, name: str, default: str | None = None
) -> str | None:
    value = params.get(name, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DemoError(f"{method} requires string params.{name}")
    return value


def require_server_path(params: dict[str, Any], method: str) -> str:
    value = params.get("path")
    if value is None:
        value = params.get("document")
    if not isinstance(value, str):
        raise DemoError(f"{method} requires string params.path")
    return value


def require_server_int(params: dict[str, Any], method: str, name: str) -> int:
    value = params.get(name)
    if type(value) is not int:
        raise DemoError(f"{method} requires integer params.{name}")
    return value


def optional_server_bool(params: dict[str, Any], method: str, name: str, default: bool = False) -> bool:
    value = params.get(name, default)
    if not isinstance(value, bool):
        raise DemoError(f"{method} requires boolean params.{name}")
    return value


def optional_boundary_policy(params: dict[str, Any], method: str) -> str:
    value = params.get("boundary_policy", "outside")
    if value not in {"outside", "inside"}:
        raise DemoError(f"{method} requires params.boundary_policy to be outside or inside")
    return str(value)


def serve_dispatch(root: Path, store: str, request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise DemoError("request params must be an object")
    paths = store_paths(root, store)
    if method == "status.current":
        return status_report(root, paths)
    if method == "citation.resolve":
        path_value = params.get("path")
        if not isinstance(path_value, str):
            raise DemoError("citation.resolve requires params.path")
        source_path = project_path(root, path_value)
        target_document_id = document_id(root, relative_path(root, source_path))
        report = status_report(root, paths)
        return {
            "schema_version": RESOLVE_SCHEMA,
            "overlays": [
                partition
                for partition in report["partitions"]
                if partition.get("document_id") == target_document_id
            ],
        }
    if method == "session.open":
        path_value = params.get("path")
        if not isinstance(path_value, str):
            raise DemoError("session.open requires params.path")
        source_path = project_path(root, path_value)
        text = read_text_document(source_path)
        _, index_records, _ = read_store(paths)
        return {
            "schema_version": "ucf-rs.session.v1",
            "session_id": framed_hash("ucf.session.v1", relative_path(root, source_path), document_hash_text(text), utc_now()),
            "document_id": document_id(root, relative_path(root, source_path)),
            "document_revision_hash": document_hash_text(text),
            "server_epoch_hash": last_epoch(index_records)[1],
        }
    if method == "partition.preflight":
        return command_json_result(
            command_preflight,
            argparse.Namespace(
                root=str(root),
                store=store,
                handle=require_server_string(params, method, "handle"),
                path=require_server_path(params, method),
                lines=require_server_string(params, method, "lines"),
                expected_content_hash=optional_server_string(params, method, "expected_content_hash"),
                task_context=optional_server_bool(params, method, "task_context"),
            ),
        )
    if method == "partition.activate":
        return command_json_result(
            command_activate,
            argparse.Namespace(
                root=str(root),
                store=store,
                handle=require_server_string(params, method, "handle"),
                path=require_server_path(params, method),
                lines=require_server_string(params, method, "lines"),
                expected_content_hash=optional_server_string(params, method, "expected_content_hash"),
                task_context=optional_server_bool(params, method, "task_context"),
                format="json",
            ),
        )
    if method == "document.apply_edit":
        return command_json_result(
            command_apply_edit,
            argparse.Namespace(
                root=str(root),
                store=store,
                path=require_server_path(params, method),
                start=require_server_int(params, method, "start"),
                end=require_server_int(params, method, "end"),
                insert=optional_server_string(params, method, "insert", "") or "",
                boundary_policy=optional_boundary_policy(params, method),
                format="json",
            ),
        )
    if method == "document.queue_offline_edit":
        return command_json_result(
            command_queue_offline_edit,
            argparse.Namespace(
                root=str(root),
                store=store,
                path=require_server_path(params, method),
                start=require_server_int(params, method, "start"),
                end=require_server_int(params, method, "end"),
                insert=optional_server_string(params, method, "insert", "") or "",
                boundary_policy=optional_boundary_policy(params, method),
                format="json",
            ),
        )
    if method == "offline.replay":
        return command_json_result(
            command_replay_offline,
            argparse.Namespace(root=str(root), store=store, format="json"),
        )
    if method == "partition.accept":
        return command_json_result(
            command_accept,
            argparse.Namespace(
                root=str(root),
                store=store,
                partition_id=require_server_string(params, method, "partition_id"),
                previous_index_record_hash=optional_server_string(
                    params, method, "previous_index_record_hash"
                ),
                format="json",
            ),
        )
    if method == "export.ledger":
        return command_json_result(
            command_export_ledger,
            argparse.Namespace(
                root=str(root),
                store=store,
                output=optional_server_string(params, method, "output", EXPORT_LEDGER_DEFAULT)
                or EXPORT_LEDGER_DEFAULT,
                format="json",
            ),
        )
    raise DemoError(f"unsupported method: {method}")


def is_json_rpc_request(request: dict[str, Any]) -> bool:
    return request.get("jsonrpc") == "2.0" or "id" in request


def serve_success_response(request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if is_json_rpc_request(request):
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
    return {"ok": True, "result": result}


def serve_error_response(request: dict[str, Any] | None, error: Exception) -> dict[str, Any]:
    if request is not None and is_json_rpc_request(request):
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32000, "message": str(error)},
        }
    return {"ok": False, "error": str(error)}


def make_http_server(root: Path, store: str, host: str, port: int) -> ThreadingHTTPServer:
    class UcfRequestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                self.send_json({"ok": False, "error": "missing Content-Length"}, 411)
                return
            request: dict[str, Any] | None = None
            try:
                length = int(length_header)
                payload = self.rfile.read(length)
                decoded = json.loads(payload.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise DemoError("request must be an object")
                request = decoded
                response = serve_success_response(request, serve_dispatch(root, store, request))
                self.send_json(response, 200)
            except (DemoError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                self.send_json(serve_error_response(request, error), 400)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def send_json(self, response: dict[str, Any], status: int) -> None:
            body = json.dumps(response, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), UcfRequestHandler)


def command_serve(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.transport == "http":
        server = make_http_server(root, args.store, args.host, args.port)
        host, port = server.server_address
        print(f"ucf-rs listening on http://{host}:{port}", flush=True)
        if args.once:
            server.handle_request()
        else:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        server.server_close()
        return 0
    for line in sys.stdin:
        if not line.strip():
            continue
        request: dict[str, Any] | None = None
        try:
            decoded = json.loads(line)
            if not isinstance(decoded, dict):
                raise DemoError("request must be an object")
            request = decoded
            response = serve_success_response(request, serve_dispatch(root, args.store, request))
        except (DemoError, json.JSONDecodeError) as error:
            response = serve_error_response(request, error)
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the UCF-RS local authority runtime.")
    parser.add_argument("--root", default=".", help="project root, defaults to the current directory")
    parser.add_argument("--store", default=STORE_DEFAULT, help=f"UCF-RS store path, default {STORE_DEFAULT}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="create the local UCF-RS store files")
    init.set_defaults(func=command_init)

    preflight = subcommands.add_parser("preflight", help="validate an activation without mutating authority")
    preflight.add_argument("--handle", required=True)
    preflight.add_argument("--path", "--document", dest="path", required=True)
    preflight.add_argument("--lines", required=True, help="1-based inclusive START:END line range")
    preflight.add_argument("--expected-content-hash")
    preflight.add_argument("--task-context", action="store_true")
    preflight.set_defaults(func=command_preflight)

    activate = subcommands.add_parser("activate", help="accept a source range without source markers")
    activate.add_argument("--handle", required=True)
    activate.add_argument("--path", "--document", dest="path", required=True)
    activate.add_argument("--lines", required=True, help="1-based inclusive START:END line range")
    activate.add_argument("--expected-content-hash")
    activate.add_argument(
        "--task-context",
        action="store_true",
        help="treat --handle as explicitly supplied by task context instead of the registry",
    )
    activate.add_argument("--format", choices=("text", "json"), default="text")
    activate.set_defaults(func=command_activate)

    apply_edit = subcommands.add_parser("apply-edit", help="apply a managed edit delta and update overlays")
    apply_edit.add_argument("--path", "--document", dest="path", required=True)
    apply_edit.add_argument("--start", type=int, required=True, help="unicode-scalar start offset")
    apply_edit.add_argument("--end", type=int, required=True, help="unicode-scalar end offset")
    apply_edit.add_argument("--insert", default="", help="replacement text")
    apply_edit.add_argument("--boundary-policy", choices=("outside", "inside"), default="outside")
    apply_edit.add_argument("--format", choices=("text", "json"), default="text")
    apply_edit.set_defaults(func=command_apply_edit)

    queue_offline = subcommands.add_parser("queue-offline-edit", help="record an offline edit for later epoch replay")
    queue_offline.add_argument("--path", "--document", dest="path", required=True)
    queue_offline.add_argument("--start", type=int, required=True)
    queue_offline.add_argument("--end", type=int, required=True)
    queue_offline.add_argument("--insert", default="")
    queue_offline.add_argument("--boundary-policy", choices=("outside", "inside"), default="outside")
    queue_offline.add_argument("--format", choices=("text", "json"), default="text")
    queue_offline.set_defaults(func=command_queue_offline_edit)

    replay_offline = subcommands.add_parser("replay-offline", help="replay queued offline edits through authority")
    replay_offline.add_argument("--format", choices=("text", "json"), default="text")
    replay_offline.set_defaults(func=command_replay_offline)

    accept = subcommands.add_parser("accept", help="explicitly accept the latest managed partition content")
    accept.add_argument("--partition-id", required=True)
    accept.add_argument("--previous-index-record-hash")
    accept.add_argument("--format", choices=("text", "json"), default="text")
    accept.set_defaults(func=command_accept)

    deactivate = subcommands.add_parser("deactivate", help="append an inactive lifecycle record")
    deactivate.add_argument("--partition-id", required=True)
    deactivate.add_argument("--format", choices=("text", "json"), default="text")
    deactivate.set_defaults(func=command_deactivate)

    reactivate = subcommands.add_parser("reactivate", help="reactivate an inactive partition with explicit evidence")
    reactivate.add_argument("--partition-id", required=True)
    reactivate.add_argument("--path", "--document", dest="path", required=True)
    reactivate.add_argument("--lines", required=True)
    reactivate.add_argument("--format", choices=("text", "json"), default="text")
    reactivate.set_defaults(func=command_reactivate)

    reconcile = subcommands.add_parser("reconcile", help="append relocation records for exact recovered moves")
    reconcile.add_argument("--partition-id")
    reconcile.add_argument("--format", choices=("text", "json"), default="text")
    reconcile.set_defaults(func=command_reconcile)

    resolve = subcommands.add_parser("resolve", help="resolve citation overlays for a document")
    resolve.add_argument("--path", "--document", dest="path", required=True)
    resolve.add_argument("--format", choices=("text", "json"), default="text")
    resolve.set_defaults(func=command_resolve)

    citations = subcommands.add_parser("citations", help="alias for resolve")
    citations.add_argument("--path", "--document", dest="path", required=True)
    citations.add_argument("--format", choices=("text", "json"), default="text")
    citations.set_defaults(func=command_resolve)

    status = subcommands.add_parser("status", help="validate the UCF-RS store and current source projection")
    status.add_argument("--format", choices=("text", "json"), default="text")
    status.add_argument("--strict", action="store_true", help="return non-zero when action is required")
    status.set_defaults(func=command_status)

    export_ledger = subcommands.add_parser("export-ledger", help="write deterministic audit JSONL")
    export_ledger.add_argument("--output", default=EXPORT_LEDGER_DEFAULT)
    export_ledger.add_argument("--format", choices=("text", "json"), default="text")
    export_ledger.set_defaults(func=command_export_ledger)

    export = subcommands.add_parser("export", help="export deterministic audit projections")
    export_subcommands = export.add_subparsers(dest="export_command", required=True)
    export_ledger_nested = export_subcommands.add_parser("ledger", help="write deterministic audit JSONL")
    export_ledger_nested.add_argument("--output", default=EXPORT_LEDGER_DEFAULT)
    export_ledger_nested.add_argument("--format", choices=("text", "json"), default="text")
    export_ledger_nested.set_defaults(func=command_export_ledger)
    export_blocks_nested = export_subcommands.add_parser("blocks", help="render virtual track blocks")
    export_blocks_nested.add_argument("--path", "--document", dest="path", required=True)
    export_blocks_nested.add_argument("--format", choices=("text", "json"), default="text")
    export_blocks_nested.set_defaults(func=command_virtual_blocks)

    virtual_blocks = subcommands.add_parser("virtual-blocks", help="render virtual track blocks for inspection")
    virtual_blocks.add_argument("--path", "--document", dest="path", required=True)
    virtual_blocks.add_argument("--format", choices=("text", "json"), default="text")
    virtual_blocks.set_defaults(func=command_virtual_blocks)

    render = subcommands.add_parser("render", help="write generated status JSON and Markdown report")
    render.add_argument("--status-output", default=EXPORT_STATUS_DEFAULT)
    render.add_argument("--report-output", default=EXPORT_REPORT_DEFAULT)
    render.set_defaults(func=command_render)

    import_registry_cmd = subcommands.add_parser("import-registry", help="import Reqtrace-compatible handle registry records")
    import_registry_cmd.add_argument("--path", default="docs/handle-registry.jsonl")
    import_registry_cmd.add_argument("--format", choices=("text", "json"), default="text")
    import_registry_cmd.set_defaults(func=command_import_registry)

    discover_reqtrace = subcommands.add_parser("discover-reqtrace", help="list brownfield @reqtrace markers as advisory candidates")
    discover_reqtrace.add_argument("--format", choices=("text", "json"), default="text")
    discover_reqtrace.set_defaults(func=command_discover_reqtrace)

    session = subcommands.add_parser("session", help="session commands for UCF-aware clients")
    session_subcommands = session.add_subparsers(dest="session_command", required=True)
    session_open = session_subcommands.add_parser("open", help="open a filesystem text document session")
    session_open.add_argument("--path", "--document", dest="path", required=True)
    session_open.set_defaults(func=command_session_open)

    serve = subcommands.add_parser("serve", help="serve JSONL or HTTP requests")
    serve.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--once", action="store_true", help="handle one HTTP request and exit")
    serve.set_defaults(func=command_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DemoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
