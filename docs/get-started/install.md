# Installation

UCF-RS can be installed globally as an npm CLI tool, or run directly from source
using Python's standard library.

---

## Option 1: Via npm (Recommended)

Requires Node.js 22 or newer.

Install `ucf-rs` globally:

```bash
npm install -g ucf-rs
```

Or run it directly without installing via `npx`:

```bash
npx ucf-rs --help
```

### How the npm package works

The npm package bundles a thin, shell-injection-safe Node.js launcher (`bin/ucf-rs.js`)
and the standalone Python runtime script (`scripts/ucf_rs.py`). When invoked, the
launcher:

1. Checks the `UCF_RS_PYTHON` environment variable if specified.
2. Probes for a local Python runtime (`py -3` or `python` on Windows; `python3`
   or `python` on Unix).
3. Verifies that the detected Python is version 3.10 or newer.
4. Spawns the Python process using safe argument arrays (never passing commands
   through a shell interpreter).
5. Passes the exact process exit code back to your terminal.

---

## Option 2: From Source (Python Standard Library Only)

UCF-RS core has **zero external runtime dependencies**. It requires only Python
3.10 or newer.

```bash
# Clone the repository
git clone https://github.com/paragon-ux/UCF-RS.git
cd UCF-RS

# Verify the CLI runs
python scripts/ucf_rs.py --help
```

You can alias or wrap the script in your shell configuration:

```bash
# In ~/.bashrc or ~/.zshrc:
alias ucf-rs="python /path/to/UCF-RS/scripts/ucf_rs.py"
```

---

## Verifying the Installation

Run `status` on a clean directory to verify that the CLI reports an
uninitialized store with exit code 1 (`EXIT_CHECK_FAILURE`):

```bash
ucf-rs status --strict
```

Output:
```text
E_STORE_UNINITIALIZED: UCF-RS store is not initialized; run 'init' first
```

Exit code: `1`.

Now proceed to the [Quickstart](quickstart.md) to set up your first citation
store.
