# Contributing to tx-verify

Thanks for taking the time to contribute!

## Quick Start

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/tx-verify.git
   cd tx-verify
   ```

2. **Create a virtual environment** and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

## Development Workflow

### Linting & Formatting

We use **Ruff** for both linting and formatting. Run it before committing:

```bash
ruff check .          # lint
ruff check . --fix    # auto-fix issues
ruff format .         # format all files
```

Pre-commit hooks will run these automatically on every commit.

### Type Checking

All code must pass **mypy** with strict settings:

```bash
mypy tx_verify/
```

- Every function must have type annotations.
- Do not use `Any` unless absolutely necessary.
- If a third-party library lacks stubs, use `# type: ignore[import-untyped]` sparingly and add a comment explaining why.

### Tests

Run the test suite with **pytest**:

```bash
pytest -v
```

- Write tests for any new functionality.
- Use `pytest-asyncio` for async tests.
- Mock external HTTP calls with `respx` when testing API clients.

### Adding a New Provider

If you want to add support for a new Ethiopian payment provider:

1. Create a new module under `tx_verify/services/verify_<provider>.py`.
2. Define a typed result dataclass (e.g. `ProviderResult`).
3. Export the verifier and result class from `tx_verify/__init__.py`.
4. Add the provider to `verify_universal.py` routing logic.
5. Write an example in `examples/<provider>.py`.
6. Add tests in `tests/`.
7. Update `README.md` with the provider reference.

## Commit Style

- Use clear, descriptive commit messages.
- Keep commits focused on a single change.
- Reference issues when applicable (`Fixes #123`).

## Opening a Pull Request

1. Ensure all checks pass locally:
   ```bash
   ruff check . && ruff format --check . && mypy tx_verify/ && pytest
   ```
2. Push your branch and open a PR against `main`.
3. Fill out the PR description with what changed and why.
4. Ensure CI is green before requesting review.

## Releasing

Releases are automated via GitHub Actions when a version tag is pushed. To release a new version:

1. Bump `__version__` in `tx_verify/__init__.py`.
2. Commit and push.
3. Create and push a tag matching the version:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

The CI workflow will validate the tag matches the package version, build the wheel, and publish to PyPI using trusted publishing.

## Code of Conduct

Be respectful and constructive in all interactions. We want this to be a welcoming project for everyone.

## License

By contributing, you agree that your contributions will be licensed under the **ISC License**.
