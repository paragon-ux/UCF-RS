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
- Explicit `accept`, `deactivate`, `reactivate`, and `reconcile` lifecycle transitions.
- Exact unmanaged move recovery from accepted evidence line hashes.
- Runtime citation resolution over stdio or local HTTP, deterministic ledger export, generated status/report rendering, and virtual block export.
- Brownfield compatibility with Reqtrace `docs/handle-registry.jsonl` and advisory `@reqtrace` discovery.
- Strict status checks that detect stale exported ledgers.

## Validation

```bash
python -m unittest discover -s tests
python scripts/ucf_rs.py --help
```
