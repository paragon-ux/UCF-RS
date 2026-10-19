# Fork Proposal: Documentation-to-Code Claim Audit Extension

> Status: **Fork Proposal (Not Implemented in Core)**
>
> Core UCF-RS tracks source-clean evidence partitions and their lifecycle under
> opaque handles. Core intentionally does not prescribe what a handle asserts
> (requirement, documentation claim, audit control, incident item) or whether a
> handle can exist without code evidence. This document captures a design for a
> domain-specific **doc-to-code audit fork** (`ucf-doc-audit`) that records
> claims, documentation source anchors, and support dispositions (`supported`,
> `divergent`, `unsupported`) inside `.ucf-rs/` without modifying the audited
> repository.

## Why this belongs in a fork, not UCF-RS core

Per [`.ucf-rs-fork-manifest.json`](../.ucf-rs-fork-manifest.json) and
[`docs/architecture.md`](architecture.md):

- **Core responsibility:** Maintain an append-only local authority
  (`.ucf-rs/operation-log.jsonl` and `.ucf-rs/citation-index.jsonl`) mapping
  opaque `upstream_handle` tokens and `partition_id`s (`HANDLE/NNN`) to explicit
  source text ranges and content hashes.
- **Application responsibility:** Define what a handle means in the caller's
  domain (e.g., a prose claim in a documentation file, its disposition when
  code diverges from prose, and how unbacked claims are reported).

Adding `claim`, `doc_source`, and `disposition` (`supported` / `divergent` /
`unsupported`) to UCF-RS core would couple a general-purpose citation authority
to one specific audit domain. Instead, core users can keep domain metadata in an
external sidecar file (see [`docs/doc-audit-recipe.md`](doc-audit-recipe.md)),
or a specialized doc-audit fork can implement the extension below within the
boundaries allowed by `.ucf-rs-fork-manifest.json` (`forkable_surfaces`:
`cli_ergonomics`, `handle_registry_connectors`, `report_formats`) using its own
fork schema namespace (`ucf-doc-audit.*`).

---

## Fork Design: Persistent Claim Handles & Dispositions in `.ucf-rs/`

### Goals

1. **Zero host-repo footprint:** Persist task-context handles, claim text, and
   documentation source locations inside `.ucf-rs/handle-cache.jsonl` so no
   `docs/handle-registry.jsonl` needs to be created in the audited repository.
2. **First-class dispositions:** Allow a handle to be recorded as `supported`,
   `divergent` (optionally pointing to the contradicting implementation range),
   or `unsupported` (no supporting code range exists; no partition activated).
3. **Preserve core hash domains:** Keep `ucf.operation.v1` and
   `ucf.index_record.v1` untouched so existing operation-log and citation-index
   verifiers remain compatible.

### 1. Store Format Changes

#### A. Append-only handle ledger in `.ucf-rs/handle-cache.jsonl` (`ucf-doc-audit.handle_cache.v1`)

Keep `.ucf-rs/handle-cache.jsonl` as the single local handle store, folded with
last-record-wins per `handle` (matching `latest_index_records` semantics for
`.ucf-rs/citation-index.jsonl`), and use the fork's schema identifier
`ucf-doc-audit.handle_cache.v1`:

```json
{
  "schema_version": "ucf-doc-audit.handle_cache.v1",
  "record_type": "handle_declaration",
  "handle": "INSTALL-DOTSLASH-RELEASE",
  "type": "task-context",
  "disposition": "unsupported",
  "claim": "docs/install.md states the GitHub Release contains a DotSlash file for the Codex CLI named codex",
  "doc_source": {
    "path": "docs/install.md",
    "start_line": 11,
    "end_line": 13,
    "content_hash": "sha256:..."
  },
  "note": "DotSlash is only used for internal repo tools (tools/buildifier, tools/argument-comment-lint/argument-comment-lint); no release workflow produces a codex DotSlash file.",
  "imported_from": null,
  "updated_at": "2026-10-19T00:00:00Z",
  "tool": {"name": "ucf-doc-audit", "version": "0.1.0"}
}
```

- **Backward compatibility:** `read_handle_records()` accepts both upstream
  `ucf-rs.handle_cache.v1` (defaulting `disposition` to `"supported"`, `claim`
  to `None`, `doc_source` to `None`) and fork `ucf-doc-audit.handle_cache.v1`.
- **Dispositions:**
  - `"supported"`: Claim is backed by one or more active code partitions in
    `citation-index.jsonl`.
  - `"divergent"`: Documentation claim conflicts with the implementation (for
    example, `codex-rs/ansi-escape/README.md:8:8` documenting
    `pub fn ansi_escape<'a>(s: &'a str) -> Text<'a>` while
    `codex-rs/ansi-escape/src/lib.rs:40` defines
    `pub fn ansi_escape(s: &str) -> Text<'static>`). May have active partitions
    in `citation-index.jsonl` pointing to the actual code that contradicts the
    doc, or stand without partitions.
  - `"unsupported"`: Documentation claim has no supporting code in the
    repository (for example, `Op::ConfigureSession` in
    `codex-rs/docs/protocol_v1.md:19:22`); no partition needs to be activated in
    `citation-index.jsonl`.
- **Doc-drift detection:** When `doc_source` includes `path`, `start_line`, and
  `end_line`, the fork computes `doc_source.content_hash` using
  `ucf.content.text.v1`, allowing `status` to detect if the documentation lines
  themselves changed after the audit (`E_DOC_SOURCE_CHANGED`).

#### B. Authority hash-chain preservation and fork status schema (`ucf-doc-audit.status.v1`)

- Neither `ucf.operation.v1` nor `ucf.index_record.v1` hash domains change.
- Instead of mutating the upstream `ucf-rs.status.v1` contract, the fork's
  `status_report()` emits `"schema_version": "ucf-doc-audit.status.v1"`, joining
  the folded handle map from `.ucf-rs/handle-cache.jsonl` against active
  partitions by `upstream_handle` and adding a top-level `"handles"` array (so
  `unsupported` and partition-less `divergent` handles appear in
  `status --format json` and `render` alongside partition-backed handles).

### 2. CLI Surface Changes in the Fork

1. **Auto-persist `--task-context` handles on `activate` (and optional metadata flags):**
   - Add optional flags to `activate` and `preflight`:
     - `--claim TEXT`
     - `--doc-source PATH[:START:END]`
     - `--disposition {supported,divergent}` (defaults to `supported` on `activate`)
     - `--note TEXT`
   - When `activate --task-context` runs and the handle is not yet present in
     `paths.handles` (or when any of `--claim`, `--doc-source`, `--disposition`,
     `--note` is supplied), `command_activate` appends a
     `ucf-doc-audit.handle_cache.v1` record to `.ucf-rs/handle-cache.jsonl`.
   - Once activated with `--task-context`, the handle is cached in
     `.ucf-rs/handle-cache.jsonl`; subsequent `preflight` and `activate` calls
     for that handle succeed without repeating `--task-context`.
   - `preflight` remains strictly read-only and never writes to
     `.ucf-rs/handle-cache.jsonl`.
2. **New `declare-handle` subcommand for `unsupported` / `divergent` claims:**
   ```bash
   python scripts/ucf_rs.py declare-handle \
     --handle PROTOCOL-OP-CONFIGURE-SESSION \
     --disposition unsupported \
     --doc-source codex-rs/docs/protocol_v1.md:19:22 \
     --claim "Session is initialized and reconfigured via Op::ConfigureSession" \
     --note "Op::ConfigureSession does not exist in pub enum Op"
   ```
   - Validates `HANDLE_RE`, optionally hashes the `doc_source` line range if it
     exists under `--root`, and appends a `ucf-doc-audit.handle_cache.v1` record
     to `.ucf-rs/handle-cache.jsonl` under `authority_write_lock`.
   - Requires no code `--path` or `--lines` when `--disposition` is
     `unsupported` or `divergent`.
3. **`status` and `render` coverage rules (`ucf-doc-audit.status.v1`):**
   - `summary` counts handle dispositions (`handles_supported`,
     `handles_divergent`, `handles_unsupported`, `handles_unbacked`).
   - A handle declared `"supported"` with `0` active partitions is flagged as
     `handles_unbacked` (failing `status --strict`), whereas `"unsupported"` and
     `"divergent"` handles are explicitly accounted for without forcing fake
     code citations.
