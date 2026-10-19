# UCF-RS Developer Reference

UCF-RS is a standalone local runtime for source-clean traceability. The `0.3.0`
release marks the hardened, production-ready baseline: explicit citation
authority, append-only mutation records, recoverable source-plus-authority
transactions, deterministic ledger exports, and strict validation.

UCF-RS is separate from Reqtrace. Reqtrace remains the grep-native v2.1.7
evidence convention; UCF-RS keeps source files clean, renders citations as
overlays, and stores authority in a durable citation index plus operation log.

## Quickstart

```bash
# In examples/managed-edit:
python ../../scripts/ucf_rs.py --root . init
python ../../scripts/ucf_rs.py --root . activate --handle AUTH-ROTATE --path src/auth.py --lines 1:4
python ../../scripts/ucf_rs.py --root . status --format json
python ../../scripts/ucf_rs.py --root . resolve --path src/auth.py
python ../../scripts/ucf_rs.py --root . export ledger
python ../../scripts/ucf_rs.py --root . render
```

The CLI uses only Python's standard library.

## Repository Status

- Local authority is stored under `.ucf-rs/`; generated ledgers and reports are
  deterministic projections, not authority.
- Mutating commands append operation and citation-index records instead of
  inferring evidence from surrounding source context.
- Managed source edits, offline queue writes, replay, lifecycle transitions,
  and reconcile flows use recoverable file transactions.
- Local HTTP serving is loopback-only by default, has bounded request bodies,
  and has no authentication or TLS claim.
- UCF-YJS may use UCF-RS as a conformance reference, but it must not depend on
  UCF-RS internals, storage layouts, or hashes.

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
- Strict status checks that detect stale exported ledgers and uninitialized stores (`E_STORE_UNINITIALIZED`).
- Local HTTP guardrails: loopback-only binding by default, bounded request bodies, and explicit unsafe remote opt-in with no authentication or TLS.

## Storage And Data Policy

- [Storage schemas](docs/storage-schemas.md) define authoritative files, derived projections, canonical hash boundaries, schema failure behavior, and the UCF-Yjs conformance matrix.
- [Data handling policy](docs/data-policy.md) defines retention, visibility, export, source/evidence disclosure, diagnostic redaction, backups, deletion, and local HTTP exposure.
- [Architecture](docs/architecture.md) and [commands](docs/commands.md) describe
  the runtime model and CLI/API surface.
- [Glossary](docs/glossary.md) provides plain-language definitions for core terms.

## Validation

```bash
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"
python -m unittest discover -s tests
python scripts/ucf_rs.py --help
python scripts/ci_status_fixture.py
```
