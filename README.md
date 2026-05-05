# Verifier API

[![PyPI version](https://img.shields.io/pypi/v/verifier-api.svg)](https://pypi.org/project/verifier-api/)
[![Python](https://img.shields.io/pypi/pyversions/verifier-api.svg)](https://pypi.org/project/verifier-api/)
[![License](https://img.shields.io/pypi/l/verifier-api.svg)](https://github.com/YOUR_USERNAME/verifier-api/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Payment Verification API — a Python library for verifying Ethiopian payment
transactions. It supports parsing receipts, extracting reference numbers, and
validating payments across multiple Ethiopian payment providers.

## Supported Providers

| Provider       | Function            | Input                |
|----------------|---------------------|----------------------|
| CBE            | `verify_cbe()`      | PDF receipt / URL    |
| Telebirr       | `verify_telebirr()` | Payment reference    |
| Dashen Bank    | `verify_dashen()`   | PDF receipt / URL    |
| Bank of Abyssinia | `verify_abyssinia()` | PDF receipt / URL |
| CBE Birr       | `verify_cbe_birr()` | PDF receipt / URL    |
| M-Pesa         | `verify_mpesa()`    | PDF receipt / URL    |
| Image (Mistral AI) | `verify_image()` | Screenshot / image  |
| Universal      | `verify_universal()`| Auto-detects provider|

## Installation

```bash
pip install verifier-api
```

## Quick Start

```python
from verifier_api import verify_telebirr, verify_cbe

# Verify a Telebirr transaction
result = await verify_telebirr(reference="YOUR_REFERENCE_NUMBER")
print(result.payer_name, result.settled_amount)

# Verify a CBE receipt from a PDF URL
result = await verify_cbe("https://example.com/receipt.pdf")
if result.success:
    print(f"Amount: {result.amount} ETB")
    print(f"Paid to: {result.receiver}")
```

### Image-based verification

```python
from verifier_api import verify_image

result = await verify_image(
    image_path="/path/to/screenshot.jpg",
    auto_verify=True,
)
print(result.type, result.reference)
```

## Error Handling

```python
from verifier_api import AppError, ErrorType, verify_telebirr

try:
    result = await verify_telebirr(reference="INVALID_REF")
except AppError as e:
    print(f"Error: {e.type.value} — {e}")
```

## Development

```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/verifier-api.git
cd verifier-api
pip install -e ".[dev]"

# Lint & format
ruff check .
ruff format .

# Type-check
mypy .

# Run tests
pytest
```

## API Key Authentication (Middleware)

The library includes optional API key middleware for protecting API endpoints:

```python
from verifier_api.middleware.api_key_auth import (
    ApiKeyAuth,
    ApiKeyStore,
    ApiKeyRecord,
    generate_api_key,
    hash_api_key,
)
```

Implement `ApiKeyStore` to plug in your database of choice.

