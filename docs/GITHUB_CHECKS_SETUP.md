# GitHub PR Checks Setup Guide

This guide explains how to configure GitHub Actions workflows and branch protection for the as-docs project.

## Part 1: GitHub Actions Workflows (Already Created)

Two workflow files have been created in `.github/workflows/`:

### 1. `test.yml` - Test Workflow
Runs on every PR and push to `main` or `develop`:
- **Job:** Run pytest test suite
- **Python Version:** 3.12
- **Coverage:** Generates coverage report and uploads to Codecov
- **Check Name:** `test` (Test (Python 3.12))

```bash
# This runs automatically on PR
pytest tests/ -v --tb=short
pytest tests/ --cov=as_docs --cov-report=xml
```

### 2. `lint.yml` - Lint & Format Workflow
Runs on every PR and push to `main` or `develop`:
- **Job 1:** Ruff lint checks (code quality issues)
- **Job 2:** Ruff format check (code style consistency)
- **Job 3:** Pyright type checking (Python type hints)
- **Check Names:** `lint`, `format`, `type-check`

```bash
# Lint checks
ruff check as_docs/ tests/

# Format validation
ruff format as_docs/ tests/ --check

# Type checking
pyright as_docs/
```

---

## Part 2: Enable Branch Protection on GitHub

### Step 1: Go to Repository Settings
1. Navigate to your repository on GitHub
2. Click **Settings** (top right)
3. Click **Branches** (left sidebar)

### Step 2: Add Branch Protection Rule
1. Click **Add rule** button
2. Enter Branch name pattern: `main`
3. Click **Create**

### Step 3: Configure Protection Settings

#### Require Pull Request Reviews
- ☑ **Require a pull request before merging**
  - Number of approvals: `1`
  - ☑ Dismiss stale pull request approvals when new commits are pushed
  - ☑ Require code owner review
  - ☐ Require approval of the most recent reviewers (optional)

#### Require Status Checks
- ☑ **Require status checks to pass before merging**
  - ☑ Require branches to be up to date before merging
  
  **Select these status checks:**
  - `test` (Test (Python 3.12))
  - `lint` (Ruff Lint)
  - `format` (Ruff Format Check)
  - `type-check` (Type Check (Pyright))

#### Other Recommended Settings
- ☑ **Require code review before merging** (1 approval minimum)
- ☑ **Require branches to be up to date before merging**
- ☑ **Require status checks to pass before merging**
- ☑ **Require all conversations to be resolved before merging**

### Step 4: Save Settings
Click **Create** or **Update** to apply branch protection rules.

---

## Part 3: Workflow Files Reference

### test.yml Overview
```yaml
name: Tests
on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - checkout code
      - setup python 3.12
      - install dependencies
      - run pytest with coverage
      - upload to codecov
```

### lint.yml Overview
```yaml
name: Lint & Format
on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  lint:        # ruff check
  format:      # ruff format --check
  type-check:  # pyright
```

---

## Part 4: Local Development (Optional)

To run the same checks locally before pushing:

### Install Tools
```bash
pip install ruff pyright
```

### Run All Checks
```bash
# Lint
ruff check as_docs/ tests/

# Format check
ruff format as_docs/ tests/ --check

# Auto-fix format
ruff format as_docs/ tests/

# Type check
pyright as_docs/

# Tests
pytest tests/ -v
```

### Configure Pre-Commit Hook (Optional)
```bash
pip install pre-commit
pre-commit install
```

Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

---

## Part 5: PR Workflow

### Creating a PR
1. Push to your feature branch
2. Create PR against `main`
3. GitHub Actions automatically runs:
   - `test` workflow (pytest)
   - `lint` workflow (ruff + pyright)
4. Wait for all checks to pass (green checkmarks)
5. Request review from team member
6. Merge once checks pass + review approved

### If Checks Fail
1. Review the failed check output (click on the red ✗)
2. Fix issues locally:
   ```bash
   ruff format as_docs/ tests/ --fix
   ruff check as_docs/ tests/ --fix
   pytest tests/ -v
   ```
3. Commit and push changes
4. Checks automatically re-run

---

## Part 6: Status Badge (Optional)

Add badge to README.md to show build status:

```markdown
## Build Status

[![Tests](https://github.com/your-org/as-docs/actions/workflows/test.yml/badge.svg)](https://github.com/your-org/as-docs/actions/workflows/test.yml)
[![Lint](https://github.com/your-org/as-docs/actions/workflows/lint.yml/badge.svg)](https://github.com/your-org/as-docs/actions/workflows/lint.yml)
```

---

## Troubleshooting

### Tests Fail on GitHub but Pass Locally
- Check Python version matches (3.12)
- Check environment variables are set
- Run: `pip install -e .` to match CI environment

### Lint Check Fails
- Run locally: `ruff check as_docs/ tests/ --fix`
- Format: `ruff format as_docs/ tests/`

### Type Check Fails
- Install locally: `pip install pyright`
- Run: `pyright as_docs/`

### Branch Protection Rule Not Working
- Wait a few minutes for settings to sync
- Refresh the page
- Ensure checks are actually running (check Actions tab)
- Verify check names match exactly

---

## Summary

✅ **Workflows Created:**
- `.github/workflows/test.yml` — Runs pytest
- `.github/workflows/lint.yml` — Runs ruff + pyright

**Next Steps:**
1. Follow **Part 2** to enable branch protection on GitHub
2. Test by creating a PR and watching checks run
3. Checks must pass before merging to `main`
