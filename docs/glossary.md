# Glossary

This glossary defines core terms used across UCF-RS documentation, command
interfaces, and storage schemas in plain language.

---

### Authority
The local single source of truth stored inside `.ucf-rs/`. It consists of the
configuration (`project.json`), cached handles (`handle-cache.jsonl`), document
metadata (`document-index.jsonl`), append-only operation log
(`operation-log.jsonl`), and citation index (`citation-index.jsonl`). Authority
files are mutated only by UCF-RS commands under write locks.

### Citation
An auditable record linking a requirement or documentation claim to an exact
file and line range in the codebase, accompanied by content hashes and lifecycle
status. UCF-RS citations are overlays: they never write markers or comments into
source files.

### Epoch
A monotonically increasing integer counter that advances on every authoritative
mutation. The epoch represents the current state version of the authority
store. Background tools and offline queues use the epoch to guarantee that
operations are not replayed against stale preconditions.

### Handle
A stable, human-chosen name representing a requirement, specification item, or
architectural concern (for example, `AUTH-ROTATE` or `LOGGING-TUI-LOG-DIR`). One
handle can govern multiple active code partitions across different files.

### JSONL (JSON Lines)
A text file format where every line is a standalone, valid JSON object separated
by a newline character (`\n`). UCF-RS uses JSONL for append-only logs, offline
queues, and streaming stdio communication, allowing atomic appends and streaming
without reading or parsing entire files into memory.

### Ledger
A deterministic, regenerable audit export file (`docs/ucf-trace-ledger.jsonl`)
listing the history and current state of all citations. Ledgers are projections
derived from authority; they can be deleted and regenerated at any time.

### Managed edit
A source code change applied through UCF-RS (`apply-edit` or the
`document.apply_edit` server method) rather than directly by an editor. When an
edit is managed, UCF-RS automatically transforms and shifts active citation
ranges as text is inserted or deleted above or around them.

### OIDC (OpenID Connect)
An identity protocol that allows CI environments (such as GitHub Actions) to
authenticate directly with package registries (such as npm) using short-lived,
cryptographically signed tokens (`id-token: write`). OIDC removes the need to
store long-lived, static access tokens in repository secrets and generates
verifiable build provenance.

### Overlay
A citation view layered on top of current source files without altering the
underlying text. The files on disk remain clean and free of special annotations;
UCF-RS reconstructs the overlay by reading the authority store and comparing it
against the current source text.

### Partition
A single, discrete cited code range belonging to a handle. If requirement
`AUTH-ROTATE` is satisfied by code in two different files, the handle will have
two active partitions.

### Partition ID
The unique identifier assigned to each partition, formatted as `HANDLE/NNN`
(for example, `AUTH-ROTATE/001`, `AUTH-ROTATE/002`). While `activate` and
`preflight` take a handle name, all partition lifecycle commands (`accept`,
`deactivate`, `reactivate`, `reconcile`) operate on specific partition IDs.

### Projection
A derived, rebuildable output file generated from the authority store, such as
`docs/ucf-trace-ledger.jsonl` (from `export ledger`), `docs/ucf-trace-status.json`
(from `render`), or `docs/ucf-trace-report.md` (from `render`). Projections are
never authoritative on their own.

### Reconcile
A recovery operation (`reconcile`) that inspects partitions marked `valid_moved`
(where an external, unmanaged edit moved the exact cited lines to a different
offset in the file) and updates the citation index to the new line numbers
without human intervention. It only reconciles exact content hash matches; it
never guesses or performs fuzzy matching.

### Unmanaged change
An edit made to a source file by an external program, editor, or git merge
without going through UCF-RS. When source changes externally, UCF-RS detects
the modification during `status` or `resolve` and flags the affected citation as
`changed_unaccepted`, `boundary_touched`, or `valid_moved`.
