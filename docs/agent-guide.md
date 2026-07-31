# UCF-RS Agent Guide

This guide is for AI agents and automated callers that use UCF-RS **as a
tool** — to create, check, or maintain citations while working in a codebase.

This is different from [`AGENTS.md`](../AGENTS.md) at the repository root,
which is contributor guidance for coding agents modifying UCF-RS's *own*
source code. If you're editing UCF-RS itself, read that file. If you're an
agent citing evidence *in a project that uses* UCF-RS, this is your guide.

## The contract, in one paragraph

UCF-RS authority is append-only and explicit. You may activate a range as a
citation, but you must never assume text similarity, symbol names, or AST
position means a citation still holds — only an explicit `resolve` /
`status` check tells you that. You must never accept `changed_unaccepted`,
`missing`, or `ambiguous` evidence on the caller's behalf; surface it and let
a human or an explicit accept/reconcile command resolve it.

## Rules

- **Do not infer evidence.** Don't add citations based on surrounding
  context, symbol names, AST identity, or fuzzy matches. Every citation
  comes from an explicit `activate` (or `preflight` first, if you want to
  validate before committing).
- **Do not silently persist markers into source.** UCF-RS's entire value is
  that source stays clean — never write your own comment-based citation
  markers into files as a workaround.
- **Prefer managed edits.** If you're editing a file that has active
  citations, use `apply-edit` (or the `document.apply_edit` / offline-queue
  server methods) instead of writing the file directly, so cited ranges
  transform correctly instead of silently going stale.
- **Never treat changed evidence as valid.** `changed_unaccepted` means the
  text moved since acceptance. Don't re-activate over it or ignore it —
  either call `accept` after confirming the new text is correct, or leave it
  for the human/workflow that owns acceptance decisions.
- **Never guess merges offline.** If `replay-offline` returns a conflict
  because authoritative state advanced, don't retry blindly — re-read
  `status` and decide a fresh course of action.
- **Treat `E_RECOVERY_RETRY_REQUIRED` as a stop sign, not an error to
  suppress.** If a mutating command returns
  `ucf-rs.recovery_required.v1`, a prior interrupted transaction was just
  completed as a side effect and your requested mutation did **not** run.
  Re-inspect current state (`status`, `transaction inspect`) and reissue the
  command with fresh preconditions — don't loop the same call blindly.
- **Never delete or hand-edit `.ucf-rs/` files.** Use `recover` and
  `transaction inspect` / `transaction abandon` for anything resembling a
  stuck or divergent state.
- **Treat exports as non-authoritative.** `export ledger`, `export blocks`,
  and `render` output are regenerable projections. Don't reason about
  current truth from a stale export — re-run `status` (with `--strict` if
  you need to detect ledger staleness) first.
- **Default to redacted output.** Don't request or forward evidence text
  (`export blocks`, `virtual-blocks`) unless the task explicitly requires
  content, not just status/hashes/ranges.

## Recommended interaction pattern

1. **Preflight before activating**, if the caller can tolerate the extra
   round trip — it validates without mutating authority, so you can catch a
   bad range before it's recorded.
2. **Activate** with an explicit, stable handle.
3. **Check `status --format json`** (or `resolve` for a specific document)
   before treating anything as currently valid. Parse the JSON; don't rely
   on prior state.
4. **On `changed_unaccepted` / `missing` / `ambiguous`**, stop and report
   rather than resolving it yourself unless you were explicitly instructed
   how to handle that class of conflict.
5. **Accept explicitly** only when you have a clear basis to do so (e.g. a
   human confirmed the new text, or the task explicitly authorizes it).
6. **Export/render only when asked**, and prefer metadata-level exports
   (`export ledger`) over content-bearing ones (`export blocks`) by default.

## Programmatic access

For scripted or headless use, `serve` accepts JSONL over stdin/stdout, or
local HTTP:

```bash
python scripts/ucf_rs.py serve
```

Request shape (simple or JSON-RPC-compatible):

```json
{"method": "status.current", "params": {}}
```

```json
{"jsonrpc": "2.0", "id": "1", "method": "partition.activate", "params": {"handle": "AUTH-ROTATE", "path": "src/auth.py", "lines": "1:4"}}
```

Available methods:

| Method | Purpose |
| --- | --- |
| `status.current` | Current authority/projection report |
| `citation.resolve` | Overlays for a document path |
| `session.open` | Session id, document revision hash, server epoch |
| `partition.preflight` | Validate an activation without mutating authority |
| `partition.activate` | Append activation records |
| `document.apply_edit` | Apply a managed edit delta, transform/refresh ranges |
| `document.queue_offline_edit` | Queue and apply a local disconnected edit |
| `offline.replay` | Replay queued offline edits through authority |
| `partition.accept` | Accept the latest managed partition content |
| `export.ledger` | Write the deterministic ledger projection |

If you're calling this over HTTP rather than stdio, remember the transport
has **no authentication and no TLS** and defaults to loopback-only. Don't
bind or advise binding to a non-loopback host unless the human operator has
explicitly opted into `--unsafe-remote` and understands the exposure.

## Minimal example session

```bash
python scripts/ucf_rs.py init
python scripts/ucf_rs.py preflight --handle AUTH-ROTATE --path src/auth.py --lines 1:4
python scripts/ucf_rs.py activate --handle AUTH-ROTATE --path src/auth.py --lines 1:4
python scripts/ucf_rs.py status --format json
# ... later, after the file changes ...
python scripts/ucf_rs.py resolve --path src/auth.py
# if changed_unaccepted and confirmed correct:
python scripts/ucf_rs.py accept --partition-id AUTH-ROTATE/001
python scripts/ucf_rs.py export ledger
```

## See also

- [User Guide](user-guide.md) — the same workflow from a human operator's
  point of view
- [`docs/commands.md`](commands.md) — full command and server reference
- [`docs/data-policy.md`](data-policy.md) — exactly what is and isn't
  disclosed by default
- [`AGENTS.md`](../AGENTS.md) — guidance for agents contributing to UCF-RS's
  own codebase (not the same audience as this guide)
