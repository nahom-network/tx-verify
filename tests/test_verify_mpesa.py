"""Tests for the M-Pesa receipt parser using real sample PDFs."""

import os
from datetime import datetime

import pytest

from tx_verify.services.verify_mpesa import _parse_mpesa_receipt


SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "internal")


def load_pdf(name: str) -> bytes:
    path = os.path.join(SAMPLES_DIR, name)
    with open(path, "rb") as f:
        return f.read()


class TestParseMpesaReceipt:
    """End-to-end parser validation against two real M-Pesa receipts."""

    def test_interoperable_bank_transfer(self):
        """Receipt UE50W6EJ68 — Interoperable Bank Transfer (CBE Birr)."""
        pdf_bytes = load_pdf("M-PESA Receipt-UE50W6EJ68.pdf")
        result = _parse_mpesa_receipt(pdf_bytes)

        assert result.success is True
        assert result.transaction_id == "UE50W6EJ68"
        assert result.receipt_no == "SCZWF71IL8DT"
        assert result.payment_date == datetime(2026, 5, 5, 18, 9, 19)
        assert result.amount == 100.0
        assert result.service_fee == 0.0
        assert result.vat == 0.0
        assert result.payer_name == "Nahomderejetasew"
        assert result.payer_account == "251910544594"
        assert result.payment_method == "M-PESA Main Account"
        assert result.transaction_type == "Interoperable Bank transfer"
        assert result.payment_channel == "APP"
        assert result.amount_in_words == "One Hundred Birr Only"

        assert result.meta == {
            "receiver_name": "Nahom Dereje Tasew",
            "receiver_account": "251703854594",
            "bank_name": "CBE Birr",
        }
        assert result.error is None

    def test_buy_package(self):
        """Receipt UE40VX8F44 — Buy Package (Airtime)."""
        pdf_bytes = load_pdf("M-PESA Receipt-UE40VX8F44.pdf")
        result = _parse_mpesa_receipt(pdf_bytes)

        assert result.success is True
        assert result.transaction_id == "UE40VX8F44"
        assert result.receipt_no == "SCZRTOJOYZCT"
        assert result.payment_date == datetime(2026, 5, 4, 14, 14, 15)
        assert result.amount == 22.4
        assert result.service_fee == 2.4
        assert result.vat == 0.0
        assert result.payer_name == "Nahom Dereje Tasew"
        assert result.payer_account == "251703854594"
        assert result.payment_method == "M-PESA"
        assert result.transaction_type == "Buy Package"
        assert result.payment_channel == "APP"
        assert result.amount_in_words == "Twenty-two Birr and Forty Cents Only"

        assert result.meta == {
            "receiver_business_name": "Airtime",
            "receiver_business_number": "999999999",
            "discount": 0.0,
        }
        assert result.error is None


class TestVerifyMpesaError:
    """Error path coverage for the parser."""

    def test_corrupt_pdf(self):
        """Corrupt / non-PDF bytes should return success=False."""
        result = _parse_mpesa_receipt(b"not a pdf at all")
        assert result.success is False
        assert result.error is not None
