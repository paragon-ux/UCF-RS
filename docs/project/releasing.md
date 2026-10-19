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
  `package.json` (`"version": "0.3.0"`) agree.
- **Python compile check**: All scripts in `scripts/` and tests in `tests/` compile
  without syntax errors under Python standard library.
- **Unit test battery (`tests/`)**: 75+ tests pass with zero failures.
- **Status fixture (`scripts/ci_status_fixture.py`)**: Deterministic release status
  fixture passes.
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

## 2. Setting Up npm Trusted Publishing (OIDC)

UCF-RS uses GitHub Actions OIDC Trusted Publishing (`id-token: write`) to publish
to the public npm registry without storing long-lived, static npm credentials.

### Step 2.1: Configure Trusted Publisher on npmjs.com

1. Log into your npm account on [https://www.npmjs.com](https://www.npmjs.com) (with 2FA enabled).
2. Go to **Account Settings** &rarr; **Publishing** (or navigate to package settings if creating a new version of an existing package).
3. Under **Trusted Publishers**, click **Add Trusted Publisher**:
   - **Publisher Type**: `GitHub Actions`
   - **Repository Owner**: `paragon-ux`
   - **Repository Name**: `UCF-RS`
   - **Workflow Name**: `release.yml`
   - **Environment Name**: Leave empty (or `npm-release` if you configure a matching GitHub environment).
4. Save the configuration.

> [!WARNING]
> **48-Hour Expiration Rule**: npm enforces that a newly created trusted publisher
> configuration must complete its first successful publish within **48 hours (2 days)**.
> If unused after 2 days, npm marks the pending publisher as expired and it cannot
> be edited — you must delete it and recreate it.

### Step 2.2: Staged Publishing & 2FA Approval

On new GitHub Actions Trusted Publisher configurations, **Staged Publishing** is
enabled by default by npm:
- When the `release.yml` GitHub Actions workflow runs, it initiates `npm stage publish`
  using the short-lived OIDC token.
- npm stages the package and generates a publish request ID.
- Maintainers with 2FA on the npm package will receive an email and notification
  prompt on npmjs.com.
- Go to the package page on [https://www.npmjs.com/package/ucf-rs](https://www.npmjs.com/package/ucf-rs),
  review the staged release, and click **Approve** (providing your 2FA token).
- Once approved, the package is immediately released and published to the public registry.

---

## 3. Cutting the Release

### Step 3.1: Merge `release-prep` to `main`

Push your local `release-prep` branch to GitHub or open a Pull Request into `main`:

```bash
git checkout main
git merge release-prep
git push origin main
```

### Step 3.2: Tag and Push `v0.3.0`

Create an annotated git tag matching the package version and push it:

```bash
git tag -a v0.3.0 -m "Release v0.3.0"
git push origin v0.3.0
```

Pushing the tag triggers `.github/workflows/release.yml`, which:
1. Runs the full test suite and metadata checks across platforms.
2. Builds the publish tarball (`ucf-rs-0.3.0.tgz`).
3. Creates a GitHub Release draft with the attached tarball and release notes.
4. Initiates npm publishing via OIDC.

---

## 4. Fallback: Manual or Token-Based Publishing

If npm Trusted Publishing cannot be configured or fails:

### Option A: Local CLI Publish (Maintainer Machine)

Run from the repository root:

```bash
# Ensure clean working directory
git checkout v0.3.0

# Verify tarball contents
python scripts/check_package.py

# Publish with 2FA
npm publish --access public
```

### Option B: GitHub Actions with `NPM_TOKEN`

If using a classic automation secret:
1. Generate an npm access token on npmjs.com with publish permissions.
2. In GitHub repository settings &rarr; **Secrets and variables** &rarr; **Actions**,
   add `NPM_TOKEN`.
3. The `release.yml` workflow will automatically fall back to using `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}`.

---

## 5. Post-Publish Verification

Once published, run these verification steps:

```bash
# 1. Verify npm package is visible on registry
npm view ucf-rs

# 2. Test running without local repository
npx ucf-rs@0.3.0 --help

# 3. Verify documentation deployment
curl -I https://paragon-ux.github.io/UCF-RS/
```

- Check [https://github.com/paragon-ux/UCF-RS/releases/tag/v0.3.0](https://github.com/paragon-ux/UCF-RS/releases/tag/v0.3.0)
  to ensure the release notes and `ucf-rs-0.3.0.tgz` asset are present.
- Visit [https://paragon-ux.github.io/UCF-RS/](https://paragon-ux.github.io/UCF-RS/)
  to confirm the Zensical documentation site deployed successfully via GitHub Pages.
