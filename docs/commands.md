# Commands

Core commands:

- `init`: create `.ucf-rs/` files and import Reqtrace handles when present.
- `preflight`: validate an activation without mutation.
- `activate`: accept an explicit text range without editing source.
- `apply-edit`: apply a managed text edit and transform or refresh active ranges.
- `queue-offline-edit`: record and apply a local offline edit without mutating authority.
- `replay-offline`: replay queued offline edits through the operation log and citation index.
- `accept`: promote current managed evidence to accepted evidence.
- `reconcile`: append relocation records for exact moved evidence.
- `deactivate` / `reactivate`: append lifecycle records.
- `resolve` / `citations`: emit overlays for a document.
- `status`: validate authority records and current projection.
- `recover`: complete pending recoverable transactions and emit structured recovery output.
- `transaction inspect`: inspect pending transaction phase, file hashes, and supported resolution actions.
- `transaction abandon`: archive an unapplied divergent transaction after explicit operator inspection.
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
- `document.apply_edit`: apply a managed edit delta and transform or refresh active ranges.
- `document.queue_offline_edit`: queue and apply a local disconnected edit.
- `offline.replay`: replay queued offline edits through authoritative operation records.
- `partition.accept`: accept the latest managed partition content.
- `export.ledger`: write the deterministic ledger projection.

HTTP transport defaults to `127.0.0.1`, enforces a maximum request body size, and
rejects invalid `Content-Length` values. Binding to a non-loopback host requires
`--unsafe-remote` and prints a warning. The HTTP transport has no authentication
and no TLS; it is intended for trusted local use only.

Offline replay stores the post-edit document text in `.ucf-rs/offline-queue.jsonl`
so UCF-RS can replay the disconnected operation deterministically. Successful
replay appends the queue content to `.ucf-rs/offline-replayed.jsonl` and clears
the pending queue.

`apply-edit`, `queue-offline-edit`, and `replay-offline` use recoverable file
transactions for source-plus-authority consistency. Mutating commands first
complete any recoverable pending transaction under the authority lock. If that
implicit recovery completes work, the requested mutation stops before execution
and JSON mode returns `ucf-rs.recovery_required.v1` with
`E_RECOVERY_RETRY_REQUIRED`. The caller must inspect current state and issue a
new command with fresh preconditions. The same structured result is returned
through `serve` for mutating request methods.

After a transaction reaches `committed`, but before the caller observes the
command response, the command outcome is intentionally uncertain. Callers must
inspect current state, status, and operation/index records instead of blindly
replaying a non-idempotent command.

If recovery fails because a target file matches neither the expected nor the
intended transaction hash, `transaction inspect --format json` reports each
file's current hash and status. `transaction abandon --transaction-id ID
--reason TEXT` is only allowed while no target contains intended transaction
bytes; it archives the resolution outside the hot recovery path and leaves
source/status to report the current filesystem state. If any intended bytes are
present, use `recover` rather than abandon.

Fault-injection environment variables are ignored unless
`UCF_RS_ENABLE_FAULT_INJECTION=1` is also set. They are test/debug hooks only.
