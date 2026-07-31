# UCF-RS Data Handling Policy

UCF-RS is a trusted local runtime. It provides local integrity and deterministic
audit behavior, not hosted security, remote authentication, TLS, or
encryption-at-rest guarantees.

## Data Classes

| Data | Retention | Visibility | Export |
| --- | --- | --- | --- |
| `.ucf-rs/project.json` | Retained until the store is deleted. | Local filesystem users with project access. | May be included in local diagnostics or backups. |
| `.ucf-rs/operation-log.jsonl` | Retained append-only. | Local filesystem users with project access. | Exportable as authority metadata; does not include full source text by default. |
| `.ucf-rs/citation-index.jsonl` | Retained append-only. | Local filesystem users with project access. | Exportable as citation metadata and hashes. |
| `.ucf-rs/document-index.jsonl` | Retained append-only. | Local filesystem users with project access. | Exportable as document revision metadata. |
| `.ucf-rs/handle-cache.jsonl` | Retained until manually edited or store deletion. | Local filesystem users with project access. | Exportable as handle metadata. |
| `.ucf-rs/offline-queue.jsonl` | Retained until replay succeeds or the user deletes/requeues it. | Local filesystem users with project access. | Operational data; may contain source text. |
| `.ucf-rs/offline-replayed.jsonl` | Retained as a local replay archive. | Local filesystem users with project access. | Operational data; may contain source text. |
| Generated projections under `docs/ucf-trace-*` | Retained until regenerated or deleted. | Project readers. | Intended for deterministic local review. |
| Source files | Retained by the project outside UCF-RS policy. | Project readers. | Export controlled by the project, not by UCF-RS. |

## Evidence Text Disclosure

Default status, resolve, and HTTP diagnostics disclose paths, ranges, statuses,
hashes, and stable diagnostic codes. They do not include selected source or
evidence text by default.

Source or evidence text can still appear in explicit content-bearing surfaces:

- source files themselves;
- `.ucf-rs/offline-queue.jsonl`, because replay requires deterministic post-edit text;
- `.ucf-rs/offline-replayed.jsonl`, because it archives consumed replay records;
- `export blocks` and `virtual-blocks`, because those commands explicitly render content.

Generated public diagnostics should keep the default redaction boundary and
prefer hashes, ranges, and statuses unless the operator explicitly requests a
content-bearing export.

## Backups And Deletion

UCF-RS does not manage backups. Filesystem, editor, cloud-drive, or repository
backup tools may copy `.ucf-rs/`, generated projections, and source files. Those
backup systems may therefore retain metadata and, for offline queues or content
exports, source text.

Deletion is manual: remove generated projections to delete rebuildable exports,
or remove `.ucf-rs/` to delete the local authority store. Removing authority
files makes existing citations unverifiable unless a backup is restored.

## Local HTTP Exposure

The HTTP transport is local by default and binds to `127.0.0.1` unless configured
otherwise. It has no authentication and no TLS. Binding to a non-loopback host
requires `--unsafe-remote` and prints a warning because any network peer that can
reach the port can submit supported requests.

The HTTP server enforces a maximum request body size and rejects invalid
`Content-Length` headers. These guardrails limit accidental local misuse; they
are not a substitute for authentication, TLS, authorization, or hostile-client
hardening.
