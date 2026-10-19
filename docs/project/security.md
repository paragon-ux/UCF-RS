# Security Policy

## Supported Versions

| Version | Supported | Notes |
| --- | --- | --- |
| `0.3.x` | Yes | Current release line. |
| `< 0.3` | No | Prototype and initial release line; upgrade to `0.3.x`. |

Security fixes are released as patch versions on the current minor line.

---

## Reporting a Vulnerability

Please report suspected security vulnerabilities privately rather than opening
a public GitHub issue.

- **GitHub Private Vulnerability Reporting**: Use the **"Report a vulnerability"**
  button under the **Security** tab of the UCF-RS repository on GitHub:
  `https://github.com/paragon-ux/UCF-RS/security/advisories/new`
- Provide a minimal reproducer and describe the observed impact.
- Maintainers will acknowledge receipt within 3 business days and coordinate a
  fix and advisory disclosure.

---

## Security Boundaries & Design Guarantees

UCF-RS is designed with the following security boundaries:

1. **Path confinement (`project_path`)**: All filesystem paths passed to CLI
   commands (`--path`, `--store`, `--output`, `--status-output`, `--report-output`)
   are strictly confined to the project root (`--root`). Directory traversal
   attempts (`../../`) are rejected with exit code 2.
2. **Local execution model**: UCF-RS is an offline, local-first tool. It never
   transmits telemetry, makes outbound HTTP requests, or contacts third-party
   endpoints.
3. **HTTP transport warnings**: The `serve` HTTP transport has **no authentication
   and no TLS encryption**. It binds strictly to `127.0.0.1` by default and enforces
   request body limits. Binding to a non-loopback host requires an explicit
   `--unsafe-remote` flag. It must never be exposed to public networks or untrusted
   clients.
4. **Offline authority privacy**: Authoritative state inside `.ucf-rs/` is
   readable only by users with local filesystem access to the repository. Full
   evidence text is never emitted by default commands; only hashes, paths, and line
   ranges are exposed.
