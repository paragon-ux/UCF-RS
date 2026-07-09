# UCF-RS Architecture

UCF-RS separates four surfaces:

- Source content is the current projection.
- Runtime overlays show citations and statuses.
- `.ucf-rs/citation-index.jsonl` and `.ucf-rs/operation-log.jsonl` are authority.
- Exported ledgers and reports are deterministic audit projections.

The central invariant is:

```text
accepted partition + document revision + explicit edit deltas + durable index = current citation overlay
```

No source-persisted citation is required by default. Managed clients send edit
deltas to UCF-RS; UCF-RS transforms ranges and appends records. Unmanaged
external edits are classified conservatively. Exact accepted evidence can be
recovered from accepted line hashes, but changed boundaries are not inferred.

Local disconnected clients can queue edits in `.ucf-rs/offline-queue.jsonl`.
Replay is epoch-checked: if authoritative state advanced while the client was
offline, replay fails with a conflict instead of guessing a merge. The queue is
local replay material, not accepted evidence; successful replay appends normal
operation and citation-index records.

Generated exports remain non-authoritative. `status --strict` reports stale
exported ledgers when `docs/ucf-trace-ledger.jsonl` no longer matches current
authority plus filesystem projection.
