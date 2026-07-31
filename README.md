# UCF-RS

UCF-RS is a separate experimental repository for the overlay-first architecture
that grew out of Reqtrace v2.1.7's evidence discipline.

Reqtrace remains the grep-native v2.1.7 evidence convention. UCF-RS explores a
different architecture: source files stay clean, citations are rendered as
overlays, and authority lives in a durable citation index plus operation log.

## Quickstart

```bash
python scripts/ucf_rs.py init
python scripts/ucf_rs.py activate --handle AUTH-ROTATE --path examples/managed-edit/src/auth.py --lines 1:4
python scripts/ucf_rs.py status --format json
python scripts/ucf_rs.py resolve --path examples/managed-edit/src/auth.py
python scripts/ucf_rs.py export ledger
python scripts/ucf_rs.py render
```

The CLI uses only Python's standard library.

## What Is Implemented

- Local `.ucf-rs/` authority store with project, handle-cache, document, operation, and citation-index files.
- Source-clean activation from explicit filesystem text ranges.
- Canonical JSON record hashes, operation hashes, and server epoch chaining.
- Managed edit deltas that transform overlay ranges and mark changed evidence.
- Offline edit queues with epoch-checked replay for local disconnected work.
- Recoverable source-plus-authority transactions for managed edits, offline queue writes, and offline replay.
- Explicit `accept`, `deactivate`, `reactivate`, and `reconcile` lifecycle transitions.
- Exact unmanaged move recovery from accepted evidence line hashes.
- Runtime citation resolution over stdio or local HTTP, deterministic ledger export, generated status/report rendering, and virtual block export.
- Brownfield compatibility with Reqtrace `docs/handle-registry.jsonl` and advisory `@reqtrace` discovery.
- Strict status checks that detect stale exported ledgers.
- Local HTTP guardrails: loopback-only binding by default, bounded request bodies, and explicit unsafe remote opt-in with no authentication or TLS.

## Storage And Data Policy

- [Storage schemas](docs/storage-schemas.md) define authoritative files, derived projections, canonical hash boundaries, schema failure behavior, and the UCF-Yjs conformance matrix.
- [Data handling policy](docs/data-policy.md) defines retention, visibility, export, source/evidence disclosure, diagnostic redaction, backups, deletion, and local HTTP exposure.

## Validation

```bash
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"
python -m unittest discover -s tests
python scripts/ucf_rs.py --help
python scripts/ci_status_fixture.py
```
