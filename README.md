# UCF-RS 🔖

**Source-clean citation tracking: cite code ranges without writing markers into source files.**

[![CI](https://github.com/paragon-ux/UCF-RS/actions/workflows/ci.yml/badge.svg)](https://github.com/paragon-ux/UCF-RS/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-Zensical-purple.svg)](https://paragon-ux.github.io/UCF-RS/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

UCF-RS lets developers, auditors, and AI coding agents attach durable,
auditable citations — "this code satisfies requirement X" or "this function
implements claim Y" — to any file and line range in a codebase. Citations live
in a local, append-only authority store (`.ucf-rs/`) next to your project; your
source files stay 100% clean.

Everything runs locally on your machine in plain files, with zero required
background daemons, zero external telemetry, and no account to create.

---

## What It's For

| When you need to... | UCF-RS provides... |
| --- | --- |
| **Audit documentation against code** | Durable citations linking claims to line ranges without modifying the audited repo. |
| **Track requirement traceability** | Source-clean overlays with zero inline marker syntax polluting production code. |
| **Edit cited code safely** | Managed edits (`apply-edit`) that automatically shift cited line ranges as text moves. |
| **Detect source drift** | Strict validation (`status --strict`) catching changed, moved, or deleted evidence immediately. |
| **Export audit evidence** | Deterministic JSONL ledgers and Markdown reports regenerated on demand from authority. |
| **Work offline or headless** | Epoch-checked offline edit queues and a lightweight stdio/HTTP server for IDEs and agents. |

---

## Why It Exists

Traceability tools usually force a compromise: either clutter source files with
in-source comment markers (`// @reqtrace AUTH-01`) that parsers scrape, or
maintain external spreadsheets that immediately drift from reality. UCF-RS
instead treats citations as **source-clean overlays**:

- **Your source files are never edited** to hold citation markers or metadata.
- **An append-only local log** (`.ucf-rs/`) is the single source of truth for
  what is cited, what changed, and what was explicitly accepted.
- **Projections and reports** (`export ledger`, `render`) are always regenerable
  projections of that log — never the authority themselves.
- **Evidence that shifts externally is flagged**, not silently kept or dropped.
  You (or an agent) explicitly accept, reject, or reconcile it.

If your project already uses [Reqtrace](https://github.com/paragon-ux/reqtrace)'s
grep-native `v2.1.7` marker convention, UCF-RS is a fully compatible alternative
for projects that want overlay citations and managed-edit tracking instead of
in-source markers — see [`docs/reqtrace-relationship.md`](docs/reqtrace-relationship.md).

---

## How It Works

```text
                           AI Agent / Developer / CI
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                activate / apply-edit               status / resolve
             (Append Authoritative Event)        (Reconstruct Overlay)
                    │                                   │
                    ▼                                   ▼
          ┌─────────────────────┐             ┌─────────────────────┐
          │  Local Authority    │             │   Runtime Overlay   │
          │     (.ucf-rs/)      │────────────►│  Clean Source Code  │
          │                     │             │    + Line Spans     │
          │ • operation-log     │             └─────────────────────┘
          │ • citation-index    │                        │
          └─────────────────────┘                        ▼
                    │                         ┌─────────────────────┐
                    ▼                         │ Derived Projections │
          Two-Phase Transaction               │  (export / render)  │
          (Atomicity & Recovery)              └─────────────────────┘
```

1. **Activate**: Cites an exact line range in a file under a stable handle.
   Records the citation in `.ucf-rs/operation-log.jsonl` and
   `.ucf-rs/citation-index.jsonl`.
2. **Overlay**: Whenever you inspect citations (`status`, `resolve`), UCF-RS
   compares current file contents against accepted content hashes, reconstructing
   the active overlays in memory.
3. **Managed Edits**: When editing files through UCF-RS (`apply-edit`), citation
   line numbers automatically transform as lines are inserted or deleted.
4. **Transactions**: Any mutation touching both source files and authority is
   protected by two-phase recoverable transactions, preventing split-brain states
   if interrupted.

---

## Installation

### Via npm (Node.js 22+)

```bash
npm install -g ucf-rs
```

The npm package bundles a thin, shell-injection-safe launcher (`ucf-rs`) that
discovers your local Python 3.10+ runtime automatically.

### From Source (Python 3.10+)

UCF-RS core has **zero runtime dependencies** and uses only Python's standard
library:

```bash
git clone https://github.com/paragon-ux/UCF-RS.git
cd UCF-RS
python scripts/ucf_rs.py --help
```

---

## Quickstart

```bash
# 1. Initialize authority store in your project root
ucf-rs init

# 2. Cite lines 1-4 of a file under a stable handle
# (--task-context allows an ad-hoc handle for this task without a pre-existing registry entry)
ucf-rs activate --handle AUTH-ROTATE --path src/auth.py --lines 1:4 --task-context

# 3. See current citation status and check for drift
ucf-rs status --format json

# 4. Re-check citations against the current file contents
ucf-rs resolve --path src/auth.py

# 5. Write a deterministic, shareable audit ledger
ucf-rs export ledger

# 6. Generate a human-readable status report
ucf-rs render
```

*(If running from source without npm, replace `ucf-rs` with `python scripts/ucf_rs.py`.)*

A runnable end-to-end example with a pre-registered handle lives in
[`examples/managed-edit/`](examples/managed-edit/); run its three commands from
inside that directory.

---

## Commands

| Command | Description |
| --- | --- |
| `init` | Initialize `.ucf-rs/` store files and import handles from existing registry. |
| `preflight` | Validate a candidate citation range without mutating authority. |
| `activate` | Activate an explicit file and line range as a new citation partition. |
| `status` | Validate authority records and active partitions; add `--strict` for CI. |
| `resolve` / `citations` | Reconstruct citation overlays for a source file. |
| `apply-edit` | Apply a managed text edit, automatically shifting active citation ranges. |
| `accept` | Promote changed managed content to accepted evidence. |
| `deactivate` / `reactivate` | Retire or relocate an existing citation partition. |
| `reconcile` | Automatically relocate exact moved evidence from line hashes. |
| `queue-offline-edit` | Queue a local offline edit delta without mutating authority. |
| `replay-offline` | Replay queued offline edits through the authoritative operation log. |
| `transaction inspect` / `recover` | Inspect and complete pending two-phase recoverable transactions. |
| `export ledger` / `export blocks` | Write deterministic JSONL audit projections. |
| `render` | Generate status JSON and human-readable Markdown reports. |
| `serve` | Run headless citation server over stdio JSONL or local loopback HTTP. |

Full options and server methods are documented in [`docs/commands.md`](docs/commands.md).

---

## Data Safety & Security

- **Offline & Private**: All authority logs, citation indexes, and projections
  reside strictly on your local disk under `.ucf-rs/`. UCF-RS makes zero network
  requests and collects zero telemetry.
- **Source Protection**: Source files are never modified during citation
  activation, deactivation, or acceptance. Edits via `apply-edit` use two-phase
  atomic replacements with rollback logs.
- **Redacted By Default**: Status reports and audit ledgers disclose only file
  paths, line numbers, and cryptographic hashes. Evidence text is only emitted
  when explicitly requested via `export blocks` or `virtual-blocks`.
- **Loopback-Only Server**: The HTTP transport binds exclusively to `127.0.0.1`
  by default, enforces body size limits, and has no TLS or authentication. It is
  strictly for local editor/tool communication. Non-loopback binding requires an
  explicit `--unsafe-remote` flag.

See [`SECURITY.md`](SECURITY.md) and [`docs/data-policy.md`](docs/data-policy.md)
for complete security and disclosure policies.

---

## Comprehensive Documentation

For complete technical references and architectural specifications, visit our
**[Documentation Site](https://paragon-ux.github.io/UCF-RS/)**:

- 📖 **[User Guide](docs/user-guide.md)**: Adopting UCF-RS, day-to-day workflow, and managed edits.
- 🤖 **[Agent Guide](docs/agent-guide.md)**: Rules and integration patterns for autonomous coding agents.
- 🔍 **[Doc-to-Code Audit Recipe](docs/doc-audit-recipe.md)**: Auditing documentation claims against code with zero repository modification.
- 📚 **[Glossary](docs/glossary.md)**: Plain-language definitions for overlay, handle, partition, ledger, epoch, and JSONL.
- 🏗️ **[Architecture](docs/architecture.md)**: The four-surface runtime model and transactional guarantees.
- 💻 **[Commands Reference](docs/commands.md)**: CLI argument catalog, exit codes, and server API methods.
- 🗄️ **[Storage Schemas](docs/storage-schemas.md)**: Exact JSON schemas and canonical hash definitions.
- 🔒 **[Data Policy](docs/data-policy.md)**: Disclosure, redaction, retention, and deletion rules.
- 🔀 **[Reqtrace Relationship](docs/reqtrace-relationship.md)**: Comparing overlay citations to in-source grep markers.
- 🚀 **[Future Direction](docs/future-direction.md)**: Non-normative future roadmap.
- 📋 **[Fork Proposal: Doc-Audit Extension](docs/fork-proposal-doc-audit.md)**: Specification for a domain-specific doc-audit fork.

---

## Validation

Run the test and verification suite:

```bash
# Stdlib compile check across all Python files
python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in [*pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('*.py')]]"

# Unit test suite (stdlib only)
python -m unittest discover -s tests

# Release status fixture validation
python scripts/ci_status_fixture.py

# Package and release metadata checks
python scripts/check_versions.py
python scripts/check_package.py
python scripts/smoke_npm_install.py
```

---

## Contributing and Security

- Contributions are welcome! Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup and guidelines.
- To report security issues, review [`SECURITY.md`](SECURITY.md).

---

## License

[MIT](LICENSE) © 2026 paragon-ux
