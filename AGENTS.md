# Agent Guidance: Modifying UCF-RS

This file is for AI coding agents and contributors modifying **UCF-RS itself**.
If you are an agent using UCF-RS as a citation tool in another project, read
[`docs/agent-guide.md`](docs/agent-guide.md) instead. Human contributors should
also consult [`CONTRIBUTING.md`](CONTRIBUTING.md).

Full documentation site: https://paragon-ux.github.io/UCF-RS/

---

## 1. Non-Negotiable Core Invariants

UCF-RS core invariants are documented in `.ucf-rs-fork-manifest.json` and must
never be relaxed or bypassed:

- **Standard library only at runtime**: `scripts/ucf_rs.py` must run under Python
  3.10+ using only Python's standard library. Never add runtime dependencies. Dev
  and docs tools (Ruff, Mypy, Zensical) belong in optional extras and CI only.
- **Source-clean overlays**: Never insert comments, docstrings, or markers into
  source files to record citations. Source files remain completely untouched.
- **Explicit evidence only**: Never infer, guess, or synthesize evidence ranges
  from surrounding context, AST identity, symbol names, or fuzzy string matches.
  Every partition activation, accept, move, or reconcile must be explicit.
- **Append-only local authority**: The `.ucf-rs/` store is the sole authority.
  Every mutation appends operation (`operation-log.jsonl`) and citation-index
  (`citation-index.jsonl`) records under the authority write lock.
- **Projections are never authority**: Ledgers (`export ledger`), block dumps
  (`export blocks`), and reports (`render`) are derived projections. They can be
  deleted and regenerated at any time.
- **Two-phase recoverable transactions**: Any operation mutating both source
  and authority (`apply-edit`, `queue-offline-edit`, `replay-offline`) must use
  recoverable file transactions. Interrupted operations must fail closed with
  `E_RECOVERY_RETRY_REQUIRED` until resolved via `recover` or `transaction abandon`.
- **Deterministic exit codes**:
  - `0` (`EXIT_OK`): Success.
  - `1` (`EXIT_CHECK_FAILURE`): Operational check failure (`status --strict` on
    diagnostics/unaccepted evidence or uninitialized store, `reconcile --partition-id`
    when not reconciled, `session open` with diagnostics).
  - `2` (`EXIT_VALIDATION_ERROR`): CLI argument errors, validation preconditions,
    or `E_RECOVERY_RETRY_REQUIRED`.

---

## 2. Validation Commands

Before submitting or reporting any changes, run the full validation battery:

```bash
# 1. Compile check (stdlib only)
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"

# 2. Full test suite (75+ unit tests, stdlib only)
python -m unittest discover -s tests

# 3. Release status fixture
python scripts/ci_status_fixture.py

# 4. Strict status check on any active store fixtures
python scripts/ucf_rs.py status --strict

# 5. Metadata and package checks
python scripts/check_versions.py
python scripts/check_package.py
python scripts/smoke_npm_install.py

# 6. Documentation site build (requires Python 3.11+ and zensical)
python -m zensical build --strict --clean
```

---

## 3. Working Guidelines

- **Never hand-edit `.ucf-rs/` state files**: Modifying `project.json`,
  `handle-cache.jsonl`, `citation-index.jsonl`, or `operation-log.jsonl` by hand
  corrupts cryptographic hashes and transaction recovery logs.
- **Commit hygiene**: Work in small, logical commits grouped by workstream.
  Write imperative commit summaries ("Add ...", "Fix ...", "Document ...").
- **Path confinement**: All paths passed to CLI commands must be validated with
  `project_path(root, path)` to prevent directory traversal outside `--root`.
- **Fail closed on ambiguity**: If an unmanaged source change creates multiple
  candidate ranges or touches boundaries, mark it `ambiguous` or `boundary_touched`
  rather than guessing a resolution.
