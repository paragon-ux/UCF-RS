# Security policy

UCF-RS is a local command-line tool. It reads and writes files in your project
and does not phone home. The sections below say what is supported and how to
report a problem.

## Supported versions

UCF-RS is experimental (`0.x`). Only the latest released version gets fixes.

| Version | Supported |
| --- | --- |
| Latest `0.x` release | Yes |
| Anything older | No |

## Reporting a vulnerability

Please report security problems privately, not in a public issue.

Use GitHub's private vulnerability reporting for this repository:
<https://github.com/paragon-ux/UCF-RS/security/advisories/new>

Include the version, your operating system and Python version, the command you
ran, and what you expected instead. You will get a reply through the same
advisory thread.

## What UCF-RS does and does not protect

- **HTTP transport has no authentication and no TLS.** `serve --transport http`
  binds to `127.0.0.1` (loopback) by default. Binding to any other address needs
  the `--unsafe-remote` flag and prints a warning. Anyone who can reach that
  port can send supported requests. Treat it as a trusted-local tool, never as
  an internet-facing service.
- **The store is not encrypted.** `.ucf-rs/` is plain files. Anyone who can read
  your project directory can read it. The offline queue
  (`.ucf-rs/offline-queue.jsonl`) and the replay archive can contain source
  text, and `export blocks` prints evidence text on request. See the
  [data handling policy](https://paragon-ux.github.io/UCF-RS/data-policy/).
- **Paths stay inside the project.** Path arguments are checked against
  `--root` and rejected if they point outside it.
- **No network access.** The core is Python standard library only and makes no
  outbound requests. The npm package is a thin launcher that runs the bundled
  Python script and has no dependencies and no install scripts.

Integrity checks (hash chains, recoverable transactions) catch accidental
damage and unrecorded edits. They are not a defense against someone who can
rewrite the whole store.
