# UCF-RS

**Source-clean citation tracking for codebases.**

UCF-RS lets you attach durable, auditable citations — "this code satisfies
requirement X" — to any file and line range, without writing markers into
your source. Citations live in a local, append-only authority store next to
your project; your files stay exactly as they are.

It's a local runtime, not a hosted service: everything runs on your machine,
in plain files, with no server to operate and no account to create.

## Why

Traceability tools usually force a choice: mark up your source with comments
the parser can find, or accept an ungoverned spreadsheet that drifts from
reality. UCF-RS instead treats citations as **overlays**:

- Your source files are never edited to hold citation markers.
- An append-only local log (`.ucf-rs/`) is the single source of truth for
  what's cited, what changed, and what's been explicitly accepted.
- Generated reports and ledgers are always regenerable projections of that
  log — never the authority themselves.
- Evidence that changes underneath a citation is flagged, not silently kept
  or silently dropped. You (or an agent) explicitly accept, reject, or
  reconcile it.

If you already use [Reqtrace](https://github.com/paragon-ux/reqtrace)'s
grep-native `v2.1.7` marker convention, UCF-RS is a compatible alternative for
projects that want overlay citations and managed-edit tracking instead of
in-source markers — see [`docs/reqtrace-relationship.md`](docs/reqtrace-relationship.md).

## Quickstart

Requires Python 3.10+ (standard library only — nothing to install).

```bash
# From your project root
python scripts/ucf_rs.py init

# Cite lines 1-4 of a file under a stable handle.
# --task-context registers the handle on the fly; omit it once the handle
# is already tracked in docs/handle-registry.jsonl (see "Handles and
# partitions" in the User Guide).
python scripts/ucf_rs.py activate --handle AUTH-ROTATE --path src/auth.py --lines 1:4 --task-context

# See current citation status
python scripts/ucf_rs.py status --format json

# Re-check citations against the current file contents
python scripts/ucf_rs.py resolve --path src/auth.py

# Write a deterministic, shareable audit ledger
python scripts/ucf_rs.py export ledger

# Generate a human-readable status report
python scripts/ucf_rs.py render
```

A runnable end-to-end example — pre-registered handle, no `--task-context`
needed — lives in [`examples/managed-edit/`](examples/managed-edit/); run its
three commands from inside that directory.

## Who this is for

- **Humans** deciding to adopt it, or running it day to day →
  read the [User Guide](docs/user-guide.md).
- **AI agents and automation** that create or maintain citations as part of
  editing a codebase → read the [Agent Guide](docs/agent-guide.md).

## What's implemented

- A local `.ucf-rs/` authority store: project config, handle cache, document
  index, operation log, and citation index.
- Source-clean activation from explicit file/line ranges — no markers, no
  parsing of code to infer evidence.
- Managed edits that transform cited ranges as text shifts, instead of
  silently losing them.
- Explicit lifecycle: `accept`, `deactivate`, `reactivate`, `reconcile`
  (for exact moved-evidence recovery).
- Offline queues with epoch-checked replay for disconnected work.
- Recoverable file transactions, so an interrupted write never leaves source
  and authority out of sync.
- Citation resolution and a local server over stdio JSONL or loopback HTTP.
- Deterministic ledger/report export and brownfield compatibility with
  existing Reqtrace `handle-registry.jsonl` files.

See [`docs/commands.md`](docs/commands.md) for the full command and server
method reference.

## Status and scope

This is a **local, trusted-client MVP**. It does not include a GUI, remote
authentication, TLS, or an encryption-at-rest guarantee — see
[`docs/data-policy.md`](docs/data-policy.md) and
[`docs/architecture.md`](docs/architecture.md) for the exact boundaries.
UCF-RS is a separate project from **UCF-YJS**, which explores the same
citation model over real-time collaborative (Yjs) documents; UCF-YJS may use
UCF-RS as a conformance reference but does not depend on its internals.

## Documentation

- [User Guide](docs/user-guide.md) — for people using UCF-RS on a project
- [Agent Guide](docs/agent-guide.md) — for AI agents driving UCF-RS
- [Contributing](CONTRIBUTING.md)
- [Architecture](docs/architecture.md)
- [Commands](docs/commands.md)
- [Storage schemas](docs/storage-schemas.md)
- [Data handling policy](docs/data-policy.md)
- [Relationship to Reqtrace](docs/reqtrace-relationship.md)
- [Future direction](docs/future-direction.md)

## Validation

```bash
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"
python -m unittest discover -s tests
python scripts/ucf_rs.py --help
python scripts/ci_status_fixture.py
```

## License

[MIT](LICENSE)
