# Contributing to aptdata

Thank you for your interest in contributing to **aptdata**!  This guide
explains how to get the project running locally, the coding standards we
follow, and the process for submitting changes.

---

## Table of contents

1. [Code of Conduct](#code-of-conduct)
2. [Setting up the development environment](#setting-up-the-development-environment)
3. [Running tests](#running-tests)
4. [Coding standards](#coding-standards)
5. [Submitting a pull request](#submitting-a-pull-request)
6. [Commit conventions](#commit-conventions)
7. [Release process](#release-process)

---

## Code of Conduct

This project follows the [Contributor Covenant v2.1](https://github.com/strondata/smart-data/blob/main/CODE_OF_CONDUCT.md).
By participating you agree to abide by its terms.

---

## Setting up the development environment

1. **Fork** the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/smart-data.git
   cd smart-data  # repository folder
   ```

2. Install [Poetry](https://python-poetry.org/docs/#installation) (≥ 1.8).

3. Install all dependencies (including optional plugins):

   ```bash
   poetry install --with dev
   ```

4. Verify the setup:

   ```bash
   make test
   ```

---

## Running tests

```bash
make test        # run the full test suite
make lint        # lint with ruff
make docs        # build the documentation site
```

Individual test files:

```bash
poetry run pytest tests/test_core.py -v
poetry run pytest tests/ -k "telemetry" -v
```

Coverage must remain ≥ 80 % (enforced by CI).

---

## Coding standards

- **Formatter / linter:** [ruff](https://docs.astral.sh/ruff/) — run
  `make lint` before pushing.
- **Type hints:** all public functions and methods must be fully annotated.
- **Docstrings:** use NumPy-style docstrings for public APIs.
- **Python version:** target Python 3.10 + (no 3.11-only syntax in production
  code; guard with `if sys.version_info >= (3, 11):` in tests).

---

## Submitting a pull request

1. Create a feature branch from `main`:

   ```bash
   git checkout -b feat/my-feature
   ```

2. Make your changes, add or update tests, and ensure `make test` and
   `make lint` both pass.

3. Push the branch and open a PR against `main`.

4. Add one of the release labels (see [Release process](#release-process))
   to your PR so the CI knows which version component to bump.

5. A maintainer will review your PR.  Please be patient — we aim to review
   within a few business days.

---

## Commit conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Type | When to use |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change that is neither a feature nor a fix |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks (CI, tooling, dependencies) |
| `perf` | Performance improvement |

Examples:

```
feat(cli): add mcp-start --transport flag
fix(quality): handle empty dataframes in SchemaContract
docs: expand telemetry page with Jaeger example
```

---

## Release process

Releases are automated via the [Release workflow](https://github.com/strondata/smart-data/blob/main/.github/workflows/release.yml).

Add **exactly one** of the following labels to your PR:

| Label | Effect |
|-------|--------|
| `release:patch` | `0.0.1 → 0.0.2` |
| `release:minor` | `0.0.1 → 0.1.0` |
| `release:major` | `0.0.1 → 1.0.0` |
| `release:skip`  | No release |
| *(no label)*    | No release (silent skip) |

After merging, the CI will:
1. Bump the version in `pyproject.toml` and `aptdata/__init__.py`.
2. Commit the bump and create a `vX.Y.Z` tag.
3. Trigger the **Publish to PyPI** workflow automatically.
