# Reqtrace v3 Direction Review

This review compares the three local v3 directions and records the demo choice.

## 1. Unoptimized Track-Block Runtime

Source: archived Reqtrace v3 `unoptimized-track-v3` direction.

This direction moves Reqtrace from single-line occurrence markers to
source-visible track blocks and an append-only requirements ledger. It is a good
conceptual bridge from v2 because evidence remains grep-visible and parser
independent.

The readiness ledger identifies implementation blockers: canonical
serialization, hash encoding, handle grammar, transactions, path
canonicalization, selector semantics, scan stability, and generated-state
freshness are not fully specified. The runtime watcher also adds moving parts
without changing the core authority model; cold scans and explicit commands are
still the real acceptance boundary.

Verdict: useful ancestor, but not the best demo target.

## 2. UCF-RS Overlay Runtime

Source: `docs/source-proposals/ucf-rs-v3/`.

This direction has the best overall architecture. Source files stay clean,
citations are rendered as overlays, and a durable citation index plus operation
log becomes authority. For managed editor sessions, explicit edit deltas can
preserve live ranges without hidden contextual fingerprints.

The cost is implementation complexity. A server/runtime boundary,
editor/client adapters, epochs, offline operation logs, reconciliation, and
durable local indexes are required before the strongest claim becomes true.
That cost is acceptable when the selection criterion is optimal architecture
rather than smallest possible demo.

Verdict: best overall v3 user-facing architecture and the corrected demo target.

## 3. Optimized Block/Snapshot/Artifact Standard

Source: archived Reqtrace v3 `block-snapshot-v3` direction.

This direction is the most promising near-term path. It keeps the authority
model local and audit-friendly while acknowledging the real tradeoff: no single
mode can provide zero source mutation, robust arbitrary edit tracking, exact
boundaries, parser independence, and no hidden context at the same time.

Its three-mode split is the practical improvement:

- `block`: source-visible partition boundaries for mutable text.
- `snapshot`: non-invasive exact text evidence with line-hash recovery.
- `artifact`: whole-file byte evidence for binary or generated artifacts.

The standard also closes the major readiness gaps from the earlier draft:
domain-separated hashes, canonical JSON, path scoping, status/action values,
strict mode, generated outputs, transaction rules, and conformance fixture
expectations are specified.

Verdict: best no-server fallback and useful comparison implementation, but not
the optimal overall architecture.

## Demo

The corrected architecture demo is the standalone UCF-RS implementation in
`scripts/ucf_rs.py`. It is intentionally separate from the Reqtrace v2 CLI and
writes authoritative state under `.ucf-rs/`:

```text
.ucf-rs/citation-index.jsonl
.ucf-rs/operation-log.jsonl
.ucf-rs/document-index.jsonl
.ucf-rs/offline-queue.jsonl
.ucf-rs/offline-replayed.jsonl
```

Example commands:

```bash
python scripts/ucf_rs.py init
python scripts/ucf_rs.py activate --handle AUTH-ROTATE --path examples/managed-edit/src/auth.py --lines 1:4
python scripts/ucf_rs.py apply-edit --path examples/managed-edit/src/auth.py --start 0 --end 0 --insert "managed\n"
python scripts/ucf_rs.py accept --partition-id AUTH-ROTATE/001
python scripts/ucf_rs.py resolve --path examples/managed-edit/src/auth.py
python scripts/ucf_rs.py export ledger
python scripts/ucf_rs.py status --format json --strict
```

Implemented UCF-RS scope:

- source-clean activation: citations are not inserted into source files
- durable append-only citation index records with `index_record_hash`
- append-only operation records with `operation_hash`
- server epoch chaining over authoritative citation mutations
- filesystem text adapter using declared `unicode-scalar` ranges
- managed edit transforms that shift ranges or mark changed evidence
- explicit `accept`, `deactivate`, `reactivate`, and `reconcile` boundaries
- exact unmanaged move recovery from accepted line hashes
- offline edit queue with base-epoch checked replay
- runtime overlay resolution through CLI, stdio server, and local HTTP server
- mutating server API parity for preflight, activate, edit, queue, replay, accept, and export
- deterministic audit export, stale export detection, generated status/report rendering, and virtual block rendering
- Reqtrace v2 brownfield handle-cache import and advisory `@reqtrace` discovery

Out-of-repo integration boundaries:

- no bundled editor extension UI
- no remote authentication, multi-client lock manager, or hosted service
- no binary artifact adapter beyond deterministic text/file projections
