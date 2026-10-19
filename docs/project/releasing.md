# Maintainer Release Guide (UCF-RS 0.3.0)

This document provides exact, step-by-step instructions for the repository maintainer
to publish the `0.3.0` release of **UCF-RS**.

All pre-release preparation, packaging verification, unit tests, and documentation
builds have been executed and verified locally on the `release-prep` branch.

---

## 1. What Has Already Been Verified Locally

Before publishing, the following verification battery passed on `release-prep`:

- **Version consistency (`scripts/check_versions.py`)**: `scripts/ucf_rs.py`
  (`TOOL_VERSION = "0.3.0"`), `pyproject.toml` (`version = "0.3.0"`), and
  `package.json` (`"version": "0.3.0"`) agree on `0.3.0`.
- **Python compile check**: All scripts in `scripts/` and tests in `tests/` compile
  without syntax errors under Python standard library.
- **Unit test battery (`tests/`)**: 75 tests pass with zero failures.
- **Release status fixture (`scripts/ci_status_fixture.py`)**: Deterministic release
  status fixture passes.
- **Package dry-run validation (`scripts/check_package.py`)**: Verified that
  `npm pack --dry-run` includes only the expected files and contains zero test,
  scratch, cache, or machine-specific paths (`C:\Users`, `.gemini`, `brain`, etc.).
- **Tarball installation smoke test (`scripts/smoke_npm_install.py`)**: `npm pack`
  builds cleanly, installs into a temporary project, and executes `ucf-rs --help`
  and `ucf-rs status --strict` with expected exit codes.
- **Lint and typecheck baselines**: `ruff check scripts tests` passes with 0 errors;
  `mypy` passes under configured baseline.
- **Documentation site build**: `zensical build --strict --clean` completes with 0
  warnings and 0 broken links.

---

## 2. First-Publish Options & Trusted Publisher Setup

Because `ucf-rs` is a new package on the npm registry, the package must exist
before package-level settings can be configured. Choose one of two routes for the
very first publish:

### Route A: Manual First Publish with 2FA (Recommended)
1. Run `scripts/check_package.py` to ensure package cleanliness.
2. Publish `0.3.0` directly from your local terminal:
   ```bash
   npm publish --access public
   ```
   *(npm will prompt for your 2FA authentication code.)*
3. Once published, proceed to configure the GitHub Actions Trusted Publisher for
   all subsequent releases.

### Route B: Workstation Staging (Placeholder Route)
1. From your local terminal, initialize staging with a `0.0.0-stage` version:
   ```bash
   npm stage publish --access public
   ```
2. Approve the staged release via npmjs.com, establishing the package namespace.
3. Configure GitHub Actions Trusted Publishing to handle the `0.3.0` release.

---

## 3. Configuring npm Trusted Publishing (OIDC)

Once the package namespace exists on npm:

1. Log into your npm account on [https://www.npmjs.com](https://www.npmjs.com) (with 2FA enabled).
2. Go to **Package Settings** (`ucf-rs`) &rarr; **Publishing** &rarr; **Add Trusted Publisher**:
   - **Publisher Type**: `GitHub Actions`
   - **Repository Owner**: `paragon-ux`
   - **Repository Name**: `UCF-RS`
   - **Workflow Name**: `release.yml` (exact filename with extension)
   - **Environment Name**: Leave empty (none)
   - **Allowed Actions**: Staged publishing (or Staged + Direct Publish)
3. Save the configuration.

> [!WARNING]
> **48-Hour Expiration Rule**: npm enforces that a newly created trusted publisher
> configuration must complete its first successful publish within **48 hours (2 days)**.
> If unused after 2 days, npm marks the pending publisher as expired and it cannot
> be edited — you must delete it and recreate it.

### Hardening npm Package Settings
After configuring the trusted publisher:
- In package settings, select **"Require two-factor authentication to publish"**.
- Ensure classic automation tokens are disabled or disallow token publishing so
  only OIDC short-lived tokens are accepted.

---

## 4. GitHub Repository Configuration

Ensure the following repository settings are active on GitHub:

1. **GitHub Pages Deployment**:
   - Go to **Settings** &rarr; **Pages**.
   - Under **Build and deployment** &rarr; **Source**, select **GitHub Actions**.
   - The `.github/workflows/docs.yml` workflow will automatically build and deploy
     the Zensical documentation site on pushes to `main`.
2. **Tag Protection**:
   - Go to **Settings** &rarr; **Rules** &rarr; **Tag rules**.
   - Add a rule targeting `v*` to prevent unauthorized tag deletion or overwriting.
3. **Private Vulnerability Reporting**:
   - Go to **Settings** &rarr; **Security** &rarr; **Advisories**.
   - Ensure **Private vulnerability reporting** is turned on.

---

## 5. Cutting the Release

### Step 5.1: Merge `release-prep` to `main`
```bash
git checkout main
git merge release-prep
git push origin main
```

### Step 5.2: Tag and Push `v0.3.0`
Run these exact commands to trigger the release workflow:
```bash
git tag -a v0.3.0 -m "Release v0.3.0"
git push origin v0.3.0
```

---

## 6. Approving the Staged npm Release

When `.github/workflows/release.yml` runs on the tag push:
1. The `verify` job runs compile checks, unit tests, and smoke tests across Ubuntu,
   macOS, and Windows.
2. The `publish` job runs `npm stage publish` using short-lived OIDC tokens.
3. As the package maintainer, approve the staged publication:
   - **Web UI**: Navigate to [https://www.npmjs.com/package/ucf-rs](https://www.npmjs.com/package/ucf-rs)
     and click **Approve** (enter your 2FA code).
   - **CLI**: Alternatively, run `npm stage list` and `npm stage approve <request-id>`.
4. Once approved, the package is immediately released to the public registry.
5. The `draft-release` job creates a draft release on GitHub with `ucf-rs-0.3.0.tgz`
   and release notes attached. Review and publish the draft release.

---

## 7. Post-Publish Verification

Once the package is live, execute these sanity checks:

```bash
# 1. Verify package visibility on npm
npm view ucf-rs

# 2. Verify global execution via npx
npx ucf-rs@0.3.0 --help

# 3. Verify documentation deployment on Pages
curl -I https://paragon-ux.github.io/UCF-RS/
```

- Add the npm version badge to `README.md` in a follow-up commit:
  `[![npm version](https://img.shields.io/npm/v/ucf-rs)](https://www.npmjs.com/package/ucf-rs)`
