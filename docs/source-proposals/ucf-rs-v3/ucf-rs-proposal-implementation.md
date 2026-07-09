# UCF-RS Proposal Implementation

Status: proposal implementation for Reqtrace v3 comparison.

UCF-RS means Universal Citation Formatter Runtime Server. It is an overlay-first
Reqtrace implementation model:

- Source files remain clean.
- Citations are not embedded in source files.
- Track blocks are virtual intermediate projections.
- The server and its durable citation index hold trace authority.
- Humans, agents, editors, CLIs, and chatbots resolve the same citation state.

This proposal uses the invariants derived from the Reqtrace v3 design
conversation. It keeps Reqtrace universal and absolutely traceable while moving
the primary user experience from source-visible markers to runtime citation
overlays.

## 1. Core Thesis

The earlier file-only model has a hard boundary: a cold scanner cannot preserve
changed non-invasive evidence ranges through arbitrary edits without either
source-visible markers, parser authority, edit deltas, or contextual
fingerprinting.

UCF-RS changes the runtime model. It is not a cold scanner. It is a managed
editing and citation runtime that records explicit operational state:

```text
accepted partition + document revision + edit deltas + durable citation index
= current citation overlay
```

Within the UCF-managed universe, live tracking can be 5/5 because boundaries are
updated from explicit edit operations. No source markers are required for the
user-facing model.

For unmanaged external edits, UCF-RS reconciles from durable citation index
files and evidence-derived block hashes. It can recover exact unchanged
partitions and classify changed partitions without pretending to infer new
boundaries.

## 2. Non-Negotiables

UCF-RS MUST preserve:

- Universal adaptability across text, source code, documents, configuration,
  generated artifacts, and binary artifacts.
- Absolute traceability from upstream handle to accepted evidence partition.
- AI-human parity through the same server/API/citation overlay.
- No source-persisted citations by default.
- No parser authority.
- No contextual fingerprinting.
- No implicit acceptance from passive file watching.
- Append-only auditability.

UCF-RS MAY use adapters, document APIs, language servers, and parsers for
display, selection, or conversion. It MUST NOT use them as acceptance authority.

## 3. Authority Summary

UCF-RS separates four surfaces:

```text
source content      current document bytes/text
runtime overlay     visible citations and highlights
durable index       authoritative partition/citation state
export ledger       portable audit projection
```

Authority is held by the durable index plus append-only operation records. The
overlay is a presentation layer. Source content is the current evidence
projection. Export ledgers are deterministic snapshots for CI, audit, and
offline comparison.

The user sees citations. The implementation may internally use virtual track
blocks. Source files do not need marker edits.

## 4. Derived Invariants

### 4.1 Externalized Authority Invariant

Trace authority MUST live outside source files in a durable UCF-RS citation
index. If source files contain no markers and no citations, the index is not a
throwaway cache. It is authoritative state.

### 4.2 User-Facing Non-Intrusion Invariant

UCF-RS MUST NOT persist user-facing citations in source files by default. Any
embedded marker or citation export MUST be explicit and reversible.

### 4.3 Virtual Track Block Invariant

Track blocks are an intermediate representation:

```text
partition id
begin boundary
end boundary
accepted content hash
current content hash
citation projection
```

They MAY be materialized for debug, export, CLI, grep, or interoperability. They
MUST NOT be required as source-file edits for normal operation.

### 4.4 Citation Projection Invariant

Citations are resolved runtime views over accepted partitions. A citation MUST
be reproducible from:

- upstream handle
- partition id
- current resolved range
- accepted content hash
- current content hash
- UCF formatter version
- citation policy

Citations MUST NOT create evidence authority merely by being displayed.

### 4.5 UCF-Managed Edit Invariant

When a document is edited through a UCF-aware client, the client MUST send edit
deltas to UCF-RS. UCF-RS MUST transform live partition ranges by those deltas.
This operational state is explicit authority, not hidden context.

### 4.6 Durable Offline Index Invariant

A UCF-aware client MUST persist last known server state locally before or during
editing. If the server is unavailable, the client records operation logs and
reconciles them later.

### 4.7 Evidence-Derived Recovery Invariant

Offline recovery MAY use hashes of accepted partitions, declared virtual blocks,
and UCF-managed block segments. It MUST NOT use before/after surrounding text as
authority.

### 4.8 No Contextual Fingerprinting Invariant

UCF-RS MUST NOT store or use the following as validation authority:

- before-context hashes
- after-context hashes
- fuzzy anchors
- semantic embeddings
- AST node identity
- symbol names
- surrounding comments
- nearby handles
- Git diff context outside accepted evidence

Diagnostics may mention these sources if a tool computes them, but acceptance
and validation MUST NOT depend on them.

### 4.9 Handle Registry Invariant

Hashes require stable handles. UCF-RS MUST validate handles against a handle
registry or explicit task context. It MUST NOT silently invent upstream handles.

### 4.10 Single-Writer Epoch Invariant

For each project and document, UCF-RS MUST serialize authoritative mutations
through server epochs. Offline clients may queue operations, but reconciliation
must prove that queued operations apply to the expected base epoch or produce a
conflict.

### 4.11 Append-Only Audit Invariant

Accepted evidence changes, lifecycle changes, reconciliations, and citation
policy changes MUST append records. UCF-RS MUST NOT rewrite accepted history.

### 4.12 AI-Human Parity Invariant

Humans and agents MUST query the same UCF-RS APIs and receive the same
partition status, citation resolution, and required-action values. Editor UI,
chatbot UI, CLI, and reports are presentation forms over one authority model.

## 5. Architecture

```text
                       +--------------------------+
                       | Handle / requirement     |
                       | registry                 |
                       +------------+-------------+
                                    |
                                    v
+------------------+      +---------+----------+      +-------------------+
| UCF-aware editor | ---> | UCF-RS server      | ---> | Citation overlay  |
| or client        |      | authority runtime  |      | UI / chatbot / CI |
+--------+---------+      +---------+----------+      +-------------------+
         |                          |
         | local offline state      | append-only durable state
         v                          v
+--------+---------+      +---------+----------+
| local citation   |      | project citation   |
| index and ops    |      | index and ops      |
+------------------+      +--------------------+
```

UCF-RS components:

- `server`: accepts sessions, edit deltas, activation commands, acceptance
  commands, and citation queries.
- `client adapter`: integrates with editor, document system, filesystem, or
  chatbot context.
- `citation index`: durable authoritative state.
- `operation log`: append-only edit and lifecycle event stream.
- `formatter`: converts partitions to UCF citation strings or structured
  citation objects.
- `reconciler`: resolves local offline operations against server epochs.
- `exporter`: writes deterministic ledgers/reports for CI and audit.

## 6. Storage Layout

The implementation MAY use a database, but it MUST provide deterministic local
export files. A simple project-local reference layout is:

```text
.ucf-rs/
  project.json
  citation-index.jsonl
  operation-log.jsonl
  document-index.jsonl
  handle-cache.jsonl
  snapshots/
    <document-id>.json
docs/
  ucf-trace-ledger.jsonl
  ucf-trace-status.json
  ucf-trace-report.md
```

Authoritative local state:

- `.ucf-rs/citation-index.jsonl`
- `.ucf-rs/operation-log.jsonl`
- `.ucf-rs/document-index.jsonl`

Generated/exported state:

- `docs/ucf-trace-ledger.jsonl`
- `docs/ucf-trace-status.json`
- `docs/ucf-trace-report.md`

If UCF-RS uses a remote server database, the project-local files are still the
required portable audit and offline-recovery format.

## 7. Identity Model

### 7.1 Project Id

Each project has a stable `project_id`:

```text
project_id = H("ucf.project.v1", canonical project root identity)
```

The project id is used to prevent accidental cross-project index reuse.

### 7.2 Document Id

Each tracked file or document has a `document_id`:

```text
document_id = H("ucf.document.v1", project_id, normalized project-relative path, adapter kind)
```

For non-filesystem documents, the adapter supplies a stable external document
URI. The URI is normalized and included instead of a path.

### 7.3 Partition Id

Each evidence partition has:

```text
partition_id = handle_token "/" ordinal
```

Ordinals are stable and allocated under server lock.

### 7.4 Citation Id

Each visible UCF citation has:

```text
citation_id = H("ucf.citation.v1", project_id, partition_id, citation_policy_id)
```

The citation id identifies the display projection, not the evidence partition.

## 8. Hash Model

UCF-RS inherits Reqtrace v3 domain-separated length-framed hashes.

Hash string format:

```text
sha256:<64 lowercase hexadecimal characters>
```

Required hashes:

```text
document_revision_hash
accepted_content_hash
current_content_hash
block_hash
partition_hash
index_record_hash
operation_hash
server_epoch_hash
export_ledger_hash
```

### 8.1 Document Revision Hash

For text documents:

```text
document_revision_hash = H("ucf.document.text.v1", canonical_text_bytes)
```

For binary documents:

```text
document_revision_hash = H("ucf.document.bytes.v1", raw_bytes)
```

### 8.2 Block Hash

A block hash is evidence-derived:

```text
block_hash = H("ucf.block.v1", partition_id, canonical_block_bytes)
```

Allowed block bytes:

- accepted partition bytes
- UCF-declared virtual block bytes
- exact current bytes for a known partition range

Disallowed block bytes:

- before-context outside the partition
- after-context outside the partition
- arbitrary neighboring text used for anchoring

### 8.3 Partition Hash

```text
partition_hash = H("ucf.partition.v1", partition_id, accepted_content_hash)
```

The partition hash changes only when the accepted evidence bytes or partition id
changes.

### 8.4 Server Epoch Hash

Each committed authoritative mutation advances the server epoch:

```text
server_epoch_hash = H("ucf.epoch.v1", previous_epoch_hash, operation_hash)
```

Epochs serialize authority without needing an always-on filesystem watcher.

## 9. Citation Index Schema

Each line of `.ucf-rs/citation-index.jsonl` is an append-only citation index
record.

```json
{
  "schema_version": "ucf-rs.index.v1",
  "record_type": "citation_index_record",
  "index_record_hash": "sha256:<64 hex>",
  "previous_index_record_hash": null,
  "server_epoch": 12,
  "server_epoch_hash": "sha256:<64 hex>",
  "transition": "activate",
  "state": "active",
  "project_id": "sha256:<64 hex>",
  "document_id": "sha256:<64 hex>",
  "adapter": {
    "kind": "filesystem-text",
    "uri": "src/auth.ts"
  },
  "upstream_handle": "AUTH-LOGIN",
  "handle_token": "AUTH-LOGIN",
  "partition_id": "AUTH-LOGIN/001",
  "citation_id": "sha256:<64 hex>",
  "accepted_content_hash": "sha256:<64 hex>",
  "current_content_hash": "sha256:<64 hex>",
  "partition_hash": "sha256:<64 hex>",
  "document_revision_hash": "sha256:<64 hex>",
  "range": {
    "encoding": "utf-16",
    "start": 120,
    "end": 240,
    "start_line": 10,
    "end_line": 18
  },
  "blocks": [
    {
      "block_id": "AUTH-LOGIN/001#0",
      "block_hash": "sha256:<64 hex>",
      "start": 120,
      "end": 240
    }
  ],
  "citation": {
    "format": "ucf.v1",
    "label": "AUTH-LOGIN/001",
    "display": "[AUTH-LOGIN/001]",
    "target": "ucf://partition/AUTH-LOGIN/001"
  },
  "created_at": "2026-07-09T18:00:00Z",
  "tool": {
    "name": "ucf-rs",
    "version": "0.1.0"
  }
}
```

Required transitions:

```text
activate
edit-transform
accept
deactivate
reactivate
relocate
reconcile
citation-policy
metadata
```

Only `accept`, `activate`, and `reactivate` may change
`accepted_content_hash`. `edit-transform` changes current range and current
content hash but does not accept changed evidence.

## 10. Operation Log Schema

Each line of `.ucf-rs/operation-log.jsonl` records an explicit operation:

```json
{
  "schema_version": "ucf-rs.operation.v1",
  "operation_hash": "sha256:<64 hex>",
  "previous_operation_hash": "sha256:<64 hex>",
  "project_id": "sha256:<64 hex>",
  "document_id": "sha256:<64 hex>",
  "base_server_epoch_hash": "sha256:<64 hex>",
  "operation_type": "edit",
  "source": {
    "kind": "editor",
    "client_id": "vscode:user-machine",
    "session_id": "sha256:<64 hex>"
  },
  "document_before_hash": "sha256:<64 hex>",
  "document_after_hash": "sha256:<64 hex>",
  "edits": [
    {
      "range_encoding": "utf-16",
      "start": 120,
      "end": 120,
      "inserted_text_hash": "sha256:<64 hex>",
      "inserted_text_length": 14
    }
  ],
  "affected_partitions": ["AUTH-LOGIN/001"],
  "created_at": "2026-07-09T18:00:00Z"
}
```

The operation log MAY omit raw inserted text by default for privacy. It MUST
store enough length/range information to transform ranges and enough hashes to
verify the resulting document state.

If raw text is needed for offline replay, it MUST be stored only under an
explicit evidence-archive policy.

## 11. Document Index Schema

`.ucf-rs/document-index.jsonl` records known document revisions:

```json
{
  "schema_version": "ucf-rs.document.v1",
  "document_id": "sha256:<64 hex>",
  "project_id": "sha256:<64 hex>",
  "adapter": {
    "kind": "filesystem-text",
    "uri": "src/auth.ts"
  },
  "current_document_revision_hash": "sha256:<64 hex>",
  "last_server_epoch_hash": "sha256:<64 hex>",
  "line_ending_policy": "lf-normalized",
  "encoding": "utf-8",
  "updated_at": "2026-07-09T18:00:00Z"
}
```

This file is authoritative for document identity and last known revision, not
for accepted evidence content.

## 12. Runtime APIs

UCF-RS SHOULD expose HTTP, local socket, or stdio JSON-RPC APIs. The transport
is implementation-specific; request/response semantics are normative.

### 12.1 Session Open

```text
session.open(project_root, adapter_kind, document_uri, document_revision_hash)
```

Returns:

```json
{
  "session_id": "sha256:<64 hex>",
  "server_epoch_hash": "sha256:<64 hex>",
  "document_id": "sha256:<64 hex>",
  "active_partitions": []
}
```

### 12.2 Activate Partition

```text
partition.activate(handle, document_id, range, expected_content_hash)
```

Behavior:

1. Validate handle.
2. Allocate partition id if needed.
3. Read range content through adapter.
4. Compute accepted content hash.
5. Verify expected content hash when supplied.
6. Append index record.
7. Return citation overlay object.

### 12.3 Apply Edit Delta

```text
document.apply_edit(session_id, document_before_hash, edits, document_after_hash)
```

Behavior:

1. Verify session and base epoch.
2. Transform all affected partition ranges.
3. Recompute current content hash for affected partitions.
4. Append operation log record.
5. Append `edit-transform` index records for affected partitions.
6. Return updated overlays and statuses.

### 12.4 Accept Current Partition

```text
partition.accept(partition_id, previous_index_record_hash, current_content_hash)
```

Behavior:

1. Verify latest index record.
2. Verify current content hash.
3. Promote current content hash to accepted content hash.
4. Append `accept` index record.

### 12.5 Query Citations

```text
citation.resolve(document_id, range?)
```

Returns all citation overlays intersecting the document or range.

### 12.6 Query Status

```text
status.current(project_id, strictness)
```

Returns project-wide validation status.

### 12.7 Export Ledger

```text
export.ledger(project_id, format)
```

Writes deterministic JSONL and report outputs for CI/audit.

## 13. Range Transform Algorithm

For text documents, UCF-RS maintains partition ranges in an adapter-declared
coordinate system:

```text
utf-8-byte
utf-16
unicode-scalar
line-column
document-native
```

The adapter MUST declare the coordinate system. The server MUST not guess.

For each edit delta:

```text
replace [edit_start, edit_end) with inserted_length
delta = inserted_length - (edit_end - edit_start)
```

Partition transform rules:

```text
edit before partition       -> shift start and end by delta
edit after partition        -> no range change
edit inserts at start       -> policy: attach-left or attach-right
edit inserts at end         -> policy: attach-left or attach-right
edit inside partition       -> expand/contract partition and mark changed
edit overlaps boundary      -> transform known side and mark boundary_touched
edit deletes whole range    -> mark missing
```

Default boundary policy:

- Insertions at partition start attach outside unless the client explicitly
  marks the edit as inside.
- Insertions at partition end attach inside only when typed from within the
  partition selection.

The client should send enough editor intent to distinguish inside/outside
boundary edits. If it cannot, UCF-RS MUST choose the conservative status
`requires_review`.

## 14. Live Status Classification

Live partition statuses:

```text
valid
valid_moved
changed_unaccepted
boundary_touched
missing
ambiguous
requires_review
inactive
unmanaged_external_change
index_conflict
adapter_unavailable
```

Meaning:

- `valid`: current range bytes match accepted content hash.
- `changed_unaccepted`: range transformed cleanly, but current content hash
  differs from accepted content hash.
- `boundary_touched`: edit operation affected a boundary and requires user or
  policy confirmation.
- `missing`: live range was deleted or cannot be resolved.
- `unmanaged_external_change`: document revision changed without UCF operation
  records.
- `index_conflict`: local and server epochs diverged.

Actions:

```text
none
accept_current
revert_current
confirm_boundary
redeclare_partition
reconcile_index
deactivate
inspect_adapter
```

## 15. Offline Reconciliation

Offline reconciliation compares:

- local citation index
- local operation log
- server citation index
- current document revision
- accepted block hashes

### 15.1 Managed Offline Edit

A managed offline edit occurs when a UCF-aware client records operations while
the server is unavailable.

Reconciliation:

1. Verify local base server epoch is an ancestor of current server epoch.
2. If no server-side conflicting partition changes occurred, replay local ops.
3. Transform ranges.
4. Verify document after hash.
5. Append reconciliation records to server index.
6. Return updated overlays.

If server-side changes touched the same partition chain, status is
`index_conflict`.

### 15.2 Unmanaged External Edit

An unmanaged external edit occurs when the document changed without UCF
operation records.

Reconciliation:

1. Compare current document revision hash with last known revision hash.
2. If equal, no reconciliation is needed.
3. If different, search for exact accepted block hashes.
4. If one exact block match exists for a partition, recover range and mark
   `valid_moved` or `valid`.
5. If current last known range exists but content differs, mark
   `changed_unaccepted`.
6. If no exact block match and no valid range exists, mark `missing`.
7. If multiple exact block matches exist, mark `ambiguous`.

UCF-RS MUST NOT infer a changed replacement boundary from surrounding context.

### 15.3 Block Hash Reconciliation

Block hash reconciliation is allowed only over UCF-known blocks:

- active partition block
- inactive partition block
- previously accepted virtual block
- exact block explicitly declared by a manifest

It MUST NOT hash arbitrary neighboring text to relocate changed evidence.

## 16. UCF Citation Format

UCF-RS should support both structured and display citations.

Structured citation:

```json
{
  "format": "ucf.v1",
  "citation_id": "sha256:<64 hex>",
  "partition_id": "AUTH-LOGIN/001",
  "handle": "AUTH-LOGIN",
  "state": "active",
  "status": "changed_unaccepted",
  "display": "[AUTH-LOGIN/001]",
  "target": "ucf://partition/AUTH-LOGIN/001",
  "accepted_content_hash": "sha256:<64 hex>",
  "current_content_hash": "sha256:<64 hex>"
}
```

Display citation examples:

```text
[AUTH-LOGIN/001]
[AUTH-LOGIN/001 changed]
[AUTH-LOGIN/001 missing]
```

The display citation is not authority. It is a rendering of structured citation
state.

## 17. Virtual Track Block Projection

UCF-RS MUST be able to project managed partitions as virtual track blocks for
grep, export, and agent workflows.

Projection example:

```text
UCF_BLOCK_BEGIN AUTH-LOGIN/001 accepted=sha256:<64 hex> current=sha256:<64 hex>
<current evidence bytes rendered as text when text is available>
UCF_BLOCK_END AUTH-LOGIN/001
```

The virtual projection MAY be exposed as:

```text
ucf-rs export blocks --document src/auth.ts
ucf-rs grep AUTH-LOGIN
ucf-rs status --format json
```

Virtual blocks satisfy grep-native discovery within the UCF boundary without
adding markers to source files.

## 18. Brownfield Adoption

Brownfield adoption flow:

1. Import handle registry.
2. Discover candidate ranges using search, selection, manifests, parser hints,
   or agents.
3. Preflight candidates through UCF-RS.
4. Activate accepted candidates into the citation index.
5. Render overlays and UCF citations.
6. Export ledger/report for audit.

Manifest candidate:

```json
{
  "handle": "AUTH-LOGIN",
  "document_uri": "src/auth.ts",
  "adapter_kind": "filesystem-text",
  "range": {
    "encoding": "utf-16",
    "start": 120,
    "end": 240
  },
  "expected_content_hash": "sha256:<64 hex>"
}
```

Preflight MUST report:

- handle validity
- range validity
- expected content hash match
- proposed partition id
- citation preview
- collision/conflict status
- adapter support

## 19. Agentic Workflow

Agents use UCF-RS through structured APIs.

Allowed agent actions:

- query current citations
- query changed partitions
- run preflight
- propose activations
- activate with explicit instruction
- accept with explicit previous-record guard
- export reports
- reconcile managed offline operations

Disallowed agent actions:

- invent handles
- accept changed evidence from fuzzy match
- infer replacement boundaries after unmanaged external edits
- rewrite source to add citations unless explicitly requested
- edit authoritative index records directly

Agent status object:

```json
{
  "partition_id": "AUTH-LOGIN/001",
  "handle": "AUTH-LOGIN",
  "status": "changed_unaccepted",
  "action": "accept_current",
  "previous_index_record_hash": "sha256:<64 hex>",
  "accepted_content_hash": "sha256:<64 hex>",
  "current_content_hash": "sha256:<64 hex>",
  "document_uri": "src/auth.ts",
  "range": {
    "encoding": "utf-16",
    "start": 120,
    "end": 260
  }
}
```

## 20. CLI Reference

Reference commands:

```text
ucf-rs init
ucf-rs serve
ucf-rs session open --document src/auth.ts
ucf-rs preflight --handle AUTH-LOGIN --document src/auth.ts --range 120:240
ucf-rs activate --handle AUTH-LOGIN --document src/auth.ts --range 120:240
ucf-rs status --format json
ucf-rs citations --document src/auth.ts --format json
ucf-rs accept --partition-id AUTH-LOGIN/001 --previous-index-record-hash sha256:...
ucf-rs reconcile
ucf-rs export ledger
ucf-rs export blocks --document src/auth.ts
ucf-rs render
```

`serve` starts the runtime server. Other commands may run in embedded server
mode if no long-lived server is active.

## 21. CI and Audit

CI SHOULD use exported state, not an editor overlay:

```text
ucf-rs export ledger
ucf-rs status --strict --format json
```

Strict CI fails on:

- invalid index record hash
- invalid operation hash
- unknown handle
- changed unaccepted active partition
- missing active partition
- ambiguous recovery
- index conflict
- orphan local operation
- stale export ledger

The exported ledger MUST be deterministic and portable. A reviewer should be
able to verify it without running the editor integration.

## 22. Security and Privacy

By default UCF-RS stores hashes, ranges, operations, and citation metadata, not
raw historical evidence bodies.

Privacy implications:

- Hashes are not secrecy boundaries.
- Short sensitive strings may be guessable.
- Operation logs can reveal edit locations and lengths.
- Citation overlays may expose requirement handles.

Optional evidence archive mode MAY store raw evidence bodies for stronger
offline replay. It MUST be explicit and configurable because it stores source
content.

## 23. Failure Modes

Required failure classifications:

```text
server_unavailable
local_index_stale
server_epoch_conflict
operation_log_gap
document_hash_mismatch
adapter_coordinate_mismatch
managed_offline_replay_failed
unmanaged_external_change
accepted_block_missing
accepted_block_ambiguous
changed_unaccepted
boundary_touched
handle_unknown
index_hash_invalid
export_stale
```

Each failure MUST include a machine-readable action.

Example:

```json
{
  "status": "unmanaged_external_change",
  "action": "reconcile_or_redeclare",
  "diagnostics": [
    {
      "code": "E_DOCUMENT_HASH_MISMATCH",
      "severity": "error",
      "message": "Document changed without matching UCF operation records."
    }
  ]
}
```

## 24. Implementation Phases

### Phase 1: Local Filesystem Prototype

Scope:

- filesystem text adapter
- local server process
- JSONL citation index
- operation log
- activate/query/status/export
- virtual block export

This phase proves the authority model without editor integration.

### Phase 2: Editor-Aware Live Tracking

Scope:

- editor extension or language-client adapter
- session open/close
- edit delta capture
- live citation overlay
- changed partition highlights
- accept/revert commands

This phase proves 5/5 live tracking within managed editing.

### Phase 3: Offline Client Cache

Scope:

- local index persistence
- offline operation queue
- server epoch reconciliation
- conflict detection
- unmanaged external edit classification

This phase proves recovery when the server is not active.

### Phase 4: Brownfield and Agentic Workflows

Scope:

- manifest preflight
- batch activation
- chatbot/API integration
- CI export
- registry bidirectional views

This phase proves AI-human parity.

## 25. Comparison to Block-Primary v3

| Category | Block-primary v3 | UCF-RS |
| --- | ---: | ---: |
| Source non-intrusion | 3/5 | 5/5 |
| Live edit robustness | 5/5 | 5/5 managed |
| Offline exact recovery | 4/5 | 5/5 managed, 4/5 unmanaged |
| Universal adaptability | 5/5 | 5/5 |
| Human/AI parity | 4/5 | 5/5 |
| Brownfield adoption | 4/5 | 5/5 |
| Grep-native discovery | 5/5 source grep | 5/5 virtual/export grep |
| CI auditability | 5/5 | 5/5 with deterministic export |
| Implementation simplicity | 4/5 | 2-3/5 |

UCF-RS is superior as the user-facing architecture if the project accepts a
runtime server and durable external index. Block-primary v3 remains simpler and
stronger as a no-server fallback.

## 26. Conformance Tests

Required tests:

- index record hash verification
- operation hash verification
- server epoch chaining
- handle registry rejection
- activation from explicit range
- citation overlay resolution
- virtual track block export
- live edit before partition
- live edit inside partition
- live edit touching boundary
- deletion of partition range
- accept current changed partition
- managed offline operation replay
- server epoch conflict
- unmanaged external exact block recovery
- unmanaged external changed partition classification
- duplicate exact block ambiguity
- no before/after context use
- deterministic export ledger
- stale export detection
- chatbot/editor/CLI parity for status JSON

An implementation MUST NOT claim UCF-RS compatibility unless these conformance
tests pass.

## 27. Open Decisions

These decisions should be finalized before implementation:

- canonical UCF display syntax
- default range coordinate system for text adapters
- whether local JSONL files or embedded SQLite is the reference store
- exact privacy mode for operation logs
- evidence archive opt-in shape
- registry import format
- remote server authentication model
- policy for boundary insertions at range start/end

None of these decisions change the authority model.

## 28. Recommendation

UCF-RS should become the primary v3 user-facing architecture:

```text
UCF-RS overlay + durable citation index + operation log + deterministic export
```

Block markers should remain available as:

- virtual projection
- export/debug format
- no-server fallback
- recovery/interchange artifact

This preserves Reqtrace's universality and absolute traceability while removing
source intrusiveness from the normal user experience. The only non-5/5 case is
unmanaged external mutation of changed evidence, and the proposed behavior is
correct: recover exact unchanged blocks, classify changed partitions, and
require explicit redeclaration or acceptance.
