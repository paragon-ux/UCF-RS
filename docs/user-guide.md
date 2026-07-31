# UCF-RS User Guide

This guide is for people using UCF-RS on a real project: developers,
tech leads, or documentation owners who want durable, auditable citations
without editing source files to hold them.

If you're an AI agent or writing automation that calls UCF-RS, read the
[Agent Guide](agent-guide.md) instead — it covers the same ground with a
focus on rules for unattended callers.

## The mental model

UCF-RS keeps four things separate:

| Thing | What it is |
| --- | --- |
| **Source files** | Your normal project files. UCF-RS never inserts citation markers into them. |
| **Runtime overlays** | What `status` / `resolve` show you: citation state layered on top of current source. |
| **Authority** (`.ucf-rs/`) | The append-only citation index and operation log. This is the only durable truth. |
| **Generated exports** | Ledgers and reports (`export`, `render`). Deterministic, regenerable, never authoritative on their own. |

The invariant to keep in mind:

```text
accepted partition + document revision + explicit edit deltas + durable index = current citation overlay
```

Nothing is inferred from symbol names, AST structure, or fuzzy text matching.
Every citation traces back to an explicit command you (or your tooling)
issued.

## Installing and running

UCF-RS is a standalone Python script using only the standard library —
there's nothing to `pip install`. Python 3.10+ is required.

```bash
python scripts/ucf_rs.py --help
```

Every command accepts `--root` (project root, defaults to the current
directory) and `--store` (authority location, defaults to `.ucf-rs`).

## Core workflow

### 1. Initialize

```bash
python scripts/ucf_rs.py init
```

Creates `.ucf-rs/` in your project root. If a Reqtrace-style
`docs/handle-registry.jsonl` already exists, `init` will pick up its handles
so you're not starting from zero.

### 2. Activate a citation

```bash
python scripts/ucf_rs.py activate --handle AUTH-ROTATE --path src/auth.py --lines 1:4
```

This accepts an explicit line range under a stable handle. It does not
modify `src/auth.py`. Use `preflight` first if you want to validate an
activation without writing anything:

```bash
python scripts/ucf_rs.py preflight --handle AUTH-ROTATE --path src/auth.py --lines 1:4
```

### 3. Check status

```bash
python scripts/ucf_rs.py status --format json
```

Shows every citation's current lifecycle state. Add `--strict` in CI or
before a release to also catch stale exported ledgers (an `export ledger`
output that no longer matches current authority).

### 4. Resolve against current source

```bash
python scripts/ucf_rs.py resolve --path src/auth.py
```

(`citations` is an alias for `resolve`.) This re-checks cited ranges against
the file as it exists right now and reports each one's status.

### Citation lifecycle states

- **active / valid** — the cited range still matches what was recorded.
- **changed_unaccepted** — the underlying text changed since activation or
  last acceptance. UCF-RS will not treat this as valid evidence until you
  explicitly resolve it.
- **inactive** — deactivated via `deactivate`.
- **missing / ambiguous** — the target can't be found, or more than one
  candidate location fits. Neither is auto-accepted.

### 5. Accept, deactivate, reactivate

```bash
python scripts/ucf_rs.py accept --partition-id AUTH-ROTATE/001
python scripts/ucf_rs.py deactivate --partition-id AUTH-ROTATE/001
python scripts/ucf_rs.py reactivate --partition-id AUTH-ROTATE/001 --path src/auth.py --lines 1:6
```

`accept` promotes the current managed content to accepted evidence. Nothing
is ever silently accepted on your behalf — a changed citation stays
`changed_unaccepted` until you run this.

### Managed edits

If your editing workflow goes through UCF-RS (rather than an external tool
touching the file directly), use `apply-edit` so cited ranges shift correctly
as text is inserted or removed:

```bash
python scripts/ucf_rs.py apply-edit --path src/auth.py --start 0 --end 0 --insert "# rotated\n"
```

If a file was edited outside UCF-RS and evidence moved but is otherwise
unchanged, `reconcile` can recover exact moves from accepted line hashes:

```bash
python scripts/ucf_rs.py reconcile --path src/auth.py
```

It will not guess at a match — only exact recovered moves are reconciled
automatically.

### Working offline

```bash
python scripts/ucf_rs.py queue-offline-edit --path src/auth.py --start 0 --end 0 --insert "# note\n"
python scripts/ucf_rs.py replay-offline
```

Offline edits are staged locally and replayed later. Replay is
epoch-checked: if authoritative state moved on while you were offline, replay
fails with a conflict rather than guessing at a merge.

### Exporting and reporting

```bash
python scripts/ucf_rs.py export ledger   # deterministic JSONL audit ledger
python scripts/ucf_rs.py export blocks --path src/auth.py  # virtual block export (includes content)
python scripts/ucf_rs.py render           # generated status JSON + Markdown report
```

Exports are always regenerable from `.ucf-rs/` — delete and re-run `export`
or `render` any time. `export blocks` and `virtual-blocks` are the only
commands that render evidence text by default; everything else sticks to
paths, ranges, hashes, and statuses. See
[`docs/data-policy.md`](data-policy.md) for the full disclosure rules.

## If something is interrupted mid-write

UCF-RS uses recoverable file transactions for any command that touches both
source and authority (`apply-edit`, `queue-offline-edit`, `replay-offline`).
If a previous command was interrupted:

```bash
python scripts/ucf_rs.py status
```

will usually prompt you toward recovery. You can also inspect directly:

```bash
python scripts/ucf_rs.py transaction inspect --format json
python scripts/ucf_rs.py recover
```

`recover` is only offered when nothing has diverged. If a target file's
current bytes match neither the expected nor intended state, `transaction
inspect` will tell you exactly what diverged and what actions are available,
including `transaction abandon --transaction-id ID --reason TEXT` (and its
`--accept-current-partial-state` variant for mixed partial states). You won't
be asked to delete files under `.ucf-rs/` by hand.

## Adopting UCF-RS alongside Reqtrace

If your project already uses Reqtrace's `@reqtrace` markers or a
`docs/handle-registry.jsonl`, `init` imports the handle registry, and:

```bash
python scripts/ucf_rs.py discover-reqtrace
```

lists existing `@reqtrace` markers as advisory candidates — nothing is
activated automatically. See
[`docs/reqtrace-relationship.md`](reqtrace-relationship.md) for how the two
tools relate.

## Serving citations to other tools

```bash
python scripts/ucf_rs.py serve
```

Reads JSONL requests from stdin and writes JSONL responses to stdout — this
is what powers editor integrations and agent tooling. For local HTTP
instead, see [`docs/commands.md`](commands.md).

**Security note:** the HTTP transport binds to `127.0.0.1` by default, has a
bounded request size, but has no authentication and no TLS. Binding to a
non-loopback address requires an explicit `--unsafe-remote` flag and prints a
warning — treat this as trusted-local-network-only, never as an
internet-facing service. Full details in
[`docs/data-policy.md`](data-policy.md).

## Backups and deletion

UCF-RS doesn't manage backups itself — your normal filesystem, editor, or
repository backup tooling covers `.ucf-rs/`. To remove UCF-RS from a project:
delete generated exports to drop rebuildable projections, or delete
`.ucf-rs/` entirely to remove the authority store (existing citations become
unverifiable unless you restore from a backup).

## Where to go next

- [`docs/architecture.md`](architecture.md) — the four-surface model in full
- [`docs/commands.md`](commands.md) — complete command and server reference
- [`docs/storage-schemas.md`](storage-schemas.md) — file formats
- [`docs/data-policy.md`](data-policy.md) — retention, visibility, export rules
