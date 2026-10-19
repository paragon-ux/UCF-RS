# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - October 2026

### Added
- **npm Distribution**: Added `package.json` and shell-injection-safe Node.js launcher `bin/ucf-rs.js` for global and npx execution (`npm install -g ucf-rs`).
- **Standardized Exit Codes**: Explicit exit codes across all commands: `0` (success), `1` (operational check failures), `2` (CLI argument and validation errors).
- **Strict Store Check**: Added `E_STORE_UNINITIALIZED` diagnostic emitted by `status --strict` on uninitialized stores with exit code `1`.
- **Documentation Site**: Added [Zensical](https://zensical.org) site configuration (`zensical.toml`) deployed to GitHub Pages with strict link validation.
- **Documentation**:
  - Added [Doc-to-Code Audit Recipe](docs/doc-audit-recipe.md) for auditing documentation claims against code with zero repo modifications.
  - Added [Fork Proposal](docs/fork-proposal-doc-audit.md) specifying a doc-to-code audit fork with persistent claims and dispositions.
  - Added [Glossary](docs/glossary.md) defining core concepts in plain language.
  - Added [Maintainer Release Guide](docs/releasing.md) covering npm Trusted Publishing and verification.
  - Added [SECURITY.md](SECURITY.md) covering vulnerability reporting and local security guarantees.
- **Release Verification Suite**: Added `scripts/check_versions.py`, `scripts/check_package.py`, `scripts/smoke_npm_install.py`, and corresponding unit tests.
- **CI Workflows**: Added comprehensive GitHub Actions workflows for multi-OS CI testing, GitHub Pages docs deployment, and automated release publishing.

### Changed
- Clarified `--task-context` flag semantics across README, User Guide, and Agent Guide.
- Bumped `TOOL_VERSION` to `0.3.0`.
- Expanded unit test suite from 61 to 75+ tests.

---

## [0.2.0] - July 2026

### Added
- Brownfield Reqtrace compatibility: `discover-reqtrace` command and automatic import of `docs/handle-registry.jsonl`.
- JSON-RPC protocol support in `serve` method.
- Strict status checking for exported ledger staleness.

### Changed
- Improved diagnostic reporting on divergent transactions and unmanaged moves.

---

## [0.1.0] - May 2026

### Added
- Initial foundation-hardening baseline.
- Local append-only authority store (`.ucf-rs/`) with operation log and citation index.
- Source-clean citation overlays without in-source comment markers.
- Two-phase recoverable file transactions (`apply-edit`, `queue-offline-edit`, `replay-offline`).
- Deterministic JSONL ledger exports (`export ledger`) and Markdown status reports (`render`).
