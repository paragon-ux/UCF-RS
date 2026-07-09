# Commands

Core commands:

- `init`: create `.ucf-rs/` files and import Reqtrace handles when present.
- `preflight`: validate an activation without mutation.
- `activate`: accept an explicit text range without editing source.
- `apply-edit`: apply a managed text edit and transform affected ranges.
- `queue-offline-edit`: record and apply a local offline edit without mutating authority.
- `replay-offline`: replay queued offline edits through the operation log and citation index.
- `accept`: promote current managed evidence to accepted evidence.
- `reconcile`: append relocation records for exact moved evidence.
- `deactivate` / `reactivate`: append lifecycle records.
- `resolve` / `citations`: emit overlays for a document.
- `status`: validate authority records and current projection.
- `export ledger` / `export blocks`: write deterministic audit projections.
- `render`: write generated status JSON and Markdown report.
- `discover-reqtrace`: list advisory brownfield `@reqtrace` markers.
- `serve`: process JSONL requests over stdin/stdout or local HTTP.

`serve` accepts either simple request objects (`{"method": "...", "params": {...}}`)
or JSON-RPC-compatible objects (`{"jsonrpc": "2.0", "id": "...", "method": "...", "params": {...}}`).
Simple responses use `ok`/`result`; JSON-RPC-compatible responses echo `jsonrpc`,
`id`, and `result` or `error`.

Server request methods:

- `status.current`: return the current authority/projection report.
- `citation.resolve`: return overlays for a document path.
- `session.open`: return a session id, document revision hash, and server epoch.
- `partition.preflight`: validate a partition activation without mutating authority.
- `partition.activate`: append activation operation and citation-index records.
- `document.apply_edit`: apply a managed edit delta and transform affected ranges.
- `document.queue_offline_edit`: queue and apply a local disconnected edit.
- `offline.replay`: replay queued offline edits through authoritative operation records.
- `partition.accept`: accept the latest managed partition content.
- `export.ledger`: write the deterministic ledger projection.

Offline replay stores the post-edit document text in `.ucf-rs/offline-queue.jsonl`
so UCF-RS can replay the disconnected operation deterministically. Successful
replay appends the queue content to `.ucf-rs/offline-replayed.jsonl` and clears
the pending queue.
