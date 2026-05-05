"""Telebirr payment verification service.

Translated from src/services/verifyTelebirr.ts
"""

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from tx_verify.utils.logger import logger


@dataclass
class TelebirrReceipt:
    """Telebirr receipt data."""

    payer_name: str = ""
    payer_telebirr_no: str = ""
    credited_party_name: str = ""
    credited_party_account_no: str = ""
    transaction_status: str = ""
    receipt_no: str = ""
    payment_date: str = ""
    settled_amount: str = ""
    service_fee: str = ""
    service_fee_vat: str = ""
    total_paid_amount: str = ""
    bank_name: str = ""


class TelebirrVerificationError(Exception):
    """Raised when Telebirr verification encounters a known error."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.name = "TelebirrVerificationError"
        self.details = details


# ---------------------------------------------------------------------------
# Regex extractors (mirrors the TS regex helpers)
# ---------------------------------------------------------------------------


def _extract_settled_amount_regex(html: str) -> str | None:
    patterns = [
        r"\u12e8\u1270\u12a8\u1348\u1208\u12cd\s+\u1218\u1320\u1295/Settled\s+Amount.*?</td>\s*<td[^>]*>\s*(\d+(?:\.\d{2})?\s+Birr)",
        r"<tr[^>]*>.*?\u12e8\u1270\u12a8\u1348\u1208\u12cd\s+\u1218\u1320\u1295/Settled\s+Amount.*?<td[^>]*>\s*(\d+(?:\.\d{2})?\s+Birr)",
        r"Settled\s+Amount.*?(\d+(?:\.\d{2})?\s+Birr)",
    ]
    for p in patterns:
        m = re.search(p, html, re.I | re.S)
        if m:
            return m.group(1).strip()
    return None


def _extract_service_fee_regex(html: str) -> str | None:
    pattern = r"\u12e8\u12a0\u1308\u120d\u130d\u120e\u1275\s+\u12ad\u134d\u12eb/Service\s+fee(?!\s+\u1270\.\u12a5\.\u1273).*?</td>\s*<td[^>]*>\s*(\d+(?:\.\d{2})?\s+Birr)"
    m = re.search(pattern, html, re.I)
    if m:
        return m.group(1).strip()
    return None


def _extract_receipt_no_regex(html: str) -> str | None:
    pattern = (
        r'<td[^>]*class="[^"]*receipttableTd[^"]*receipttableTd2[^"]*"[^>]*>\s*([A-Z0-9]+)\s*</td>'
    )
    m = re.search(pattern, html, re.I)
    if m:
        return m.group(1).strip()
    return None


def _extract_date_regex(html: str) -> str | None:
    m = re.search(r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})", html)
    if m:
        return m.group(1).strip()
    return None


def _extract_with_regex(html: str, label_pattern: str) -> str | None:
    escaped = re.escape(label_pattern)
    pattern = f"{escaped}.*?</td>\\s*<td[^>]*>\\s*([^<]+)"
    m = re.search(pattern, html, re.I)
    if m:
        val = re.sub(r"<[^>]*>", "", m.group(1)).strip()
        return val
    return None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


def _scrape_telebirr_receipt(html: str) -> TelebirrReceipt:
    """Scrape Telebirr receipt data from HTML using BeautifulSoup + regex fallbacks."""
    soup = BeautifulSoup(html, "html.parser")

    def get_text(label: str) -> str:
        td = soup.find("td", string=re.compile(re.escape(label), re.I))
        if td:
            nxt = td.find_next_sibling("td")
            if nxt:
                return nxt.get_text(strip=True)
        return ""

    def get_text_with_fallback(label: str) -> str:
        regex_result = _extract_with_regex(html, label)
        if regex_result:
            return regex_result
        return get_text(label)

    def get_payment_date() -> str:
        rd = _extract_date_regex(html)
        if rd:
            return rd
        td = soup.find("td", class_="receipttableTd", string=re.compile(r"-202"))
        return td.get_text(strip=True) if td else ""

    def get_receipt_no() -> str:
        rn = _extract_receipt_no_regex(html)
        if rn:
            return rn
        tds = soup.find_all("td", class_=re.compile(r"receipttableTd.*receipttableTd2"))
        if len(tds) > 1:
            return tds[1].get_text(strip=True)
        return ""

    def get_settled_amount() -> str:
        ra = _extract_settled_amount_regex(html)
        if ra:
            return ra
        # Cheerio-style fallback
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if tds and tds[0].get_text():
                text = tds[0].get_text()
                if (
                    "\u12e8\u1270\u12a8\u1348\u1208\u12cd \u1218\u1320\u1295" in text
                    or "Settled Amount" in text
                ):
                    return tds[-1].get_text(strip=True)
        return ""

    def get_service_fee() -> str:
        rf = _extract_service_fee_regex(html)
        if rf:
            return rf
        for tr in soup.find_all("tr"):
            text = tr.get_text()
            if (
                (
                    "\u12e8\u12a0\u1308\u120d\u130d\u120e\u1275 \u12ad\u134d\u12eb" in text
                    or "Service fee" in text
                )
                and "\u1270.\u12a5.\u1273" not in text
                and "VAT" not in text
            ):
                tds = tr.find_all("td")
                if tds:
                    return tds[-1].get_text(strip=True)
        return ""

    credited_party_name = get_text_with_fallback(
        "\u12e8\u1308\u1295\u12d8\u1265 \u1270\u1240\u1263\u12ed \u1235\u121d/Credited Party name"
    )
    credited_party_account_no = get_text_with_fallback(
        "\u12e8\u1308\u1295\u12d8\u1265 \u1270\u1240\u1263\u12ed \u1274\u120c\u1265\u122d \u1241./Credited party account no"
    )
    bank_name = ""

    bank_account_raw = get_text_with_fallback(
        "\u12e8\u1263\u1295\u12ad \u12a0\u12ab\u12cd\u1295\u1275 \u1241\u1325\u122d/Bank account number"
    )
    if bank_account_raw:
        bank_name = credited_party_name
        m = re.match(r"(\d+)\s+(.*)", bank_account_raw)
        if m:
            credited_party_account_no = m.group(1).strip()
            credited_party_name = m.group(2).strip()

    return TelebirrReceipt(
        payer_name=get_text_with_fallback("\u12e8\u12a8\u134b\u12ed \u1235\u121d/Payer Name"),
        payer_telebirr_no=get_text_with_fallback(
            "\u12e8\u12a8\u134b\u12ed \u1274\u120c\u1265\u122d \u1241./Payer telebirr no."
        ),
        credited_party_name=credited_party_name,
        credited_party_account_no=credited_party_account_no,
        transaction_status=get_text_with_fallback(
            "\u12e8\u12ad\u134d\u12eb\u12cd \u1201\u1294\u1273/transaction status"
        ),
        receipt_no=get_receipt_no(),
        payment_date=get_payment_date(),
        settled_amount=get_settled_amount(),
        service_fee=get_service_fee(),
        service_fee_vat=get_text_with_fallback(
            "\u12e8\u12a0\u1308\u120d\u130d\u120e\u1275 \u12ad\u134d\u12eb \u1270.\u12a5.\u1273/Service fee VAT"
        ),
        total_paid_amount=get_text_with_fallback(
            "\u1320\u1245\u120b\u120b \u12e8\u1270\u12a8\u1348\u1208/Total Paid Amount"
        ),
        bank_name=bank_name,
    )


def _parse_telebirr_json(json_data: Any) -> TelebirrReceipt | None:
    """Parse receipt from a proxy JSON response."""
    try:
        if not json_data or not json_data.get("success") or not json_data.get("data"):
            logger.warning("Invalid JSON structure from proxy endpoint")
            return None

        d = json_data["data"]
        return TelebirrReceipt(
            payer_name=d.get("payerName", ""),
            payer_telebirr_no=d.get("payerTelebirrNo", ""),
            credited_party_name=d.get("creditedPartyName", ""),
            credited_party_account_no=d.get("creditedPartyAccountNo", ""),
            transaction_status=d.get("transactionStatus", ""),
            receipt_no=d.get("receiptNo", ""),
            payment_date=d.get("paymentDate", ""),
            settled_amount=d.get("settledAmount", ""),
            service_fee=d.get("serviceFee", ""),
            service_fee_vat=d.get("serviceFeeVAT", ""),
            total_paid_amount=d.get("totalPaidAmount", ""),
            bank_name=d.get("bankName", ""),
        )
    except Exception as e:
        logger.error("Error parsing JSON from proxy endpoint: %s", e)
        return None


def _is_valid_receipt(receipt: TelebirrReceipt) -> bool:
    return bool(receipt.receipt_no and receipt.payer_name and receipt.transaction_status)


async def _fetch_from_primary_source(reference: str, base_url: str) -> TelebirrReceipt | None:
    url = f"{base_url}{reference}"
    try:
        logger.info("Attempting to fetch Telebirr receipt from primary source: %s", url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
        logger.debug("Received response with status: %s", response.status_code)

        extracted = _scrape_telebirr_receipt(response.text)
        logger.info(
            "Successfully extracted Telebirr data for reference: %s",
            reference,
        )
        return extracted
    except Exception as e:
        logger.error("Error fetching Telebirr receipt from primary source %s: %s", url, e)
        return None


async def _fetch_from_proxy_source(reference: str, proxy_url: str) -> TelebirrReceipt | None:
    proxy_key = os.getenv("TELEBIRR_PROXY_KEY", "")
    url = f"{proxy_url}{reference}"
    if proxy_key:
        url += f"&key={proxy_key}"

    try:
        logger.info("Attempting to fetch Telebirr receipt from proxy: %s", url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "VerifierAPI/1.0",
                },
            )
        logger.debug("Received proxy response with status: %s", response.status_code)

        # Try JSON first
        try:
            data = response.json()
        except Exception:
            logger.warning("Proxy response is not valid JSON, attempting to scrape as HTML")
            return _scrape_telebirr_receipt(response.text)

        if isinstance(data, dict) and data.get("success") is False and data.get("error"):
            raise TelebirrVerificationError(data["error"], data.get("details"))

        extracted = _parse_telebirr_json(data)
        if not extracted:
            logger.warning("Failed to parse JSON from proxy, attempting HTML scrape")
            return _scrape_telebirr_receipt(response.text)

        logger.info(
            "Successfully extracted Telebirr data from proxy for reference: %s",
            reference,
        )
        return extracted

    except TelebirrVerificationError:
        raise
    except httpx.ConnectError as e:
        raise TelebirrVerificationError(
            "The fallback proxy server is unreachable or timed out.",
            str(e),
        ) from e
    except httpx.TimeoutException as e:
        raise TelebirrVerificationError(
            "The fallback proxy server is unreachable or timed out.",
            str(e),
        ) from e
    except Exception as e:
        logger.error("Error fetching Telebirr receipt from proxy %s: %s", url, e)
        return None


async def verify_telebirr(reference: str) -> TelebirrReceipt | None:
    """Verify a Telebirr transaction using primary source then fallback proxies."""
    primary_url = "https://transactioninfo.ethiotelecom.et/receipt/"

    env_proxies = os.getenv("FALLBACK_PROXIES", "")
    fallback_proxies = [u.strip() for u in env_proxies.split(",") if u.strip()]
    skip_primary = os.getenv("SKIP_PRIMARY_VERIFICATION") == "true"

    if not skip_primary:
        logger.info("Attempting primary verification for: %s", reference)
        primary_result = await _fetch_from_primary_source(reference, primary_url)
        if primary_result and _is_valid_receipt(primary_result):
            return primary_result
        logger.warning("Primary verification failed. Moving to fallback proxy pool...")
    else:
        logger.info("Skipping primary verifier (SKIP_PRIMARY_VERIFICATION=true).")

    if not fallback_proxies and skip_primary:
        logger.error("CRITICAL: Primary check skipped, but no FALLBACK_PROXIES defined!")
        return None

    for proxy_url in fallback_proxies:
        try:
            logger.info("Attempting verification with proxy: %s", proxy_url)
            result = await _fetch_from_proxy_source(reference, proxy_url)
            if result and _is_valid_receipt(result):
                logger.info("Successfully verified using proxy: %s", proxy_url)
                return result
        except TelebirrVerificationError:
            raise
        except Exception:
            logger.warning("Proxy %s failed or timed out. Trying next...", proxy_url)

    logger.error(
        "All primary and proxy verification methods failed for reference: %s",
        reference,
    )
    return None
