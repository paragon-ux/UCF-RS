# Recipe: Doc-to-Code Audits with Existing UCF-RS Features

This recipe shows how to use **unmodified UCF-RS** to audit whether a
repository's documentation is supported by its codebase, while:

1. **Never modifying tracked files** in the audited repository (no
   `docs/handle-registry.jsonl` and no exported files inside `docs/`).
2. **Only citing verified code** in `.ucf-rs/`, never forcing a citation when a
   documented claim is stale, divergent, or unsupported.
3. **Recording claim text, doc locations, and divergent/unsupported findings**
   in an external sidecar JSONL file outside both the target repository and
   `.ucf-rs/` that UCF-RS never reads.

---

## 1. Initialize `.ucf-rs/` and pre-cache handles

Run `init` against the target repository root (`--root`):

```bash
python scripts/ucf_rs.py --root /path/to/codex init
```

Verify the initialized store passes strict validation (`E_STORE_UNINITIALIZED`
is emitted if `init` was skipped):

```bash
python scripts/ucf_rs.py --root /path/to/codex status --strict
```

### Importing handles once without touching tracked files

`import-registry --path` validates its argument with `project_path(root, path)`,
so a path outside `--root` (either an absolute path or `../...`) is rejected
with exit code `2`. However, you can stage a temporary registry file inside
`.ucf-rs/`, import it into `.ucf-rs/handle-cache.jsonl`, and delete the
temporary file.

The minimum record format accepted by `read_handle_records()` is a JSON object
with a string `"handle"` key (`{"handle": "HANDLE_NAME"}`; `type` defaults to
`"unknown"` and `source` defaults to `null`):

```bash
cat <<'EOF' > /path/to/codex/.ucf-rs/temp-registry.jsonl
{"handle":"INSTALL-STANDALONE-FALLBACK"}
{"handle":"INSTALL-JUSTFILE-HELPERS"}
{"handle":"LOGGING-TUI-LOG-DIR"}
{"handle":"LOGGING-EXEC-DEFAULT-FILTER"}
{"handle":"ANSI-ESCAPE-HELPERS"}
{"handle":"PROTOCOL-SQ-EQ-STRUCTS"}
{"handle":"PROTOCOL-OP-VARIANTS"}
{"handle":"PROTOCOL-EVENTMSG-VARIANTS"}
{"handle":"PROTOCOL-USER-INPUT-ITEMS"}
EOF

python scripts/ucf_rs.py --root /path/to/codex import-registry \
  --path .ucf-rs/temp-registry.jsonl

rm /path/to/codex/.ucf-rs/temp-registry.jsonl
```

Once cached in `.ucf-rs/handle-cache.jsonl`, every subsequent `preflight` and
`activate` call for those handles works without `--task-context` (or you can
skip `import-registry` and pass `--task-context` on each `preflight` and
`activate` call).

---

## 2. Preflight and activate verified code ranges

When a documentation claim is verified by reading the implementation, run
`preflight` and `activate` against the exact supporting code lines:

```bash
python scripts/ucf_rs.py --root /path/to/codex preflight \
  --handle LOGGING-TUI-LOG-DIR \
  --path codex-rs/tui/src/lib.rs \
  --lines 274:274

python scripts/ucf_rs.py --root /path/to/codex activate \
  --handle LOGGING-TUI-LOG-DIR \
  --path codex-rs/tui/src/lib.rs \
  --lines 274:274

python scripts/ucf_rs.py --root /path/to/codex activate \
  --handle LOGGING-TUI-LOG-DIR \
  --path codex-rs/tui/src/startup_orchestration.rs \
  --lines 763:797
```

### Citation quality rules for code audits

- **Cite runtime definitions and behavior, not module doc comments (`//!`).**
  A comment inside a Rust/Python source file is still prose, not executable
  evidence.
- **Keep line ranges tight.** Exclude outer enum headers (`pub enum Op {` when
  citing a single variant), adjacent unmentioned variants or recipes, comments
  belonging to the following field, and trailing blank lines.
- **Prove negative or structural claims with positive code evidence.** For
  example, to cite that `Op` is an in-process Rust enum rather than a
  `Serialize`/`Deserialize` wire contract, cite both the `#[derive(Debug)]` /
  `pub enum Op` header (`codex-rs/protocol/src/protocol.rs` `586:590`) and a
  variant carrying an in-memory channel (`Op::InterruptIfNoPendingInput` with
  `reply: oneshot::Sender<bool>` at `597:600`).

---

## 3. Tighten or drop a partition (`deactivate` + `reactivate`)

If review shows that an active partition (`HANDLE/NNN`) is too wide or points
at a comment instead of executable code, tighten it in place using the intended
two-step lifecycle (`deactivate` followed by `reactivate`):

```bash
# Tighten PROTOCOL-OP-VARIANTS/001 from 590:594 (which included `pub enum Op {`
# and a trailing blank line) to 591:593 (just the Interrupt variant):
python scripts/ucf_rs.py --root /path/to/codex deactivate \
  --partition-id PROTOCOL-OP-VARIANTS/001

python scripts/ucf_rs.py --root /path/to/codex reactivate \
  --partition-id PROTOCOL-OP-VARIANTS/001 \
  --path codex-rs/protocol/src/protocol.rs \
  --lines 591:593
```

If a partition should be dropped altogether, run `deactivate` and leave it
inactive.

---

## 4. Keep claims and divergent/unsupported findings in an external sidecar

Because UCF-RS core does not prescribe what a handle asserts, store the prose
claim, documentation source location, disposition (`supported`, `divergent`,
`unsupported`), and associated `partitions` in a sidecar JSONL file **outside**
both the target repository and `.ucf-rs/` (for example,
`/tmp/codex-audit-findings.jsonl`) that UCF-RS never reads:

```jsonl
{"handle":"LOGGING-TUI-LOG-DIR","disposition":"supported","doc_source":"docs/install.md:54:61","claim":"TUI records diagnostics in bounded local stores by default and writes plaintext logs to <log_dir>/codex-tui.log when log_dir is explicitly configured, honoring RUST_LOG","partitions":["LOGGING-TUI-LOG-DIR/001","LOGGING-TUI-LOG-DIR/002","LOGGING-TUI-LOG-DIR/003","LOGGING-TUI-LOG-DIR/004"]}
{"handle":"INSTALL-DOTSLASH-RELEASE","disposition":"unsupported","doc_source":"docs/install.md:11:13","claim":"GitHub Release contains a DotSlash file for the Codex CLI named codex","partitions":[],"note":"DotSlash is only used for internal repo tools (tools/buildifier, tools/argument-comment-lint/argument-comment-lint); no release workflow produces a codex DotSlash file"}
{"handle":"ANSI-ESCAPE-LIFETIME-SIGNATURE","disposition":"divergent","doc_source":"codex-rs/ansi-escape/README.md:8:8","claim":"pub fn ansi_escape<'a>(s: &'a str) -> Text<'a> returns a borrowed Text<'a>","partitions":["ANSI-ESCAPE-HELPERS/002"],"note":"Actual signature in codex-rs/ansi-escape/src/lib.rs:40 is pub fn ansi_escape(s: &str) -> Text<'static>"}
{"handle":"PROTOCOL-OP-CONFIGURE-SESSION","disposition":"unsupported","doc_source":"codex-rs/docs/protocol_v1.md:19:22","claim":"Session is initialized and reconfigured via Op::ConfigureSession","partitions":[],"note":"Op::ConfigureSession does not exist in pub enum Op; session configuration is provided at session creation and updated per turn via Op::OverrideTurnContext"}
```

Always derive partition IDs in the sidecar from `status --format json` rather
than assuming sequential numbering across separate activation batches:

```bash
python scripts/ucf_rs.py --root /path/to/codex status --strict --format json
```

> **Note on `export ledger` and `render`:** Default output paths write to
> `docs/ucf-trace-ledger.jsonl`, `docs/ucf-trace-status.json`, and
> `docs/ucf-trace-report.md`. Their override flags (`export ledger --output`,
> `render --status-output`, `render --report-output`) are also validated by
> `project_path(root, ...)`, so they reject paths outside `--root`. To keep the
> audited repository's `docs/` directory untouched, either consume
> `status --format json` over stdout or pass project-relative paths under
> `.ucf-rs/` (and remove them if you need a clean `.ucf-rs/` store afterwards).

---

## 5. Known limitations and workarounds

1. **Handle persistence (`--task-context` vs `import-registry`):**
   - *Limitation:* `--task-context` bypasses handle validation for a single
     command without writing to `.ucf-rs/handle-cache.jsonl`, and
     `import-registry --path` requires a project-relative path inside `--root`.
   - *Workaround:* Stage a temporary `{"handle": "..."}` JSONL file at
     `.ucf-rs/temp-registry.jsonl`, run
     `import-registry --path .ucf-rs/temp-registry.jsonl`, and delete the
     temporary file (or pass `--task-context` on each `preflight`/`activate`
     invocation).
2. **Tightening an active partition's range:**
   - *Limitation:* `reactivate` only accepts partitions in the `inactive`
     state.
   - *Workaround:* Use the intended two-step lifecycle: `deactivate --partition-id ID`
     followed by `reactivate --partition-id ID --path P --lines START:END`.
3. **Batching preflight and activation calls:**
   - *Limitation:* Running dozens of separate CLI invocations spawns a new
     Python process per partition.
   - *Workaround:* Stream newline-delimited JSON requests (`partition.preflight`,
     `partition.activate`, `status.current`) into a single long-lived process
     via `python scripts/ucf_rs.py --root /path/to/codex serve --transport stdio`.
4. **Opaque domain metadata (claims, doc sources, dispositions):**
   - *Limitation:* Core authority records store opaque handle tokens and code
     evidence ranges without domain-specific claim or disposition fields.
   - *Workaround:* Record claims, documentation source anchors, and
     `supported`/`divergent`/`unsupported` dispositions in an external sidecar
     JSONL file outside the repository and `.ucf-rs/`, joined against
     `status --format json` by `handle` and `partition_id`.
