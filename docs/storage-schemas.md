# UCF-RS Storage Schemas

UCF-RS keeps source files clean by default. The authoritative state lives in the
project-local `.ucf-rs/` store, while source files and generated exports are
projections over that authority.

## Authority And Projection Classes

| Path | Class | Purpose | Hash Boundary |
| --- | --- | --- | --- |
| `.ucf-rs/project.json` | Authoritative metadata | Project identity, root, tool metadata, and authority file names. | Not part of operation or citation-index record hashes. |
| `.ucf-rs/operation-log.jsonl` | Authoritative append-only log | Managed source operations, affected/refreshed partitions, before/after document hashes, and operation chain links. | Each record is hashed as `ucf.operation.v1` over canonical JSON without `operation_hash`. |
| `.ucf-rs/citation-index.jsonl` | Authoritative append-only index | Citation lifecycle state, accepted evidence hashes, current evidence hashes, ranges, and server epoch chain. | Each record is hashed as `ucf.index_record.v1` over canonical JSON without `index_record_hash`. |
| `.ucf-rs/document-index.jsonl` | Authoritative revision index | Current known filesystem text revision for each document. | Records are append-only but are not inputs to operation or citation-index hashes. |
| `.ucf-rs/handle-cache.jsonl` | Authoritative local handle cache | Imported Reqtrace-compatible handle registry records. | Records are schema-checked by command paths, not chained into operation/index hashes. |
| `.ucf-rs/offline-queue.jsonl` | Local replay authority | Pending disconnected edits, affected/refreshed partition context, replay text, and queue chain hash. | Each record is hashed as `ucf.offline_operation.v1`; this hash is separate from operation/index canonical hashes. |
| `.ucf-rs/offline-replayed.jsonl` | Local replay archive | Consumed offline queue records after successful replay. | Archive records retain their offline hashes; they are not accepted evidence and do not alter operation/index hash domains. |
| `.ucf-rs/snapshots/` | Reserved operational storage | Local runtime snapshots when present. | Provider/runtime data only; not canonical citation authority. |
| `.ucf-rs/transactions/*.json` | Hot recoverable consistency metadata | Pending file transaction manifests for source-plus-authority writes. | Transaction file hashes use `ucf.transaction_file.v1` and are outside operation/index canonical hashes. |
| `.ucf-rs/transactions-committed/*.json` | Transaction recovery archive | Committed manifests after prepared-file cleanup. | Archived records are not scanned during the mutation/status hot path and are outside operation/index canonical hashes. |
| `.ucf-rs/transactions-abandoned/*.json` | Explicit transaction-resolution archive | Operator-approved abandonment records for unapplied divergent transactions. | Archive records preserve inspection evidence and are outside operation/index canonical hashes. |
| `docs/ucf-trace-ledger.jsonl` | Generated projection | Deterministic audit ledger export. | The file content may be hashed as `ucf.export_ledger.v1`; it is not source authority. |
| `docs/ucf-trace-status.json` | Generated projection | Rendered status report. | Rebuildable from source projection and `.ucf-rs/` authority. |
| `docs/ucf-trace-report.md` | Generated projection | Human-readable status report. | Rebuildable and non-authoritative. |
| Source files | Current projection | Clean editable documents. | Source text hashes are recorded in authority records; source files are not themselves the citation index. |

## Canonical Hashing Boundaries

Canonical JSON uses sorted object keys, compact separators, UTF-8 encoding, and
the existing framed hash helper. Foundation A does not change any existing hash
domain or canonical byte rule.

The current canonical domains are:

- `ucf.operation.v1`: operation log record without `operation_hash`.
- `ucf.index_record.v1`: citation-index record without `index_record_hash`.
- `ucf.offline_operation.v1`: offline queue record without `offline_operation_hash`.
- `ucf.epoch.v1`: previous server epoch hash plus committed operation hash.
- `ucf.document.text.v1`: normalized UTF-8 text for filesystem document revision.
- `ucf.content.text.v1`: normalized UTF-8 selected evidence text.
- `ucf.line.v1`: normalized evidence line bytes.
- `ucf.block.v1`: partition id plus normalized block content.
- `ucf.export_ledger.v1`: exported ledger file bytes.
- `ucf.transaction_file.v1`: transaction expected/intended file bytes. This
  domain is recoverability metadata only and does not alter operation or
  citation-index record identity.

UCF-Yjs conformance tests may reproduce behaviors and expected outcomes from
these records, but UCF-Yjs must not depend on these storage files, JSONL layouts,
transaction formats, hash domains, or canonical serialization.

## Schema Compatibility

Supported schema identifiers are explicitly versioned in `scripts/ucf_rs.py`.
Known records with supported schemas are validated by their command-specific
reader before mutation or strict status reporting.

Unsupported or malformed authoritative records fail closed:

- malformed JSONL records produce fatal diagnostics;
- non-object JSONL values produce fatal diagnostics;
- missing or invalid hash fields produce fatal diagnostics;
- hash mismatches produce fatal diagnostics;
- operation chain gaps produce fatal diagnostics;
- citation-index references to missing operations produce fatal diagnostics;
- edit citation-index records not covered by matching operation partition fields
  produce fatal diagnostics;
- invalid server epoch ordering produces fatal diagnostics;
- invalid offline queue chain order blocks queue append and replay.

Commands that mutate authority first read the relevant store and refuse to
continue when fatal diagnostics are present.

## Offline Queue And Replay Archive Classification

The offline queue is local replay material. It may contain source text needed to
replay disconnected edits deterministically. It is not accepted evidence, and
successful replay is not implicit citation acceptance. Successful replay appends
normal operation and citation-index records, then archives the consumed queue
records in `.ucf-rs/offline-replayed.jsonl`.
Queued records preserve affected and refreshed partition context so replay
conflict checks can detect intervening touches to the same partition.

The replay archive is retained operational history. It is not a canonical
operation log and does not replace the append-only operation/index authority.

## Recoverable Transaction Manifests

Transaction manifests are stored below `.ucf-rs/transactions/` and use
`ucf-rs.transaction.v1`. Each manifest records:

- transaction id and purpose;
- current phase: `prepared`, `source_applied`, `authority_applied`, or `committed`;
- target file paths;
- prepared replacement file paths in the target file directories;
- expected file hashes before replacement;
- intended file hashes after replacement.

Recovery recognizes already completed phases from actual file hashes and
continues forward. Residual prepared replacement files are deleted once the
target has the intended hash, and committed manifests are moved to
`.ucf-rs/transactions-committed/` after cleanup so hot recovery cost stays
proportional to pending work. Replacement filenames are excluded from exact
source-recovery scanning.

Malformed manifests, missing replacements, or target divergence fail closed.
For divergence, `transaction inspect` reports file-level expected, intended, and
current hashes. `transaction abandon` may archive a resolution only when no
target contains the transaction's intended bytes; afterward, source status is
computed from the current filesystem and authority records. Manual deletion of
hot manifests is not the recovery procedure.

## UCF-Yjs Behavior Matrix

| UCF-RS Behavior | UCF-Yjs Conformance Requirement |
| --- | --- |
| Source files remain clean unless a managed edit command changes document text. | Public clients use typed commands; raw CRDT changes are not the normal agent contract. |
| Citation activation uses an explicit selected range and records accepted evidence hashes. | `citation.activate` creates a stable citation over an explicit selection with accepted evidence hash. |
| Managed edits before a citation preserve validity through range transformation. | Relative anchors resolve identically after synchronization and preserve citation validity for outside edits. |
| Managed edits outside a citation append `edit-refresh` records for unchanged active partitions. | Unchanged anchors still refresh document revision authority so future managed edits are not misclassified as unmanaged. |
| Managed edits inside accepted evidence become `changed_unaccepted`. | Structural convergence never implies semantic acceptance. |
| Whole-partition deletion is classified as missing. | Deleted or unresolved anchors yield a typed missing or unresolved status. |
| Unmanaged source changes are not implicitly accepted. | Changed evidence requires `citation.accept_current` before acceptance. |
| Exact moved accepted evidence can be reported as moved; duplicates are ambiguous. | Multiple legitimate anchor/evidence candidates remain explicitly ambiguous. |
| Offline replay is epoch checked and fails on conflicting authority changes. | Queued semantic commands distinguish stale observation and semantic conflicts from provider failures. |
| Operation and citation-index records are append-only. | Durable semantic log commands and outcomes are append-only and outside sole Y.Doc authority. |
| Generated ledgers and reports are rebuildable projections. | Projections and agent views are rebuildable and never accepted authority. |
| `status --strict` fails on invalid chains or stale generated ledgers. | Validation detects corrupt log/projection state and refuses to treat it as accepted. |
