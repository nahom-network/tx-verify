# tx-verify

[![PyPI](https://img.shields.io/pypi/v/tx-verify.svg)](https://pypi.org/project/tx-verify/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: ISC](https://img.shields.io/badge/License-ISC-blue.svg)](https://opensource.org/licenses/ISC)

> Python library for verifying Ethiopian payment transactions across multiple
> providers: **CBE**, **Telebirr**, **Dashen Bank**, **Bank of Abyssinia**,
> **CBE Birr**, and **M-Pesa**.

Each verifier fetches the official receipt from the provider (PDF or HTML),
parses it, and returns typed result objects. No headless browser is bundled —
PDFs are parsed with `pypdf` and HTML with `BeautifulSoup` — so it runs
anywhere Python does.

---

## Supported Providers

| Provider           | Function             | Input (example)                         |
| ------------------ | -------------------- | --------------------------------------- |
| CBE                | `verify_cbe()`       | `reference="FT…"`, `account_suffix="…"` |
| Telebirr           | `verify_telebirr()`  | `reference="CE12345678"`                |
| Dashen Bank        | `verify_dashen()`    | `transaction_reference="123…"` (16 dig) |
| Bank of Abyssinia  | `verify_abyssinia()` | `reference="FT…"`, `suffix="…"` (5 dig) |
| CBE Birr           | `verify_cbe_birr()`  | `receipt="…"`, `phone="09…"` (local)  |
| M-Pesa             | `verify_mpesa()`     | `transaction_id="UE20VG1GS8"`           |
| Image (Mistral AI) | `verify_image()`     | `image_bytes`, auto-detects provider    |
| Universal          | `verify_universal()` | `reference` — auto-routes by format     |

---

## Installation

```bash
pip install tx-verify
```

Or with `uv`:

```bash
uv pip install tx-verify
```

---

## Quick Start

```python
import asyncio
from tx_verify import verify_telebirr, verify_cbe

async def main():
    # --- Telebirr ---
    receipt = await verify_telebirr("CE12345678")
    if receipt:
        print(receipt.payer_name, receipt.settled_amount)

    # --- CBE ---
    result = await verify_cbe("FT23062669JJ", account_suffix="12345678")
    if result.success:
        print(f"Paid {result.amount} ETB to {result.receiver}")

asyncio.run(main())
```

---

## Examples

See the [`examples/`](examples/) directory for a runnable example per
provider:

| File                                              | What it shows                                    |
| ------------------------------------------------- | ------------------------------------------------ |
| [`telebirr.py`](examples/telebirr.py)             | Verify a Telebirr receipt by reference number    |
| [`cbe.py`](examples/cbe.py)                       | Fetch and parse a CBE PDF receipt                |
| [`cbe_birr.py`](examples/cbe_birr.py)             | Verify a CBE Birr wallet transaction             |
| [`dashen.py`](examples/dashen.py)                 | Verify a Dashen Bank receipt with retry logic    |
| [`abyssinia.py`](examples/abyssinia.py)           | Verify a Bank of Abyssinia transaction           |
| [`mpesa.py`](examples/mpesa.py)                   | Verify an Ethiopian M-Pesa transaction           |
| [`image.py`](examples/image.py)                   | Analyse a receipt image with Mistral Vision AI   |
| [`universal.py`](examples/universal.py)           | Let the library auto-route to the right provider |
| [`error_handling.py`](examples/error_handling.py) | Catch provider-specific errors gracefully        |

---

## Provider Reference

### CBE — Commercial Bank of Ethiopia

CBE references are **12 characters** starting with `FT`. You must supply the
last **8 digits** of the account number as a suffix. The bank returns a PDF
that is fetched and parsed automatically.

```python
from tx_verify import verify_cbe

result = await verify_cbe("FT23062669JJ", "12345678")
# result.success      → bool
# result.payer        → str | None
# result.receiver     → str | None
# result.amount       → float | None
# result.date         → datetime | None
# result.reference    → str | None
# result.reason       → str | None
# result.error        → str | None
```

### Telebirr

Telebirr references are **10-character alphanumeric** codes. The library scrapes
the public Ethio Telecom receipt page.

```python
from tx_verify import verify_telebirr

receipt = await verify_telebirr("CE12345678")
# receipt.payer_name, receipt.settled_amount, receipt.total_paid_amount, …
```

### Dashen Bank

Dashen references are **16-digit numbers** starting with 3 digits (e.g.
`1234567890123456`). The verifier fetches a PDF with built-in retry logic
(up to 5 attempts).

```python
from tx_verify import verify_dashen

result = await verify_dashen("1234567890123456")
# result.sender_name, result.transaction_amount, result.total, …
```

### Bank of Abyssinia

Abyssinia references are also **12 characters** starting with `FT`, but the
suffix is the last **5 digits** of the account number. The bank returns JSON
rather than a PDF.

```python
from tx_verify import verify_abyssinia

result = await verify_abyssinia("FT23062669JJ", "90172")
# result.payer, result.amount, result.date, …
```

### CBE Birr

CBE Birr receipts are **10-character alphanumeric** codes. You also need the
wallet phone number in **local Ethiopian format** (e.g. `0911234567`).

```python
from tx_verify import verify_cbe_birr

result = await verify_cbe_birr("AB1234CD56", "0911234567")
# result.customer_name, result.amount, result.paid_amount, …
```

### M-Pesa

M-Pesa references are **10-character alphanumeric** codes. The verifier hits
the Safaricom primary API.

```python
from tx_verify import verify_mpesa

result = await verify_mpesa("UE20VG1GS8")
# result.payer_name, result.amount, result.service_fee, result.vat, …
```

### Image verification (Mistral Vision)

Upload a receipt image (JPEG/PNG) and Mistral Vision AI will detect whether it
is a CBE or Telebirr receipt, extract the reference, and optionally verify it
automatically.

```python
from tx_verify import verify_image

with open("receipt.jpg", "rb") as f:
    image_bytes = f.read()

# Detect only
info = await verify_image(image_bytes, auto_verify=False)
print(info.type, info.reference, info.forward_to)

# Auto-verify (account_suffix required for CBE)
info = await verify_image(
    image_bytes,
    auto_verify=True,
    account_suffix="12345678",
)
print(info.verified, info.details)
```

> Requires `MISTRAL_API_KEY` environment variable and the `mistralai` package
> (installed automatically).

### Universal — auto-route by reference format

Hand any reference to `verify_universal()` and it routes to the correct provider
based on length and prefix:

| Reference format                             | Routed to         |
| -------------------------------------------- | ----------------- |
| 16 digits starting with `3`                  | Dashen Bank       |
| 12 chars starting with `FT` + 8-digit suffix | CBE               |
| 12 chars starting with `FT` + 5-digit suffix | Bank of Abyssinia |
| 10 chars + `phone_number`                    | CBE Birr          |
| 10 chars (no phone)                          | Telebirr          |

```python
from tx_verify import verify_universal

result = await verify_universal("CE12345678")
print(result.success, result.data, result.error)
```

---

## Proxy Support

All receipt verifiers accept an explicit ``proxies`` argument.  **Environment
variables are never read automatically** — you must pass the proxy yourself.

Supported schemes:

| Scheme   | Description                                    |
| -------- | ---------------------------------------------- |
| `http`   | Plain HTTP forward proxy                       |
| `https`  | HTTPS proxy (CONNECT tunnel)                   |
| `socks4` | SOCKS4 proxy                                   |
| `socks5` | SOCKS5 proxy (client resolves DNS)             |
| `socks5h`| SOCKS5 proxy (proxy resolves DNS)              |

Authentication is embedded in the URL:

```python
# Single global proxy
proxies = "http://user:pass@proxy.example.com:8080"

# Per-scheme mapping
proxies = {
    "http://":  "http://proxy.example.com:8080",
    "https://": "socks5://localhost:1080",
}
```

Pass it to any verifier:

```python
from tx_verify import verify_telebirr, verify_cbe, verify_mpesa

# Telebirr through an HTTP proxy
receipt = await verify_telebirr("CE12345678", proxies="http://proxy:8080")

# CBE through SOCKS5
result = await verify_cbe("FT23062669JJ", "12345678", proxies="socks5://127.0.0.1:1080")

# M-Pesa with per-scheme mapping
result = await verify_mpesa("UE20VG1GS8", proxies={
    "http://": "http://proxy:8080",
    "https://": "socks5h://proxy:1080",
})
```

`verify_universal` and `verify_image` also forward ``proxies`` to the
underlying provider automatically.

> **SOCKS tip:** `socks5h://` tells the proxy server to resolve hostnames,
> which is useful when the client cannot reach DNS directly.

---

## Error Handling

All verifiers return **result objects** rather than raising for expected
failures (network errors, missing receipts, parsing failures). Inspect
`result.success` and `result.error`.

Telebirr may raise `TelebirrVerificationError` when a proxy returns an explicit
error message. Catch it if you want to show the user a friendly message:

```python
from tx_verify import TelebirrVerificationError, verify_telebirr

try:
    receipt = await verify_telebirr("INVALID_REF")
except TelebirrVerificationError as exc:
    print(f"Telebirr error: {exc}")
    if exc.details:
        print(f"Details: {exc.details}")
```

The library also provides a generic error handler for wrapping database or
internal errors:

```python
from tx_verify.utils.error_handler import AppError, ErrorType
```

---

## Environment Variables

| Variable          | Purpose                       |
| ----------------- | ----------------------------- |
| `MISTRAL_API_KEY` | Required for `verify_image()` |
| `LOG_LEVEL`       | `DEBUG` or `INFO` (default `INFO`) |

---

## Development

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/tx-verify.git
cd tx-verify

# Install with dev dependencies
pip install -e ".[dev]"

# Lint & format
ruff check .
ruff format .

# Type-check
mypy tx_verify/

# Run tests
pytest
```
