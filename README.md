# tx-verify

[![PyPI](https://img.shields.io/pypi/v/tx-verify.svg)](https://pypi.org/project/tx-verify/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: ISC](https://img.shields.io/badge/License-ISC-blue.svg)](https://opensource.org/licenses/ISC)

> Async Python library for verifying Ethiopian payment transactions across
> **CBE**, **Telebirr**, **Dashen Bank**, **Bank of Abyssinia**, **CBE Birr**,
> and **M-Pesa**.

For every provider the library fetches the official receipt (PDF or HTML API
response), parses it, and returns a strongly-typed result object.  No headless
browser is bundled — PDF parsing uses `pypdf`, HTML parsing uses
`BeautifulSoup`, and M-Pesa uses the public Safaricom API — so it runs anywhere
Python 3.10+ does.

---

## Supported Providers

| Provider          | Function            | Input (example)                              | Result type                |
| ----------------- | ------------------- | -------------------------------------------- | -------------------------- |
| CBE               | `verify_cbe()`      | `"FT23062669JJ"`, `"12345678"` (8-digit suffix) | `VerifyResult`             |
| Telebirr          | `verify_telebirr()` | `"CE12345678"` (10-char alphanumeric)        | `TelebirrReceipt \| None`   |
| Dashen Bank       | `verify_dashen()`   | `"1234567890123456"` (16 digits)             | `DashenVerifyResult`       |
| Bank of Abyssinia | `verify_abyssinia()`| `"FT23062669JJ"`, `"90172"` (5-digit suffix)   | `AbyssiniaVerifyResult`    |
| CBE Birr          | `verify_cbe_birr()` | `"AB1234CD56"`, `"0911234567"` (local phone)   | `CBEBirrReceipt \| CBEBirrError` |
| M-Pesa            | `verify_mpesa()`    | `"UE20VG1GS8"` (10-char alphanumeric)        | `MpesaVerifyResult`        |
| Image (Mistral)   | `verify_image()`    | `image_bytes` (JPEG/PNG)                     | `ImageVerifyResult`        |
| Universal         | `verify_universal()`| Auto-routes by reference format              | `UniversalResult`          |

---

## Installation

```bash
pip install tx-verify
```

Or with `uv`:

```bash
uv pip install tx-verify
```

`verify_image()` additionally requires the `MISTRAL_API_KEY` environment
variable (see [Image verification](#image-verification-mistral-vision)).

---

## Quick Start

```python
import asyncio
from tx_verify import verify_telebirr, verify_cbe

async def main():
    # --- Telebirr ---
    receipt = await verify_telebirr("CE12345678")
    if receipt is not None:
        print(receipt.payer_name, receipt.settled_amount)

    # --- CBE ---
    result = await verify_cbe("FT23062669JJ", "12345678")
    if result.success:
        print(f"Paid {result.amount} ETB to {result.receiver}")

asyncio.run(main())
```

---

## Provider Reference

### CBE — Commercial Bank of Ethiopia

CBE transaction references are **12 characters** starting with `FT`. You must
also supply the last **8 digits** of the account number as the second
positional argument.

```python
from tx_verify import verify_cbe

result = await verify_cbe("FT23062669JJ", "12345678")
# result.success          → bool
# result.payer            → str | None
# result.payer_account    → str | None
# result.receiver         → str | None
# result.receiver_account → str | None
# result.amount           → float | None
# result.date             → datetime | None
# result.reference        → str | None
# result.reason           → str | None
# result.error            → str | None
```

The verifier fetches a PDF receipt from CBE servers, extracts text with
`pypdf`, and parses payer / receiver / amount / date fields.

---

### Telebirr

Telebirr references are **10-character alphanumeric** codes. The verifier
scrapes the public Ethio Telecom receipt page and returns a `TelebirrReceipt`
dataclass.  On failure it returns `None`.

```python
from tx_verify import verify_telebirr

receipt = await verify_telebirr("CE12345678")
if receipt is not None:
    print(receipt.payer_name)               # str
    print(receipt.payer_telebirr_no)        # str
    print(receipt.credited_party_name)      # str
    print(receipt.credited_party_account_no)# str
    print(receipt.transaction_status)       # str
    print(receipt.receipt_no)               # str
    print(receipt.payment_date)             # str
    print(receipt.settled_amount)           # str
    print(receipt.service_fee)              # str
    print(receipt.service_fee_vat)          # str
    print(receipt.total_paid_amount)        # str
    print(receipt.bank_name)                # str
    print(receipt.meta)                     # dict
```

`TelebirrVerificationError` may be raised when a proxy returns an explicit
error message (see [Error Handling](#error-handling)).

---

### Dashen Bank

Dashen references are **16-digit numbers** starting with 3 digits (e.g.
`1234567890123456`). The verifier fetches a PDF with built-in retry logic
(up to 5 attempts).

```python
from tx_verify import verify_dashen

result = await verify_dashen("1234567890123456")
# result.success               → bool
# result.sender_name           → str | None
# result.sender_account_number → str | None
# result.transaction_channel   → str | None
# result.service_type          → str | None
# result.narrative             → str | None
# result.receiver_name         → str | None
# result.receiver_account_number → str | None
# result.institution_name      → str | None
# result.transaction_reference → str | None
# result.transfer_reference    → str | None
# result.transaction_date      → datetime | None
# result.transaction_amount    → float | None
# result.service_charge        → float | None
# result.excise_tax            → float | None
# result.drrf_fee              → float | None
# result.vat                   → float | None
# result.penalty_fee           → float | None
# result.income_tax_fee        → float | None
# result.tax                   → float | None
# result.interest_fee          → float | None
# result.stamp_duty            → float | None
# result.discount_amount       → float | None
# result.total                 → float | None
# result.amount_in_words       → str | None
# result.meta                  → dict[str, Any]
# result.error                 → str | None
```

---

### Bank of Abyssinia

Abyssinia references are also **12 characters** starting with `FT`, but the
suffix is the last **5 digits** of the account number. The bank returns JSON
rather than a PDF, so parsing is done directly from the API response.

```python
from tx_verify import verify_abyssinia

result = await verify_abyssinia("FT23062669JJ", "90172")
# result.success                    → bool
# result.transaction_reference      → str | None
# result.payer_name                 → str | None
# result.payer_account              → str | None
# result.receiver_name              → str | None
# result.receiver_account           → str | None
# result.transferred_amount         → float | None
# result.total_amount_including_vat → float | None
# result.vat                        → float | None
# result.service_charge             → float | None
# result.currency                   → str | None
# result.transaction_type           → str | None
# result.narrative                  → str | None
# result.transaction_date           → datetime | None
# result.transferred_amount_in_words → str | None
# result.address                    → str | None
# result.phone                      → str | None
# result.meta                       → dict[str, Any]
# result.error                      → str | None
```

---

### CBE Birr

CBE Birr receipts are **10-character alphanumeric** codes. You also need the
wallet phone number in **local Ethiopian format** starting with `09` and 10
digits long (e.g. `0911234567`).

```python
from tx_verify import verify_cbe_birr

result = await verify_cbe_birr("AB1234CD56", "0911234567")
# result is either CBEBirrReceipt or CBEBirrError

# On success:
# result.customer_name      → str
# result.debit_account      → str
# result.credit_account     → str
# result.receiver_name      → str
# result.order_id           → str
# result.transaction_status → str
# result.receipt_number     → str
# result.transaction_date   → str
# result.amount             → str
# result.paid_amount        → str
# result.service_charge     → str
# result.vat                → str
# result.total_paid_amount  → str
# result.payment_reason     → str
# result.payment_channel    → str
# result.meta               → dict
```

On failure the function returns a `CBEBirrError` object:

```python
if isinstance(result, CBEBirrError):
    print(result.error)
```

---

### M-Pesa

M-Pesa references are **10-character alphanumeric** codes. The verifier calls
the Safaricom primary API, decodes a Base64-encoded PDF from the response, and
parses it.

```python
from tx_verify import verify_mpesa

result = await verify_mpesa("UE20VG1GS8")
# result.success         → bool
# result.transaction_id  → str | None
# result.receipt_no      → str | None
# result.payment_date    → datetime | None
# result.amount          → float | None
# result.service_fee     → float | None
# result.vat             → float | None
# result.payer_name      → str | None
# result.payer_account   → str | None
# result.payment_method  → str | None
# result.transaction_type → str | None
# result.payment_channel → str | None
# result.amount_in_words → str | None
# result.meta            → dict
# result.error           → str | None
```

---

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
print(info.type)          # "telebirr" | "cbe" | None
print(info.reference)     # e.g. "CE12345678"
print(info.forward_to)    # "/verify-telebirr" | "/verify-cbe"

# Auto-verify (account_suffix required for CBE)
info = await verify_image(
    image_bytes,
    auto_verify=True,
    account_suffix="12345678",
)
print(info.verified)    # bool | None
print(info.details)     # TelebirrReceipt | VerifyResult | None
```

Requires the `MISTRAL_API_KEY` environment variable. The `mistralai` package
is already installed as a dependency.

---

### Universal — auto-route by reference format

`verify_universal()` accepts a reference string and routes it to the correct
provider based on length and prefix.  Extra arguments are forwarded
automatically.

| Reference length & prefix | How `verify_universal` decides | Required extra args |
| -------------------------- | -------------------------------- | ------------------- |
| 16 digits starting with `3` | Dashen Bank                      | None                |
| 12 chars starting with `FT` + **8-digit** suffix | CBE | `suffix="12345678"` |
| 12 chars starting with `FT` + **5-digit** suffix | Bank of Abyssinia | `suffix="90172"` |
| 10 chars alphanumeric + **phone number** | CBE Birr | `phone_number="0911234567"` |
| 10 chars alphanumeric (no phone) | Telebirr | None |

```python
from tx_verify import verify_universal

# Telebirr — no extra args needed
result = await verify_universal("CE12345678")

# CBE — pass an 8-digit suffix
result = await verify_universal("FT23062669JJ", suffix="12345678")

# CBE Birr — pass a local phone number
result = await verify_universal("AB1234CD56", phone_number="0911234567")

# The wrapper always returns a UniversalResult
print(result.success)   # bool
print(result.data)      # underlying provider result (or None)
print(result.error)     # str | None
print(result.details)   # str | None
```

---

## Proxy Support

All receipt verifiers accept an explicit `proxies` argument. **Environment
variables are never read automatically** — you must pass the proxy yourself.

Supported schemes:

| Scheme    | Description                        |
| --------- | ---------------------------------- |
| `http`    | Plain HTTP forward proxy           |
| `https`   | HTTPS proxy (CONNECT tunnel)       |
| `socks4`  | SOCKS4 proxy                       |
| `socks5`  | SOCKS5 proxy (client resolves DNS) |
| `socks5h` | SOCKS5 proxy (proxy resolves DNS)  |

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
result = await verify_cbe(
    "FT23062669JJ", "12345678", proxies="socks5://127.0.0.1:1080"
)

# M-Pesa with per-scheme mapping
result = await verify_mpesa("UE20VG1GS8", proxies={
    "http://": "http://proxy:8080",
    "https://": "socks5h://proxy:1080",
})
```

`verify_universal` and `verify_image` also forward `proxies` to the
underlying provider automatically.

> **SOCKS tip:** `socks5h://` tells the proxy server to resolve hostnames,
> which is useful when the client cannot reach DNS directly.

---

## Error Handling

Most verifiers return **result objects** rather than raising for expected
failures (network errors, missing receipts, parsing failures).  Inspect
`result.success` and `result.error`.

- `verify_telebirr` returns `None` when the receipt cannot be fetched or
  validated.
- `verify_cbe_birr` returns a `CBEBirrError` object on failure.
- `TelebirrVerificationError` may be raised for proxy-level errors.  Catch it
  if you want to show the user a friendly message:

```python
from tx_verify import TelebirrVerificationError, verify_telebirr

try:
    receipt = await verify_telebirr("INVALID_REF")
    if receipt is None:
        print("Receipt not found.")
except TelebirrVerificationError as exc:
    print(f"Telebirr error: {exc}")
    if exc.details:
        print(f"Details: {exc.details}")
```

The library also provides a generic error handler for wrapping internal errors:

```python
from tx_verify.utils.error_handler import AppError, ErrorType
```

---

## Environment Variables

| Variable          | Purpose                            | Required by                |
| ----------------- | ---------------------------------- | -------------------------- |
| `MISTRAL_API_KEY` | Mistral Vision API key             | `verify_image()`           |
| `LOG_LEVEL`       | `DEBUG` or `INFO` (default `INFO`) | Optional for all verifiers |

---

## Development

```bash
# Clone
git clone https://github.com/nahom-network/tx-verify.git
cd tx-verify

# Install with dev dependencies (uv is recommended because uv.lock exists)
uv pip install -e ".[dev]"

# Or pip
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Lint & format
ruff check . --fix
ruff format .

# Type-check
mypy tx_verify/

# Run tests
pytest -v
```

CI enforces **lint → typecheck → test** in this order.  A one-liner that
matches the CI gate locally:

```bash
ruff check . && ruff format --check . && mypy tx_verify/ && pytest
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

## License

ISC © Nahom D
