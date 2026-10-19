# Quickstart

This walkthrough takes you through initializing a project, creating your first
source-clean citations, and exporting audit ledgers in under two minutes.

---

## 1. Initialize the Authority Store

In your project's root directory, run `init`:

```bash
ucf-rs init
```

Output:
```text
initialized .ucf-rs imported_handles=0
```

This creates the `.ucf-rs/` store containing:
- `project.json`: Project identity and settings.
- `operation-log.jsonl`: Append-only cryptographic ledger of operations.
- `citation-index.jsonl`: Append-only index of active citation partitions.
- `document-index.jsonl`: Document revision history and line hash anchors.
- `handle-cache.jsonl`: Cached requirement and claim handles.

*(If your project already has a Reqtrace `docs/handle-registry.jsonl`, `init`
automatically imports those handles into `handle-cache.jsonl`.)*

---

## 2. Validate Candidate Citations with `preflight`

Before writing to authority, you can validate candidate citations with
`preflight`. Preflight checks file existence, boundary lines, and hashes without
modifying `.ucf-rs/`:

```bash
ucf-rs preflight \
  --handle AUTH-ROTATE \
  --path src/auth.py \
  --lines 1:4 \
  --task-context
```

The `--task-context` flag allows ad-hoc handles for the current invocation
without requiring a pre-existing handle registry file.

---

## 3. Activate a Citation

Activate the citation range under the handle:

```bash
ucf-rs activate \
  --handle AUTH-ROTATE \
  --path src/auth.py \
  --lines 1:4 \
  --task-context
```

Output:
```text
activated AUTH-ROTATE/001 citation=[AUTH-ROTATE/001]
```

Notice that:
- `src/auth.py` was **not modified at all**. No comment tags or markers were inserted.
- A new partition `AUTH-ROTATE/001` was created and appended to `.ucf-rs/`.

---

## 4. Check Store Status

Run `status` to inspect active partitions and verify integrity:

```bash
ucf-rs status --format json
```

In CI or pre-commit checks, add `--strict` to fail closed if any citation has
drifted, has unaccepted changes, or if generated ledgers are out of date:

```bash
ucf-rs status --strict
```

---

## 5. Resolve Overlays for a File

Reconstruct the citation overlay on top of current source files:

```bash
ucf-rs resolve --path src/auth.py
```

Output shows the file's current revision hash, active partitions, line spans,
and current validity status.

---

## 6. Export Projections

Generate deterministic, shareable audit artifacts from authority:

```bash
# Export deterministic JSONL audit ledger
ucf-rs export ledger

# Generate status JSON and human-readable Markdown report
ucf-rs render
```

These exports are written to:
- `docs/ucf-trace-ledger.jsonl`
- `docs/ucf-trace-status.json`
- `docs/ucf-trace-report.md`

Exports are projections: they can be deleted and regenerated from `.ucf-rs/` at
any time.

---

## Next Steps

- Read the [User Guide](../user-guide.md) to learn how to apply managed edits,
  work offline, and handle moved code.
- Read the [Agent Guide](../agent-guide.md) if you are integrating UCF-RS into
  an AI coding assistant or automated workflow.
- Explore the [Doc-to-Code Audit Recipe](../doc-audit-recipe.md) for auditing
  documentation claims against code.
