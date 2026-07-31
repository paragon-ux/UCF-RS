# Contributing

UCF-RS is a standalone local runtime for source-clean citation authority. Keep
changes local, explicit, and append-only: source files stay clean by default,
and mutating commands must record authority through the operation log and
citation index.

## Development Setup

UCF-RS uses Python's standard library only. Python 3.10 or newer is required.

```bash
python scripts/ucf_rs.py --help
python -m unittest discover -s tests
python scripts/ci_status_fixture.py
```

## Change Guidelines

- Do not add source-persisted citations by default.
- Do not infer evidence from surrounding context, symbol names, AST identity,
  or fuzzy matches.
- Mutating commands must append operation and citation-index records.
- Keep exported ledgers and rendered reports deterministic projections, not
  authority.
- Preserve recoverable transaction behavior for source-plus-authority writes.
- Add focused tests for command, transaction, recovery, storage, or projection
  behavior when those contracts change.

## Documentation

- Root `README.md`, `docs/user-guide.md`, and `docs/agent-guide.md` are the
  public entry points.
- `README.dev.md`, `docs/architecture.md`, `docs/commands.md`,
  `docs/storage-schemas.md`, and `docs/data-policy.md` capture runtime and
  developer reference material.
- `build-docs/` is ignored local planning material and should not be added to
  the repository.

## Validation Before Pushing

Run the same checks expected by CI:

```bash
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"
python -m unittest discover -s tests
python scripts/ucf_rs.py --help
python scripts/ci_status_fixture.py
git diff --check
```
