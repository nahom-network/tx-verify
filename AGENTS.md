# AGENTS.md — tx-verify

High-signal notes for agents working in this repo.

## Project

Python library (`tx-verify`) for verifying Ethiopian payment transactions across CBE, Telebirr, Dashen Bank, Bank of Abyssinia, CBE Birr, and M-Pesa. Fetches official receipts (PDF/HTML), parses them, and returns typed results.

## Environment

- **Python:** 3.10+ (`.python-version` pins 3.12).
- **Build system:** hatchling (`pyproject.toml`).
- **Lockfile:** `uv.lock` is present — use `uv` for dependency sync when possible, but `pip install -e ".[dev]"` also works.

## Setup

```bash
# uv (recommended because uv.lock exists)
uv pip install -e ".[dev]"

# Or pip
pip install -e ".[dev]"

# Pre-commit hooks (required)
pre-commit install
```

## Verification pipeline (run in this order)

CI enforces: **lint → typecheck → test**.

```bash
ruff check . --fix        # lint + auto-fix
ruff format .             # format
ruff format --check .       # CI formatting gate
mypy tx_verify/           # strict typecheck
pytest -v                 # run tests
```

Shortcut for full local validation (matches CI):

```bash
ruff check . && ruff format --check . && mypy tx_verify/ && pytest
```

## Toolchain quirks

- **Ruff** is the primary linter and formatter. Black config exists for compatibility only.
- **Line length:** 100.
- **MyPy is strict:** `disallow_untyped_defs = true`, `disallow_incomplete_defs = true`, `ignore_missing_imports = false`. Every function needs type annotations. Use `# type: ignore[import-untyped]` sparingly and only with an explanatory comment.
- **pytest-asyncio:** `asyncio_mode = "auto"` — async tests work without decorators.
- **HTTP mocking:** Mock all external HTTP calls in tests with `respx`.

## Architecture

```
tx_verify/
  __init__.py           # Public API exports + __version__
  services/
    verify_<provider>.py # One module per provider
    verify_universal.py  # Auto-routes by reference format
  utils/
    http_client.py       # httpx client factory; explicit proxy only
    logger.py
    error_handler.py
examples/               # Runnable example per provider
tests/                  # Test suite
scripts/                # Standalone scripts (e.g., proxy scenario tests)
```

Adding a provider: create `tx_verify/services/verify_<provider>.py`, export from `tx_verify/__init__.py`, add routing in `verify_universal.py`, add example, add tests, update README.

## Testing gotchas

- `tests/test_verify_mpesa.py` references sample PDFs in a `../internal/` directory (relative to `tests/`). If the `internal/` directory does not exist at repo root, those tests will fail.
- Use `pytest -v` to run. CI runs on Python 3.10, 3.11, 3.12, and 3.13.

## Release flow

1. Bump `__version__` in `tx_verify/__init__.py`.
2. Commit and push.
3. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
4. GitHub Actions validates the tag matches `__version__`, builds the wheel, and publishes to PyPI via trusted publishing.

## Runtime conventions

- **Proxies must be passed explicitly.** The library never reads `HTTP_PROXY` or env vars automatically. All verifiers accept a `proxies` arg forwarded to `httpx`.
- **Result objects, not exceptions:** Expected failures return typed result objects with `success=False` and `error` set. `TelebirrVerificationError` is the one exception that may be raised for proxy-level errors.
- **Env vars:** `MISTRAL_API_KEY` is required for `verify_image()`. `LOG_LEVEL` is optional (`DEBUG`/`INFO`).
