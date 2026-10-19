# UCF-RS

**Source-clean citation tracking: cite code ranges without writing markers into source files.**

---

## Welcome to UCF-RS

UCF-RS lets developers, auditors, and AI coding agents attach durable, auditable citations — "this code satisfies requirement X" — to any file and line range in a codebase. Citations live in a local, append-only authority store (`.ucf-rs/`) next to your project; your source files stay completely clean.

Everything runs on your local machine using only Python's standard library. There are no servers to operate, no external accounts, and no background daemons required.

---

## How It Works

Traceability tools usually force a painful choice: either clutter source files with comment markers (`// @reqtrace AUTH-01`) that parsers scrape, or maintain external spreadsheets that immediately drift and rot.

UCF-RS treats citations as **source-clean overlays**:

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

- **Source files stay untouched**: No citation annotations, tags, or comments are ever written into tracked source files.
- **Append-only local authority**: The `.ucf-rs/` store is the sole source of truth, recording every mutation in `operation-log.jsonl` and `citation-index.jsonl`.
- **Projections are rebuildable**: Ledgers (`export ledger`) and Markdown reports (`render`) are derived projections that can be deleted and regenerated at any time.
- **Fail-closed drift detection**: When source code changes externally, citations are flagged (`changed_unaccepted`, `boundary_touched`, or `valid_moved`) rather than silently dropped or assumed valid.

---

## Documentation Roadmap

- **Get Started**:
  - [Installation](get-started/install.md): Install via npm or run from source with Python standard library.
  - [Quickstart](get-started/quickstart.md): Step-by-step walkthrough initializing a project and citing code.
- **Guides**:
  - [User Guide](user-guide.md): Day-to-day workflows, managed edits, offline replay, and status inspection.
  - [Agent Guide](agent-guide.md): Invariants, programmatic interfaces, and best practices for AI coding agents.
  - [Doc-to-Code Audit Recipe](doc-audit-recipe.md): Auditing repository documentation against real code with zero footprint.
- **Concepts**:
  - [Architecture](architecture.md): The four runtime surfaces, transactions, and hash domains.
  - [Glossary](glossary.md): Plain-language definitions for overlay, handle, partition, ledger, epoch, and JSONL.
  - [Reqtrace Relationship](reqtrace-relationship.md): Comparing overlay-first citations to in-source marker conventions.
  - [Future Direction](future-direction.md): Non-normative architectural roadmap.
- **Reference**:
  - [Commands](commands.md): Canonical CLI options, exit codes, and server JSON-RPC methods.
  - [Storage Schemas](storage-schemas.md): File layouts, canonical JSON serialization, and hash formulas.
  - [Data Handling Policy](data-policy.md): Disclosure boundaries, evidence redaction, and retention policies.
- **Project**:
  - [Contributing](project/contributing.md): Development setup, tests, and contribution guidelines.
  - [Security](project/security.md): Vulnerability reporting, network exposure warnings, and local storage safety.
  - [Release Notes](release-notes/0.3.0.md): What's new in version 0.3.0.
  - [Fork Proposal](fork-proposal-doc-audit.md): Design for a doc-to-code audit extension fork.
