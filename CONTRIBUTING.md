# Contributing to UCF-RS

UCF-RS is an overlay-first citation runtime for source-clean code traceability.
We welcome contributions that maintain its local, explicit, and append-only
architecture.

---

## 1. Development Prerequisites

UCF-RS runtime uses **Python's standard library only**. Python 3.10 or newer is
required.

Optional developer and documentation tools are declared as extras in
`pyproject.toml` and pinned for reproducible environments:

```bash
# Core runtime has zero dependencies:
python scripts/ucf_rs.py --help

# To install development tools (Ruff, Mypy) and documentation generator (Zensical):
pip install -e ".[dev,docs]"
```

*Note: Building documentation via Zensical requires Python 3.11+.*

---

## 2. Core Invariants

Every change to UCF-RS must uphold these principles:

- **Source files stay clean**: Never inject comments, annotations, or citation
  markers into source files. Citations are overlays stored in `.ucf-rs/`.
- **No evidence guessing**: Never infer evidence from context, AST structure,
  symbol names, or fuzzy matching.
- **Append-only authority**: The `.ucf-rs/` store is the sole source of truth.
  Mutations append to `operation-log.jsonl` and `citation-index.jsonl`.
- **Projections are rebuildable**: Ledgers (`export ledger`) and reports
  (`render`) are derived projections and can be deleted and regenerated at any
  time.
- **Recoverable file transactions**: Operations mutating both source and
  authority (`apply-edit`, `queue-offline-edit`, `replay-offline`) must be
  transactionally safe and fail closed on interruption.
- **Explicit exit codes**: `0` for success, `1` for operational check failures
  (`status --strict` on diagnostics or unaccepted evidence), and `2` for CLI
  validation errors.

---

## 3. Local Documentation Server (Zensical)

UCF-RS documentation is built using [Zensical](https://zensical.org).

```bash
# Preview documentation locally (live reload at http://localhost:8000)
zensical serve

# Build production documentation with strict link and anchor validation
zensical build --strict --clean
```

Documentation files live in `docs/`. When adding new documentation pages:
- Update `nav` in `zensical.toml` at the repository root.
- Keep links strictly internal to `docs/` or use absolute GitHub URLs for files
  outside `docs/` (such as `AGENTS.md` or `LICENSE`).

---

## 4. Validation Before Submitting

Run the full local validation battery before opening a pull request:

```bash
# 1. Compile check (stdlib only)
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"

# 2. Run unit test suite
python -m unittest discover -s tests

# 3. Verify status fixture
python scripts/ci_status_fixture.py

# 4. Strict status check on current store
python scripts/ucf_rs.py status --strict

# 5. Metadata and package checks
python scripts/check_versions.py
python scripts/check_package.py
python scripts/smoke_npm_install.py

# 6. Lint and typecheck (with [dev] extra)
ruff check scripts tests
mypy

# 7. Documentation build (with [docs] extra)
zensical build --strict --clean
```

---

## 5. Branching and Commits

- Work on a focused feature or bugfix branch.
- Keep commits small, self-contained, and grouped by workstream.
- Write imperative commit messages (`Add ...`, `Fix ...`, `Document ...`).
- Never commit `.ucf-rs/`, `site/`, `node_modules/`, `*.tgz`, or temporary test
  directories.
